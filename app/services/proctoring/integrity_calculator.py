from typing import List
from app.models.proctoring import ProctoringLog

DEDUCTION_MAP = {
    "tab_switch": 5,
    "fullscreen_exit": 5,
    "face_absent": 8,
    "multiple_faces": 15,
    "suspicious_object": 20,
    "phone_detected": 20,
    "gaze_away": 4,
    "companion_disconnected": 10,
}

SEVERITY_MULTIPLIER = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.5,
}


def calculate_session_integrity(logs: List[ProctoringLog]) -> int:
    """Calculates integrity score [0 - 100] based on violation frequency and severity.

    Ignored false positives by teacher do not contribute to penalty.
    """
    total_deduction = 0.0

    for log in logs:
        if log.teacher_verdict == "ignored_false_positive":
            continue

        base_penalty = DEDUCTION_MAP.get(log.event_type, 5)
        multiplier = SEVERITY_MULTIPLIER.get(log.severity, 1.0)
        total_deduction += base_penalty * multiplier

    score = max(0, int(round(100.0 - total_deduction)))
    return score
