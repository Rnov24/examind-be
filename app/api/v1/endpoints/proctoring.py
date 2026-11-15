import io
from datetime import datetime
from typing import List, Optional
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.dependencies import get_current_active_user, require_teacher
from app.core.tenant_scope import require_exam, require_session
from app.models.user import User
from app.models.session import ExamSession
from app.models.proctoring import ProctoringLog
from app.schemas.proctoring import (
    ProctoringEventCreate,
    ProctoringLogResponse,
    WarningRequest,
    VerdictUpdateRequest,
    SessionTolerateRequest,
    SessionDisqualifyRequest,
)
from app.schemas.common import ApiResponse
from app.services.proctoring.storage import save_snapshot_base64
from app.services.proctoring.integrity_calculator import calculate_session_integrity
from app.services.proctoring.websocket_hub import ws_hub

router = APIRouter(prefix="/proctoring", tags=["AI Proctoring & Live Monitoring"])


@router.post("/log-event", response_model=ApiResponse[ProctoringLogResponse])
async def log_proctoring_event(
    request: ProctoringEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Isolation: the event must target a session the caller may touch.
    # Students log events only for their OWN session; teachers/admins only
    # for sessions of their exam/tenant. Without this, anyone could inject
    # fake violations into another student's session and tank their
    # integrity score.
    session = require_session(db, current_user, request.session_id)

    # Save snapshot if provided
    snapshot_url = None
    if request.snapshot_base64:
        snapshot_url = save_snapshot_base64(session.id, request.snapshot_base64)

    now = datetime.utcnow()
    log = ProctoringLog(
        session_id=session.id,
        event_type=request.event_type,
        camera_source=request.camera_source,
        severity=request.severity,
        duration_seconds=request.duration_seconds,
        snapshot_url=snapshot_url,
        event_timestamp=now,
        reviewed_by_teacher=False,
        teacher_verdict="pending",
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # Recalculate session integrity
    all_logs = db.query(ProctoringLog).filter(ProctoringLog.session_id == session.id).all()
    new_integrity = calculate_session_integrity(all_logs)
    session.integrity_score = new_integrity
    db.commit()

    student_name = session.student.full_name if session.student else "Siswa"

    # Broadcast event to teacher live monitoring room via WebSocket
    broadcast_payload = {
        "event": "PROCTORING_FLAG_ALERT",
        "payload": {
            "session_id": session.id,
            "student_id": session.student_id,
            "student_name": student_name,
            "event_type": log.event_type,
            "camera_source": log.camera_source,
            "severity": log.severity,
            "duration_seconds": log.duration_seconds,
            "timestamp": log.event_timestamp.isoformat(),
            "snapshot_url": log.snapshot_url,
            "current_integrity_score": new_integrity,
        },
    }
    await ws_hub.broadcast_to_exam(session.exam_id, broadcast_payload)

    res = ProctoringLogResponse(
        id=log.id,
        session_id=log.session_id,
        event_type=log.event_type,
        camera_source=log.camera_source,
        severity=log.severity,
        duration_seconds=log.duration_seconds,
        snapshot_url=log.snapshot_url,
        event_timestamp=log.event_timestamp,
        reviewed_by_teacher=log.reviewed_by_teacher,
        teacher_verdict=log.teacher_verdict,
        student_name=student_name,
    )
    return ApiResponse.ok(data=res, message="Event pelanggaran berhasil dicatat")


@router.get("/exam/{exam_id}/logs", response_model=ApiResponse[List[ProctoringLogResponse]])
def get_exam_proctoring_logs(
    exam_id: int,
    page: int = Query(1, ge=1, description="Nomor halaman"),
    page_size: int = Query(50, ge=1, le=200, description="Jumlah data per halaman"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    # 404 when the exam belongs to another school or another teacher.
    require_exam(db, current_user, exam_id)
    sessions = db.query(ExamSession).filter(ExamSession.exam_id == exam_id).all()
    session_ids = [s.id for s in sessions]
    if not session_ids:
        return ApiResponse.ok(data=[], message="Belum ada catatan insiden.")

    logs = (
        db.query(ProctoringLog)
        .options(joinedload(ProctoringLog.session).joinedload(ExamSession.student))
        .filter(ProctoringLog.session_id.in_(session_ids))
        .order_by(ProctoringLog.event_timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    results = []
    for l in logs:
        student_name = l.session.student.full_name if l.session and l.session.student else "Siswa"
        results.append(
            ProctoringLogResponse(
                id=l.id,
                session_id=l.session_id,
                event_type=l.event_type,
                camera_source=l.camera_source,
                severity=l.severity,
                duration_seconds=l.duration_seconds,
                snapshot_url=l.snapshot_url,
                event_timestamp=l.event_timestamp,
                reviewed_by_teacher=l.reviewed_by_teacher,
                teacher_verdict=l.teacher_verdict,
                student_name=student_name,
            )
        )

    return ApiResponse.ok(data=results, message="Daftar log pengawasan berhasil dimuat")


@router.put("/log/{log_id}/verdict", response_model=ApiResponse[dict])
def update_teacher_verdict(
    log_id: int,
    request: VerdictUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    log = db.query(ProctoringLog).filter(ProctoringLog.id == log_id).first()
    if not log:
        raise AppException(
            message="Catatan insiden tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="LOG_NOT_FOUND",
        )
    # Isolation: the log's session must belong to the caller's exam/tenant.
    require_session(db, current_user, log.session_id)

    log.teacher_verdict = request.verdict
    log.reviewed_by_teacher = True
    db.commit()

    # Recalculate session integrity score
    session = log.session
    if session:
        all_logs = db.query(ProctoringLog).filter(ProctoringLog.session_id == session.id).all()
        session.integrity_score = calculate_session_integrity(all_logs)
        db.commit()

    return ApiResponse.ok(
        data={"log_id": log.id, "new_integrity_score": session.integrity_score if session else 100},
        message="Verdict guru berhasil diperbarui",
    )


@router.post("/send-warning", response_model=ApiResponse[dict])
async def send_teacher_warning(
    request: WarningRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    # Isolation: only the exam's teacher, a tenant admin, or superadmin
    # may warn / tolerate / disqualify this session.
    session = require_session(db, current_user, request.session_id)

    # Deliver alert straight to student's screen in real-time
    warning_payload = {
        "event": "TEACHER_DIRECT_WARNING",
        "payload": {
            "teacher_name": current_user.full_name,
            "message_text": request.message_text,
            "urgency": request.urgency,
            "timestamp": datetime.utcnow().isoformat(),
        },
    }
    await ws_hub.send_to_student(session.id, warning_payload)
    await ws_hub.send_to_companion(session.id, warning_payload)

    return ApiResponse.ok(
        data={"session_id": request.session_id, "delivered": True},
        message="Peringatan langsung berhasil dikirimkan ke layar siswa",
    )


@router.post("/session/tolerate", response_model=ApiResponse[dict])
async def tolerate_session_incidents(
    request: SessionTolerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    """Prinsip Human-in-the-Loop: Pengawas memberikan toleransi wajar untuk anomali yang dinilai false positive.

    Seluruh catatan log yang belum diverifikasi pelanggaran ditandai sebagai 'ignored_false_positive'
    dan skor integritas dihitung ulang.
    """
    # Isolation: only the exam's teacher, a tenant admin, or superadmin
    # may adjudicate this session.
    session = require_session(db, current_user, request.session_id)

    # Mark pending logs for this session as ignored_false_positive
    logs = (
        db.query(ProctoringLog)
        .filter(
            ProctoringLog.session_id == session.id,
            ProctoringLog.teacher_verdict != "confirmed_violation",
        )
        .all()
    )
    for l in logs:
        l.teacher_verdict = "ignored_false_positive"
        l.reviewed_by_teacher = True

    # Recalculate session integrity score
    all_logs = db.query(ProctoringLog).filter(ProctoringLog.session_id == session.id).all()
    session.integrity_score = calculate_session_integrity(all_logs)
    db.commit()

    student_name = session.student.full_name if session.student else "Siswa"

    # Broadcast update to teacher live monitoring room
    broadcast_payload = {
        "event": "PROCTORING_FLAG_ALERT",
        "payload": {
            "session_id": session.id,
            "student_id": session.student_id,
            "student_name": student_name,
            "event_type": "tolerated_by_teacher",
            "camera_source": "human_supervisor",
            "severity": "low",
            "duration_seconds": 0,
            "timestamp": datetime.utcnow().isoformat(),
            "snapshot_url": None,
            "current_integrity_score": session.integrity_score,
            "status": session.status,
        },
    }
    await ws_hub.broadcast_to_exam(session.exam_id, broadcast_payload)

    return ApiResponse.ok(
        data={"session_id": session.id, "new_integrity_score": session.integrity_score},
        message=f"Catatan anomali untuk {student_name} telah ditoleransi wajar oleh pengawas.",
    )


@router.post("/session/disqualify", response_model=ApiResponse[dict])
async def deliberate_teacher_disqualify(
    request: SessionDisqualifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    """Prinsip Human-in-the-Loop: Diskualifikasi hanya dapat diputuskan oleh guru/pengawas secara sadar.

    Sistem AI tidak pernah menggugurkan secara sepihak. Pengawas memberikan alasan dan catatan resmi.
    """
    # Isolation: only the exam's teacher, a tenant admin, or superadmin
    # may adjudicate this session.
    session = require_session(db, current_user, request.session_id)

    now = datetime.utcnow()
    session.status = "aborted"
    session.total_score = 0.00
    session.integrity_score = 0
    if not session.submit_time:
        session.submit_time = now

    # Create official supervisor adjudication log
    audit_log = ProctoringLog(
        session_id=session.id,
        event_type="teacher_disqualification",
        camera_source="human_supervisor",
        severity="high",
        duration_seconds=1,
        snapshot_url=None,
        event_timestamp=now,
        reviewed_by_teacher=True,
        teacher_verdict="confirmed_violation",
    )
    db.add(audit_log)
    db.commit()

    student_name = session.student.full_name if session.student else "Siswa"

    # Broadcast to live monitoring room
    disqualify_payload = {
        "event": "STUDENT_DISQUALIFIED",
        "payload": {
            "session_id": session.id,
            "student_id": session.student_id,
            "student_name": student_name,
            "reason": request.reason,
            "notes": request.notes,
            "current_integrity_score": 0,
            "status": "aborted",
            "timestamp": now.isoformat(),
        },
    }
    await ws_hub.broadcast_to_exam(session.exam_id, disqualify_payload)

    # Deliver official adjudication notification to student's screen in real-time
    direct_msg = {
        "event": "TEACHER_DISQUALIFIED",
        "payload": {
            "teacher_name": current_user.full_name,
            "reason": request.reason,
            "notes": request.notes,
            "timestamp": now.isoformat(),
        },
    }
    await ws_hub.send_to_student(session.id, direct_msg)

    return ApiResponse.ok(
        data={"session_id": session.id, "status": "aborted"},
        message=f"Sesi ujian {student_name} resmi didiskualifikasi oleh pengawas.",
    )


@router.get("/exam/{exam_id}/export/excel")
def export_exam_camera_log_excel(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    # Same scoping as GET /proctoring/exam/{exam_id}/logs: 404 when the exam
    # belongs to another school or another teacher. Students never reach
    # here (require_teacher rejects them with 403 first).
    exam = require_exam(db, current_user, exam_id)

    sessions = db.query(ExamSession).filter(ExamSession.exam_id == exam_id).all()
    session_ids = [s.id for s in sessions]
    logs = []
    if session_ids:
        logs = (
            db.query(ProctoringLog)
            .options(joinedload(ProctoringLog.session).joinedload(ExamSession.student))
            .filter(ProctoringLog.session_id.in_(session_ids))
            .order_by(ProctoringLog.event_timestamp.asc(), ProctoringLog.id.asc())
            .all()
        )
    session_by_id = {s.id: s for s in sessions}

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Laporan Kamera"

    title_font = Font(name="Calibri", size=16, bold=True, color="1E3A8A")
    sub_font = Font(name="Calibri", size=11, italic=True)
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")

    ws["A1"] = f"LAPORAN LOG KAMERA UJIAN: {exam.title.upper() if exam and exam.title else 'UJIAN'}"
    ws["A1"].font = title_font
    ws["A2"] = (
        f"Guru: {exam.teacher.full_name if exam and exam.teacher else '-'}"
        f" | Total Kejadian: {len(logs)}"
    )
    ws["A2"].font = sub_font

    # NOTE: ProctoringLog stores no per-event integrity score, so the
    # integrity column below is the session's CURRENT score at export time
    # (header says so explicitly), not the score at the moment of the event.
    headers = [
        "No",
        "Waktu Kejadian",
        "Nama Siswa",
        "NISN / ID",
        "ID Sesi",
        "Jenis Kejadian",
        "Tingkat Keparahan",
        "Durasi (detik)",
        "Sumber Kamera",
        "Verdict Guru",
        "Sudah Direview",
        "Skor Integritas Sesi Saat Ini (%)",
        "Tautan Snapshot",
    ]

    # Write headers at row 4 (same layout as the gradebook exporter)
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # One row per proctoring log, chronological order.
    for row_idx, log in enumerate(logs, start=5):
        session = session_by_id.get(log.session_id)
        student = session.student if session else None
        row_data = [
            row_idx - 4,
            log.event_timestamp,
            student.full_name if student else "Siswa",
            student.identifier if student else "-",
            log.session_id,
            log.event_type,
            log.severity,
            log.duration_seconds,
            log.camera_source,
            log.teacher_verdict,
            "Ya" if log.reviewed_by_teacher else "Belum",
            session.integrity_score if session is not None else None,
            log.snapshot_url or "-",
        ]

        for col_idx, val in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.border = thin_border
            if col_idx in [1, 4, 5, 7, 8, 11, 12]:
                cell.alignment = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=2).number_format = "yyyy-mm-dd hh:mm:ss"

    # Adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"laporan_kamera_exam_{exam_id}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

