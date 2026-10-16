import os
import base64
import uuid
from datetime import datetime

# Local directory for saving proctoring violation snapshots
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "snapshots")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def save_snapshot_base64(session_id: int, base64_str: str) -> str:
    """Decodes base64 image and saves to disk, returning relative/accessible URL."""
    if not base64_str:
        return ""

    try:
        # Strip header if present (e.g. data:image/jpeg;base64,)
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]

        image_data = base64.b64decode(base64_str)
        filename = f"{session_id}_{uuid.uuid4().hex[:8]}_{int(datetime.utcnow().timestamp())}.jpg"
        filepath = os.path.join(UPLOAD_DIR, filename)

        with open(filepath, "wb") as f:
            f.write(image_data)

        return f"/uploads/snapshots/{filename}"
    except Exception as exc:
        print(f"[Storage] Failed to save snapshot: {exc}")
        return ""
