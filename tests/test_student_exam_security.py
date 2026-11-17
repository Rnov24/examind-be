"""Student exam security — Blockers 1, 3, 5.

Blocker 1: POST /student/exam/{id}/start must never leak the answer key
(is_correct / rationale / correct_answer / explanation) to the student,
whatever the exam's randomize flags are. The graded result review keeps
per-question correctness by design.
Blocker 5: start / begin / resume past the exam window must 400 instead
of returning 200 with a 0-second clock.
Blocker 3: GET /student/exam/{id}/result must serve the exam-owning
teacher and same-tenant admin (via ?session_id=), keep cross-tenant /
non-owner callers out, and leave the student's own result untouched.

Fixture style mirrors tests/test_exam_modes.py: in-memory SQLite, real
JWTs, ONLY get_db overridden.

Run: .venv/bin/python -m pytest tests/test_student_exam_security.py -v
"""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.models.academic import Class, ClassMember
from app.models.exam import Exam, ExamQuestion
from app.models.question import Question, QuestionBank
from app.models.session import ExamSession, StudentAnswer
from app.models.tenant import Tenant
from app.models.user import User

LEAK_KEYS = ["is_correct", "rationale", "correct_answer", "explanation"]


def _user(uid, identifier, email, role, tenant_id, name):
    return User(
        id=uid,
        identifier=identifier,
        email=email,
        password_hash="fakehash",
        full_name=name,
        role=role,
        tenant_id=tenant_id,
        is_active=True,
        is_email_verified=True,
    )


