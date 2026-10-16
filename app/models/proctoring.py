from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Enum, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class ProctoringLog(Base):
    __tablename__ = "proctoring_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(
        Enum(
            "face_absent",
            "multiple_faces",
            "gaze_away",
            "tab_switch",
            "fullscreen_exit",
            "suspicious_object",
            "companion_disconnected",
            name="proctoring_event_types",
        ),
        nullable=False,
    )
    camera_source = Column(
        Enum("primary_camera", "secondary_camera", "system_event", name="camera_sources"),
        nullable=False,
    )
    severity = Column(Enum("low", "medium", "high", name="violation_severities"), nullable=False)
    duration_seconds = Column(Integer, default=1)
    snapshot_url = Column(String(255), nullable=True)
    event_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_by_teacher = Column(Boolean, default=False)
    teacher_verdict = Column(
        Enum("ignored_false_positive", "confirmed_violation", "pending", name="teacher_verdicts"),
        default="pending",
    )

    # Relationships
    session = relationship("ExamSession", back_populates="proctoring_logs")
