"""Seed the three application roles into the database.

Idempotent: safe to run multiple times. Existing roles are never modified
or deleted. Only missing roles are inserted.

Usage (from backend/):
    python scripts/seed_roles.py
"""

import sys
from pathlib import Path

# Allow imports from backend/app without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.models.user import Role

ROLES = ["EMPLOYEE", "HR", "ADMIN"]


def seed_roles() -> None:
    db = SessionLocal()
    try:
        existing = {r.name for r in db.query(Role).all()}
        missing = [name for name in ROLES if name not in existing]

        for name in missing:
            db.add(Role(name=name))

        db.commit()
        print(f"Roles ensured: {', '.join(ROLES)}")
        if missing:
            print(f"  Inserted: {', '.join(missing)}")
        else:
            print("  No changes — all roles already present.")
    except Exception as exc:
        db.rollback()
        print(f"ERROR: role seeding failed — {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed_roles()
