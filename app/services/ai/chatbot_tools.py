"""Scoped function-calling tools for the EXAMIND AI chatbot.

The LLM may call these tools to fetch SPECIFIC data on demand (beyond the fixed
scoped context setlist), but every tool enforces scoping SERVER-SIDE from the
authenticated user object. The LLM only ever supplies lookup arguments
(exam_id, class_id, session_id, keyword) — never user_id, tenant_id, or role.

Security contract:
- Identity ALWAYS comes from the `user` argument (the authenticated principal
  resolved from the JWT by the endpoint), never from tool arguments.
- execute_tool() drops any argument that is not a declared parameter of the
  tool, and logs a warning when identity-like keys appear (prompt-injection
  probe indicator).
- All tools are read-only.
"""
import logging
from typing import Dict, Any, List, Optional

from sqlalchemy import func, or_

from app.models.user import User
from app.models.academic import Class, ClassMember
from app.models.exam import Exam, ExamQuestion
from app.models.session import ExamSession, StudentAnswer

logger = logging.getLogger(__name__)

# Keys that must never be honored from LLM-supplied arguments. If the model
# sends any of these, it is either confused or being prompt-injected.
IDENTITY_ARG_KEYS = {
    "user_id", "tenant_id", "role", "student_id", "teacher_id",
    "admin_id", "current_user", "user", "is_admin", "is_superadmin",
}

_NO_ACCESS = "Anda tidak memiliki akses ke data ini."


# ---------------------------------------------------------------------------
# Scoping helpers (server-side only; identity comes from the `user` object)
# ---------------------------------------------------------------------------

def _tenant_teacher_ids(db, tenant_id: Optional[int]):
    """Subquery of teacher user ids belonging to a tenant."""
    return db.query(User.id).filter(User.tenant_id == tenant_id, User.role == "teacher")


def _tenant_student_ids(db, tenant_id: Optional[int]):
    """Subquery of student user ids belonging to a tenant."""
    return db.query(User.id).filter(User.tenant_id == tenant_id, User.role == "student")


def _student_can_view_exam(user: User, db, exam: Exam) -> bool:
    """Student sees an exam if they have a session in it, or it is visible
    (published / in progress / completed) for a class they belong to."""
    has_session = (
        db.query(ExamSession.id)
        .filter(ExamSession.exam_id == exam.id, ExamSession.student_id == user.id)
        .first()
        is not None
    )
    if has_session:
        return True
    if exam.status in ("published", "in_progress", "completed"):
        is_member = (
            db.query(ClassMember.id)
            .filter(ClassMember.class_id == exam.class_id, ClassMember.user_id == user.id)
            .first()
            is not None
        )
        return is_member
    return False


def _can_view_exam(user: User, db, exam: Exam) -> bool:
    role = (user.role or "").lower()
    if role == "superadmin":
        return True
    if role == "teacher":
        return exam.teacher_id == user.id
    if role == "admin":
        if not user.tenant_id:
            return False
        teacher = db.query(User).filter(User.id == exam.teacher_id).first()
        return bool(teacher and teacher.tenant_id == user.tenant_id)
    if role == "student":
        return _student_can_view_exam(user, db, exam)
    return False


def _fmt_dt(dt) -> str:
    if dt is None:
        return "-"
    try:
        return dt.strftime("%d %b %Y %H:%M")
    except Exception:
        return str(dt)


# ---------------------------------------------------------------------------
# Tool implementations: tool_*(user, db, <lookup args>) -> str
# ---------------------------------------------------------------------------

def tool_get_my_grades(user: User, db) -> str:
    """Student only: all graded/submitted sessions with exam title, score, date."""
    if (user.role or "").lower() != "student":
        return "Tool ini hanya untuk siswa."
    sessions = (
        db.query(ExamSession)
        .filter(
            ExamSession.student_id == user.id,
            ExamSession.status.in_(["graded", "submitted"]),
        )
        .order_by(ExamSession.submit_time.desc(), ExamSession.start_time.desc())
        .limit(50)
        .all()
    )
    if not sessions:
        return "Belum ada ujian yang selesai dikerjakan atau dinilai."
    lines = ["Daftar nilai ujian Anda:"]
    for s in sessions:
        title = s.exam.title if s.exam else "Ujian"
        score = float(s.total_score) if s.total_score is not None else 0.0
        when = s.submit_time or s.start_time
        lines.append(f"- {title} | Skor: {score:g} | Status: {s.status} | Tanggal: {_fmt_dt(when)}")
    return "\n".join(lines)


