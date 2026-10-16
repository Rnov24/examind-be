# Ticket: FND-001 — Database Schema, SQLAlchemy Models & Seeders

- **Epic**: Epic 0 — Project Setup, Database & DevOps Foundation
- **Priority**: P0 (Blocker)
- **Status**: Ready for Development
- **Estimasi Effort**: 5 Story Points (SP)
- **Assignee / Role**: Backend Engineer
- **Dokumen Terkait**: [docs/PRD.md](../../PRD.md) | [database/schema.sql](../../../database/schema.sql) | [database/seeds/01_initial_seeds.sql](../../../database/seeds/01_initial_seeds.sql)

---

## 1. User Story / Objective
> **Sebagai** Backend Developer,  
> **Saya ingin** mengimplementasikan model ORM SQLAlchemy 2.0 yang merefleksikan skema MySQL XAMPP lengkap beserta migration tooling (Alembic) dan script seeder data awal,  
> **Agar** seluruh modul backend dapat melakukan transaksi database relasional secara konsisten, aman, dan berkinerja tinggi.

---

## 2. Technical Scope & Implementation Details

### A. Target File Structure
```text
backend/app/
├── core/
│   └── database.py             # Engine creation, SessionLocal, get_db dependency
└── models/
    ├── __init__.py             # Export all models for Alembic autogenerate
    ├── user.py                 # User model (admin, teacher, student)
    ├── academic.py             # Class & ClassMember models
    ├── question.py             # QuestionBank & Question models
    ├── exam.py                 # Exam & ExamQuestion models
    ├── session.py              # ExamSession, StudentAnswer, AutosaveSnapshot models
    └── proctoring.py           # ProctoringLog model
```

### B. Spesifikasi Model SQLAlchemy 2.0
1. **`User`** (`backend/app/models/user.py`):
   - Kolom: `id`, `identifier` (unique), `email` (unique), `password_hash`, `full_name`, `role` (`Enum('admin', 'teacher', 'student')`), `avatar_url`, `is_active`, `created_at`, `updated_at`.
2. **`Class` & `ClassMember`** (`backend/app/models/academic.py`):
   - Relasi: One-to-Many `Class` ke `ClassMember`, Many-to-One `User`.
3. **`QuestionBank` & `Question`** (`backend/app/models/question.py`):
   - Kolom: `question_type` (`multiple_choice`, `short_essay`, `long_essay`), `options_json` (JSON), `rubric_json` (JSON), `difficulty`, `default_points`.
4. **`Exam` & `ExamQuestion`** (`backend/app/models/exam.py`):
   - Kolom: `duration_minutes`, `start_time`, `end_time`, `randomize_questions`, `randomize_options`, `proctoring_level`, `explanation_policy`, `status`.
5. **`ExamSession` & `StudentAnswer`** (`backend/app/models/session.py`):
   - Kolom: `status` (`in_progress`, `submitted`, `grading_in_progress`, `graded`, `aborted`), `total_score`, `integrity_score`, `auto_score`, `teacher_override_score`, `ai_confidence_level`.
6. **`ProctoringLog`** (`backend/app/models/proctoring.py`):
   - Kolom: `event_type`, `camera_source`, `severity`, `duration_seconds`, `snapshot_url`, `event_timestamp`, `reviewed_by_teacher`.

---

## 3. Acceptance Criteria (Gherkin Scenarios)

```gherkin
Scenario: Inisialisasi koneksi database dan query model
  Given Database MySQL pada XAMPP port 3306 sedang berjalan
  When Backend menginisialisasi SQLAlchemy engine dan SessionLocal
  Then Koneksi berhasil terbentuk tanpa timeout
  And Query terhadap model User mengembalikan daftar pengguna awal dari seeder
```

---

## 4. Verification Steps
1. Jalankan inisialisasi schema: `mysql -u root examind < database/schema.sql`
2. Jalankan seeder data awal: `mysql -u root examind < database/seeds/01_initial_seeds.sql`
3. Jalankan unit test Pytest untuk memverifikasi CRUD session DB: `pytest backend/tests/test_database.py`
