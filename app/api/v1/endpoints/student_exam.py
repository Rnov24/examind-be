from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, BackgroundTasks, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload, selectinload
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.dependencies import get_current_active_user, require_student
from app.models.user import User
from app.models.exam import Exam, ExamQuestion
from app.models.session import ExamSession, StudentAnswer, AutosaveSnapshot
from app.models.proctoring import ProctoringLog
from app.models.academic import ClassMember
from app.schemas.session import (
    ExamStartResponse,
    AutosaveRequest,
    AutosaveResponse,
    SubmitExamRequest,
    SubmitExamResponse,
    AbortExamRequest,
    AbortExamResponse,
    StudentExamResultResponse,
    StudentAnswerDetail,
)
from app.schemas.exam import ExamResponse
from app.api.v1.endpoints.exams import build_exam_response
from app.schemas.common import ApiResponse
from app.services.exam.session_guard import get_or_create_exam_session
from app.services.exam.randomizer import randomize_exam_package
from app.services.grading.mcq_evaluator import evaluate_instant_mcq
from app.services.grading.background_worker import grade_exam_session_async
from app.services.proctoring.websocket_hub import ws_hub
from app.services.reporting.pdf_exporter import generate_pdf_student_result

router = APIRouter(prefix="/student", tags=["Student Exam Flow"])


