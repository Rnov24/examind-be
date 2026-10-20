import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, case

from app.models.user import User
from app.models.tenant import Tenant, TenantRegistrationCode
from app.models.academic import Class, ClassMember
from app.models.exam import Exam, ExamQuestion
from app.models.session import ExamSession, StudentAnswer
from app.models.question import Question, QuestionBank
from app.models.proctoring import ProctoringLog
from app.models.secret import SystemSecret
from app.core.exceptions import AppException
from app.core.cache import memory_cache
from app.core.billing_defaults import (
    DEFAULT_PRICING_PLANS,
    DEFAULT_AI_CREDITS_CONFIG,
    DEFAULT_PROMO_CODES,
)
from fastapi import status

# Plan rates (in IDR) - matching app/api/v1/endpoints/superadmin.py PLAN_PRICES
PLAN_PRICES = {
    "starter": 1500000,
    "pro": 3500000,
    "enterprise": 7500000,
}

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
        # Aggregates via SQL (no full-row load); display list capped at 15 with eager loading.
        completed_cond = ExamSession.status.in_(["graded", "submitted"])
        agg = (
            db.query(
                func.count(ExamSession.id),
                func.coalesce(func.sum(case((completed_cond, 1), else_=0)), 0),
                func.avg(case((completed_cond, func.coalesce(ExamSession.total_score, 0.0)))),
                func.max(case((completed_cond, func.coalesce(ExamSession.total_score, 0.0)))),
            )
            .filter(ExamSession.student_id == user.id)
            .one()
        )
        total_sessions_count = agg[0] or 0
        completed_count = int(agg[1] or 0)
        avg_score = round(float(agg[2]), 1) if completed_count and agg[2] is not None else 0.0
        highest_score = float(agg[3]) if completed_count and agg[3] is not None else 0.0

        sessions = (
            db.query(ExamSession)
            .options(joinedload(ExamSession.exam).joinedload(Exam.class_))
            .filter(ExamSession.student_id == user.id)
            .order_by(ExamSession.submit_time.desc(), ExamSession.start_time.desc())
            .limit(15)
            .all()
        )

        lines.append(f"=== REKAP AKADEMIK SISWA ===")
        lines.append(f"- Total Ujian Dikerjakan: {total_sessions_count}")
        lines.append(f"- Total Ujian Selesai/Dinilai: {completed_count}")
        if completed_count:
            lines.append(f"- Rata-rata Nilai: {avg_score}")
            lines.append(f"- Nilai Tertinggi: {highest_score}")
            latest_s = (
                db.query(ExamSession)
                .options(joinedload(ExamSession.exam))
                .filter(ExamSession.student_id == user.id, completed_cond)
                .order_by(ExamSession.submit_time.desc(), ExamSession.start_time.desc())
                .first()
            )
            lines.append(f"- Nilai Ujian Terakhir: {latest_s.total_score} pada ujian '{latest_s.exam.title if latest_s.exam else 'Ujian'}'")
        lines.append("")

        lines.append(f"=== DAFTAR RIWAYAT UJIAN & NILAI SISWA ===")
        if not sessions:
            lines.append("- Belum pernah mengikuti ujian.")
        else:
            for s in sessions:  # Up to 15 latest (already limited by query)
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
        class_ids = [c.id for c in classes]
        student_counts = (
            dict(
                db.query(ClassMember.class_id, func.count(ClassMember.id))
                .filter(ClassMember.class_id.in_(class_ids), ClassMember.role == "student")
                .group_by(ClassMember.class_id)
                .all()
            )
            if class_ids
            else {}
        )
        lines.append(f"=== KELAS YANG DIAJAR ===")
        if not classes:
            lines.append("- Belum ada kelas yang dibuat.")
        else:
            for c in classes:
                student_count = student_counts.get(c.id, 0)
                lines.append(f"- {c.name} ({c.grade_level}) - {student_count} siswa")
        lines.append("")

        # Exams created
        exams = db.query(Exam).filter(Exam.teacher_id == user.id).order_by(Exam.created_at.desc()).limit(10).all()
        exam_ids = [e.id for e in exams]
        session_counts = (
            dict(
                db.query(ExamSession.exam_id, func.count(ExamSession.id))
                .filter(ExamSession.exam_id.in_(exam_ids))
                .group_by(ExamSession.exam_id)
                .all()
            )
            if exam_ids
            else {}
        )
        lines.append(f"=== UJIAN YANG DIBUAT (10 TERAKHIR) ===")
        if not exams:
            lines.append("- Belum ada ujian yang dibuat.")
        else:
            for e in exams:
                sess_count = session_counts.get(e.id, 0)
                lines.append(f"- '{e.title}' ({e.status.upper()}) | Peserta mengerjakan: {sess_count}")
        lines.append("")

        # Question Banks
        banks = db.query(QuestionBank).filter(QuestionBank.teacher_id == user.id).all()
        bank_ids = [b.id for b in banks]
        question_counts = (
            dict(
                db.query(Question.bank_id, func.count(Question.id))
                .filter(Question.bank_id.in_(bank_ids))
                .group_by(Question.bank_id)
                .all()
            )
            if bank_ids
            else {}
        )
        lines.append(f"=== BANK SOAL ===")
        if not banks:
            lines.append("- Belum ada bank soal.")
        else:
            for b in banks:
                q_count = question_counts.get(b.id, 0)
                lines.append(f"- '{b.title}' ({b.subject}) - {q_count} butir soal")
        lines.append("")

    elif user.role == "superadmin":
        # 1. Platform Statistics (Global)
        total_tenants = db.query(func.count(Tenant.id)).scalar() or 0
        active_tenants = db.query(func.count(Tenant.id)).filter(Tenant.is_active == True).scalar() or 0
        total_users = db.query(func.count(User.id)).scalar() or 0
        total_exams = db.query(func.count(Exam.id)).scalar() or 0
        total_sessions = db.query(func.count(ExamSession.id)).scalar() or 0
        total_classes = db.query(func.count(Class.id)).scalar() or 0

        # Plan distribution across all tenants
        all_tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
        plan_distribution = {"starter": 0, "pro": 0, "enterprise": 0}
        for t in all_tenants:
            p = t.subscription_plan or "pro"
            plan_distribution[p] = plan_distribution.get(p, 0) + 1

        # Global users by role
        global_role_counts = (
            db.query(User.role, func.count(User.id))
            .group_by(User.role)
            .all()
        )
        global_roles = {r: cnt for r, cnt in global_role_counts}

        lines.append("=== STATISTIK & METRIK PLATFORM GLOBAL ===")
        lines.append(f"- Total Sekolah/Tenant: {total_tenants} ({active_tenants} Aktif)")
        lines.append(
            f"- Distribusi Paket: Starter: {plan_distribution.get('starter', 0)}, "
            f"Pro: {plan_distribution.get('pro', 0)}, "
            f"Enterprise: {plan_distribution.get('enterprise', 0)}"
        )
        lines.append(
            f"- Total Pengguna: {total_users} (Superadmin: {global_roles.get('superadmin', 0)}, "
            f"Admin Sekolah: {global_roles.get('admin', 0)}, "
            f"Guru: {global_roles.get('teacher', 0)}, "
            f"Siswa: {global_roles.get('student', 0)})"
        )
        lines.append(
            f"- Total Ujian Dibuat: {total_exams} | "
            f"Total Sesi Pengerjaan: {total_sessions} | "
            f"Total Kelas: {total_classes}"
        )
        lines.append("")

        # 2. Finance Summary (MRR, ARR, ARPU)
        mrr = 0
        for t in all_tenants:
            if t.is_active and t.subscription_status in ("active", "trial"):
                price = PLAN_PRICES.get(t.subscription_plan, 3500000)
                mrr += price
        arr = mrr * 12
        active_count = sum(1 for t in all_tenants if t.is_active)
        arpu = (mrr // active_count) if active_count > 0 else 0

        lines.append("=== RINGKASAN FINANSIAL SAAS (MRR, ARR, ARPU) ===")
        lines.append(f"- MRR (Monthly Recurring Revenue): Rp {mrr:,}".replace(",", "."))
        lines.append(f"- ARR (Annual Recurring Revenue): Rp {arr:,}".replace(",", "."))
        lines.append(f"- ARPU (Average Revenue Per Tenant): Rp {arpu:,}".replace(",", "."))
        lines.append("")

        # 3. Tenant List (capped at 20) with student/teacher counts
        user_counts = (
            db.query(User.tenant_id, User.role, func.count(User.id))
            .filter(User.tenant_id.isnot(None))
            .group_by(User.tenant_id, User.role)
            .all()
        )
        tenant_user_stats = {}
        for tid, r, cnt in user_counts:
            if tid not in tenant_user_stats:
                tenant_user_stats[tid] = {"student": 0, "teacher": 0, "admin": 0, "total": 0}
            tenant_user_stats[tid][r] = cnt
            tenant_user_stats[tid]["total"] += cnt

        lines.append("=== DAFTAR SEKOLAH / TENANT (MAKS. 20) ===")
        if not all_tenants:
            lines.append("- Belum ada sekolah/tenant terdaftar.")
        else:
            for t in all_tenants[:20]:
                u_stat = tenant_user_stats.get(t.id, {"student": 0, "teacher": 0, "admin": 0, "total": 0})
                plan_str = (t.subscription_plan or "pro").upper()
                status_str = (t.subscription_status or "active").upper()
                lines.append(
                    f"- [{t.code}] {t.name} | Paket: {plan_str} | Status: {status_str} | "
                    f"{u_stat['student']} Siswa, {u_stat['teacher']} Guru, {u_stat['admin']} Admin"
                )
        lines.append("")

        # 4. Subscription Due Dates (next 14 days)
        now = datetime.utcnow()
        fourteen_days_later = now + timedelta(days=14)
        due_tenants = []
        for t in all_tenants:
            due_date = getattr(t, "subscription_due_date", None)
            if due_date and now <= due_date <= fourteen_days_later:
                due_tenants.append((t, due_date))

        lines.append("=== JATUH TEMPO / DUE DATE LANGGANAN (14 HARI KE DEPAN) ===")
        if not due_tenants:
            lines.append("- Tidak ada sekolah yang jatuh tempo (due date) dalam 14 hari ke depan.")
        else:
            for t, due_date in due_tenants[:20]:
                due_str = due_date.strftime("%d %b %Y")
                plan_str = (t.subscription_plan or "pro").upper()
                status_str = (t.subscription_status or "active").upper()
                lines.append(f"- {t.name} ({t.code}): Jatuh Tempo pada {due_str} (due date) | Paket: {plan_str} | Status: {status_str}")
        lines.append("")

        # 5. Registration Codes (capped at 10 per tenant)
        reg_codes = (
            db.query(TenantRegistrationCode)
            .filter(TenantRegistrationCode.is_active == True)
            .order_by(TenantRegistrationCode.tenant_id.asc(), TenantRegistrationCode.role.asc())
            .all()
        )
        codes_by_tenant = {}
        for rc in reg_codes:
            codes_by_tenant.setdefault(rc.tenant_id, []).append(rc)

        tenant_map = {t.id: t for t in all_tenants}
        lines.append("=== KODE REGISTRASI ONBOARDING SEKOLAH ===")
        if not reg_codes:
            lines.append("- Belum ada kode registrasi aktif.")
        else:
            for tid, t_codes in list(codes_by_tenant.items())[:20]:
                t_obj = tenant_map.get(tid)
                t_name = t_obj.name if t_obj else f"Tenant #{tid}"
                t_code = t_obj.code if t_obj else "-"
                lines.append(f"Sekolah: {t_name} [{t_code}]")
                for rc in t_codes[:10]:
                    uses_str = f"{rc.used_count}/{rc.max_uses}" if rc.max_uses > 0 else f"{rc.used_count}/unlimited"
                    lines.append(
                        f"  - Role: {rc.role.upper()} | Kode: {rc.code} | "
                        f"Penggunaan: {uses_str} | Deskripsi: {rc.description or '-'}"
                    )
        lines.append("")

        # 6. Secrets Metadata ONLY (never values)
        secrets = (
            db.query(
                SystemSecret.key_name,
                SystemSecret.service_name,
                SystemSecret.is_active,
                SystemSecret.description,
            )
            .order_by(SystemSecret.service_name.asc(), SystemSecret.key_name.asc())
            .all()
        )
        lines.append("=== STATUS KONFIGURASI API & SECRETS (METADATA ONLY) ===")
        if not secrets:
            lines.append("- Belum ada secret/integrasi yang terkonfigurasi.")
        else:
            for s_key, s_service, s_active, s_desc in secrets[:20]:
                status_label = "terkonfigurasi (Aktif)" if s_active else "nonaktif"
                lines.append(f"- {s_key} ({s_service}) — {status_label}")
        lines.append("")

        # 7. Proctoring Aggregates (last 7 days) — bucket counts via SQL aggregation
        seven_days_ago = now - timedelta(days=7)
        eff_score = func.coalesce(ExamSession.integrity_score, 100)
        integ_agg = (
            db.query(
                func.count(ExamSession.id),
                func.coalesce(func.sum(case((eff_score >= 90, 1), else_=0)), 0),
                func.coalesce(func.sum(case(((eff_score >= 70) & (eff_score < 90), 1), else_=0)), 0),
                func.coalesce(func.sum(case((eff_score < 70, 1), else_=0)), 0),
            )
            .filter(ExamSession.start_time >= seven_days_ago)
            .one()
        )
        total_recent_sessions = integ_agg[0] or 0
        high_integrity = int(integ_agg[1] or 0)
        med_integrity = int(integ_agg[2] or 0)
        low_integrity = int(integ_agg[3] or 0)

        violation_counts = (
            db.query(ProctoringLog.event_type, func.count(ProctoringLog.id))
            .filter(ProctoringLog.event_timestamp >= seven_days_ago)
            .group_by(ProctoringLog.event_type)
            .all()
        )

        lines.append("=== AGREGAT PENGAWASAN & INTEGRITAS (7 HARI TERAKHIR) ===")
        lines.append(f"- Total Sesi Ujian (7 Hari Terakhir): {total_recent_sessions}")
        lines.append("- Distribusi Skor Integritas Sesi:")
        lines.append(f"  * Integritas Tinggi (90-100%): {high_integrity} sesi")
        lines.append(f"  * Integritas Sedang (70-89%): {med_integrity} sesi")
        lines.append(f"  * Integritas Rendah / Indikasi Pelanggaran (<70%): {low_integrity} sesi")
        if violation_counts:
            lines.append("- Frekuensi Pelanggaran Proctoring:")
            for v_type, cnt in violation_counts:
                lines.append(f"  * {v_type}: {cnt} kali")
        else:
            lines.append("- Tidak ada pelanggaran tercatat dalam 7 hari terakhir.")
        lines.append("")

        # 8. Promos and Pricing Plans
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

    elif user.role == "admin":
        tenant = (
            db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
            if user.tenant_id
            else None
        )

        lines.append("=== INFORMASI SEKOLAH / TENANT ===")
        if not tenant:
            lines.append("- Akun admin belum diasosiasikan dengan sekolah/tenant manapun.")
        else:
            plan_str = (tenant.subscription_plan or "pro").upper()
            status_str = (tenant.subscription_status or "active").upper()
            lines.append(f"- Nama Sekolah: {tenant.name} [{tenant.code}]")
            lines.append(f"- Paket Langganan: {plan_str} | Status: {status_str}")
            lines.append(f"- Kuota Kapasitas: Maks {tenant.max_students} Siswa, Maks {tenant.max_teachers} Guru")
            lines.append(f"- Kuota AI Credits: {tenant.ai_credits_used} / {tenant.ai_credits_monthly} terpakai")
            due_date = getattr(tenant, "subscription_due_date", None)
            if due_date:
                lines.append(f"- Tanggal Jatuh Tempo Langganan (due date): {due_date.strftime('%d %b %Y')}")
        lines.append("")

        if tenant:
            # Users by role in this tenant
            tenant_users = (
                db.query(User.role, func.count(User.id))
                .filter(User.tenant_id == tenant.id)
                .group_by(User.role)
                .all()
            )
            role_counts = {r: cnt for r, cnt in tenant_users}
            lines.append("=== REKAP PENGGUNA SEKOLAH ===")
            lines.append(f"- Total Guru: {role_counts.get('teacher', 0)}")
            lines.append(f"- Total Siswa: {role_counts.get('student', 0)}")
            lines.append(f"- Total Admin Sekolah: {role_counts.get('admin', 0)}")
            lines.append("")

            # Academic & Exam stats for this tenant (ID lists as subqueries, not materialized)
            teacher_ids_subq = db.query(User.id).filter(User.tenant_id == tenant.id, User.role == "teacher")
            total_classes = db.query(func.count(Class.id)).filter(Class.created_by.in_(teacher_ids_subq)).scalar() or 0
            total_exams = db.query(func.count(Exam.id)).filter(Exam.teacher_id.in_(teacher_ids_subq)).scalar() or 0

            student_ids_subq = db.query(User.id).filter(User.tenant_id == tenant.id, User.role == "student")
            total_sessions = db.query(func.count(ExamSession.id)).filter(ExamSession.student_id.in_(student_ids_subq)).scalar() or 0

            lines.append("=== REKAP AKADEMIK & UJIAN SEKOLAH ===")
            lines.append(f"- Total Kelas Aktif: {total_classes}")
            lines.append(f"- Total Ujian Dibuat: {total_exams}")
            lines.append(f"- Total Pengerjaan Sesi Ujian: {total_sessions}")
            lines.append("")

            # Registration codes (SCOPED to this tenant only, capped at 10)
            reg_codes = (
                db.query(TenantRegistrationCode)
                .filter(
                    TenantRegistrationCode.tenant_id == tenant.id,
                    TenantRegistrationCode.is_active == True,
                )
                .order_by(TenantRegistrationCode.role.asc())
                .limit(10)
                .all()
            )
            lines.append(f"=== KODE REGISTRASI ONBOARDING ({tenant.name}) ===")
            if not reg_codes:
                lines.append("- Belum ada kode registrasi aktif.")
            else:
                for rc in reg_codes:
                    uses_str = f"{rc.used_count}/{rc.max_uses}" if rc.max_uses > 0 else f"{rc.used_count}/unlimited"
                    lines.append(
                        f"- Role: {rc.role.upper()} | Kode: {rc.code} | "
                        f"Penggunaan: {uses_str} | Deskripsi: {rc.description or '-'}"
                    )
            lines.append("")

            # Proctoring aggregates (last 7 days, scoped to this tenant's students)
            # Bucket counts via SQL aggregation; session sets passed as subqueries.
            now = datetime.utcnow()
            seven_days_ago = now - timedelta(days=7)
            recent_filter = (
                ExamSession.student_id.in_(student_ids_subq),
                ExamSession.start_time >= seven_days_ago,
            )
            eff_score = func.coalesce(ExamSession.integrity_score, 100)
            integ_agg = (
                db.query(
                    func.count(ExamSession.id),
                    func.coalesce(func.sum(case((eff_score >= 90, 1), else_=0)), 0),
                    func.coalesce(func.sum(case(((eff_score >= 70) & (eff_score < 90), 1), else_=0)), 0),
                    func.coalesce(func.sum(case((eff_score < 70, 1), else_=0)), 0),
                )
                .filter(*recent_filter)
                .one()
            )
            total_recent_sessions = integ_agg[0] or 0
            high_integrity = int(integ_agg[1] or 0)
            med_integrity = int(integ_agg[2] or 0)
            low_integrity = int(integ_agg[3] or 0)

            recent_session_ids_subq = db.query(ExamSession.id).filter(*recent_filter)
            violation_counts = (
                db.query(ProctoringLog.event_type, func.count(ProctoringLog.id))
                .filter(ProctoringLog.session_id.in_(recent_session_ids_subq), ProctoringLog.event_timestamp >= seven_days_ago)
                .group_by(ProctoringLog.event_type)
                .all()
            )

            lines.append("=== AGREGAT PENGAWASAN & INTEGRITAS SEKOLAH (7 HARI TERAKHIR) ===")
            lines.append(f"- Total Sesi Ujian (7 Hari Terakhir): {total_recent_sessions}")
            lines.append("- Distribusi Skor Integritas Sesi:")
            lines.append(f"  * Integritas Tinggi (90-100%): {high_integrity} sesi")
            lines.append(f"  * Integritas Sedang (70-89%): {med_integrity} sesi")
            lines.append(f"  * Integritas Rendah / Indikasi Pelanggaran (<70%): {low_integrity} sesi")
            if violation_counts:
                lines.append("- Frekuensi Pelanggaran Proctoring:")
                for v_type, cnt in violation_counts:
                    lines.append(f"  * {v_type}: {cnt} kali")
            else:
                lines.append("- Tidak ada pelanggaran tercatat dalam 7 hari terakhir.")
            lines.append("")

        # Secrets metadata (names and provider, never values)
        secrets = (
            db.query(
                SystemSecret.key_name,
                SystemSecret.service_name,
                SystemSecret.is_active,
            )
            .order_by(SystemSecret.service_name.asc(), SystemSecret.key_name.asc())
            .all()
        )
        if secrets:
            lines.append("=== STATUS KONFIGURASI API & SECRETS (METADATA ONLY) ===")
            for s_key, s_service, s_active in secrets[:20]:
                status_label = "terkonfigurasi (Aktif)" if s_active else "nonaktif"
                lines.append(f"- {s_key} ({s_service}) — {status_label}")
            lines.append("")

        # Promos and pricing plans
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
