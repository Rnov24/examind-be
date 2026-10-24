-- Persist the mobile companion pairing token on the exam session so the
-- companion WebSocket can validate it (previously the token was regenerated
-- per /start call and never checked on connect).
ALTER TABLE exam_sessions ADD COLUMN pairing_token VARCHAR(64) NULL AFTER companion_paired;
