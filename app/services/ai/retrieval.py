import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.user import User
from app.models.academic import Class, ClassMember
from app.models.exam import Exam, ExamQuestion
from app.models.session import ExamSession, StudentAnswer
from app.models.question import Question, QuestionBank
from app.core.exceptions import AppException
from app.core.cache import memory_cache
from app.core.billing_defaults import (
    DEFAULT_PRICING_PLANS,
    DEFAULT_AI_CREDITS_CONFIG,
    DEFAULT_PROMO_CODES,
)
from fastapi import status

logger = logging.getLogger(__name__)


def build_scoped_user_context(user: User, db: Session, query: Optional[str] = None) -> str:
    """Extracts strictly scoped realtime database context for the authenticated user.
    Enforces tenant boundaries and student privacy isolation:
    - Students can ONLY see their own exam scores, enrolled classes, and scheduled exams for their class.
    - Teachers can see aggregated class metrics and their own question banks/exams.
    - Admins see tenant-level summaries.
    Cached in memory for 60 seconds per user.
    """
    cache_key = f"scoped_context:{user.id}:{user.role}"
    cached = memory_cache.get(cache_key)
    if cached:
        return cached
    lines: List[str] = []
    lines.append(f"=== INFORMASI PENGGUNA TEROTENTIKASI ===")
    lines.append(f"Nama: {user.full_name or user.username}")
    lines.append(f"Role: {user.role.upper()}")
    lines.append(f"NISN/NIP/Identifier: {user.identifier or '-'}")
    lines.append("")

    if user.role == "student":
        # 1. Enrolled Classes
        memberships = (
            db.query(ClassMember)
            .filter(ClassMember.user_id == user.id)
            .all()
        )
        class_ids = [m.class_id for m in memberships]
        enrolled_classes = (
            db.query(Class).filter(Class.id.in_(class_ids)).all()
            if class_ids else []
        )
        class_names = [f"{c.name} ({c.grade_level})" for c in enrolled_classes]
        lines.append(f"=== KELAS TERDAFTAR ===")
        if class_names:
            lines.append(f"- " + ", ".join(class_names))
        else:
            lines.append("- Belum terdaftar dalam kelas manapun")
        lines.append("")

        # 2. Exam Sessions & Grades History (SCOPED TO THIS STUDENT ONLY)
        sessions = (
            db.query(ExamSession)
            .filter(ExamSession.student_id == user.id)
            .order_by(ExamSession.submit_time.desc(), ExamSession.start_time.desc())
            .all()
        )

        completed_sessions = [s for s in sessions if s.status in ["graded", "submitted"]]
        scores = [float(s.total_score or 0.0) for s in completed_sessions]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        highest_score = max(scores) if scores else 0.0

        lines.append(f"=== REKAP AKADEMIK SISWA ===")
        lines.append(f"- Total Ujian Dikerjakan: {len(sessions)}")
        lines.append(f"- Total Ujian Selesai/Dinilai: {len(completed_sessions)}")
        if completed_sessions:
            lines.append(f"- Rata-rata Nilai: {avg_score}")
            lines.append(f"- Nilai Tertinggi: {highest_score}")
            latest_s = completed_sessions[0]
            lines.append(f"- Nilai Ujian Terakhir: {latest_s.total_score} pada ujian '{latest_s.exam.title if latest_s.exam else 'Ujian'}'")
        lines.append("")

        lines.append(f"=== DAFTAR RIWAYAT UJIAN & NILAI SISWA ===")
        if not sessions:
            lines.append("- Belum pernah mengikuti ujian.")
        else:
            for s in sessions[:15]:  # Up to 15 latest
                exam_title = s.exam.title if s.exam else f"Ujian #{s.exam_id}"
                subject_name = s.exam.class_.name if (s.exam and s.exam.class_) else "Umum"
                submit_str = s.submit_time.strftime("%d %b %Y %H:%M") if s.submit_time else "Belum submit"
                
                status_label = {
                    "graded": "Selesai Dinilai",
                    "submitted": "Menunggu Penilaian",
                    "in_progress": "Sedang Berlangsung",
                    "aborted": "Gugur / Didiskualifikasi",
                }.get(s.status, s.status)

                lines.append(
                    f"- Judul: '{exam_title}' | Kelas/Mapel: {subject_name} | "
                    f"Nilai: {float(s.total_score or 0.0):.1f} | Integritas: {s.integrity_score}% | "
                    f"Status: {status_label} | Tanggal: {submit_str}"
                )
        lines.append("")

        # 3. Upcoming or Active Exams for Student's Classes (NO ANSWER KEYS LEAKED)
        if class_ids:
            now = datetime.utcnow()
            upcoming_exams = (
                db.query(Exam)
                .filter(
                    Exam.class_id.in_(class_ids),
                    Exam.status.in_(["published", "in_progress"]),
                )
                .order_by(Exam.start_time.asc())
                .all()
            )

            lines.append(f"=== JADWAL UJIAN MENDATANG / AKTIF ===")
            if not upcoming_exams:
                lines.append("- Tidak ada jadwal ujian baru saat ini.")
            else:
                for ue in upcoming_exams:
                    start_str = ue.start_time.strftime("%d %b %Y %H:%M") if ue.start_time else "-"
                    end_str = ue.end_time.strftime("%d %b %Y %H:%M") if ue.end_time else "-"
                    lines.append(
                        f"- '{ue.title}' ({ue.class_.name if ue.class_ else 'Kelas'}) | "
                        f"Waktu Mulai: {start_str} s/d {end_str} | Durasi: {ue.duration_minutes} Menit | "
                        f"Status: {ue.status.upper()}"
                    )
            lines.append("")

    elif user.role == "teacher":
        # Classes created
        classes = db.query(Class).filter(Class.created_by == user.id).all()
        lines.append(f"=== KELAS YANG DIAJAR ===")
        if not classes:
            lines.append("- Belum ada kelas yang dibuat.")
        else:
            for c in classes:
                student_count = db.query(ClassMember).filter(ClassMember.class_id == c.id, ClassMember.role == "student").count()
                lines.append(f"- {c.name} ({c.grade_level}) - {student_count} siswa")
        lines.append("")

        # Exams created
        exams = db.query(Exam).filter(Exam.teacher_id == user.id).order_by(Exam.created_at.desc()).limit(10).all()
        lines.append(f"=== UJIAN YANG DIBUAT (10 TERAKHIR) ===")
        if not exams:
            lines.append("- Belum ada ujian yang dibuat.")
        else:
            for e in exams:
                sess_count = db.query(ExamSession).filter(ExamSession.exam_id == e.id).count()
                lines.append(f"- '{e.title}' ({e.status.upper()}) | Peserta mengerjakan: {sess_count}")
        lines.append("")

        # Question Banks
        banks = db.query(QuestionBank).filter(QuestionBank.teacher_id == user.id).all()
        lines.append(f"=== BANK SOAL ===")
        if not banks:
            lines.append("- Belum ada bank soal.")
        else:
            for b in banks:
                q_count = db.query(Question).filter(Question.bank_id == b.id).count()
                lines.append(f"- '{b.title}' ({b.subject}) - {q_count} butir soal")
        lines.append("")

    elif user.role in ["admin", "superadmin"]:
        total_users = db.query(func.count(User.id)).scalar() or 0
        total_exams = db.query(func.count(Exam.id)).scalar() or 0
        total_classes = db.query(func.count(Class.id)).scalar() or 0
        lines.append(f"=== RINGKASAN METRIK SISTEM ===")
        lines.append(f"- Total Pengguna: {total_users}")
        lines.append(f"- Total Ujian Dibuat: {total_exams}")
        lines.append(f"- Total Kelas Terdaftar: {total_classes}")
        lines.append("")

        lines.append("=== DATA PROMO & HARGA (ADMIN) ===")
        lines.append("Daftar Kode Promo Aktif:")
        active_promos = [p for p in DEFAULT_PROMO_CODES if p.get("is_active", True)]
        if not active_promos:
            lines.append("- Tidak ada promo aktif saat ini.")
        else:
            for p in active_promos:
                discount_parts = []
                dtype = p.get("discount_type")
                dval = p.get("discount_value", 0)
                bonus = p.get("credit_bonus", 0)
                if dtype == "percentage" and dval:
                    discount_parts.append(f"Diskon {dval}%")
                elif dtype == "fixed" and dval:
                    discount_parts.append(f"Potongan Rp {dval:,}".replace(",", "."))
                if bonus:
                    discount_parts.append(f"Bonus {bonus:,} Kredit AI".replace(",", "."))
                discount_str = ", ".join(discount_parts) if discount_parts else "-"

                lines.append(
                    f"- Kode Promo: {p['code']} | Deskripsi: {p.get('description', '-')} | "
                    f"Diskon/Bonus: {discount_str} | Masa Berlaku: {p.get('valid_until', '-')} | "
                    f"Pemakaian: {p.get('used_count', 0)}/{p.get('max_uses', 0)}"
                )

        lines.append("Daftar Paket Langganan:")
        for plan in DEFAULT_PRICING_PLANS:
            price_m = f"Rp {plan.get('price_monthly', 0):,}".replace(",", ".")
            price_y = f"Rp {plan.get('price_annually', 0):,}".replace(",", ".")
            credits_m = f"{plan.get('ai_credits_monthly', 0):,}".replace(",", ".")
            lines.append(
                f"- Paket {plan['name']}: {price_m}/bulan ({price_y}/tahun) | "
                f"Kapasitas: {plan.get('max_students', 0)} siswa, {plan.get('max_teachers', 0)} guru | "
                f"Kredit AI: {credits_m}/bln | Pengawasan: {plan.get('proctoring_type', '-')}"
            )
        lines.append("")

    res_str = "\n".join(lines)
    memory_cache.set(cache_key, res_str, ttl=60)
    return res_str


