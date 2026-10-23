-- Track when a student actually begins answering (after the camera-setup
-- wizard) so preparation time never counts against the exam duration.
-- Run on the production TiDB `examind` database.

ALTER TABLE exam_sessions
  ADD COLUMN begun_at DATETIME NULL AFTER start_time;