def assert_no_key_leak(payload):
    blob = json.dumps(payload)
    for key in LEAK_KEYS:
        assert key not in blob, f"answer-key field {key!r} leaked into student payload"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    now = datetime.now()
    db.add_all([
        Tenant(id=1, name="Sekolah A", code="SCH-A"),
        Tenant(id=2, name="Sekolah B", code="SCH-B"),
        _user(4, "TCH-A", "guru-a@sch-a.id", "teacher", 1, "Guru A"),
        _user(6, "SIS-A1", "siswa-a1@sch-a.id", "student", 1, "Siswa A1"),
        _user(7, "SIS-A2", "siswa-a2@sch-a.id", "student", 1, "Siswa A2"),
        _user(8, "TCH-B", "guru-b@sch-a.id", "teacher", 1, "Guru B"),
        _user(9, "ADM-A", "admin-a@sch-a.id", "admin", 1, "Admin A"),
        _user(10, "ADM-B", "admin-b@sch-b.id", "admin", 2, "Admin B"),
        _user(11, "TCH-C", "guru-c@sch-b.id", "teacher", 2, "Guru C"),
    ])
    db.add_all([
        Class(id=1, name="Kelas A", grade_level="10", academic_year="2025/2026", created_by=4),
        ClassMember(class_id=1, user_id=6, role="student"),
        ClassMember(class_id=1, user_id=7, role="student"),
        QuestionBank(id=1, teacher_id=4, title="Bank A", subject="Matematika"),
        # Options deliberately carry the key material a leak would expose.
        Question(id=1, bank_id=1, question_type="multiple_choice", prompt="Berapakah 2+2?",
                 options_json=[
                     {"id": "A", "text": "3", "is_correct": False, "rationale": "3 itu kurang satu."},
                     {"id": "B", "text": "4", "is_correct": True, "rationale": "2 tambah 2 sama dengan 4."},
                 ],
                 correct_answer="B", explanation="Penjumlahan dasar."),
        Question(id=2, bank_id=1, question_type="multiple_choice", prompt="Ibukota Indonesia?",
                 options_json=[
                     {"id": "A", "text": "Jakarta", "is_correct": True, "rationale": "Ibukota sejak lama."},
                     {"id": "B", "text": "Bandung", "is_correct": False, "rationale": "Bandung bukan ibukota."},
                     {"id": "C", "text": "Surabaya", "is_correct": False, "rationale": "Surabaya bukan ibukota."},
                 ],
                 correct_answer="A", explanation="Pengetahuan umum."),
        Question(id=3, bank_id=1, question_type="long_essay", prompt="Jelaskan fotosintesis.",
                 options_json=None,
                 correct_answer="Jawaban ideal esai.",
                 explanation="Rubrik esai."),
    ])
    db.add_all([
        # 1: LIVE, window open, shuffling OFF — the leak case: the randomizer
        # only strips the key when randomize_options is on.
        Exam(id=1, teacher_id=4, class_id=1, title="Tanpa Acak",
             duration_minutes=60, start_time=now - timedelta(hours=1),
             end_time=now + timedelta(hours=2), status="published",
             exam_mode="live", randomize_questions=False, randomize_options=False),
        # 2: LIVE, window open, shuffling ON.
        Exam(id=2, teacher_id=4, class_id=1, title="Dengan Acak",
             duration_minutes=60, start_time=now - timedelta(hours=1),
             end_time=now + timedelta(hours=2), status="published",
             exam_mode="live", randomize_questions=True, randomize_options=True),
        # 3: LIVE, window EXPIRED, student 6 has an in_progress session
        # (began 2h ago) — the resume-past-window hole.
        Exam(id=3, teacher_id=4, class_id=1, title="Sudah Tutup",
             duration_minutes=60, start_time=now - timedelta(hours=3),
             end_time=now - timedelta(hours=1), status="published",
             exam_mode="live"),
        # 4: LIVE, window EXPIRED, no session yet (guard path).
        Exam(id=4, teacher_id=4, class_id=1, title="Tutup Tanpa Sesi",
             duration_minutes=60, start_time=now - timedelta(hours=3),
             end_time=now - timedelta(hours=1), status="published",
             exam_mode="live"),
        # 5: NON-LIVE, window open, student 6 mid-exam (began 50 min ago).
        Exam(id=5, teacher_id=4, class_id=1, title="Mandiri Jalan",
             duration_minutes=60, start_time=now - timedelta(hours=1),
             end_time=now + timedelta(hours=2), status="published",
             exam_mode="non_live"),
        # 6: LIVE, window open, student 6 GRADED (review fixture).
        Exam(id=6, teacher_id=4, class_id=1, title="Sudah Dinilai",
             duration_minutes=60, start_time=now - timedelta(hours=1),
             end_time=now + timedelta(hours=2), status="published",
             exam_mode="live"),
        # 7: LIVE, window open, policy instant, student 6 IN_PROGRESS.
        Exam(id=7, teacher_id=4, class_id=1, title="Instan Jalan",
             duration_minutes=60, start_time=now - timedelta(hours=1),
             end_time=now + timedelta(hours=2), status="published",
             exam_mode="live", explanation_policy="instant"),
        # 8: LIVE, window open, student 6 IN_PROGRESS (PDF gate fixture).
        Exam(id=8, teacher_id=4, class_id=1, title="PDF Jalan",
             duration_minutes=60, start_time=now - timedelta(hours=1),
             end_time=now + timedelta(hours=2), status="published",
             exam_mode="live"),
        # 9: LIVE, window open, student 6 GRADING_IN_PROGRESS with
        # already-stored instant MCQ scores (Finding 3 fixture: the
        # submit path writes is_correct / auto_score / final_score
        # before the async essay grading finishes).
        Exam(id=9, teacher_id=4, class_id=1, title="Sedang Dinilai",
             duration_minutes=60, start_time=now - timedelta(hours=1),
             end_time=now + timedelta(hours=2), status="published",
             exam_mode="live"),
    ])
    for exam_id in (1, 2, 5, 6, 7, 8, 9):
        db.add_all([
            ExamQuestion(exam_id=exam_id, question_id=1, order_index=1, allocated_points=10),
            ExamQuestion(exam_id=exam_id, question_id=2, order_index=2, allocated_points=10),
            ExamQuestion(exam_id=exam_id, question_id=3, order_index=3, allocated_points=10),
        ])
    db.add_all([
        ExamSession(id=30, exam_id=3, student_id=6,
                    start_time=now - timedelta(hours=2),
                    begun_at=now - timedelta(hours=2),
                    status="in_progress", total_score=0.0, integrity_score=100,
                    pairing_token="tok-30"),
        ExamSession(id=50, exam_id=5, student_id=6,
                    start_time=now - timedelta(minutes=50),
                    begun_at=now - timedelta(minutes=50),
                    status="in_progress", total_score=0.0, integrity_score=100,
                    pairing_token="tok-50"),
        ExamSession(id=60, exam_id=6, student_id=6,
                    start_time=now - timedelta(hours=2),
                    begun_at=now - timedelta(hours=2),
                    submit_time=now - timedelta(minutes=10),
                    status="graded", total_score=20.0, integrity_score=100,
                    pairing_token="tok-60"),
        ExamSession(id=61, exam_id=6, student_id=7,
                    start_time=now - timedelta(minutes=30),
                    begun_at=now - timedelta(minutes=30),
                    status="in_progress", total_score=0.0, integrity_score=100,
                    pairing_token="tok-61"),
        ExamSession(id=70, exam_id=7, student_id=6,
                    start_time=now - timedelta(minutes=30),
                    begun_at=now - timedelta(minutes=30),
                    status="in_progress", total_score=0.0, integrity_score=100,
                    pairing_token="tok-70"),
        ExamSession(id=80, exam_id=8, student_id=6,
                    start_time=now - timedelta(minutes=30),
                    begun_at=now - timedelta(minutes=30),
                    status="in_progress", total_score=0.0, integrity_score=100,
                    pairing_token="tok-80"),
        ExamSession(id=90, exam_id=9, student_id=6,
                    start_time=now - timedelta(minutes=30),
                    begun_at=now - timedelta(minutes=30),
                    submit_time=now - timedelta(minutes=5),
                    status="grading_in_progress", total_score=10.0,
                    integrity_score=100, pairing_token="tok-90"),
        StudentAnswer(session_id=90, question_id=1, student_response="B",
                      is_correct=True, auto_score=10, final_score=10),
        StudentAnswer(session_id=90, question_id=2, student_response="B",
                      is_correct=False, auto_score=0, final_score=0),
        # Essay with a teacher override already entered mid-grading.
        StudentAnswer(session_id=90, question_id=3,
                      student_response="Fotosintesis adalah proses tumbuhan.",
                      is_correct=None, auto_score=0, final_score=7,
                      teacher_override_score=7,
                      ai_confidence_level="high",
                      ai_explanation="Penjelasan esai."),
        StudentAnswer(session_id=60, question_id=1, student_response="B",
                      is_correct=True, auto_score=10, final_score=10),
        StudentAnswer(session_id=60, question_id=2, student_response="B",
                      is_correct=False, auto_score=0, final_score=0),
        StudentAnswer(session_id=60, question_id=3, student_response="Fotosintesis adalah proses tumbuhan.",
                      is_correct=None, auto_score=0, final_score=10,
                      ai_confidence_level="high",
                      ai_explanation="Penjelasan esai."),
    ])
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def _auth(user_id: int):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user_id)})}"}


