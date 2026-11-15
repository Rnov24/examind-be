-- Add 'teacher_disqualification' to proctoring_logs.event_type enum and
-- 'human_supervisor' to proctoring_logs.camera_source enum
-- (A teacher-initiated disqualification writes a ProctoringLog with
-- event_type='teacher_disqualification', camera_source='human_supervisor'.
-- Without these values the INSERT fails on live TiDB with
-- DataError 1265 "Data truncated for column 'event_type'", the transaction
-- rolls back and the session stays in_progress.)
-- Run on the production TiDB `examind` database.

ALTER TABLE proctoring_logs
  MODIFY event_type ENUM(
    'face_absent',
    'multiple_faces',
    'gaze_away',
    'tab_switch',
    'fullscreen_exit',
    'suspicious_object',
    'companion_disconnected',
    'phone_detected',
    'teacher_disqualification'
  ) NOT NULL;

ALTER TABLE proctoring_logs
  MODIFY camera_source ENUM(
    'primary_camera',
    'secondary_camera',
    'system_event',
    'human_supervisor'
  ) NOT NULL;
