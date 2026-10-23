import json
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.core.database import SessionLocal
from app.models.session import ExamSession
from app.models.proctoring import ProctoringLog
from app.services.proctoring.websocket_hub import ws_hub
from app.services.proctoring.storage import save_snapshot_base64
from app.services.proctoring.integrity_calculator import calculate_session_integrity

router = APIRouter(tags=["WebSockets"])


@router.websocket("/ws/exam/{exam_id}/live-monitor")
async def ws_live_monitor(websocket: WebSocket, exam_id: int):
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
async def ws_student_alerts(websocket: WebSocket, session_id: int):
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
    await ws_hub.connect_companion(session_id, websocket)

    # Resolve exam_id and student details
    db = SessionLocal()
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    exam_id = session.exam_id if session else None
    student_name = session.student.full_name if session and session.student else "Siswa"
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
