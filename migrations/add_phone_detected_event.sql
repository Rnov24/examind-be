-- Add 'phone_detected' to proctoring_logs.event_type enum
-- (MediaPipe object detection on the client now distinguishes a detected
-- mobile phone from the generic suspicious_object bucket.)
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
    'phone_detected'
  ) NOT NULL;