def tool_get_exam_detail(user: User, db, exam_id: int) -> str:
    """Exam detail, only if the exam is inside the caller's scope."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if exam is None:
        return "Ujian tidak ditemukan."
    if not _can_view_exam(user, db, exam):
        return _NO_ACCESS
    question_count = (
        db.query(func.count(ExamQuestion.id)).filter(ExamQuestion.exam_id == exam.id).scalar() or 0
    )
    class_name = exam.class_.name if exam.class_ else "-"
    return (
        f"Detail ujian [ID {exam.id}]:\n"
        f"- Judul: {exam.title}\n"
        f"- Status: {exam.status}\n"
        f"- Kelas: {class_name}\n"
        f"- Jumlah soal: {question_count}\n"
        f"- Durasi: {exam.duration_minutes} menit\n"
        f"- Jadwal: {_fmt_dt(exam.start_time)} s/d {_fmt_dt(exam.end_time)}"
    )


def tool_search_exams(user: User, db, keyword: str) -> str:
    """Search exam titles within the caller's scope. Max 10 results."""
    kw = (keyword or "").strip()
    if not kw:
        return "Kata kunci pencarian kosong."
    role = (user.role or "").lower()
    query = db.query(Exam).filter(Exam.title.ilike(f"%{kw}%"))

    if role == "superadmin":
        pass  # no extra filter
    elif role == "teacher":
        query = query.filter(Exam.teacher_id == user.id)
    elif role == "admin":
        if not user.tenant_id:
            return _NO_ACCESS
        query = query.filter(Exam.teacher_id.in_(_tenant_teacher_ids(db, user.tenant_id)))
    elif role == "student":
        class_ids = db.query(ClassMember.class_id).filter(ClassMember.user_id == user.id)
        session_exam_ids = db.query(ExamSession.exam_id).filter(ExamSession.student_id == user.id)
        query = query.filter(
            or_(
                Exam.id.in_(session_exam_ids),
                (Exam.class_id.in_(class_ids))
                & (Exam.status.in_(["published", "in_progress", "completed"])),
            )
        )
    else:
        return _NO_ACCESS

    exams = query.order_by(Exam.created_at.desc()).limit(10).all()
    if not exams:
        return f"Tidak ada ujian yang cocok dengan kata kunci '{kw}' dalam ruang lingkup Anda."
    lines = [f"Hasil pencarian ujian untuk '{kw}':"]
    for e in exams:
        lines.append(f"- [ID {e.id}] {e.title} | Status: {e.status}")
    return "\n".join(lines)


def tool_get_class_info(user: User, db, class_id: int) -> str:
    """Class info, only if the class is inside the caller's scope."""
    cls = db.query(Class).filter(Class.id == class_id).first()
    if cls is None:
        return "Kelas tidak ditemukan."
    role = (user.role or "").lower()
    allowed = False
    if role == "superadmin":
        allowed = True
    elif role == "teacher":
        allowed = cls.created_by == user.id
    elif role == "admin":
        if user.tenant_id:
            creator = db.query(User).filter(User.id == cls.created_by).first()
            allowed = bool(creator and creator.tenant_id == user.tenant_id)
    elif role == "student":
        allowed = (
            db.query(ClassMember.id)
            .filter(ClassMember.class_id == cls.id, ClassMember.user_id == user.id)
            .first()
            is not None
        )
    if not allowed:
        return _NO_ACCESS
    member_count = (
        db.query(func.count(ClassMember.id)).filter(ClassMember.class_id == cls.id).scalar() or 0
    )
    exam_count = db.query(func.count(Exam.id)).filter(Exam.class_id == cls.id).scalar() or 0
    return (
        f"Info kelas [ID {cls.id}]:\n"
        f"- Nama: {cls.name}\n"
        f"- Jenjang: {cls.grade_level}\n"
        f"- Jumlah anggota: {member_count}\n"
        f"- Jumlah ujian: {exam_count}"
    )


