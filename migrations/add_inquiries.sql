-- Consultation inquiries from the public landing page.
-- The landing form previously never reached the server (local state only);
-- this table backs the real POST /api/v1/public/inquiries endpoint.
CREATE TABLE IF NOT EXISTS inquiries (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    role VARCHAR(150) NULL,
    school_name VARCHAR(200) NOT NULL,
    whatsapp VARCHAR(30) NOT NULL,
    package_interest VARCHAR(200) NULL,
    student_count_range VARCHAR(100) NULL,
    notes TEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'new',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_inquiries_whatsapp (whatsapp),
    INDEX idx_inquiries_status (status),
    INDEX idx_inquiries_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
