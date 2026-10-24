"""Proctoring WebSockets — authenticated.

Tenant isolation used to be absent here entirely: anyone who guessed an
exam/session id could connect to the live monitor (student names, snapshots,
violations), listen on a student's alert channel, or connect as a
"companion" and inject fake violations into any session.

- /ws/exam/{exam_id}/live-monitor and /ws/student/{session_id}/alerts now
  require the caller's JWT as ?token= (the same access token the REST API
  uses) and enforce the same exam/session access rules as the REST
  endpoints (see app/core/tenant_scope.py). Connections that fail auth or
  access are closed with 4401 / 4403.
  FRONTEND FOLLOW-UP REQUIRED: the monitor page and the student exam
  workspace must append ?token=<accessToken> to these two URLs
  (fe: monitor page + src/stores/proctoringStore.ts initStudentWebSocket).
  Until then, live monitoring will not connect.
- /ws/proctoring/{session_id}/companion validates the pairing token
  against the token persisted on the session (see ExamSession.pairing_token).
  A wrong or missing token is rejected with 4403. Sessions created before
  the pairing_token column existed (NULL) are accepted during the migration
  window; all new sessions carry a token.
"""
import json
from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.core.database import SessionLocal
from app.core.exceptions import AppException
from app.core.security import decode_access_token
from app.core.tenant_scope import require_exam, require_session
from app.models.session import ExamSession
from app.models.proctoring import ProctoringLog
from app.models.user import User
from app.services.proctoring.websocket_hub import ws_hub
from app.services.proctoring.storage import save_snapshot_base64
from app.services.proctoring.integrity_calculator import calculate_session_integrity

router = APIRouter(tags=["WebSockets"])

WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN = 4403
WS_CLOSE_NOT_FOUND = 4404


def _authenticate_ws(token: str | None):
    """Resolve a JWT (?token=) to a light namespace with the fields the
    tenant-scope helpers need, or None when missing/invalid/inactive."""
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or payload.get("sub") is None:
        return None
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(payload["sub"])).first()
        if not user or not user.is_active:
            return None
        return SimpleNamespace(id=user.id, role=user.role, tenant_id=user.tenant_id)
    finally:
        db.close()


def _check_access(db, user, checker, *args):
    """Run a tenant_scope require_* checker; returns True when allowed."""
    try:
        checker(db, user, *args)
        return True
    except AppException:
        return False


@router.websocket("/ws/exam/{exam_id}/live-monitor")
async def ws_live_monitor(websocket: WebSocket, exam_id: int, token: str = Query(None)):
    user = _authenticate_ws(token)
    if user is None:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return
    db = SessionLocal()
    try:
        allowed = _check_access(db, user, require_exam, exam_id)
    finally:
        db.close()
    if not allowed:
        await websocket.close(code=WS_CLOSE_FORBIDDEN)
        return

    await ws_hub.connect_monitor(exam_id, websocket)
    try:
        while True:
            # Keep-alive heartbeat listener
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_hub.disconnect_monitor(exam_id, websocket)
    except Exception:
        ws_hub.disconnect_monitor(exam_id, websocket)