def tool_get_session_result(user: User, db, session_id: int) -> str:
    """Session result summary (counts only, never full answer text)."""
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if session is None:
        return "Sesi ujian tidak ditemukan."
    role = (user.role or "").lower()
    exam = session.exam
    allowed = False
    if role == "superadmin":
        allowed = True
    elif role == "student":
        allowed = session.student_id == user.id
    elif role == "teacher":
        allowed = bool(exam and exam.teacher_id == user.id)
    elif role == "admin":
        if user.tenant_id:
            if exam is not None:
                teacher = db.query(User).filter(User.id == exam.teacher_id).first()
                allowed = bool(teacher and teacher.tenant_id == user.tenant_id)
            if not allowed:
                student = db.query(User).filter(User.id == session.student_id).first()
                allowed = bool(student and student.tenant_id == user.tenant_id)
    if not allowed:
        return _NO_ACCESS

    total_answers = (
        db.query(func.count(StudentAnswer.id))
        .filter(StudentAnswer.session_id == session.id)
        .scalar()
        or 0
    )
    correct_answers = (
        db.query(func.count(StudentAnswer.id))
        .filter(StudentAnswer.session_id == session.id, StudentAnswer.is_correct == True)  # noqa: E712
        .scalar()
        or 0
    )
    score = float(session.total_score) if session.total_score is not None else 0.0
    title = exam.title if exam else "Ujian"
    student_name = session.student.full_name if session.student else "-"
    lines = [
        f"Hasil sesi ujian [ID {session.id}]:",
        f"- Ujian: {title}",
    ]
    if role != "student":
        lines.append(f"- Siswa: {student_name}")
    lines += [
        f"- Skor total: {score:g}",
        f"- Status: {session.status}",
        f"- Jawaban benar: {correct_answers} dari {total_answers} soal terjawab",
        f"- Tanggal: {_fmt_dt(session.submit_time or session.start_time)}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool registry + provider definitions
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS: Dict[str, Any] = {
    "get_my_grades": tool_get_my_grades,
    "get_exam_detail": tool_get_exam_detail,
    "search_exams": tool_search_exams,
    "get_class_info": tool_get_class_info,
    "get_session_result": tool_get_session_result,
}

_TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "get_my_grades",
        "description": (
            "Mengambil daftar nilai ujian milik siswa yang sedang login "
            "(ujian yang sudah selesai/dinilai, beserta skor dan tanggal). "
            "Hanya untuk pengguna ber-role siswa. Tidak butuh argumen."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_exam_detail",
        "description": (
            "Mengambil detail satu ujian (judul, status, jumlah soal, jadwal) "
            "berdasarkan exam_id. Hanya berhasil jika ujian berada dalam ruang "
            "lingkup akses pengguna yang login."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exam_id": {"type": "integer", "description": "ID ujian yang ingin dilihat detailnya."},
            },
            "required": ["exam_id"],
        },
    },
    {
        "name": "search_exams",
        "description": (
            "Mencari ujian berdasarkan kata kunci pada judul, terbatas pada "
            "ruang lingkup akses pengguna yang login. Maksimal 10 hasil."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Kata kunci pada judul ujian."},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_class_info",
        "description": (
            "Mengambil info satu kelas (nama, jenjang, jumlah anggota) "
            "berdasarkan class_id. Hanya berhasil jika kelas berada dalam "
            "ruang lingkup akses pengguna yang login."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "class_id": {"type": "integer", "description": "ID kelas yang ingin dilihat infonya."},
            },
            "required": ["class_id"],
        },
    },
    {
        "name": "get_session_result",
        "description": (
            "Mengambil ringkasan hasil satu sesi ujian (skor, status, jumlah "
            "jawaban benar dari total soal) berdasarkan session_id. Hanya "
            "berhasil jika sesi berada dalam ruang lingkup akses pengguna."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "integer", "description": "ID sesi ujian yang ingin dilihat hasilnya."},
            },
            "required": ["session_id"],
        },
    },
]

# Gemini REST API function_declarations format.
TOOL_DEFINITIONS_GEMINI: List[Dict[str, Any]] = [dict(spec) for spec in _TOOL_SPECS]

# OpenAI-compatible tools format.
TOOL_DEFINITIONS_OPENAI: List[Dict[str, Any]] = [
    {"type": "function", "function": dict(spec)} for spec in _TOOL_SPECS
]

# Declared parameter names per tool (the ONLY args execute_tool will forward).
TOOL_PARAMETERS: Dict[str, List[str]] = {
    spec["name"]: list(spec["parameters"].get("properties", {}).keys()) for spec in _TOOL_SPECS
}

_INT_PARAMS = {"exam_id", "class_id", "session_id"}


def execute_tool(name: str, user: User, db, args: Optional[Dict[str, Any]] = None) -> str:
    """Executes a chatbot tool with strict argument filtering.

    - Unknown tool names are rejected.
    - Only the tool's declared parameters are forwarded; everything else the
      LLM sends is dropped. Identity-like keys (user_id, tenant_id, role, ...)
      trigger a warning log because they indicate a prompt-injection probe —
      identity ALWAYS comes from the authenticated `user` object.
    - Any exception is caught and turned into a safe error string.
    """
    fn = TOOL_FUNCTIONS.get(name or "")
    if fn is None:
        logger.warning(f"[ChatbotTools] unknown tool requested: {name!r}")
        return "Tool tidak dikenal."

    raw_args = dict(args or {})
    suspicious = [k for k in raw_args if k in IDENTITY_ARG_KEYS]
    if suspicious:
        logger.warning(
            f"[ChatbotTools] tool={name} user_id={getattr(user, 'id', '?')} "
            f"sent identity args {suspicious} (possible prompt-injection probe); ignoring them"
        )

    allowed = TOOL_PARAMETERS.get(name, [])
    clean_args: Dict[str, Any] = {}
    for key in allowed:
        if key in raw_args and raw_args[key] is not None:
            value = raw_args[key]
            if key in _INT_PARAMS:
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    return f"Argumen {key} harus berupa angka."
            clean_args[key] = value

    missing = [k for k in _required_params(name) if k not in clean_args]
    if missing:
        return f"Argumen wajib belum lengkap: {', '.join(missing)}."

    dropped = [k for k in raw_args if k not in clean_args]
    if dropped:
        logger.info(f"[ChatbotTools] tool={name} dropped undeclared args: {dropped}")

    try:
        return fn(user, db, **clean_args)
    except Exception as e:
        logger.warning(f"[ChatbotTools] tool={name} failed for user_id={getattr(user, 'id', '?')}: {e}")
        return "Maaf, data tidak dapat diambil saat ini. Silakan coba lagi."


def _required_params(name: str) -> List[str]:
    for spec in _TOOL_SPECS:
        if spec["name"] == name:
            return list(spec["parameters"].get("required", []))
    return []
