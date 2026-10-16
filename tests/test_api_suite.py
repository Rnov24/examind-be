import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.user import User

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_auth_success_and_me():
    # Login as teacher
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "198507232010011005", "password": "Password123!"},
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "access_token" in res_data["data"]
    assert res_data["data"]["user"]["role"] == "teacher"

    token = res_data["data"]["access_token"]

    # Test /me
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["identifier"] == "198507232010011005"


def test_auth_invalid_credentials():
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "198507232010011005", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_rbac_student_forbidden_on_teacher_route():
    # Login as student
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"identifier": "0061234501", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["data"]["access_token"]

    # Student attempts to create class (forbidden)
    class_resp = client.post(
        "/api/v1/classes",
        json={"name": "Forbidden Class", "grade_level": "10", "academic_year": "2026/2027"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert class_resp.status_code == 403
    assert class_resp.json()["success"] is False


def test_ai_question_generator():
    # Login as teacher
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"identifier": "198507232010011005", "password": "Password123!"},
    )
    token = login_resp.json()["data"]["access_token"]

    gen_resp = client.post(
        "/api/v1/ai/generate-questions",
        json={
            "subject": "Fisika",
            "topic_content": "Efek Fotolistrik",
            "grade_level": "12",
            "mcq_count": 3,
            "essay_count": 2,
            "difficulty": "medium",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert gen_resp.status_code == 200
    data = gen_resp.json()["data"]
    assert len(data["mcq_questions"]) == 3
    assert len(data["essay_questions"]) == 2
    # Verify MCQ structure
    first_mcq = data["mcq_questions"][0]
    assert len(first_mcq["options"]) == 4
    assert first_mcq["correct_option_id"] in ["A", "B", "C", "D"]
    # Verify Essay 4D rubric
    first_essay = data["essay_questions"][0]
    assert "dimension_1_concept" in first_essay["rubric"]
    assert "dimension_2_argument" in first_essay["rubric"]


def test_ai_assistant_chat():
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"identifier": "198507232010011005", "password": "Password123!"},
    )
    token = login_resp.json()["data"]["access_token"]

    chat_resp = client.post(
        "/api/v1/ai/assistant/chat",
        json={
            "message": "Bagaimana cara menyusun rubrik esai yang objektif?",
            "history": [],
            "context": "Bank Soal Fisika",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert chat_resp.status_code == 200
    res = chat_resp.json()
    assert res["success"] is True
    assert "reply" in res["data"]
    assert len(res["data"]["reply"]) > 10
    assert res["data"]["provider"] in ["gemini", "mock"]


def test_full_student_exam_taking_and_grading():
    # Clean previous test session if exists
    from app.models.session import ExamSession
    db = SessionLocal()
    st = db.query(User).filter(User.identifier == "0061234501").first()
    if st:
        sess = db.query(ExamSession).filter(ExamSession.exam_id == 1, ExamSession.student_id == st.id).first()
        if sess:
            db.delete(sess)
            db.commit()
    db.close()

    # 1. Login Teacher to get exam
    t_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "198507232010011005", "password": "Password123!"},
    )
    t_token = t_login.json()["data"]["access_token"]

    # Ensure exam 1 is published
    pub_resp = client.post(
        "/api/v1/exams/1/publish",
        headers={"Authorization": f"Bearer {t_token}"},
    )
    assert pub_resp.status_code in [200, 400]  # If already published or ok

    # 2. Login Student
    s_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "0061234501", "password": "Password123!"},
    )
    s_token = s_login.json()["data"]["access_token"]

    # 3. Start Exam
    start_resp = client.post(
        "/api/v1/student/exam/1/start",
        headers={"Authorization": f"Bearer {s_token}"},
    )
    assert start_resp.status_code == 200
    start_data = start_resp.json()["data"]
    session_id = start_data["session_id"]
    assert session_id > 0
    assert len(start_data["questions"]) > 0

    # 4. Autosave answers
    q1 = start_data["questions"][0]
    autosave_resp = client.post(
        "/api/v1/student/exam/1/autosave",
        json={
            "session_id": session_id,
            "answers": [
                {"question_id": 1, "response": "B"},
                {"question_id": 2, "response": "A"},
                {"question_id": 3, "response": "Efek fotolistrik terjadi karena foton mentransfer energi kuantum E=hf secara instan ke elektron."},
            ],
        },
        headers={"Authorization": f"Bearer {s_token}"},
    )
    assert autosave_resp.status_code == 200
    assert autosave_resp.json()["data"]["saved_items_count"] == 3

    # 5. Log proctoring incident (tab switch)
    proc_resp = client.post(
        "/api/v1/proctoring/log-event",
        json={
            "session_id": session_id,
            "event_type": "tab_switch",
            "camera_source": "system_event",
            "severity": "medium",
            "duration_seconds": 2,
        },
        headers={"Authorization": f"Bearer {s_token}"},
    )
    assert proc_resp.status_code == 200
    assert proc_resp.json()["data"]["event_type"] == "tab_switch"

    # 6. Submit Exam
    sub_resp = client.post(
        "/api/v1/student/exam/1/submit",
        json={"session_id": session_id},
        headers={"Authorization": f"Bearer {s_token}"},
    )
    assert sub_resp.status_code == 200
    assert sub_resp.json()["data"]["status"] == "grading_in_progress"

    # 7. Check result after async worker runs
    from app.services.grading.background_worker import grade_exam_session_async
    grade_exam_session_async(session_id)

    res_resp = client.get(
        "/api/v1/student/exam/1/result",
        headers={"Authorization": f"Bearer {s_token}"},
    )
    assert res_resp.status_code == 200
    res_data = res_resp.json()["data"]
    assert res_data["total_score"] > 0
    assert res_data["integrity_score"] <= 100


