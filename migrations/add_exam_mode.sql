-- Two exam modes: 'live' (all students simultaneously at start_time,
-- shared clock) and 'non_live' (each student starts independently inside
-- the [start_time, end_time] window, personal clock from their begun_at,
-- hard-capped at end_time). Existing exams are 'live' — behavior unchanged.
-- Run on the production TiDB `examind` database.
ALTER TABLE exams
  ADD COLUMN exam_mode ENUM('live', 'non_live') NOT NULL DEFAULT 'live'
  AFTER proctoring_level;
