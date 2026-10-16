-- =============================================================================
-- EXAMIND Database Schema Initialization
-- Target: MySQL 8.0+ (served via XAMPP on default port 3306)
-- Encoding: UTF-8 Unicode (utf8mb4_unicode_ci)
-- =============================================================================

CREATE DATABASE IF NOT EXISTS examind
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE examind;

-- -----------------------------------------------------------------------------
-- 1. Table: users
-- Mengelola data akun pengguna: Admin, Guru, dan Siswa
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    identifier VARCHAR(50) NOT NULL UNIQUE COMMENT 'NISN untuk Siswa, NIP/NUPTK untuk Guru, Username untuk Admin',
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    role ENUM('admin', 'teacher', 'student') NOT NULL,
    avatar_url VARCHAR(255) NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_role (role),
    INDEX idx_user_identifier (identifier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 2. Table: classes & class_members
-- Mengelola data kelas dan keanggotaan siswa/guru
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS classes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT 'Contoh: XII MIPA 1, XI IPS 2',
    grade_level VARCHAR(20) NOT NULL COMMENT '10, 11, 12, etc.',
    academic_year VARCHAR(20) NOT NULL COMMENT 'Contoh: 2026/2027',
    created_by INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS class_members (
    id INT AUTO_INCREMENT PRIMARY KEY,
    class_id INT NOT NULL,
    user_id INT NOT NULL,
    role ENUM('teacher', 'student') NOT NULL,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_class_user (class_id, user_id),
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 3. Table: question_banks & questions
-- Mengelola bank soal terpusat dan butir soal (PG & Esai)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS question_banks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    teacher_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    subject VARCHAR(100) NOT NULL COMMENT 'Contoh: Matematika, Fisika, Bahasa Indonesia',
    description TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bank_id INT NOT NULL,
    question_type ENUM('multiple_choice', 'short_essay', 'long_essay') NOT NULL,
    prompt TEXT NOT NULL COMMENT 'Konten pertanyaan (teks/markdown/latex)',
    options_json JSON NULL COMMENT 'Opsi PG: [{"id":"A","text":"..."},{"id":"B","text":"..."}]',
    correct_answer TEXT NULL COMMENT 'ID opsi yang benar (PG) atau kunci ideal (Esai)',
    rubric_json JSON NULL COMMENT 'Rubrik grading esai: kriteria dimensi & kata kunci',
    explanation TEXT NULL COMMENT 'Penjelasan konsep mengapa jawaban ini benar/salah',
    difficulty ENUM('easy', 'medium', 'hard') DEFAULT 'medium',
    default_points DECIMAL(5,2) DEFAULT 10.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bank_id) REFERENCES question_banks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 4. Table: exams & exam_questions
-- Paket ujian, jadwal, kebijakan pengawasan, dan alokasi butir soal
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exams (
    id INT AUTO_INCREMENT PRIMARY KEY,
    teacher_id INT NOT NULL,
    class_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NULL,
    duration_minutes INT NOT NULL COMMENT 'Durasi pengerjaan dalam menit',
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    randomize_questions BOOLEAN DEFAULT TRUE,
    randomize_options BOOLEAN DEFAULT TRUE,
    proctoring_level ENUM('disabled', 'single_camera', 'dual_camera') DEFAULT 'dual_camera',
    explanation_policy ENUM('instant', 'after_exam_closed') DEFAULT 'after_exam_closed',
    status ENUM('draft', 'published', 'in_progress', 'completed', 'archived') DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS exam_questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    exam_id INT NOT NULL,
    question_id INT NOT NULL,
    order_index INT NOT NULL,
    allocated_points DECIMAL(5,2) NOT NULL,
    UNIQUE KEY uq_exam_question (exam_id, question_id),
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 5. Table: exam_sessions, student_answers, & autosave_snapshots
-- Sesi ujian aktif, rekaman jawaban, nilai, dan autosave
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exam_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    exam_id INT NOT NULL,
    student_id INT NOT NULL,
    start_time DATETIME NOT NULL,
    submit_time DATETIME NULL,
    status ENUM('in_progress', 'submitted', 'grading_in_progress', 'graded', 'aborted') DEFAULT 'in_progress',
    total_score DECIMAL(5,2) DEFAULT 0.00,
    integrity_score INT DEFAULT 100 COMMENT 'Nilai integritas 0 - 100%',
    companion_paired BOOLEAN DEFAULT FALSE,
    client_ip VARCHAR(45) NULL,
    user_agent TEXT NULL,
    UNIQUE KEY uq_student_exam (exam_id, student_id),
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS student_answers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    question_id INT NOT NULL,
    student_response TEXT NULL,
    is_correct BOOLEAN NULL COMMENT 'Untuk PG',
    auto_score DECIMAL(5,2) DEFAULT 0.00,
    teacher_override_score DECIMAL(5,2) NULL,
    final_score DECIMAL(5,2) DEFAULT 0.00,
    ai_confidence_level ENUM('low', 'medium', 'high') NULL,
    ai_grading_rationale TEXT NULL,
    ai_explanation TEXT NULL,
    teacher_notes TEXT NULL,
    graded_at DATETIME NULL,
    UNIQUE KEY uq_session_question (session_id, question_id),
    FOREIGN KEY (session_id) REFERENCES exam_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS autosave_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL UNIQUE,
    answers_payload JSON NOT NULL,
    last_saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES exam_sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 6. Table: proctoring_logs
-- Catatan insiden pengawasan cerdas (snapshot & timestamp)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proctoring_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    event_type ENUM(
        'face_absent',
        'multiple_faces',
        'gaze_away',
        'tab_switch',
        'fullscreen_exit',
        'suspicious_object',
        'companion_disconnected'
    ) NOT NULL,
    camera_source ENUM('primary_camera', 'secondary_camera', 'system_event') NOT NULL,
    severity ENUM('low', 'medium', 'high') NOT NULL,
    duration_seconds INT DEFAULT 1,
    snapshot_url VARCHAR(255) NULL,
    event_timestamp DATETIME NOT NULL,
    reviewed_by_teacher BOOLEAN DEFAULT FALSE,
    teacher_verdict ENUM('ignored_false_positive', 'confirmed_violation', 'pending') DEFAULT 'pending',
    FOREIGN KEY (session_id) REFERENCES exam_sessions(id) ON DELETE CASCADE,
    INDEX idx_session_event (session_id, event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