@pytest.fixture
def client(db_session):
    return TestClient(app, raise_server_exceptions=False)


def _questions_by_id(resp):
    return {q["id"]: q for q in resp.json()["data"]["questions"]}


# --- Blocker 1: answer key must never reach the student pre-grading -------

def test_start_strips_key_when_shuffling_off(client):
    # Exam 1 has randomize_options=False: the old code returned the raw
    # options_json (with is_correct + rationale) verbatim.
    resp = client.post("/api/v1/student/exam/1/start", headers=_auth(7))
    assert resp.status_code == 200
    assert_no_key_leak(resp.json())
    q1 = _questions_by_id(resp).get(1)
    assert q1 is not None
    # Only id + text survive, in original order (no shuffle).
    assert q1["options_json"] == [{"id": "A", "text": "3"}, {"id": "B", "text": "4"}]


def test_start_strips_key_when_shuffling_on(client):
    resp = client.post("/api/v1/student/exam/2/start", headers=_auth(7))
    assert resp.status_code == 200
    assert_no_key_leak(resp.json())
    q1 = _questions_by_id(resp).get(1)
    assert q1 is not None
    assert sorted(o["id"] for o in q1["options_json"]) == ["A", "B"]
    for opt in q1["options_json"]:
        assert set(opt.keys()) == {"id", "text"}


def test_start_still_serves_render_data(client):
    # The workspace renders from id/text/points/prompt; none of that may
    # be lost by the strip.
    resp = client.post("/api/v1/student/exam/1/start", headers=_auth(7))
    qs = _questions_by_id(resp)
    assert qs[1]["prompt"] == "Berapakah 2+2?"
    assert qs[1]["question_type"] == "multiple_choice"
    assert qs[1]["points"] == 10.0
    assert qs[3]["question_type"] == "long_essay"
    assert qs[3]["options_json"] is None


def test_autosave_response_carries_no_key(client):
    resp = client.post("/api/v1/student/exam/1/start", headers=_auth(7))
    session_id = resp.json()["data"]["session_id"]
    resp = client.post(
        "/api/v1/student/exam/1/autosave",
        headers=_auth(7),
        json={"session_id": session_id,
              "answers": [{"question_id": 1, "response": "B"}]},
    )
    assert resp.status_code == 200
    assert_no_key_leak(resp.json())
    assert resp.json()["data"]["saved_items_count"] == 1


def test_graded_result_keeps_per_question_correctness(client):
    # Post-grading review is the intended feature: correctness, the key
    # and the rationales stay visible on a GRADED session.
    resp = client.get("/api/v1/student/exam/6/result", headers=_auth(6))
    assert resp.status_code == 200
    answers = {a["question_id"]: a for a in resp.json()["data"]["answers"]}
    assert answers[1]["is_correct"] is True
    assert answers[1]["correct_answer"] == "B"
    assert answers[2]["is_correct"] is False
    assert answers[2]["correct_answer"] == "A"
    # Full option key is part of the review payload here, by design.
    assert any(o.get("is_correct") is True
               for o in answers[1]["options_json"])
    assert answers[3]["ai_explanation"] == "Penjelasan esai."


