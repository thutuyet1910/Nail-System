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


def verify_internal_service_token(request: Request) -> None:
    """Service-to-service read access (Check-In -> Owner). Fails closed when no token is configured."""
    expected = os.getenv("CHECKIN_INTERNAL_SERVICE_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Internal service access is not configured")
    supplied = request.headers.get("X-Internal-Service-Token", "")
    if not supplied or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid internal service token")


# --- Owner security settings ---------------------------------------------------------------------
MAX_PASSWORD_LENGTH = 128


def validate_new_password(new_password: str, current_password: str | None = None) -> str:
    """Same floor as login/bootstrap (hash_password: at least 8 characters), plus an upper bound."""
    if not isinstance(new_password, str) or not new_password.strip():
        raise HTTPException(status_code=400, detail="Enter a new password")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="The new password must be at least 8 characters")
    if len(new_password) > MAX_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"The new password must be at most {MAX_PASSWORD_LENGTH} characters")
    if current_password is not None and new_password == current_password:
        raise HTTPException(status_code=400, detail="The new password must be different from the current one")
    return new_password


def current_owner(request: Request, db: Session) -> tuple["models.OwnerSession", "models.OwnerCredential"]:
    session = authenticate_request(request, db)
    credential = db.get(models.OwnerCredential, session.credential_id)
    if not credential or not credential.is_active:
        raise HTTPException(status_code=401, detail="Owner session is invalid or expired")
    return session, credential


def require_current_password(credential: "models.OwnerCredential", password: str, client_key: str) -> None:
    """Re-verifies the owner password for a sensitive change. Throttled like login; nothing is stored."""
    _check_login_rate_limit(client_key)
    if not isinstance(password, str) or not verify_password(password, credential.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    with _attempt_lock:
        _attempts.pop(client_key, None)


def revoke_owner_sessions(db: Session, credential_id: int) -> int:
    now = utc_now_naive()
    revoked = 0
    for session in db.query(models.OwnerSession).filter(
        models.OwnerSession.credential_id == credential_id, models.OwnerSession.revoked_at.is_(None)
    ):
        session.revoked_at = now
        revoked += 1
    db.commit()
    return revoked


def set_owner_password(db: Session, credential: "models.OwnerCredential", new_password: str) -> int:
    """Stores the new scrypt hash and revokes EVERY owner session, the caller's included: the owner signs in
    again with the new password. Staff sessions are a separate mechanism and are not touched."""
    credential.password_hash = hash_password(validate_new_password(new_password))
    db.commit()
    return revoke_owner_sessions(db, credential.id)


def reset_owner_password_offline(db: Session, new_password: str) -> int:
    """Used by the local reset tool (reset_owner_password.py), which needs access to this computer."""
    credential = db.query(models.OwnerCredential).filter(models.OwnerCredential.is_active.is_(True)).first()
    if not credential:
        raise ValueError("No owner credential exists yet")
    return set_owner_password(db, credential, new_password)


# --- Staff access --------------------------------------------------------------------------------
# Daily-operations access for the salon computer (customers, appointments, checkout). It carries NO
# password and NO owner privilege: a staff session can only reach the allow-listed staff routes in
# main.py, with the same cookie + CSRF discipline as the owner session. Held in memory, so it simply
# lapses on restart (the dashboard re-creates it). A future per-technician PIN would plug in here.
STAFF_COOKIE = "staff_session"
STAFF_CSRF_COOKIE = "staff_csrf"
STAFF_SESSION_TTL_MINUTES = int(os.getenv("STAFF_SESSION_TTL_MINUTES", "720"))
_MAX_STAFF_SESSIONS = 200
_staff_sessions: dict[str, tuple[str, datetime]] = {}  # token hash -> (csrf hash, expires_at)
_staff_lock = threading.Lock()


def create_staff_session() -> tuple[str, str, datetime]:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    now = utc_now_naive()
    expires_at = now + timedelta(minutes=STAFF_SESSION_TTL_MINUTES)
    with _staff_lock:
        for key in [k for k, (_c, exp) in _staff_sessions.items() if exp <= now]:
            del _staff_sessions[key]
        while len(_staff_sessions) >= _MAX_STAFF_SESSIONS:
            del _staff_sessions[min(_staff_sessions, key=lambda k: _staff_sessions[k][1])]
        _staff_sessions[_token_hash(token)] = (_token_hash(csrf), expires_at)
    return token, csrf, expires_at


def set_staff_cookies(response: Response, token: str, csrf: str, expires_at: datetime) -> None:
    max_age = max(0, int((expires_at - utc_now_naive()).total_seconds()))
    response.set_cookie(STAFF_COOKIE, token, max_age=max_age, httponly=True, secure=COOKIE_SECURE, samesite="strict", path="/")
    response.set_cookie(STAFF_CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=COOKIE_SECURE, samesite="strict", path="/")


def authenticate_staff(request: Request, require_csrf: bool = False) -> None:
    raw_token = request.cookies.get(STAFF_COOKIE)
    entry = _staff_sessions.get(_token_hash(raw_token)) if raw_token else None
    if not entry or entry[1] <= utc_now_naive():
        raise HTTPException(status_code=401, detail="Staff session required")
    if require_csrf:
        header = request.headers.get("X-Staff-CSRF-Token", "")
        cookie = request.cookies.get(STAFF_CSRF_COOKIE, "")
        if not header or not cookie or not hmac.compare_digest(header, cookie) or not hmac.compare_digest(_token_hash(header), entry[0]):
            raise HTTPException(status_code=403, detail="CSRF validation failed")


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
