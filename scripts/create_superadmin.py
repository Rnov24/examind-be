#!/usr/bin/env python3
"""Create a superadmin user (idempotent).

Usage:
    DATABASE_URL='mysql+pymysql://...' python scripts/create_superadmin.py \
        --email me@rijal.work --password 'secret' [--name "Rijal"]

Tables are created first via SQLAlchemy metadata (no dummy data seeded).
Safe to re-run: skips if the email already exists.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine, SessionLocal, Base  # noqa: E402
import app.models  # noqa: E402,F401  (register all models)
from app.core.security import get_password_hash  # noqa: E402
from app.models.user import User  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Create EXAMIND superadmin")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--name", default="Superadmin")
    ap.add_argument("--identifier", default=None)
    args = ap.parse_args()

    print("Ensuring tables exist...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == args.email).first()
        if existing:
            print(f"User {args.email} already exists (id={existing.id}, role={existing.role}). No changes.")
            return 0
        identifier = args.identifier or (
            "SUPERADMIN-" + args.email.split("@")[0].upper().replace(".", "-")[:24]
        )
        user = User(
            identifier=identifier,
            email=args.email,
            password_hash=get_password_hash(args.password),
            full_name=args.name,
            role="superadmin",
            tenant_id=None,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Superadmin created: {user.email} (id={user.id})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