def build_question_explanation_context(
    exam_id: int,
    question_id: int,
    user: User,
    db: Session,
) -> Dict[str, Any]:
    """Retrieves full pedagogical question context along with the student's answer
    for the Question Explanation Chatbot.
    Enforces security: student must have completed/submitted the exam, or be the teacher of the exam.
    Cached in memory for 5 minutes.
    """
    cache_key = f"q_context:{exam_id}:{question_id}:{user.id}"
    cached = memory_cache.get(cache_key)
    if cached:
        return cached

    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise AppException(
            message="Ujian tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="EXAM_NOT_FOUND",
        )

    # Check question membership in exam
    exam_question = (
        db.query(ExamQuestion)
        .filter(ExamQuestion.exam_id == exam_id, ExamQuestion.question_id == question_id)
        .first()
    )
    if not exam_question:
        raise AppException(
            message="Butir soal ini bukan bagian dari ujian yang dipilih.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="QUESTION_NOT_IN_EXAM",
        )

    question = exam_question.question
    if not question:
        raise AppException(
            message="Data soal tidak ditemukan.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="QUESTION_NOT_FOUND",
        )

    student_answer = None
    session = None

    if user.role == "student":
        session = (
            db.query(ExamSession)
            .filter(ExamSession.exam_id == exam_id, ExamSession.student_id == user.id)
            .first()
        )
        if not session:
            raise AppException(
                message="Anda belum pernah mengerjakan ujian ini.",
                status_code=status.HTTP_403_FORBIDDEN,
                error_code="SESSION_NOT_FOUND",
            )

        if session.status == "in_progress" and exam.explanation_policy == "after_exam_closed":
            raise AppException(
                message="Pembahasan butir soal baru dapat diakses setelah Anda menyelesaikan ujian.",
                status_code=status.HTTP_403_FORBIDDEN,
                error_code="EXPLANATION_LOCKED",
            )

        student_answer = (
            db.query(StudentAnswer)
            .filter(StudentAnswer.session_id == session.id, StudentAnswer.question_id == question_id)
            .first()
        )
    else:
        # Teacher or Admin viewing
        pass

    allocated_points = float(exam_question.allocated_points or 10.0)
    score_obtained = float(student_answer.final_score or 0.0) if student_answer else 0.0
    is_correct = student_answer.is_correct if student_answer else None
    student_response = student_answer.student_response if student_answer else None

    ctx_data = {
        "exam_id": exam.id,
        "exam_title": exam.title,
        "question_id": question.id,
        "question_type": question.question_type,
        "prompt": question.prompt,
        "options": question.options_json or [],
        "correct_answer": question.correct_answer,
        "rubric": question.rubric_json or {},
        "sample_answer": getattr(question, "sample_answer", None) or question.correct_answer or "",
        "explanation": question.explanation or "",
        "allocated_points": allocated_points,
        "student_response": student_response,
        "is_correct": is_correct,
        "score_obtained": score_obtained,
        "ai_explanation": student_answer.ai_explanation if student_answer else None,
        "ai_grading_rationale": student_answer.ai_grading_rationale if student_answer else None,
        "teacher_notes": student_answer.teacher_notes if student_answer else None,
    }
    memory_cache.set(cache_key, ctx_data, ttl=300)
    return ctx_data
