import json
from typing import Dict, List, Set, Any
from fastapi import WebSocket


class WebSocketHub:
    """Manages real-time WebSocket connections across live monitoring, companion pairing, and student alerts."""

    def __init__(self):
        # exam_id -> list of teacher websockets
        self.exam_monitors: Dict[int, List[WebSocket]] = {}
        # session_id -> list of student websockets
        self.student_listeners: Dict[int, List[WebSocket]] = {}
        # session_id -> companion websocket
        self.companion_streams: Dict[int, WebSocket] = {}

    async def connect_monitor(self, exam_id: int, websocket: WebSocket):
        await websocket.accept()
        if exam_id not in self.exam_monitors:
            self.exam_monitors[exam_id] = []
        self.exam_monitors[exam_id].append(websocket)

    def disconnect_monitor(self, exam_id: int, websocket: WebSocket):
        if exam_id in self.exam_monitors and websocket in self.exam_monitors[exam_id]:
            self.exam_monitors[exam_id].remove(websocket)

    async def connect_student(self, session_id: int, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.student_listeners:
            self.student_listeners[session_id] = []
        self.student_listeners[session_id].append(websocket)

    def disconnect_student(self, session_id: int, websocket: WebSocket):
        if session_id in self.student_listeners and websocket in self.student_listeners[session_id]:
            self.student_listeners[session_id].remove(websocket)

    async def connect_companion(self, session_id: int, websocket: WebSocket):
        await websocket.accept()
        self.companion_streams[session_id] = websocket

    def disconnect_companion(self, session_id: int):
        self.companion_streams.pop(session_id, None)

    async def broadcast_to_exam(self, exam_id: int, message: Dict[str, Any]):
        """Broadcasts event to all active teacher monitors for the exam."""
        if exam_id in self.exam_monitors:
            dead_sockets = []
            for ws in self.exam_monitors[exam_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_sockets.append(ws)
            for ws in dead_sockets:
                self.exam_monitors[exam_id].remove(ws)

    async def send_to_student(self, session_id: int, message: Dict[str, Any]):
        """Sends warning/direct message to a specific student session."""
        if session_id in self.student_listeners:
            dead_sockets = []
            for ws in self.student_listeners[session_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_sockets.append(ws)
            for ws in dead_sockets:
                self.student_listeners[session_id].remove(ws)

    async def send_to_companion(self, session_id: int, message: Dict[str, Any]):
        """Sends warning/alert to secondary companion device."""
        if session_id in self.companion_streams:
            try:
                await self.companion_streams[session_id].send_json(message)
            except Exception:
                self.companion_streams.pop(session_id, None)


ws_hub = WebSocketHub()
