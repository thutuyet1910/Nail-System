"""Offline owner-password reset: run on the salon computer when the owner password is forgotten.

    cd backend
    python reset_owner_password.py

It needs access to this computer and to the salon database (DATABASE_URL, same as the app). The new
password is typed twice at a hidden prompt, never passed on the command line, and every owner session is
revoked. This is the supported recovery path until text-message recovery exists.
"""
import getpass
import sys

import auth_service
from database import SessionLocal


def main() -> int:
    first = getpass.getpass("New owner password: ")
    if first != getpass.getpass("Repeat new owner password: "):
        print("The passwords do not match. Nothing was changed.")
        return 1
    db = SessionLocal()
    try:
        revoked = auth_service.reset_owner_password_offline(db, first)
    except Exception as exc:  # validation (length) or "no credential yet"
        print(f"Nothing was changed: {getattr(exc, 'detail', exc)}")
        return 1
    finally:
        db.close()
    print(f"Owner password changed. {revoked} owner session(s) were signed out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
