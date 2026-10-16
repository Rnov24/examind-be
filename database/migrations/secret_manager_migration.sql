-- EXAMIND Secret Manager Migration for Super Admin
-- Stores third-party API keys (Gemini, Resend, OpenAI, etc.) encrypted at rest with Fernet/AES

CREATE TABLE IF NOT EXISTS system_secrets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    key_name VARCHAR(100) NOT NULL UNIQUE,
    service_name VARCHAR(50) NOT NULL,
    encrypted_value TEXT NOT NULL,
    description VARCHAR(255) NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_secret_service (service_name),
    INDEX idx_secret_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
