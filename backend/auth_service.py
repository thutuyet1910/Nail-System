import hashlib
import hmac
import os
import secrets
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

import models
from timeutils import utc_now_naive


SESSION_COOKIE = "owner_session"
CSRF_COOKIE = "owner_csrf"
SESSION_TTL_MINUTES = int(os.getenv("OWNER_SESSION_TTL_MINUTES", "480"))
COOKIE_SECURE = os.getenv("OWNER_COOKIE_SECURE", "false").lower() == "true"
LOGIN_LIMIT = int(os.getenv("OWNER_LOGIN_ATTEMPTS_PER_5_MINUTES", "5"))
_attempts: dict[str, deque[datetime]] = defaultdict(deque)
_attempt_lock = threading.Lock()


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Owner password/PIN must be at least 8 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, expected_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(actual, bytes.fromhex(expected_hex))
    except (ValueError, TypeError):
        return False


def ensure_owner_credential(db: Session) -> None:
    if db.query(models.OwnerCredential).first():
        return
    configured_hash = os.getenv("OWNER_PASSWORD_HASH")
    bootstrap_password = os.getenv("OWNER_BOOTSTRAP_PASSWORD")
    if not configured_hash and not bootstrap_password:
        return
    password_hash = configured_hash or hash_password(bootstrap_password)
    db.add(models.OwnerCredential(username="owner", password_hash=password_hash, is_active=True))
    db.commit()


def _check_login_rate_limit(client_key: str) -> None:
    now = utc_now_naive()
    cutoff = now - timedelta(minutes=5)
    with _attempt_lock:
        attempts = _attempts[client_key]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if len(attempts) >= LOGIN_LIMIT:
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        attempts.append(now)


def login(db: Session, password: str, client_key: str) -> tuple[str, str, datetime]:
    _check_login_rate_limit(client_key)
    credential = db.query(models.OwnerCredential).filter(models.OwnerCredential.is_active.is_(True)).first()
    if not credential:
        raise HTTPException(status_code=503, detail="Owner authentication is not configured")
    if not verify_password(password, credential.password_hash):
        raise HTTPException(status_code=401, detail="Invalid owner credentials")
    with _attempt_lock:
        _attempts.pop(client_key, None)
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    expires_at = utc_now_naive() + timedelta(minutes=SESSION_TTL_MINUTES)
    db.add(models.OwnerSession(
        credential_id=credential.id,
        token_hash=_token_hash(session_token),
        csrf_hash=_token_hash(csrf_token),
        expires_at=expires_at,
        created_at=utc_now_naive(),
    ))
    db.commit()
    return session_token, csrf_token, expires_at


def set_session_cookies(response: Response, session_token: str, csrf_token: str, expires_at: datetime) -> None:
    max_age = max(0, int((expires_at - utc_now_naive()).total_seconds()))
    response.set_cookie(SESSION_COOKIE, session_token, max_age=max_age, httponly=True, secure=COOKIE_SECURE, samesite="strict", path="/")
    response.set_cookie(CSRF_COOKIE, csrf_token, max_age=max_age, httponly=False, secure=COOKIE_SECURE, samesite="strict", path="/")


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def authenticate_request(request: Request, db: Session, require_csrf: bool = False) -> models.OwnerSession:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Owner authentication required")
    session = db.query(models.OwnerSession).filter(models.OwnerSession.token_hash == _token_hash(raw_token)).first()
    if not session or session.revoked_at or session.expires_at <= utc_now_naive():
        raise HTTPException(status_code=401, detail="Owner session is invalid or expired")
    if require_csrf:
        header = request.headers.get("X-CSRF-Token", "")
        cookie = request.cookies.get(CSRF_COOKIE, "")
        if not header or not cookie or not hmac.compare_digest(header, cookie) or not hmac.compare_digest(_token_hash(header), session.csrf_hash):
            raise HTTPException(status_code=403, detail="CSRF validation failed")
    return session


def logout(db: Session, request: Request) -> None:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        return
    session = db.query(models.OwnerSession).filter(models.OwnerSession.token_hash == _token_hash(raw_token)).first()
    if session and not session.revoked_at:
        session.revoked_at = utc_now_naive()
        db.commit()
