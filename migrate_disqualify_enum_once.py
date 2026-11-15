"""Apply the disqualify-enum migration to production TiDB (one-off).

Adds 'teacher_disqualification' to proctoring_logs.event_type and
'human_supervisor' to proctoring_logs.camera_source. Without these values
POST /proctoring/session/disqualify fails on live TiDB with
DataError 1265 ("Data truncated for column 'event_type'") and the session
stays in_progress.

Idempotent: re-running the MODIFY with the same enum lists is a no-op.
Run via: modal run migrate_disqualify_enum_once.py::migrate_disqualify_enum
"""
import modal

image = (
    modal.Image.debian_slim()
    .pip_install_from_requirements("/home/hatch/workspace/examind-be/requirements.txt")
    .add_local_dir("/home/hatch/workspace/examind-be/app", remote_path="/root/app")
    .add_local_file(
        "/home/hatch/workspace/examind-be/migrations/add_disqualify_enums.sql",
        remote_path="/root/add_disqualify_enums.sql",
    )
)

app = modal.App("examind-migrate-disqualify-enum")


def _column_types(db):
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT COLUMN_NAME, COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'proctoring_logs' "
            "AND COLUMN_NAME IN ('event_type', 'camera_source') "
            "ORDER BY COLUMN_NAME"
        )
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _migrate_impl():
    import sys
    sys.path.insert(0, "/root")
    from sqlalchemy import text
    from app.core.database import SessionLocal

    with open("/root/add_disqualify_enums.sql", encoding="utf-8") as f:
        sql = f.read()

    db = SessionLocal()
    try:
        print("BEFORE:")
        for column, col_type in _column_types(db).items():
            print(f"  {column}: {col_type}")

        # The file holds two ALTER statements plus comments; strip the
        # comment lines, then run each statement separately
        # (SQLAlchemy text() takes one at a time).
        sql_no_comments = "\n".join(
            line for line in sql.splitlines() if not line.strip().startswith("--")
        )
        statements = [stmt.strip() for stmt in sql_no_comments.split(";") if stmt.strip()]
        for stmt in statements:
            db.execute(text(stmt))
        db.commit()

        print("AFTER:")
        after = _column_types(db)
        for column, col_type in after.items():
            print(f"  {column}: {col_type}")

        assert "teacher_disqualification" in after["event_type"], (
            f"event_type enum missing teacher_disqualification: {after['event_type']}"
        )
        assert "human_supervisor" in after["camera_source"], (
            f"camera_source enum missing human_supervisor: {after['camera_source']}"
        )
        print("DONE: disqualify enums present in proctoring_logs")
        return after
    finally:
        db.close()


@app.function(image=image, secrets=[modal.Secret.from_name("examind-env")], timeout=300)
def migrate_disqualify_enum():
    return _migrate_impl()


@app.local_entrypoint()
def main():
    migrate_disqualify_enum.remote()
