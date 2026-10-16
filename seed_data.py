import sys
import os
from datetime import datetime, timedelta

# Ensure backend root is on Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.core.database import engine, SessionLocal, Base
from app.core.security import get_password_hash
from app.models.tenant import Tenant
from app.models.user import User
from app.models.academic import Class, ClassMember
from app.models.question import QuestionBank, Question
from app.models.exam import Exam, ExamQuestion
from app.models.session import ExamSession, StudentAnswer
from app.models.proctoring import ProctoringLog


def seed_database():
    print("=" * 60)
    print("EXAMIND — Comprehensive Logic & Dummy Data Seeder")
    print("=" * 60)

    try:
        # Ensure database 'examind' exists
        import pymysql
        conn = pymysql.connect(host="localhost", user="root", port=3306)
        with conn.cursor() as cur:
            cur.execute("CREATE DATABASE IF NOT EXISTS examind CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.commit()
        conn.close()

        # Create all tables if not exist
        print("1. Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("   -> Tables verified / created successfully.")
    except Exception as e:
        print(f"   [!] Database connection failed: {e}")
        print("   Pastikan MySQL di XAMPP telah dinyalakan pada port 3306.")
        return False

    db: Session = SessionLocal()

    try:
        # 1. Tenant
        print("\n2. Seeding School Tenant...")
        tenant = db.query(Tenant).filter(Tenant.code == "SMAN1-UNGGUL").first()
        if not tenant:
            tenant = Tenant(
                name="SMA Negeri 1 Indonesia Unggul",
                code="SMAN1-UNGGUL",
                domain="sman1unggul.sch.id",
                subscription_plan="pro",
                subscription_status="active",
                max_students=1000,
                max_teachers=100,
                max_storage_gb=50,
                ai_credits_monthly=5000,
                ai_credits_used=120,
                is_active=True,
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            print(f"   -> Tenant created: {tenant.name} (ID: {tenant.id})")
        else:
            print(f"   -> Tenant already exists: {tenant.name} (ID: {tenant.id})")

        # 2. Users (SuperAdmin, Admin, Teachers, Students)
        print("\n3. Seeding User Accounts (Bcrypt Hashed Passwords)...")
        users_data = [
            {
                "identifier": "SUPERADMIN-001",
                "email": "superadmin@examind.id",
                "full_name": "Master SuperAdmin",
                "role": "superadmin",
                "tenant_id": None,
                "password": "SuperAdmin123!",
            },
            {
                "identifier": "ADM-SMAN1-01",
                "email": "admin@sman1unggul.sch.id",
                "full_name": "Dra. Hj. Haryati, M.Pd",
                "role": "admin",
                "tenant_id": tenant.id,
                "password": "Admin123!",
            },
            {
                "identifier": "GUR-FIS-001",
                "email": "budi.santoso@sman1unggul.sch.id",
                "full_name": "Budi Santoso, M.Si.",
                "role": "teacher",
                "tenant_id": tenant.id,
                "password": "Guru123!",
            },
            {
                "identifier": "GUR-MAT-002",
                "email": "siti.aminah@sman1unggul.sch.id",
                "full_name": "Siti Aminah, S.Pd.",
                "role": "teacher",
                "tenant_id": tenant.id,
                "password": "Guru123!",
            },
            {
                "identifier": "0081234567",
                "email": "andi.pratama@student.sman1unggul.sch.id",
                "full_name": "Andi Pratama",
                "role": "student",
                "tenant_id": tenant.id,
                "password": "Siswa123!",
            },
            {
                "identifier": "0081234568",
                "email": "dewi.lestari@student.sman1unggul.sch.id",
                "full_name": "Dewi Lestari",
                "role": "student",
                "tenant_id": tenant.id,
                "password": "Siswa123!",
            },
            {
                "identifier": "0081234569",
                "email": "rizky.ramadhan@student.sman1unggul.sch.id",
                "full_name": "Rizky Ramadhan",
                "role": "student",
                "tenant_id": tenant.id,
                "password": "Siswa123!",
            },
        ]

        users_by_email = {}
        for u in users_data:
            existing = db.query(User).filter(User.email == u["email"]).first()
            if not existing:
                existing = User(
                    identifier=u["identifier"],
                    email=u["email"],
                    password_hash=get_password_hash(u["password"]),
                    full_name=u["full_name"],
                    role=u["role"],
                    tenant_id=u["tenant_id"],
                    is_active=True,
                    is_email_verified=True,
                )
                db.add(existing)
                db.commit()
                db.refresh(existing)
                print(f"   -> User created: {existing.full_name} ({existing.role})")
            else:
                print(f"   -> User exists: {existing.full_name} ({existing.role})")
            users_by_email[u["email"]] = existing

        teacher_budi = users_by_email["budi.santoso@sman1unggul.sch.id"]
        teacher_siti = users_by_email["siti.aminah@sman1unggul.sch.id"]
        student_andi = users_by_email["andi.pratama@student.sman1unggul.sch.id"]
        student_dewi = users_by_email["dewi.lestari@student.sman1unggul.sch.id"]
        student_rizky = users_by_email["rizky.ramadhan@student.sman1unggul.sch.id"]

        # 3. Classes
        print("\n4. Seeding Academic Classes & Enrolled Students...")
        class_1 = db.query(Class).filter(Class.name == "12 MIPA 1", Class.created_by == teacher_budi.id).first()
        if not class_1:
            class_1 = Class(
                name="12 MIPA 1",
                grade_level="12",
                academic_year="2025/2026",
                created_by=teacher_budi.id,
            )
            db.add(class_1)
            db.commit()
            db.refresh(class_1)
            print(f"   -> Class created: {class_1.name}")

        class_2 = db.query(Class).filter(Class.name == "12 MIPA 2", Class.created_by == teacher_siti.id).first()
        if not class_2:
            class_2 = Class(
                name="12 MIPA 2",
                grade_level="12",
                academic_year="2025/2026",
                created_by=teacher_siti.id,
            )
            db.add(class_2)
            db.commit()
            db.refresh(class_2)
            print(f"   -> Class created: {class_2.name}")

        # Class memberships
        memberships_data = [
            (class_1.id, teacher_budi.id, "teacher"),
            (class_1.id, student_andi.id, "student"),
            (class_1.id, student_dewi.id, "student"),
            (class_2.id, teacher_siti.id, "teacher"),
            (class_2.id, student_rizky.id, "student"),
        ]

        for cid, uid, role in memberships_data:
            cm = db.query(ClassMember).filter(ClassMember.class_id == cid, ClassMember.user_id == uid).first()
            if not cm:
                cm = ClassMember(class_id=cid, user_id=uid, role=role)
                db.add(cm)
        db.commit()
        print("   -> Class memberships assigned.")

        # 4. Question Banks
        print("\n5. Seeding Question Banks & Pedagogical Questions...")
        bank_fisika = db.query(QuestionBank).filter(QuestionBank.title == "Fisika Kuantum & Relativitas", QuestionBank.teacher_id == teacher_budi.id).first()
        if not bank_fisika:
            bank_fisika = QuestionBank(
                teacher_id=teacher_budi.id,
                title="Fisika Kuantum & Relativitas",
                subject="Fisika",
                description="Paket butir soal kurikulum Merdeka mengenai efek fotolistrik, panjang gelombang de Broglie, dan relativitas massa.",
            )
            db.add(bank_fisika)
            db.commit()
            db.refresh(bank_fisika)
            print(f"   -> Question Bank created: {bank_fisika.title}")

        # Questions for Fisika
        q1 = db.query(Question).filter(Question.bank_id == bank_fisika.id, Question.prompt.like("Menurut teori kuantum Max Planck%")).first()
        if not q1:
            q1 = Question(
                bank_id=bank_fisika.id,
                question_type="multiple_choice",
                prompt="Menurut teori kuantum Max Planck, radiasi gelombang elektromagnetik dipancarkan dalam bentuk paket-paket energi diskrit yang disebut kuanta foton. Rumus matematis ekuivalen energi foton terkait panjang gelombang (lambda) adalah...",
                options_json=[
                    {"id": "A", "text": "E = (h . c) / lambda", "is_correct": True, "rationale": "Hubungan Planck E = h.f dan f = c/lambda menghasilkan E = h.c / lambda."},
                    {"id": "B", "text": "E = m . c^2", "is_correct": False, "rationale": "Ini adalah rumus kesetaraan massa-energi Einstein, bukan energi kuantum Planck."},
                    {"id": "C", "text": "E = 1/2 . m . v^2", "is_correct": False, "rationale": "Ini adalah energi kinetik mekanika klasik."},
                    {"id": "D", "text": "E = h / lambda", "is_correct": False, "rationale": "Ini adalah rumus momentum foton p = h/lambda, bukan energi."},
                ],
                correct_answer="A",
                explanation="Energi kuantum berbanding lurus dengan frekuensi gelombang E = h.f. Karena kecepatan rambat c = f.lambda (sehingga f = c/lambda), substitusi langsung menghasilkan E = (h.c) / lambda.",
                difficulty="medium",
                default_points=10.00,
            )
            db.add(q1)

        q2 = db.query(Question).filter(Question.bank_id == bank_fisika.id, Question.prompt.like("Pada fenomena efek fotolistrik%")).first()
        if not q2:
            q2 = Question(
                bank_id=bank_fisika.id,
                question_type="multiple_choice",
                prompt="Pada fenomena efek fotolistrik, elektron foto hanya dapat terlepas dari permukaan katoda logam jika foton cahaya datang memenuhi syarat...",
                options_json=[
                    {"id": "A", "text": "Frekuensi cahaya datang lebih kecil daripada frekuensi ambang logam", "is_correct": False, "rationale": "Jika f < f0, energi foton tidak cukup untuk melampaui fungsi kerja W0 katoda."},
                    {"id": "B", "text": "Frekuensi cahaya datang sama dengan atau lebih besar daripada frekuensi ambang logam", "is_correct": True, "rationale": "Energi foton h.f harus >= fungsi kerja katoda W0 = h.f0."},
                    {"id": "C", "text": "Intensitas cahaya ditingkatkan hingga batas jenuh tanpa pengaruh frekuensi", "is_correct": False, "rationale": "Fisika klasik memprediksi intensitas menentukan pelepasan, namun eksperimen membuktikan frekuensi adalah syarat utama."},
                    {"id": "D", "text": "Panjang gelombang cahaya lebih besar dari panjang gelombang ambang", "is_correct": False, "rationale": "Jika lambda > lambda0 maka f < f0, elektron tidak akan terlepas."},
                ],
                correct_answer="B",
                explanation="Elektron foto membutuhkan energi minimum sebesar fungsi kerja logam (W0 = h.f0). Oleh karena itu, frekuensi cahaya penyinar (f) wajib melampaui atau minimal sama dengan frekuensi ambang katoda (f >= f0).",
                difficulty="medium",
                default_points=10.00,
            )
            db.add(q2)

        q3 = db.query(Question).filter(Question.bank_id == bank_fisika.id, Question.prompt.like("Sebuah foton memiliki panjang gelombang 660 nm%")).first()
        if not q3:
            q3 = Question(
                bank_id=bank_fisika.id,
                question_type="multiple_choice",
                prompt="Sebuah foton memiliki panjang gelombang 660 nm (6.6 x 10^-7 m). Jika tetapan Planck h = 6.6 x 10^-34 J.s, momentum foton tersebut adalah...",
                options_json=[
                    {"id": "A", "text": "1.0 x 10^-27 kg.m/s", "is_correct": True, "rationale": "p = h / lambda = (6.6 x 10^-34) / (6.6 x 10^-7) = 1.0 x 10^-27 kg.m/s."},
                    {"id": "B", "text": "2.0 x 10^-27 kg.m/s", "is_correct": False, "rationale": "Kekeliruan pembagian tetapan Planck."},
                    {"id": "C", "text": "4.3 x 10^-27 kg.m/s", "is_correct": False, "rationale": "Perhitungan salah eksponen."},
                    {"id": "D", "text": "6.6 x 10^-27 kg.m/s", "is_correct": False, "rationale": "Lupa membagi dengan nilai panjang gelombang."},
                ],
                correct_answer="A",
                explanation="Berdasarkan hipotesis Louis de Broglie, momentum kuantum dirumuskan p = h / lambda. Dengan memasukkan angka p = (6.6 x 10^-34) / (6.6 x 10^-7), diperoleh momentum tepat 1.0 x 10^-27 kg.m/s.",
                difficulty="hard",
                default_points=10.00,
            )
            db.add(q3)

        q4 = db.query(Question).filter(Question.bank_id == bank_fisika.id, Question.prompt.like("Jelaskan secara mendalam perbedaan mendasar%")).first()
        if not q4:
            q4 = Question(
                bank_id=bank_fisika.id,
                question_type="short_essay",
                prompt="Jelaskan secara mendalam perbedaan mendasar antara teori gelombang klasik Maxwell dan teori kuantum foton Einstein dalam menjelaskan peranan intensitas cahaya pada efek fotolistrik!",
                options_json=None,
                correct_answer="Teori klasik memprediksi intensitas menentukan energi kinetik elektron, sedangkan teori kuantum membuktikan intensitas hanya menentukan kuantitas (jumlah) elektron yang terlepas per satuan waktu, sementara energi kinetik elektron sepenuhnya ditentukan oleh frekuensi foton.",
                rubric_json={
                    "dimension_1_concept": 40,
                    "dimension_2_argument": 30,
                    "dimension_3_terminology": 15,
                    "dimension_4_clarity": 15,
                },
                explanation="Penilaian esai ditekankan pada pemahaman pergeseran paradigma dari model kontinu ke kuantisasi foton individual.",
                difficulty="hard",
                default_points=20.00,
            )
            db.add(q4)

        db.commit()
        db.refresh(q1)
        db.refresh(q2)
        db.refresh(q3)
        db.refresh(q4)
        print("   -> 4 Questions seeded successfully.")

        # 5. Exams
        print("\n6. Seeding Examination Packages...")
        now = datetime.utcnow()

        # Exam 1: Completed Physics Exam
        exam_1 = db.query(Exam).filter(Exam.title == "Penilaian Akhir Semester — Fisika Kuantum").first()
        if not exam_1:
            exam_1 = Exam(
                teacher_id=teacher_budi.id,
                class_id=class_1.id,
                title="Penilaian Akhir Semester — Fisika Kuantum",
                description="Evaluasi akhir semester mata pelajaran Fisika peminatan kelas 12 MIPA kurikulum Merdeka.",
                duration_minutes=60,
                start_time=now - timedelta(days=2, hours=2),
                end_time=now - timedelta(days=2, hours=1),
                randomize_questions=False,
                randomize_options=False,
                proctoring_level="dual_camera",
                explanation_policy="instant",
                status="completed",
            )
            db.add(exam_1)
            db.commit()
            db.refresh(exam_1)
            print(f"   -> Exam 1 (Completed): '{exam_1.title}' (ID: {exam_1.id})")

            # Link questions to Exam 1
            eq1 = ExamQuestion(exam_id=exam_1.id, question_id=q1.id, order_index=1, allocated_points=10.00)
            eq2 = ExamQuestion(exam_id=exam_1.id, question_id=q2.id, order_index=2, allocated_points=10.00)
            eq3 = ExamQuestion(exam_id=exam_1.id, question_id=q3.id, order_index=3, allocated_points=10.00)
            eq4 = ExamQuestion(exam_id=exam_1.id, question_id=q4.id, order_index=4, allocated_points=20.00)
            db.add_all([eq1, eq2, eq3, eq4])
            db.commit()

        # Exam 2: Upcoming Math Exam
        exam_2 = db.query(Exam).filter(Exam.title == "Ujian Tengah Semester — Matematika Lanjut").first()
        if not exam_2:
            exam_2 = Exam(
                teacher_id=teacher_siti.id,
                class_id=class_1.id,
                title="Ujian Tengah Semester — Matematika Lanjut",
                description="Ujian materi kalkulus diferensial, turunan fungsi trigonometri, dan matriks transformasi.",
                duration_minutes=90,
                start_time=now + timedelta(days=1, hours=1),
                end_time=now + timedelta(days=1, hours=2, minutes=30),
                randomize_questions=True,
                randomize_options=True,
                proctoring_level="dual_camera",
                explanation_policy="after_exam_closed",
                status="published",
            )
            db.add(exam_2)
            db.commit()
            db.refresh(exam_2)
            print(f"   -> Exam 2 (Upcoming Scheduled): '{exam_2.title}' (ID: {exam_2.id})")

        # 6. Student Exam Sessions, Answers & Results
        print("\n7. Seeding Student Submission Records & Graded Answers...")
        # Andi Pratama Session on Exam 1
        sess_andi = db.query(ExamSession).filter(ExamSession.exam_id == exam_1.id, ExamSession.student_id == student_andi.id).first()
        if not sess_andi:
            sess_andi = ExamSession(
                exam_id=exam_1.id,
                student_id=student_andi.id,
                start_time=now - timedelta(days=2, hours=1, minutes=55),
                submit_time=now - timedelta(days=2, hours=1, minutes=10),
                status="graded",
                total_score=40.00,  # 10 + 0 + 10 + 20 = 40 / 50 (80%)
                integrity_score=96,
                companion_paired=True,
                client_ip="192.168.1.15",
            )
            db.add(sess_andi)
            db.commit()
            db.refresh(sess_andi)

            # Andi Answers:
            # Q1: Correct (A) -> 10.0
            # Q2: Incorrect (A chosen instead of B) -> 0.0 (Perfect for explanation tutor demo!)
            # Q3: Correct (A) -> 10.0
            # Q4: Essay (High Score) -> 20.0
            ans1 = StudentAnswer(
                session_id=sess_andi.id,
                question_id=q1.id,
                student_response="A",
                is_correct=True,
                auto_score=10.00,
                final_score=10.00,
                ai_explanation="Pilihan Anda tepat! Hubungan Planck E = h.f dikombinasikan dengan f = c/lambda menghasilkan rumusan E = (h.c)/lambda.",
                graded_at=now - timedelta(days=2, hours=1, minutes=9),
            )
            ans2 = StudentAnswer(
                session_id=sess_andi.id,
                question_id=q2.id,
                student_response="A",
                is_correct=False,
                auto_score=0.00,
                final_score=0.00,
                ai_explanation="Jawaban Anda belum tepat. Jika frekuensi cahaya lebih kecil daripada frekuensi ambang (f < f0), energi foton tidak sanggup melepaskan elektron dari potensial penghalang katoda.",
                graded_at=now - timedelta(days=2, hours=1, minutes=9),
            )
            ans3 = StudentAnswer(
                session_id=sess_andi.id,
                question_id=q3.id,
                student_response="A",
                is_correct=True,
                auto_score=10.00,
                final_score=10.00,
                ai_explanation="Perhitungan Anda akurat. p = (6.6 x 10^-34) / (6.6 x 10^-7) = 1.0 x 10^-27 kg.m/s.",
                graded_at=now - timedelta(days=2, hours=1, minutes=9),
            )
            ans4 = StudentAnswer(
                session_id=sess_andi.id,
                question_id=q4.id,
                student_response="Menurut fisika klasik, energi elektron dipengaruhi oleh intensitas cahaya. Namun Einstein membuktikan bahwa intensitas hanya memperbanyak kuantitas foton sehingga jumlah elektron yang keluar lebih banyak, sedangkan energi kinetik elektron ditentukan oleh frekuensi foton.",
                is_correct=True,
                auto_score=19.00,
                teacher_override_score=20.00,
                final_score=20.00,
                ai_confidence_level="high",
                ai_grading_rationale="Konsep perbandingan fisika klasik dan kuantum dielaborasi dengan sangat jelas dan terminologi foton serta fungsi kerja tepat.",
                ai_explanation="Uraian jawaban sangat lengkap dan komprehensif.",
                teacher_notes="Analisis sangat memuaskan, pertahankan penguasaan konsep fisika kuantum!",
                graded_at=now - timedelta(days=2, hours=1),
            )
            db.add_all([ans1, ans2, ans3, ans4])

            # Proctoring Log for Andi
            plog = ProctoringLog(
                session_id=sess_andi.id,
                event_type="gaze_away",
                camera_source="primary_camera",
                severity="low",
                duration_seconds=3,
                event_timestamp=now - timedelta(days=2, hours=1, minutes=30),
                reviewed_by_teacher=True,
                teacher_verdict="ignored_false_positive",
            )
            db.add(plog)
            db.commit()
            print(f"   -> Graded session created for Andi Pratama (Score: 40.0/50.0 | Integrity: 96%)")
        else:
            print("   -> Session for Andi Pratama already exists.")

        # Dewi Lestari Session on Exam 1
        sess_dewi = db.query(ExamSession).filter(ExamSession.exam_id == exam_1.id, ExamSession.student_id == student_dewi.id).first()
        if not sess_dewi:
            sess_dewi = ExamSession(
                exam_id=exam_1.id,
                student_id=student_dewi.id,
                start_time=now - timedelta(days=2, hours=1, minutes=58),
                submit_time=now - timedelta(days=2, hours=1, minutes=15),
                status="graded",
                total_score=50.00,  # 100%
                integrity_score=100,
                companion_paired=True,
                client_ip="192.168.1.18",
            )
            db.add(sess_dewi)
            db.commit()
            print(f"   -> Graded session created for Dewi Lestari (Score: 50.0/50.0 | Integrity: 100%)")

        print("\n" + "=" * 60)
        print("DATABASE SEEDING COMPLETED SUCCESSFULLY!")
        print("Akun Uji Coba Tersedia:")
        print("  SuperAdmin : superadmin@examind.id / SuperAdmin123!")
        print("  Admin      : admin@sman1unggul.sch.id / Admin123!")
        print("  Guru Fisika: budi.santoso@sman1unggul.sch.id / Guru123!")
        print("  Guru Mat   : siti.aminah@sman1unggul.sch.id / Guru123!")
        print("  Siswa 1    : andi.pratama@student.sman1unggul.sch.id / Siswa123! (NISN: 0081234567)")
        print("  Siswa 2    : dewi.lestari@student.sman1unggul.sch.id / Siswa123! (NISN: 0081234568)")
        print("=" * 60)
        return True

    except Exception as e:
        db.rollback()
        print(f"\n[!] Error seeding database: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
