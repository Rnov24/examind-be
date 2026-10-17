-- =============================================================================
-- EXAMIND Migration: Add Performance Indexes for High-Traffic SQL Queries
-- Target: TiDB Cloud (Production) / MySQL 8.0+ / XAMPP
-- Database: examind
--
-- Manual Execution Command (run by Jal):
--   mysql -h <tidb_host> -P 4000 -u <user> -p examind < migrations/add_performance_indexes.sql
-- or for local XAMPP MySQL CLI:
--   mysql -u root examind < migrations/add_performance_indexes.sql
-- =============================================================================

USE examind;

-- Helper procedure for idempotent index creation in standard MySQL / MariaDB / TiDB
DELIMITER $$

DROP PROCEDURE IF EXISTS CreateIndexIfNotExists $$
CREATE PROCEDURE CreateIndexIfNotExists(
    IN target_table VARCHAR(64),
    IN index_name VARCHAR(64),
    IN column_list VARCHAR(255)
)
BEGIN
    DECLARE index_count INT DEFAULT 0;

    SELECT COUNT(1) INTO index_count
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = target_table
      AND INDEX_NAME = index_name;

    IF index_count = 0 THEN
        SET @sql = CONCAT('CREATE INDEX ', index_name, ' ON ', target_table, ' (', column_list, ')');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        SELECT CONCAT('Created index: ', index_name, ' on ', target_table) AS status;
    ELSE
        SELECT CONCAT('Index already exists: ', index_name, ' on ', target_table) AS status;
    END IF;
END $$

DELIMITER ;

-- =============================================================================
-- 1. EXAM SESSIONS & ANSWERS INDEXES
-- =============================================================================
-- ExamSession foreign keys and status queries (critical for student exams, grading, and admin stats)
CALL CreateIndexIfNotExists('exam_sessions', 'ix_exam_sessions_exam_id', 'exam_id');
CALL CreateIndexIfNotExists('exam_sessions', 'ix_exam_sessions_student_id', 'student_id');
CALL CreateIndexIfNotExists('exam_sessions', 'ix_exam_sessions_status', 'status');
CALL CreateIndexIfNotExists('exam_sessions', 'ix_exam_sessions_exam_status', 'exam_id, status');

-- StudentAnswer foreign keys and confidence filtering (critical for async AI grading and grading dashboard)
CALL CreateIndexIfNotExists('student_answers', 'ix_student_answers_session_id', 'session_id');
CALL CreateIndexIfNotExists('student_answers', 'ix_student_answers_question_id', 'question_id');
CALL CreateIndexIfNotExists('student_answers', 'ix_student_answers_confidence', 'ai_confidence_level');

-- =============================================================================
-- 2. QUESTIONS & QUESTION BANKS INDEXES
-- =============================================================================
-- QuestionBank teacher filtering
CALL CreateIndexIfNotExists('question_banks', 'ix_question_banks_teacher_id', 'teacher_id');

-- Question bank_id and question_type filtering
CALL CreateIndexIfNotExists('questions', 'ix_questions_bank_id', 'bank_id');
CALL CreateIndexIfNotExists('questions', 'ix_questions_question_type', 'question_type');

-- =============================================================================
-- 3. EXAMS & EXAM QUESTIONS INDEXES
-- =============================================================================
-- Exam teacher, class, and status filtering
CALL CreateIndexIfNotExists('exams', 'ix_exams_teacher_id', 'teacher_id');
CALL CreateIndexIfNotExists('exams', 'ix_exams_class_id', 'class_id');
CALL CreateIndexIfNotExists('exams', 'ix_exams_status', 'status');
CALL CreateIndexIfNotExists('exams', 'ix_exams_class_status', 'class_id, status');

-- ExamQuestion question_id lookup
CALL CreateIndexIfNotExists('exam_questions', 'ix_exam_questions_question_id', 'question_id');

-- =============================================================================
-- 4. PROCTORING LOGS INDEXES
-- =============================================================================
-- ProctoringLog session lookup, event timestamp sorting, and verdict filtering
CALL CreateIndexIfNotExists('proctoring_logs', 'ix_proctoring_logs_session_id', 'session_id');
CALL CreateIndexIfNotExists('proctoring_logs', 'ix_proctoring_logs_event_timestamp', 'event_timestamp');
CALL CreateIndexIfNotExists('proctoring_logs', 'ix_proctoring_logs_teacher_verdict', 'teacher_verdict');
CALL CreateIndexIfNotExists('proctoring_logs', 'ix_proctoring_logs_sess_verdict', 'session_id, teacher_verdict');

-- =============================================================================
-- 5. ACADEMIC CLASSES & MEMBERSHIPS INDEXES
-- =============================================================================
-- Class creator lookup
CALL CreateIndexIfNotExists('classes', 'ix_classes_created_by', 'created_by');

-- ClassMember student lookup (essential for active exams lookup for students)
CALL CreateIndexIfNotExists('class_members', 'ix_class_members_user_id', 'user_id');
CALL CreateIndexIfNotExists('class_members', 'ix_class_members_user_role', 'user_id, role');

-- =============================================================================
-- 6. TENANTS & USERS INDEXES
-- =============================================================================
-- Tenant plan and status filtering (superadmin finance & stats)
CALL CreateIndexIfNotExists('tenants', 'ix_tenants_subscription_plan', 'subscription_plan');
CALL CreateIndexIfNotExists('tenants', 'ix_tenants_subscription_status', 'subscription_status');
CALL CreateIndexIfNotExists('tenants', 'ix_tenants_is_active', 'is_active');
CALL CreateIndexIfNotExists('tenants', 'ix_tenants_created_at', 'created_at');

-- User active status filtering
CALL CreateIndexIfNotExists('users', 'ix_users_is_active', 'is_active');
CALL CreateIndexIfNotExists('users', 'ix_users_tenant_role', 'tenant_id, role');

-- Clean up helper procedure
DROP PROCEDURE IF EXISTS CreateIndexIfNotExists;