@router.get("/exams/active", response_model=ApiResponse[List[ExamResponse]])
def get_student_active_exams(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    # Find enrolled classes
    class_ids = [m.class_id for m in db.query(ClassMember).filter(ClassMember.user_id == current_user.id).all()]
    if not class_ids:
        return ApiResponse.ok(data=[], message="Tidak ada ujian aktif untuk kelas Anda.")

    exams = (
        db.query(Exam)
        .options(
            joinedload(Exam.teacher),
            joinedload(Exam.class_),
            selectinload(Exam.exam_questions),
        )
        .filter(Exam.class_id.in_(class_ids), Exam.status.in_(["published", "in_progress", "completed"]))
        .limit(100)
        .all()
    )

    results = [build_exam_response(e) for e in exams]

    return ApiResponse.ok(data=results, message="Daftar ujian aktif berhasil dimuat")


@router.post("/exam/{exam_id}/start", response_model=ApiResponse[ExamStartResponse])
def start_exam(
    exam_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise AppException(
            message="Paket ujian tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EXAM_NOT_FOUND",
        )

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    session, is_new, pairing_token = get_or_create_exam_session(
        db=db,
        exam=exam,
        student_id=current_user.id,
        client_ip=client_ip,
        user_agent=user_agent,
    )

    # Format questions list
    raw_questions = []
    for eq in exam.exam_questions:
        q = eq.question
        if not q:
            continue
        raw_questions.append({
            "id": q.id,
            "order_index": eq.order_index,
            "question_type": q.question_type,
            "prompt": q.prompt,
            "options_json": q.options_json,
            "difficulty": q.difficulty,
            "points": float(eq.allocated_points),
        })

    # Apply deterministic student randomizer
    shuffled_questions = randomize_exam_package(
        questions=raw_questions,
        exam_id=exam.id,
        student_id=current_user.id,
        randomize_questions=exam.randomize_questions,
        randomize_options=exam.randomize_options,
    )

    # Calculate remaining seconds — the clock runs from begun_at when the
    # student has finished the setup wizard; before that, no time is consumed.
    if session.begun_at:
        elapsed_seconds = int((datetime.utcnow() - session.begun_at).total_seconds())
        remaining_seconds = max(0, exam.duration_minutes * 60 - elapsed_seconds)
    else:
        remaining_seconds = exam.duration_minutes * 60

    # Load any previously autosaved answers for resume
    cached_answers = {}
    if session.autosave_snapshot and session.autosave_snapshot.answers_payload:
        cached_answers = session.autosave_snapshot.answers_payload

    # Attach previous answer if available
    for q in shuffled_questions:
        qid_str = str(q["id"])
        if qid_str in cached_answers:
            q["saved_response"] = cached_answers[qid_str]

    res = ExamStartResponse(
        session_id=session.id,
        exam={
            "id": exam.id,
            "title": exam.title,
            "description": exam.description,
            "duration_minutes": exam.duration_minutes,
            "start_time": exam.start_time.isoformat(),
            "end_time": exam.end_time.isoformat(),
            "proctoring_level": exam.proctoring_level,
            "total_questions": len(shuffled_questions),
        },
        pairing_token=pairing_token,
        companion_qr_url=f"/companion/pair?session_id={session.id}&token={pairing_token}",
        duration_remaining_seconds=remaining_seconds,
        questions=shuffled_questions,
        begun_at=session.begun_at,
    )
    return ApiResponse.ok(data=res, message="Sesi ujian dimulai")


@router.post("/exam/{exam_id}/begin")
def begin_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    """Mark the moment the student actually starts answering (after the
    camera-setup wizard). Idempotent: only the first call sets begun_at,
    so reloads/resumes never reset the clock."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise AppException(
            message="Paket ujian tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EXAM_NOT_FOUND",
        )
    session = (
        db.query(ExamSession)
        .filter(ExamSession.exam_id == exam_id, ExamSession.student_id == current_user.id)
        .first()
    )
    if not session:
        raise AppException(
            message="Sesi ujian tidak ditemukan. Muat ulang halaman ujian.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="SESSION_NOT_FOUND",
        )
    if session.status != "in_progress":
        raise AppException(
            message="Sesi ujian sudah tidak aktif.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="SESSION_NOT_ACTIVE",
        )
    if session.begun_at is None:
        session.begun_at = datetime.utcnow()
        db.commit()
        db.refresh(session)
    elapsed = int((datetime.utcnow() - session.begun_at).total_seconds())
    remaining = max(0, exam.duration_minutes * 60 - elapsed)
    return ApiResponse.ok(
        data={
            "begun_at": session.begun_at.isoformat(),
            "duration_remaining_seconds": remaining,
        },
        message="Ujian dimulai",
    )


@router.post("/exam/{exam_id}/autosave", response_model=ApiResponse[AutosaveResponse])
def autosave_answers(
    exam_id: int,
    request: AutosaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    session = (
        db.query(ExamSession)
        .filter(ExamSession.id == request.session_id, ExamSession.student_id == current_user.id)
        .first()
    )
    if not session:
        raise AppException(
            message="Sesi ujian tidak valid.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="SESSION_NOT_FOUND",
        )

    if session.status in ["submitted", "graded", "aborted"]:
        raise AppException(
            message="Ujian telah selesai atau dibatalkan.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="SESSION_CLOSED",
        )

    # Payload dict: { "101": "B", "102": "essay text..." }
    payload = {str(item.question_id): item.response for item in request.answers}

    snapshot = (
        db.query(AutosaveSnapshot)
        .filter(AutosaveSnapshot.session_id == session.id)
        .first()
    )
    now = datetime.utcnow()
    if snapshot:
        snapshot.answers_payload = payload
        snapshot.last_saved_at = now
    else:
        snapshot = AutosaveSnapshot(
            session_id=session.id,
            answers_payload=payload,
            last_saved_at=now,
        )
        db.add(snapshot)

    db.commit()

    res = AutosaveResponse(
        saved_items_count=len(payload),
        last_saved_at=now,
    )
    return ApiResponse.ok(data=res, message="Jawaban berhasil diautosave ke server")


@router.post("/exam/{exam_id}/submit", response_model=ApiResponse[SubmitExamResponse])
def submit_exam(
    exam_id: int,
    request: SubmitExamRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    session = (
        db.query(ExamSession)
        .filter(ExamSession.id == request.session_id, ExamSession.student_id == current_user.id)
        .first()
    )
    if not session:
        raise AppException(
            message="Sesi ujian tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="SESSION_NOT_FOUND",
        )

    if session.status in ["submitted", "graded", "aborted"]:
        raise AppException(
            message="Sesi ujian ini telah dikumpulkan atau dibatalkan sebelumnya.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="ALREADY_SUBMITTED",
        )

    # Gather answers from autosave snapshot
    submitted_answers = {}
    if session.autosave_snapshot and session.autosave_snapshot.answers_payload:
        for qid_str, val in session.autosave_snapshot.answers_payload.items():
            try:
                submitted_answers[int(qid_str)] = val
            except ValueError:
                pass

    # Instant MCQ scoring
    mcq_score = evaluate_instant_mcq(
        db=db,
        session=session,
        submitted_answers=submitted_answers,
    )

    now = datetime.utcnow()
    session.submit_time = now
    session.status = "grading_in_progress"
    session.total_score = mcq_score
    db.commit()

    # Trigger async AI essay grading pipeline in background
    background_tasks.add_task(grade_exam_session_async, session.id)

    res = SubmitExamResponse(
        session_id=session.id,
        status="grading_in_progress",
        submitted_at=now,
        message="Ujian telah selesai dikumpulkan. Penilaian esai sedang diproses secara asinkron.",
    )
    return ApiResponse.ok(data=res, message="Submit ujian berhasil")


@router.post("/exam/{exam_id}/fail", response_model=ApiResponse[AbortExamResponse])
async def fail_exam_session(
    exam_id: int,
    request: AbortExamRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    session = (
        db.query(ExamSession)
        .filter(ExamSession.id == request.session_id, ExamSession.student_id == current_user.id)
        .first()
    )
    if not session:
        raise AppException(
            message="Sesi ujian tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="SESSION_NOT_FOUND",
        )

    now = datetime.utcnow()

    if session.status == "aborted":
        return ApiResponse.ok(
            data=AbortExamResponse(
                session_id=session.id,
                status="aborted",
                aborted_at=session.submit_time or now,
                reason=request.reason,
                message="Sesi ujian telah didiskualifikasi sebelumnya.",
            ),
            message="Ujian telah didiskualifikasi",
        )

    # Immediate disqualification: mark aborted, score 0, integrity 0
    session.submit_time = now
    session.status = "aborted"
    session.total_score = 0.00
    session.integrity_score = 0

    event_type = "fullscreen_exit" if "fullscreen" in request.reason.lower() else "tab_switch"

    # Add verified high severity proctoring log
    log = ProctoringLog(
        session_id=session.id,
        event_type=event_type,
        camera_source="system_event",
        severity="high",
        duration_seconds=1,
        snapshot_url=None,
        event_timestamp=now,
        reviewed_by_teacher=True,
        teacher_verdict="confirmed_violation",
    )
    db.add(log)
    db.commit()

    student_name = current_user.full_name or "Siswa"

    # Broadcast real-time alerts to teacher monitoring room
    alert_payload = {
        "event": "STUDENT_DISQUALIFIED",
        "payload": {
            "session_id": session.id,
            "student_id": session.student_id,
            "student_name": student_name,
            "student_identifier": current_user.identifier,
            "event_type": event_type,
            "reason": request.reason,
            "details": request.details or "Pelanggaran keamanan: Keluar layar penuh atau berpindah tab/desktop",
            "timestamp": now.isoformat(),
            "status": "aborted",
            "current_integrity_score": 0,
        },
    }
    await ws_hub.broadcast_to_exam(session.exam_id, alert_payload)

    flag_payload = {
        "event": "PROCTORING_FLAG_ALERT",
        "payload": {
            "session_id": session.id,
            "student_id": session.student_id,
            "student_name": student_name,
            "event_type": event_type,
            "camera_source": "system_event",
            "severity": "high",
            "duration_seconds": 1,
            "timestamp": now.isoformat(),
            "snapshot_url": None,
            "current_integrity_score": 0,
            "status": "aborted",
        },
    }
    await ws_hub.broadcast_to_exam(session.exam_id, flag_payload)

    res = AbortExamResponse(
        session_id=session.id,
        status="aborted",
        aborted_at=now,
        reason=request.reason,
        message="Sesi ujian Anda telah dibatalkan dan dinyatakan tidak lulus (gugur) karena pelanggaran protokol keamanan.",
    )
    return ApiResponse.ok(data=res, message="Siswa berhasil didiskualifikasi dari ujian")


@router.get("/exam/{exam_id}/result", response_model=ApiResponse[StudentExamResultResponse])
def get_exam_result(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    session = (
        db.query(ExamSession)
        .filter(ExamSession.exam_id == exam_id, ExamSession.student_id == current_user.id)
        .first()
    )
    if not session:
        raise AppException(
            message="Hasil ujian belum tersedia atau sesi belum dibuat.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="RESULT_NOT_FOUND",
        )

    exam = (
        db.query(Exam)
        .options(selectinload(Exam.exam_questions).selectinload(ExamQuestion.question))
        .filter(Exam.id == session.exam_id)
        .first()
    )
    answers_detail = []
    max_score = 0.0

    # One query for all answers in this session (no per-question N+1).
    answers_by_question = {
        a.question_id: a
        for a in db.query(StudentAnswer)
        .filter(StudentAnswer.session_id == session.id)
        .all()
    }

    for eq in exam.exam_questions:
        q = eq.question
        if not q:
            continue
        pts = float(eq.allocated_points)
        max_score += pts

        ans = answers_by_question.get(q.id)

        show_explanation = (
            exam.explanation_policy == "instant"
            or (exam.explanation_policy == "after_exam_closed" and session.status in ["graded", "submitted"])
        )

        answers_detail.append(
            StudentAnswerDetail(
                id=ans.id if ans else 0,
                question_id=q.id,
                question_type=q.question_type,
                prompt=q.prompt,
                options_json=q.options_json if show_explanation else None,
                correct_answer=q.correct_answer if show_explanation else None,
                student_response=ans.student_response if ans else None,
                is_correct=ans.is_correct if ans else None,
                allocated_points=pts,
                auto_score=float(ans.auto_score or 0.0) if ans else 0.0,
                teacher_override_score=float(ans.teacher_override_score) if ans and ans.teacher_override_score is not None else None,
                final_score=float(ans.final_score or 0.0) if ans else 0.0,
                ai_confidence_level=ans.ai_confidence_level if ans and show_explanation else None,
                ai_grading_rationale=ans.ai_grading_rationale if ans and show_explanation else None,
                ai_explanation=ans.ai_explanation if ans and show_explanation else None,
                teacher_notes=ans.teacher_notes if ans else None,
                rubric_json=q.rubric_json if show_explanation else None,
            )
        )

    res = StudentExamResultResponse(
        session_id=session.id,
        exam_id=exam.id,
        exam_title=exam.title,
        subject=exam.class_.name if exam.class_ else "Ujian",
        student_name=current_user.full_name,
        student_identifier=current_user.identifier,
        status=session.status,
        start_time=session.start_time,
        submit_time=session.submit_time,
        total_score=float(session.total_score or 0.0),
        max_score=max_score,
        integrity_score=session.integrity_score,
        explanation_policy=exam.explanation_policy,
        answers=answers_detail,
    )
    return ApiResponse.ok(data=res, message="Hasil ujian berhasil dimuat")


@router.get("/exam/{exam_id}/export/pdf")
def export_student_result_pdf(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student),
):
    session = (
        db.query(ExamSession)
        .filter(ExamSession.exam_id == exam_id, ExamSession.student_id == current_user.id)
        .first()
    )
    if not session:
        raise AppException(
            message="Hasil lembar ujian belum tersedia atau belum diikuti.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="RESULT_NOT_FOUND",
        )

    pdf_buffer = generate_pdf_student_result(db, session.id)
    filename = f"transkrip_nilai_{current_user.identifier}_exam_{exam_id}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