@router.websocket("/ws/student/{session_id}/alerts")
async def ws_student_alerts(websocket: WebSocket, session_id: int, token: str = Query(None)):
    user = _authenticate_ws(token)
    if user is None:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return
    db = SessionLocal()
    try:
        allowed = _check_access(db, user, require_session, session_id)
    finally:
        db.close()
    if not allowed:
        await websocket.close(code=WS_CLOSE_FORBIDDEN)
        return

    await ws_hub.connect_student(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_hub.disconnect_student(session_id, websocket)
    except Exception:
        ws_hub.disconnect_student(session_id, websocket)


@router.websocket("/ws/proctoring/{session_id}/companion")
async def ws_companion(websocket: WebSocket, session_id: int, token: str = Query(None)):
    # Validate the pairing token BEFORE accepting: the companion camera is
    # allowed to inject violation events that change a student's integrity
    # score, so an unchecked connection could tank any student's score.
    db = SessionLocal()
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        db.close()
        await websocket.close(code=WS_CLOSE_NOT_FOUND)
        return
    stored_token = session.pairing_token
    exam_id = session.exam_id
    student_name = session.student.full_name if session.student else "Siswa"
    db.close()
    if stored_token and token != stored_token:
        await websocket.close(code=WS_CLOSE_FORBIDDEN)
        return

    await ws_hub.connect_companion(session_id, websocket)

    # Mark the session as companion-paired
    db = SessionLocal()
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if session:
        session.companion_paired = True
        db.commit()
    db.close()

    # Notify student exam workspace that companion is paired
    await ws_hub.send_to_student(session_id, {
        "event": "COMPANION_PAIRED_SUCCESS",
        "payload": {"session_id": session_id, "status": "connected"}
    })

    # Notify teacher live monitor
    if exam_id:
        await ws_hub.broadcast_to_exam(exam_id, {
            "event": "COMPANION_STATUS_CHANGE",
            "payload": {"session_id": session_id, "companion_paired": True}
        })

    try:
        while True:
            raw_data = await websocket.receive_text()
            if not raw_data:
                continue

            try:
                msg = json.loads(raw_data)
            except Exception:
                continue

            msg_type = msg.get("type") or msg.get("event")

            # 1. Edge CV snapshot preview frame for teacher monitor
            if msg_type == "COMPANION_FRAME" and exam_id:
                frame_data = msg.get("frame") or msg.get("snapshot_url")
                metrics = msg.get("metrics", {})
                await ws_hub.broadcast_to_exam(exam_id, {
                    "event": "COMPANION_FRAME_UPDATE",
                    "payload": {
                        "session_id": session_id,
                        "snapshot_url": frame_data,
                        "metrics": metrics,
                    }
                })

            # 2. Edge CV detected violation directly on mobile client
            elif msg_type == "COMPANION_EDGE_VIOLATION" and exam_id:
                event_type = msg.get("event_type", "suspicious_object")
                severity = msg.get("severity", "medium")
                snapshot_base64 = msg.get("snapshot")
                snapshot_url = None
                if snapshot_base64:
                    snapshot_url = save_snapshot_base64(session_id, snapshot_base64)

                now = datetime.utcnow()
                db = SessionLocal()
                log = ProctoringLog(
                    session_id=session_id,
                    event_type=event_type,
                    camera_source="secondary_camera",
                    severity=severity,
                    duration_seconds=msg.get("duration_seconds", 1),
                    snapshot_url=snapshot_url,
                    event_timestamp=now,
                    reviewed_by_teacher=False,
                    teacher_verdict="pending",
                )
                db.add(log)
                db.commit()

                all_logs = db.query(ProctoringLog).filter(ProctoringLog.session_id == session_id).all()
                new_integrity = calculate_session_integrity(all_logs)
                s_rec = db.query(ExamSession).filter(ExamSession.id == session_id).first()
                if s_rec:
                    s_rec.integrity_score = new_integrity
                    db.commit()
                db.close()

                # Broadcast alert to teacher monitor
                await ws_hub.broadcast_to_exam(exam_id, {
                    "event": "PROCTORING_FLAG_ALERT",
                    "payload": {
                        "session_id": session_id,
                        "student_name": student_name,
                        "event_type": event_type,
                        "camera_source": "secondary_camera",
                        "severity": severity,
                        "duration_seconds": 1,
                        "timestamp": now.isoformat(),
                        "snapshot_url": snapshot_url,
                        "current_integrity_score": new_integrity,
                    }
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[CompanionWS] Unexpected disconnect/error: {e}")
    finally:
        ws_hub.disconnect_companion(session_id)
        db = SessionLocal()
        s_rec = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if s_rec:
            s_rec.companion_paired = False
            db.commit()
        db.close()

        await ws_hub.send_to_student(session_id, {
            "event": "COMPANION_DISCONNECTED",
            "payload": {"session_id": session_id}
        })
        if exam_id:
            await ws_hub.broadcast_to_exam(exam_id, {
                "event": "COMPANION_STATUS_CHANGE",
                "payload": {"session_id": session_id, "companion_paired": False}
            })