def test_analytics_and_export():
    # Login Teacher
    t_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "198507232010011005", "password": "Password123!"},
    )
    t_token = t_login.json()["data"]["access_token"]

    # Item analysis
    items_resp = client.get(
        "/api/v1/analytics/exam/1/items",
        headers={"Authorization": f"Bearer {t_token}"},
    )
    assert items_resp.status_code == 200
    data = items_resp.json()["data"]
    assert "average_score" in data
    assert "item_analysis" in data

    # Export Excel
    excel_resp = client.get(
        "/api/v1/analytics/exam/1/export/excel",
        headers={"Authorization": f"Bearer {t_token}"},
    )
    assert excel_resp.status_code == 200
    assert excel_resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(excel_resp.content) > 100

    # Export PDF
    pdf_resp = client.get(
        "/api/v1/analytics/exam/1/export/pdf",
        headers={"Authorization": f"Bearer {t_token}"},
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert len(pdf_resp.content) > 100


def test_student_exam_security_failure_auto_fail():
    from app.models.session import ExamSession
    from app.models.proctoring import ProctoringLog

    db = SessionLocal()
    st = db.query(User).filter(User.identifier == "0061234501").first()
    if st:
        sess = db.query(ExamSession).filter(ExamSession.exam_id == 1, ExamSession.student_id == st.id).first()
        if sess:
            db.delete(sess)
            db.commit()
    db.close()

    # Login Student
    s_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "0061234501", "password": "Password123!"},
    )
    assert s_login.status_code == 200
    s_token = s_login.json()["data"]["access_token"]

    # Start Exam
    start_resp = client.post(
        "/api/v1/student/exam/1/start",
        headers={"Authorization": f"Bearer {s_token}"},
    )
    assert start_resp.status_code == 200
    session_id = start_resp.json()["data"]["session_id"]

    # Trigger security breach: fullscreen_exit
    fail_resp = client.post(
        "/api/v1/student/exam/1/fail",
        json={
            "session_id": session_id,
            "reason": "fullscreen_exit",
            "details": "Menutup mode layar penuh",
        },
        headers={"Authorization": f"Bearer {s_token}"},
    )
    assert fail_resp.status_code == 200
    fail_data = fail_resp.json()["data"]
    assert fail_data["status"] == "aborted"

    # Verify session is aborted and cannot restart
    restart_resp = client.post(
        "/api/v1/student/exam/1/start",
        headers={"Authorization": f"Bearer {s_token}"},
    )
    assert restart_resp.status_code == 403
    assert restart_resp.json()["error"]["code"] == "EXAM_DISQUALIFIED"

    # Verify cannot autosave after fail
    auto_resp = client.post(
        "/api/v1/student/exam/1/autosave",
        json={"session_id": session_id, "answers": [{"question_id": 1, "response": "A"}]},
        headers={"Authorization": f"Bearer {s_token}"},
    )
    assert auto_resp.status_code == 400

    # Verify cannot submit after fail
    sub_resp = client.post(
        "/api/v1/student/exam/1/submit",
        json={"session_id": session_id},
        headers={"Authorization": f"Bearer {s_token}"},
    )
    assert sub_resp.status_code == 400

    # Verify result endpoint reports aborted with 0 score and 0 integrity
    res_resp = client.get(
        "/api/v1/student/exam/1/result",
        headers={"Authorization": f"Bearer {s_token}"},
    )
    assert res_resp.status_code == 200
    res_data = res_resp.json()["data"]
    assert res_data["status"] == "aborted"
    assert res_data["total_score"] == 0.0
    assert res_data["integrity_score"] == 0


