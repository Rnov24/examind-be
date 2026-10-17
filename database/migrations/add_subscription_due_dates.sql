-- =============================================================================
-- EXAMIND Migration: Add Subscription Due Dates & Grace Period
-- Target: MySQL 8.0+ / TiDB (Default Port: 3306 / 4000)
-- Database: examind
-- Encoding: UTF-8 Unicode (utf8mb4_unicode_ci)
--
-- Manual Execution Command (run by Jal):
--   mysql -h 127.0.0.1 -P 3306 -u root -p examind < migrations/add_subscription_due_dates.sql
-- or via XAMPP MySQL CLI:
--   mysql -u root examind < migrations/add_subscription_due_dates.sql
-- =============================================================================

USE examind;

-- 1. Add subscription_due_date and grace_period_ends columns to tenants table
-- Direct ALTER TABLE for TiDB and modern MySQL (8.0.29+)
-- Using idempotent PREPARE / EXECUTE so it is safe to run on any MySQL / MariaDB / TiDB version.

SET @dbname = DATABASE();
SET @tablename = "tenants";

-- Add subscription_due_date column
SET @col1 = "subscription_due_date";
SET @prep1 = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @dbname
      AND TABLE_NAME = @tablename
      AND COLUMN_NAME = @col1
  ) > 0,
  "SELECT 1",
  "ALTER TABLE tenants ADD COLUMN subscription_due_date DATETIME NULL AFTER is_active"
));
PREPARE stmt1 FROM @prep1;
EXECUTE stmt1;
DEALLOCATE PREPARE stmt1;

-- Add grace_period_ends column
SET @col2 = "grace_period_ends";
SET @prep2 = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @dbname
      AND TABLE_NAME = @tablename
      AND COLUMN_NAME = @col2
  ) > 0,
  "SELECT 1",
  "ALTER TABLE tenants ADD COLUMN grace_period_ends DATETIME NULL AFTER subscription_due_date"
));
PREPARE stmt2 FROM @prep2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

-- 2. Create subscription_reminders_log table to track sent email stages and avoid duplicates
CREATE TABLE IF NOT EXISTS subscription_reminders_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tenant_id INT NOT NULL,
    stage VARCHAR(50) NOT NULL COMMENT 'Reminder stage: due_in_7, due_in_3, due_today, grace_period, expired',
    sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_reminders_tenant (tenant_id),
    INDEX idx_reminders_stage (stage),
    CONSTRAINT fk_reminders_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- MIGRATION NOTES & BACKFILL LOGIC (NOT AUTO-RUN)
-- =============================================================================
-- For existing tenants with NULL subscription_due_date:
--   subscription_due_date = created_at + 30 days
--   grace_period_ends     = subscription_due_date + 7 days
--
-- OPTION A: SQL Backfill Query (Run manually via MySQL CLI):
--
--   UPDATE tenants
--   SET
--       subscription_due_date = DATE_ADD(IFNULL(created_at, NOW()), INTERVAL 30 DAY),
--       grace_period_ends = DATE_ADD(DATE_ADD(IFNULL(created_at, NOW()), INTERVAL 30 DAY), INTERVAL 7 DAY)
--   WHERE subscription_due_date IS NULL;
--
-- OPTION B: Python CLI Utility Backfill (Run from repository root):
--
--   python3 -c "from app.core.database import SessionLocal; from app.services.billing.subscription_reminders import backfill_existing_tenants; db = SessionLocal(); count = backfill_existing_tenants(db); print(f'Successfully backfilled {count} tenants.'); db.close()"
-- =============================================================================
