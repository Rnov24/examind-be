"""Tests for scoped chatbot tools (app/services/ai/chatbot_tools.py).

Key guarantees under test:
- execute_tool forwards ONLY declared parameters; identity args the LLM
  sends (user_id, tenant_id, role, ...) are dropped.
- Scoping is enforced server-side from the authenticated user: cross-user /
  cross-tenant access is denied even when the caller knows the target id.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.user import User
from app.models.academic import Class, ClassMember
from app.models.exam import Exam
from app.models.session import ExamSession, StudentAnswer
from app.models.question import Question, QuestionBank
from app.services.ai import chatbot_tools
from app.services.ai.chatbot_tools import execute_tool


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_user(session, uid, role, tenant_id=None):
    user = User(
        id=uid,
        identifier=f"U{uid}",
        email=f"user{uid}@test.sch.id",
        password_hash="fakehash",
        full_name=f"User {uid}",
        role=role,
        tenant_id=tenant_id,
        is_active=True,
        is_email_verified=True,
    )
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def world(db_session):
    """Two tenants; teacher_a owns class+exam; student_a is a member with a session."""
    teacher_a = _make_user(db_session, 1, "teacher", tenant_id=10)
    teacher_b = _make_user(db_session, 2, "teacher", tenant_id=20)
    student_a = _make_user(db_session, 3, "student", tenant_id=10)
    student_b = _make_user(db_session, 4, "student", tenant_id=20)
    admin_a = _make_user(db_session, 5, "admin", tenant_id=10)
    admin_b = _make_user(db_session, 6, "admin", tenant_id=20)

    cls = Class(id=1, name="XII RPL 1", grade_level="12", academic_year="2026/2027", created_by=teacher_a.id)
    db_session.add(cls)
    db_session.add(ClassMember(id=1, class_id=1, user_id=student_a.id, role="student"))

    now = datetime.utcnow()
    exam = Exam(
        id=1,
        teacher_id=teacher_a.id,
        class_id=1,
        title="Ujian Matematika Bab 1",
        duration_minutes=60,
        start_time=now - timedelta(days=1),
        end_time=now + timedelta(days=1),
        status="published",
    )
    db_session.add(exam)

    exam_session = ExamSession(
        id=1,
        exam_id=1,
        student_id=student_a.id,
        start_time=now - timedelta(hours=2),
        submit_time=now - timedelta(hours=1),
        status="graded",
        total_score=80,
    )
    db_session.add(exam_session)

    bank = QuestionBank(id=1, teacher_id=teacher_a.id, title="Bank Matematika", subject="Matematika")
    db_session.add(bank)
    db_session.add(Question(
        id=1,
        bank_id=1,
        prompt="2+2=?",
        question_type="multiple_choice",
    ))
    db_session.add(Question(
        id=2,
        bank_id=1,
        prompt="3+3=?",
        question_type="multiple_choice",
    ))
    db_session.add(StudentAnswer(id=1, session_id=1, question_id=1, is_correct=True))
    db_session.add(StudentAnswer(id=2, session_id=1, question_id=2, is_correct=False))
    db_session.commit()

    return {
        "teacher_a": teacher_a, "teacher_b": teacher_b,
        "student_a": student_a, "student_b": student_b,
        "admin_a": admin_a, "admin_b": admin_b,
    }


# --- execute_tool argument filtering ---------------------------------------

def test_execute_tool_drops_identity_and_undeclared_args(db_session, monkeypatch):
    captured = {}

    def spy(user, db, exam_id):
        captured["user"] = user
        captured["exam_id"] = exam_id
        return "spy-result"

    monkeypatch.setitem(chatbot_tools.TOOL_FUNCTIONS, "get_exam_detail", spy)
    user = _make_user(db_session, 99, "student")

    result = execute_tool(
        "get_exam_detail",
        user,
        db_session,
        {
            "exam_id": 5,
            "user_id": 12345,       # identity arg: must be dropped
            "tenant_id": 777,       # identity arg: must be dropped
            "role": "superadmin",   # identity arg: must be dropped
            "is_admin": True,       # undeclared + identity-like: dropped
            "random_junk": "x",     # undeclared: dropped
        },
    )

    assert result == "spy-result"
    assert captured["exam_id"] == 5
    assert captured["user"] is user  # identity came from the authenticated user, not args


def test_execute_tool_coerces_string_ids(db_session, monkeypatch):
    captured = {}

    def spy(user, db, exam_id):
        captured["exam_id"] = exam_id
        return "ok"

    monkeypatch.setitem(chatbot_tools.TOOL_FUNCTIONS, "get_exam_detail", spy)
    user = _make_user(db_session, 98, "teacher")
    execute_tool("get_exam_detail", user, db_session, {"exam_id": "42"})
    assert captured["exam_id"] == 42
    assert isinstance(captured["exam_id"], int)


def test_execute_tool_unknown_tool(db_session):
    user = _make_user(db_session, 97, "student")
    assert execute_tool("drop_all_tables", user, db_session, {}) == "Tool tidak dikenal."


def test_execute_tool_missing_required_arg(db_session):
    user = _make_user(db_session, 96, "student")
    result = execute_tool("get_exam_detail", user, db_session, {})
    assert "Argumen wajib" in result


# --- per-tool scoping -------------------------------------------------------

def test_get_my_grades_student_only(db_session, world):
    result = execute_tool("get_my_grades", world["teacher_a"], db_session, {})
    assert result == "Tool ini hanya untuk siswa."
    result = execute_tool("get_my_grades", world["student_a"], db_session, {})
    assert "Ujian Matematika Bab 1" in result
    assert "80" in result


def test_get_exam_detail_scoping(db_session, world):
    # Owner teacher: allowed
    assert "Ujian Matematika" in execute_tool(
        "get_exam_detail", world["teacher_a"], db_session, {"exam_id": 1})
    # Other tenant's teacher: denied
    assert execute_tool(
        "get_exam_detail", world["teacher_b"], db_session, {"exam_id": 1}
    ) == chatbot_tools._NO_ACCESS
    # Member student (published exam in their class): allowed
    assert "Ujian Matematika" in execute_tool(
        "get_exam_detail", world["student_a"], db_session, {"exam_id": 1})
    # Other tenant's student: denied
    assert execute_tool(
        "get_exam_detail", world["student_b"], db_session, {"exam_id": 1}
    ) == chatbot_tools._NO_ACCESS
    # Same-tenant admin: allowed; other-tenant admin: denied
    assert "Ujian Matematika" in execute_tool(
        "get_exam_detail", world["admin_a"], db_session, {"exam_id": 1})
    assert execute_tool(
        "get_exam_detail", world["admin_b"], db_session, {"exam_id": 1}
    ) == chatbot_tools._NO_ACCESS
    # LLM-supplied identity args cannot widen access
    assert execute_tool(
        "get_exam_detail", world["student_b"], db_session,
        {"exam_id": 1, "user_id": world["student_a"].id, "role": "superadmin"},
    ) == chatbot_tools._NO_ACCESS


def test_search_exams_scoping(db_session, world):
    assert "Ujian Matematika" in execute_tool(
        "search_exams", world["teacher_a"], db_session, {"keyword": "Matematika"})
    assert "Tidak ada ujian" in execute_tool(
        "search_exams", world["teacher_b"], db_session, {"keyword": "Matematika"})
    assert "Tidak ada ujian" in execute_tool(
        "search_exams", world["student_b"], db_session, {"keyword": "Matematika"})


def test_get_class_info_scoping(db_session, world):
    assert "XII RPL 1" in execute_tool(
        "get_class_info", world["teacher_a"], db_session, {"class_id": 1})
    assert "XII RPL 1" in execute_tool(
        "get_class_info", world["student_a"], db_session, {"class_id": 1})
    assert execute_tool(
        "get_class_info", world["teacher_b"], db_session, {"class_id": 1}
    ) == chatbot_tools._NO_ACCESS
    assert execute_tool(
        "get_class_info", world["student_b"], db_session, {"class_id": 1}
    ) == chatbot_tools._NO_ACCESS


def test_get_session_result_scoping_and_counts(db_session, world):
    result = execute_tool(
        "get_session_result", world["student_a"], db_session, {"session_id": 1})
    assert "Jawaban benar: 1 dari 2" in result
    # Another student must not see it
    assert execute_tool(
        "get_session_result", world["student_b"], db_session, {"session_id": 1}
    ) == chatbot_tools._NO_ACCESS
    # Owning teacher can
    assert "Jawaban benar: 1 dari 2" in execute_tool(
        "get_session_result", world["teacher_a"], db_session, {"session_id": 1})
    # Other teacher cannot
    assert execute_tool(
        "get_session_result", world["teacher_b"], db_session, {"session_id": 1}
    ) == chatbot_tools._NO_ACCESS
