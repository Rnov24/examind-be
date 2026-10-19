"""Seed clearly-marked dummy data into production TiDB for dashboard review.

All dummy records use codes/names prefixed so they are easy to identify and remove.
Idempotent: skips tenants whose code already exists.
Run via: modal run seed_dummy_once.py
Cleanup via: modal run seed_dummy_once.py::cleanup_dummy
"""
import modal

image = (
    modal.Image.debian_slim()
    .pip_install_from_requirements("/home/hatch/workspace/examind-be/requirements.txt")
    .add_local_dir("/home/hatch/workspace/examind-be/app", remote_path="/root/app")
)

app = modal.App("examind-seed-dummy")

DUMMY_PREFIX = "DUMMY"


def _seed_impl():
    import sys
    from datetime import datetime, timedelta
    import random
    sys.path.insert(0, "/root")
    from app.core.database import SessionLocal
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.academic import Class, ClassMember
    from app.models.exam import Exam
    from app.models.session import ExamSession
    from app.core.security import get_password_hash

    random.seed(42)
    db = SessionLocal()
    now = datetime.utcnow()
    dummy_pw = get_password_hash("Dummy123!")

    schools = [
        ("SMA Negeri 1 Cirebon", "pro", "active", 170),
        ("SMK Teknologi Bandung", "enterprise", "active", 140),
        ("SMA Islam Al-Azhar Jakarta", "enterprise", "active", 110),
        ("SMK Negeri 2 Surabaya", "starter", "trial", 60),
        ("SMA PGRI Semarang", "pro", "past_due", 25),
    ]
    first_names = ["Andi", "Budi", "Citra", "Dewi", "Eko", "Fitri", "Gilang", "Hesti",
                   "Irfan", "Joko", "Kirana", "Lukman", "Maya", "Nadia", "Putri", "Rian"]
    last_names = ["Pratama", "Saputra", "Wijaya", "Kusuma", "Santoso", "Rahmawati",
                  "Nugroho", "Setiawan", "Hidayat", "Firmansyah"]

    def pick_name():
        return f"{random.choice(first_names)} {random.choice(last_names)}"

    created = {"tenants": 0, "users": 0, "classes": 0, "exams": 0, "sessions": 0}

    for i, (school_name, plan, sub_status, days_ago) in enumerate(schools, 1):
        code = f"{DUMMY_PREFIX}-SCH-{i:02d}"
        if db.query(Tenant).filter(Tenant.code == code).first():
            print(f"skip {code} (exists)")
            continue

        created_at = now - timedelta(days=days_ago)
        due = created_at + timedelta(days=365)
        tenant = Tenant(
            name=school_name,
            code=code,
            domain=f"{code.lower()}.examind.local",
            subscription_plan=plan,
            subscription_status=sub_status,
            max_students=500, max_teachers=50,
            ai_credits_monthly=2000,
            ai_credits_used=random.randint(200, 1500),
            is_active=sub_status != "canceled",
            subscription_due_date=due,
            grace_period_ends=due + timedelta(days=7),
            created_at=created_at,
        )
        db.add(tenant)
        db.flush()
        created["tenants"] += 1

        # Users: 1 admin, 2 teachers, 10 students
        users = []
        admin = User(
            identifier=f"{code}-ADM", email=f"admin.{code.lower()}@examind.local",
            password_hash=dummy_pw, full_name=pick_name(), role="admin",
            tenant_id=tenant.id, is_active=True, is_email_verified=True,
            created_at=created_at + timedelta(days=1),
        )
        db.add(admin)
        users.append(admin)
        teachers = []
        for t in range(2):
            teacher = User(
                identifier=f"{code}-T{t+1}", email=f"guru{t+1}.{code.lower()}@examind.local",
                password_hash=dummy_pw, full_name=pick_name(), role="teacher",
                tenant_id=tenant.id, is_active=True, is_email_verified=True,
                created_at=created_at + timedelta(days=2),
            )
            db.add(teacher)
            teachers.append(teacher)
            users.append(teacher)
        students = []
        for s in range(10):
            student = User(
                identifier=f"{code}-S{s+1:02d}", email=f"siswa{s+1:02d}.{code.lower()}@examind.local",
                password_hash=dummy_pw, full_name=pick_name(), role="student",
                tenant_id=tenant.id, is_active=True, is_email_verified=True,
                created_at=created_at + timedelta(days=3),
            )
            db.add(student)
            students.append(student)
            users.append(student)
        db.flush()  # ensure all user IDs are assigned before referencing
        created["users"] += len(users)

        # Classes
        classes = []
        for c, (cname, grade) in enumerate([("XII IPA 1", "12"), ("XII IPS 2", "12")]):
            cls = Class(
                name=f"{cname} ({school_name.split()[0]} {school_name.split()[1]})",
                grade_level=grade, academic_year="2025/2026",
                created_by=teachers[c % 2].id,
                created_at=created_at + timedelta(days=5),
            )
            db.add(cls)
            db.flush()
            classes.append(cls)
            created["classes"] += 1
            for st in students:
                db.add(ClassMember(class_id=cls.id, user_id=st.id, role="student"))

        # Exams
        exam_titles = [
            ("Ujian Tengah Semester Matematika", "published"),
            ("Try Out UTBK Fisika", "completed"),
            ("Kuis Harian Bahasa Indonesia", "in_progress"),
        ]
        for e, (title, exam_status) in enumerate(exam_titles):
            teacher = teachers[e % 2]
            cls = classes[e % 2]
            start = now - timedelta(days=random.randint(1, 20))
            exam = Exam(
                teacher_id=teacher.id, class_id=cls.id, title=title,
                description=f"Ujian dummy untuk review dashboard",
                duration_minutes=90, start_time=start,
                end_time=start + timedelta(minutes=90),
                status=exam_status,
                created_at=created_at + timedelta(days=10),
            )
            db.add(exam)
            db.flush()
            created["exams"] += 1
            # A few sessions for completed/in_progress exams
            if exam_status in ("completed", "in_progress"):
                for st in random.sample(students, k=random.randint(3, 6)):
                    sess = ExamSession(
                        exam_id=exam.id, student_id=st.id,
                        status="submitted" if exam_status == "completed" else "in_progress",
                        start_time=start,
                        submit_time=start + timedelta(minutes=random.randint(40, 85)) if exam_status == "completed" else None,
                        total_score=round(random.uniform(55, 98), 2) if exam_status == "completed" else 0,
                    )
                    db.add(sess)
                    created["sessions"] += 1

        db.commit()
        print(f"seeded {code}: {school_name}")

    db.close()
    print(f"DONE: {created}")
    return created


def _cleanup_impl():
    import sys
    sys.path.insert(0, "/root")
    from app.core.database import SessionLocal
    from app.models.tenant import Tenant

    db = SessionLocal()
    try:
        dummies = db.query(Tenant).filter(Tenant.code.like(f"{DUMMY_PREFIX}-%")).all()
        count = len(dummies)
        for t in dummies:
            db.delete(t)
        db.commit()
        print(f"removed {count} dummy tenants (cascade deletes users, classes, exams, sessions)")
        return count
    finally:
        db.close()


@app.function(image=image, secrets=[modal.Secret.from_name("examind-env")], timeout=300)
def seed_dummy():
    return _seed_impl()


@app.function(image=image, secrets=[modal.Secret.from_name("examind-env")], timeout=300)
def cleanup_dummy():
    return _cleanup_impl()