def test_result_hides_key_before_grading_even_with_instant_policy(client):
    # Old code: policy "instant" exposed options_json + correct_answer for
    # ANY status, so a mid-exam student could fetch /result and read the
    # whole key. Session 70 is in_progress on an instant-policy exam.
    resp = client.get("/api/v1/student/exam/7/result", headers=_auth(6))
    assert resp.status_code == 200
    for ans in resp.json()["data"]["answers"]:
        assert ans["options_json"] is None
        assert ans["correct_answer"] is None
        assert ans["is_correct"] is None


def test_grading_in_progress_result_hides_correctness(client):
    # Finding 3: session 90 is grading_in_progress with instant MCQ
    # scores already stored (Q1 correct 10/10, Q2 wrong 0/0, essay
    # override 7). A student polling /result mid-grading must see NO
    # per-question correctness — null, not 0 — for every answer.
    resp = client.get("/api/v1/student/exam/9/result", headers=_auth(6))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "grading_in_progress"
    answers = {a["question_id"]: a for a in data["answers"]}
    assert len(answers) == 3
    for qid, ans in answers.items():
        assert ans["is_correct"] is None, f"Q{qid} leaked is_correct"
        assert ans["auto_score"] is None, f"Q{qid} leaked auto_score"
        assert ans["final_score"] is None, f"Q{qid} leaked final_score"
        assert ans["teacher_override_score"] is None, f"Q{qid} leaked override"
        assert ans["correct_answer"] is None
        assert ans["options_json"] is None
    # The student's own responses are theirs; they stay visible.
    assert answers[1]["student_response"] == "B"
    assert answers[3]["student_response"].startswith("Fotosintesis")
    # Same gate for every role: the admin and the exam-owning teacher
    # read through the same get_exam_result function.
    for user_id in (9, 4):
        resp = client.get("/api/v1/student/exam/9/result?session_id=90",
                          headers=_auth(user_id))
        assert resp.status_code == 200
        for ans in resp.json()["data"]["answers"]:
            assert ans["is_correct"] is None
            assert ans["auto_score"] is None
            assert ans["final_score"] is None
            assert ans["teacher_override_score"] is None


def test_graded_result_reveals_correctness_after_flip(client, db_session):
    # Flip the SAME session 90 to graded: the identical payload must
    # now carry the real per-question values, exactly as stored.
    db_session.query(ExamSession).filter(ExamSession.id == 90).update(
        {"status": "graded"})
    db_session.commit()
    resp = client.get("/api/v1/student/exam/9/result", headers=_auth(6))
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "graded"
    answers = {a["question_id"]: a for a in resp.json()["data"]["answers"]}
    assert answers[1]["is_correct"] is True
    assert answers[1]["auto_score"] == 10.0
    assert answers[1]["final_score"] == 10.0
    assert answers[2]["is_correct"] is False
    assert answers[2]["auto_score"] == 0.0
    assert answers[2]["final_score"] == 0.0
    assert answers[3]["teacher_override_score"] == 7.0
    assert answers[3]["final_score"] == 7.0
    assert answers[1]["correct_answer"] == "B"


def test_in_progress_own_result_hides_key(client):
    # Student 7 has an in_progress session (61) on exam 6: their own result
    # view must not show the key either (default after_exam_closed policy).
    resp = client.get("/api/v1/student/exam/6/result", headers=_auth(7))
    assert resp.status_code == 200
    assert resp.json()["data"]["session_id"] == 61
    for ans in resp.json()["data"]["answers"]:
        assert ans["options_json"] is None
        assert ans["correct_answer"] is None


def test_pdf_export_blocked_mid_exam_and_allowed_after_grading(client):
    # The transcript PDF prints a "Kunci / Jawaban Benar" column, so the
    # student export must not serve it while the exam is still running.
    resp = client.get("/api/v1/student/exam/8/export/pdf", headers=_auth(6))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RESULT_NOT_READY"
    resp = client.get("/api/v1/student/exam/6/export/pdf", headers=_auth(6))
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]


# --- Blocker 5: expired exams must 400, not 200 with a 0s clock ----------

def test_expired_resume_start_returns_400(client):
    # Session 30 began 2h ago on exam 3 (ended 1h ago): the old resume
    # path bypassed the window gate and returned 200 with 0s remaining.
    resp = client.post("/api/v1/student/exam/3/start", headers=_auth(6))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EXAM_ENDED"


