-- =============================================================================
-- EXAMIND SaaS Migration: Multi-tenancy & Super Admin Role
-- Target: MySQL 8.0+ (served via XAMPP on default port 3306)
-- Encoding: UTF-8 Unicode (utf8mb4_unicode_ci)
-- =============================================================================

USE examind;

-- 1. Create tenants table
CREATE TABLE IF NOT EXISTS tenants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL COMMENT 'Nama Sekolah / Institusi',
    code VARCHAR(50) NOT NULL UNIQUE COMMENT 'Kode Subdomain / Identifier Sekolah, misal: sman1jkt',
    domain VARCHAR(100) NULL UNIQUE,
    subscription_plan ENUM('starter', 'pro', 'enterprise') DEFAULT 'pro',
    subscription_status ENUM('active', 'trial', 'past_due', 'canceled') DEFAULT 'active',
    max_students INT DEFAULT 500,
    max_teachers INT DEFAULT 50,
    max_storage_gb INT DEFAULT 10,
    ai_credits_monthly INT DEFAULT 1000,
    ai_credits_used INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tenant_code (code),
    INDEX idx_tenant_status (subscription_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Insert Default Initial Tenant: SMA Negeri 1 Jakarta
INSERT INTO tenants (id, name, code, domain, subscription_plan, subscription_status, max_students, max_teachers, max_storage_gb, ai_credits_monthly, ai_credits_used, is_active)
VALUES (1, 'SMA Negeri 1 Jakarta', 'sman1jkt', 'sman1jkt.examind.sch.id', 'enterprise', 'active', 1000, 100, 50, 5000, 120, 1)
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- 3. Insert Second Demo Tenant: SMA Harapan Bangsa
INSERT INTO tenants (id, name, code, domain, subscription_plan, subscription_status, max_students, max_teachers, max_storage_gb, ai_credits_monthly, ai_credits_used, is_active)
VALUES (2, 'SMA Harapan Bangsa', 'shb-edu', 'shb.examind.sch.id', 'starter', 'active', 150, 15, 10, 800, 45, 1)
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- 4. Update users table: Modify role enum to include 'superadmin' and add tenant_id
ALTER TABLE users MODIFY COLUMN role ENUM('superadmin', 'admin', 'teacher', 'student') NOT NULL;

-- Add tenant_id if not exists
SET @dbname = DATABASE();
SET @tablename = "users";
SET @columnname = "tenant_id";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      TABLE_SCHEMA = @dbname
      AND TABLE_NAME = @tablename
      AND COLUMN_NAME = @columnname
  ) > 0,
  "SELECT 1",
  "ALTER TABLE users ADD COLUMN tenant_id INT NULL AFTER role, ADD CONSTRAINT fk_users_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE SET NULL"
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- 5. Associate existing users to Tenant 1
UPDATE users SET tenant_id = 1 WHERE tenant_id IS NULL AND role != 'superadmin';

-- 6. Insert Default Platform Super Admin
-- Password hash for "Password123!"
INSERT INTO users (identifier, email, password_hash, full_name, role, tenant_id, is_active)
VALUES ('superadmin', 'superadmin@examind.ai', '$2b$12$e8YkYxLw9J5kR7gL1b.2u.3qK4e0.wW2r7r7V0oE6a6Q5w0u1u4m2', 'Platform Super Administrator', 'superadmin', NULL, 1)
ON DUPLICATE KEY UPDATE role='superadmin', full_name='Platform Super Administrator';
