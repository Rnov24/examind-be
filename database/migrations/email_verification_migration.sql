-- =============================================================================
-- EXAMIND Email Verification & OTP Migration
-- Target: MySQL 8.0+ (served via XAMPP on default port 3306)
-- Encoding: UTF-8 Unicode (utf8mb4_unicode_ci)
-- =============================================================================

USE examind;

-- 1. Create email_verifications table
CREATE TABLE IF NOT EXISTS email_verifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(120) NOT NULL,
    otp_code VARCHAR(10) NOT NULL,
    purpose ENUM('email_verification', 'password_reset', 'login_2fa') DEFAULT 'email_verification',
    expires_at DATETIME NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_verification_email (email),
    INDEX idx_verification_purpose (purpose)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Add is_email_verified to users table if not exists
SET @dbname = DATABASE();
SET @tablename = "users";
SET @columnname = "is_email_verified";
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      TABLE_SCHEMA = @dbname
      AND TABLE_NAME = @tablename
      AND COLUMN_NAME = @columnname
  ) > 0,
  "SELECT 1",
  "ALTER TABLE users ADD COLUMN is_email_verified BOOLEAN DEFAULT FALSE AFTER is_active"
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- 3. Set existing demo users as verified
UPDATE users SET is_email_verified = TRUE WHERE is_email_verified = FALSE;