def test_expired_begin_returns_400(client):
    resp = client.post("/api/v1/student/exam/3/begin", headers=_auth(6))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EXAM_ENDED"


def test_expired_fresh_start_returns_400(client):
    # No session yet: the guard already rejected this; it must stay 400.
    resp = client.post("/api/v1/student/exam/4/start", headers=_auth(6))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EXAM_ENDED"


def test_resume_inside_window_returns_200(client):
    # Session 50 began 50 min ago on non-live exam 5 (ends in 2h): resume
    # must keep working with ~600s left (duration remainder).
    resp = client.post("/api/v1/student/exam/5/start", headers=_auth(6))
    assert resp.status_code == 200
    remaining = resp.json()["data"]["duration_remaining_seconds"]
    assert 540 <= remaining <= 600


def test_begin_inside_window_returns_200(client):
    resp = client.post("/api/v1/student/exam/5/begin", headers=_auth(6))
    assert resp.status_code == 200
    remaining = resp.json()["data"]["duration_remaining_seconds"]
    assert 540 <= remaining <= 600


def test_start_inside_window_returns_200(client):
    # Fresh non-live start mid-window, and fresh live start (exam 1).
    resp = client.post("/api/v1/student/exam/5/start", headers=_auth(7))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["exam"]["exam_mode"] == "non_live"
    assert data["duration_remaining_seconds"] == 3600
    resp = client.post("/api/v1/student/exam/1/start", headers=_auth(7))
    assert resp.status_code == 200
    assert resp.json()["data"]["duration_remaining_seconds"] == 3600


# --- Blocker 3: result page for admin and the exam-owning teacher --------

def test_admin_can_view_student_result(client):
    resp = client.get("/api/v1/student/exam/6/result?session_id=60",
                      headers=_auth(9))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"] == 60
    # The sheet is the SESSION's student, not the admin opening it.
    assert data["student_name"] == "Siswa A1"
    assert data["student_identifier"] == "SIS-A1"


def test_owner_teacher_can_view_student_result(client):
    resp = client.get("/api/v1/student/exam/6/result?session_id=60",
                      headers=_auth(4))
    assert resp.status_code == 200
    assert resp.json()["data"]["session_id"] == 60
    assert resp.json()["data"]["student_name"] == "Siswa A1"


def test_other_tenant_admin_gets_404_on_result(client):
    resp = client.get("/api/v1/student/exam/6/result?session_id=60",
                      headers=_auth(10))
    assert resp.status_code == 404


def test_non_owner_teacher_gets_404_on_result(client):
    # Guru B is same-tenant but does not own exam 6; Guru C is other-tenant.
    for teacher_id in (8, 11):
        resp = client.get("/api/v1/student/exam/6/result?session_id=60",
                          headers=_auth(teacher_id))
        assert resp.status_code == 404


def test_admin_without_session_id_gets_400(client):
    resp = client.get("/api/v1/student/exam/6/result", headers=_auth(9))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SESSION_ID_REQUIRED"


def test_student_result_ignores_foreign_session_param(client):
    # Student 6 passes student 7's session id: they must still only see
    # their OWN result, never someone else's.
    resp = client.get("/api/v1/student/exam/6/result?session_id=61",
                      headers=_auth(6))
    assert resp.status_code == 200
    assert resp.json()["data"]["session_id"] == 60
    assert resp.json()["data"]["student_name"] == "Siswa A1"


def test_student_without_session_gets_404(client, db_session):
    # Student 7 has no session on exam 7 at all.
    resp = client.get("/api/v1/student/exam/7/result", headers=_auth(7))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RESULT_NOT_FOUND"


# --- Blocker 3, step 1: /grading/session/{id} for the owner teacher ------

def test_owner_teacher_grading_session_step1_200(client):
    resp = client.get("/api/v1/grading/session/60", headers=_auth(4))
    assert resp.status_code == 200
    assert resp.json()["data"]["session_id"] == 60


def test_admin_grading_session_step1_200(client):
    resp = client.get("/api/v1/grading/session/60", headers=_auth(9))
    assert resp.status_code == 200


def test_non_owner_teacher_grading_session_404(client):
    resp = client.get("/api/v1/grading/session/60", headers=_auth(8))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_other_tenant_admin_grading_session_404(client):
    resp = client.get("/api/v1/grading/session/60", headers=_auth(10))
    assert resp.status_code == 404


def test_student_grading_session_403(client):
    resp = client.get("/api/v1/grading/session/60", headers=_auth(6))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_ROLE"
