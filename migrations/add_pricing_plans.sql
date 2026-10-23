-- =============================================================================
-- EXAMIND Migration: Pricing Plans Table (superadmin-editable)
-- Target: MySQL 8.0+ / TiDB (Default Port: 3306 / 4000)
-- Database: examind
-- Encoding: UTF-8 Unicode (utf8mb4_unicode_ci)
--
-- Manual Execution Command (run by Jal):
--   mysql -h 127.0.0.1 -P 3306 -u root -p examind < migrations/add_pricing_plans.sql
-- or via XAMPP MySQL CLI:
--   mysql -u root examind < migrations/add_pricing_plans.sql
--
-- Notes:
--   Rows are seeded automatically by the application on first read
--   (app/services/billing/pricing_plans.py) from DEFAULT_PRICING_PLANS
--   in app/core/billing_defaults.py, so no INSERT statements are needed here.
-- =============================================================================

USE examind;

CREATE TABLE IF NOT EXISTS pricing_plans (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    price_monthly INT NOT NULL DEFAULT 0,
    price_annually INT NOT NULL DEFAULT 0,
    max_students INT NOT NULL DEFAULT 0,
    max_teachers INT NOT NULL DEFAULT 0,
    max_storage_gb INT NOT NULL DEFAULT 0,
    ai_credits_monthly INT NOT NULL DEFAULT 0,
    proctoring_type VARCHAR(30) NOT NULL DEFAULT 'single_camera' COMMENT 'single_camera | dual_camera',
    description TEXT NULL,
    features JSON NULL COMMENT 'JSON array of feature strings',
    is_popular TINYINT(1) NOT NULL DEFAULT 0,
    sort_order INT NOT NULL DEFAULT 0,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_pricing_plans_popular (is_popular),
    INDEX idx_pricing_plans_sort (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
