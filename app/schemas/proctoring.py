from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict


class ProctoringEventCreate(BaseModel):
    session_id: int
    event_type: str  # face_absent, multiple_faces, gaze_away, tab_switch, fullscreen_exit, suspicious_object, companion_disconnected
    camera_source: str  # primary_camera, secondary_camera, system_event
    severity: str = "medium"  # low, medium, high
    duration_seconds: int = 1
    snapshot_base64: Optional[str] = None


class ProctoringLogResponse(BaseModel):
    id: int
    session_id: int
    event_type: str
    camera_source: str
    severity: str
    duration_seconds: int
    snapshot_url: Optional[str] = None
    event_timestamp: datetime
    reviewed_by_teacher: bool
    teacher_verdict: str
    student_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WarningRequest(BaseModel):
    session_id: int
    message_text: str
    urgency: str = "high"


class VerdictUpdateRequest(BaseModel):
    verdict: str  # ignored_false_positive, confirmed_violation, pending


class SessionTolerateRequest(BaseModel):
    session_id: int
    notes: Optional[str] = "Toleransi wajar oleh pengawas (false positive / gerakan alami)"


class SessionDisqualifyRequest(BaseModel):
    session_id: int
    reason: str
    notes: Optional[str] = None