def test_admin_dashboard_and_user_management():
    # 1. Login as admin
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "admin", "password": "Password123!"},
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["data"]["access_token"]
    assert admin_login.json()["data"]["user"]["role"] == "admin"

    # 2. Get Admin Stats
    stats_resp = client.get(
        "/api/v1/admin/stats",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert stats_resp.status_code == 200
    stats = stats_resp.json()["data"]
    assert stats["total_users"] >= 5
    assert stats["total_admins"] >= 1
    assert stats["total_teachers"] >= 1
    assert stats["total_students"] >= 3
    assert "Connected" in stats["database_status"]

    # 3. Get Admin Users list
    users_resp = client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert users_resp.status_code == 200
    user_list = users_resp.json()["data"]
    assert len(user_list) >= 5

    # 4. Verify RBAC: Teacher and Student forbidden from admin endpoints
    t_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "198507232010011005", "password": "Password123!"},
    )
    t_token = t_login.json()["data"]["access_token"]
    t_denied = client.get(
        "/api/v1/admin/stats",
        headers={"Authorization": f"Bearer {t_token}"},
    )
    assert t_denied.status_code == 403


def test_student_exam_export_pdf():
    # Login as student (0061234501 has session for exam 1)
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"identifier": "0061234501", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["data"]["access_token"]

    # Export PDF
    pdf_resp = client.get(
        "/api/v1/student/exam/1/export/pdf",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert "transkrip_nilai" in pdf_resp.headers.get("content-disposition", "")
    assert len(pdf_resp.content) > 500  # Valid binary PDF data


def test_superadmin_saas_management():
    # 1. Login as Super Admin
    sa_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "superadmin", "password": "Password123!"},
    )
    assert sa_login.status_code == 200
    sa_token = sa_login.json()["data"]["access_token"]
    assert sa_login.json()["data"]["user"]["role"] == "superadmin"

    # 2. Get Global SaaS stats
    stats_resp = client.get(
        "/api/v1/superadmin/stats",
        headers={"Authorization": f"Bearer {sa_token}"},
    )
    assert stats_resp.status_code == 200
    stats = stats_resp.json()["data"]
    assert stats["total_tenants"] >= 1
    assert "plan_distribution" in stats
    assert stats["total_global_users"] >= 5

    # 3. List tenants
    tenants_resp = client.get(
        "/api/v1/superadmin/tenants",
        headers={"Authorization": f"Bearer {sa_token}"},
    )
    assert tenants_resp.status_code == 200
    tenants = tenants_resp.json()["data"]
    assert len(tenants) >= 1

    # 4. Create a new school tenant
    import time
    unique_code = f"test-sch-{int(time.time())}"
    create_resp = client.post(
        "/api/v1/superadmin/tenants",
        json={
            "name": "SMA Test Nusantara",
            "code": unique_code,
            "subscription_plan": "pro",
            "max_students": 300,
            "max_teachers": 30,
            "admin_identifier": f"admin_{unique_code}",
            "admin_email": f"admin@{unique_code}.sch.id",
            "admin_full_name": "Admin Nusantara",
            "admin_password": "Password123!",
        },
        headers={"Authorization": f"Bearer {sa_token}"},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    assert created["code"] == unique_code
    assert created["subscription_plan"] == "pro"

    # 5. Toggle tenant active status
    toggle_resp = client.patch(
        f"/api/v1/superadmin/tenants/{created['id']}/toggle-status",
        headers={"Authorization": f"Bearer {sa_token}"},
    )
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["data"]["is_active"] is False

    admin_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "admin", "password": "Password123!"},
    )
    admin_token = admin_login.json()["data"]["access_token"]
    denied_resp = client.get(
        "/api/v1/superadmin/stats",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert denied_resp.status_code == 403


def test_resend_otp_and_email_verification():
    from app.models.verification import EmailVerification

    test_email = "ahmad.dahlan@siswa.sch.id"

    # 1. Request OTP
    send_resp = client.post(
        "/api/v1/auth/otp/send",
        json={"email": test_email, "purpose": "email_verification"},
    )
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["success"] is True
    assert send_data["data"]["email"] == test_email
    assert send_data["data"]["expires_in_minutes"] == 10

    # 2. Retrieve OTP record from DB
    db = SessionLocal()
    try:
        record = (
            db.query(EmailVerification)
            .filter(EmailVerification.email == test_email, EmailVerification.is_used == False)
            .order_by(EmailVerification.id.desc())
            .first()
        )
        assert record is not None
        assert len(record.otp_code) == 6
        correct_otp = record.otp_code

        # 3. Verify with wrong OTP
        wrong_resp = client.post(
            "/api/v1/auth/otp/verify",
            json={"email": test_email, "otp_code": "999999", "purpose": "email_verification"},
        )
        assert wrong_resp.status_code == 400
        assert wrong_resp.json()["error"]["code"] == "INVALID_OTP"

        # 4. Verify with correct OTP
        verify_resp = client.post(
            "/api/v1/auth/otp/verify",
            json={"email": test_email, "otp_code": correct_otp, "purpose": "email_verification"},
        )
        assert verify_resp.status_code == 200
        verify_data = verify_resp.json()
        assert verify_data["success"] is True
        assert verify_data["data"]["is_email_verified"] is True

        # 5. Check user in DB has is_email_verified = True
        user = db.query(User).filter(User.email == test_email).first()
        assert user is not None
        assert user.is_email_verified is True

        # 6. Replay attack: reusing already consumed OTP must fail
        replay_resp = client.post(
            "/api/v1/auth/otp/verify",
            json={"email": test_email, "otp_code": correct_otp, "purpose": "email_verification"},
        )
        assert replay_resp.status_code == 400
        assert replay_resp.json()["error"]["code"] == "INVALID_OR_EXPIRED_OTP"
    finally:
        db.close()


def test_superadmin_secret_manager_flow():
    from app.core.secret_manager import get_secret, mask_secret, decrypt_secret
    from app.models.secret import SystemSecret

    # 1. Login as superadmin
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"identifier": "superadmin", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    sa_token = login_resp.json()["data"]["access_token"]
    sa_headers = {"Authorization": f"Bearer {sa_token}"}

    # 2. Add / Update a test secret
    test_key_name = "TEST_GEMINI_API_KEY"
    raw_key_val = "AIzaSyTestKey1234567890ABC"

    save_resp = client.post(
        "/api/v1/superadmin/secrets",
        json={
            "key_name": test_key_name,
            "service_name": "gemini",
            "value": raw_key_val,
            "description": "Test Gemini Key for Automated Tests",
            "is_active": True,
        },
        headers=sa_headers,
    )
    assert save_resp.status_code == 200
    save_data = save_resp.json()["data"]
    assert save_data["key_name"] == test_key_name
    assert save_data["service_name"] == "gemini"
    assert save_data["masked_value"] == mask_secret(raw_key_val)
    assert raw_key_val not in save_data["masked_value"]  # masked, not plain

    # 3. Verify at-rest encryption in DB
    db = SessionLocal()
    try:
        secret_rec = db.query(SystemSecret).filter(SystemSecret.key_name == test_key_name).first()
        assert secret_rec is not None
        assert secret_rec.encrypted_value != raw_key_val  # must be encrypted!
        assert decrypt_secret(secret_rec.encrypted_value) == raw_key_val

        # 4. Test dynamic resolution via get_secret
        resolved_val = get_secret(test_key_name, db=db)
        assert resolved_val == raw_key_val

        # 5. List all secrets
        list_resp = client.get("/api/v1/superadmin/secrets", headers=sa_headers)
        assert list_resp.status_code == 200
        secrets = list_resp.json()["data"]
        found = [s for s in secrets if s["key_name"] == test_key_name]
        assert len(found) == 1
        assert found[0]["masked_value"] == mask_secret(raw_key_val)

        # 6. Test connection ping endpoint (custom mode to avoid external network dependency)
        ping_resp = client.post(
            "/api/v1/superadmin/secrets/test",
            json={"service_name": "custom", "key_name": test_key_name},
            headers=sa_headers,
        )
        assert ping_resp.status_code == 200
        assert ping_resp.json()["data"]["success"] is True

        # 7. Toggle active status
        toggle_resp = client.patch(
            f"/api/v1/superadmin/secrets/{test_key_name}/toggle",
            headers=sa_headers,
        )
        assert toggle_resp.status_code == 200
        assert toggle_resp.json()["data"]["is_active"] is False

        # Inactive secret should not be returned by get_secret
        db.commit()
        inactive_resolved = get_secret(test_key_name, default="FALLBACK")
        assert inactive_resolved == "FALLBACK"

        # 8. RBAC Test: Non-superadmin (school admin) cannot access secrets
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"identifier": "admin", "password": "Password123!"},
        )
        admin_token = admin_login.json()["data"]["access_token"]
        forbidden_resp = client.get(
            "/api/v1/superadmin/secrets",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert forbidden_resp.status_code == 403

        # 9. Delete test secret
        del_resp = client.delete(
            f"/api/v1/superadmin/secrets/{test_key_name}",
            headers=sa_headers,
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["data"]["deleted_key"] == test_key_name

        # Verify deletion in DB
        assert db.query(SystemSecret).filter(SystemSecret.key_name == test_key_name).first() is None
    finally:
        db.close()




