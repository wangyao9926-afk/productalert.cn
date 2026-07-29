from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, Header, HTTPException, Response

from app.db import execute_sql, fetchone, get_db, row_to_dict


SESSION_DAYS = 30
SESSION_COOKIE_NAME = "monitor_session"
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 6
_login_failures: dict[str, list[float]] = defaultdict(list)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 180_000)
    return f"pbkdf2_sha256$180000${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(computed, digest)
    except Exception:
        return False


def normalize_email(email: str) -> str:
    return email.strip().lower()


def public_user(row) -> dict:
    user = row_to_dict(row)
    user.pop("password_hash", None)
    return user


def hash_session_token(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"sha256${digest}"


def create_session(user_id: int) -> dict:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with get_db() as db:
        execute_sql(
            db,
            """
            INSERT INTO sessions (token, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (hash_session_token(token), user_id, now_iso(), expires_at.isoformat()),
        )
    return {"token": token, "token_type": "bearer", "expires_at": expires_at.isoformat()}


def set_session_cookie(response: Response, session: dict) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session["token"],
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def request_token(authorization: str | None, session_cookie: str | None) -> str:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Invalid authentication state")
        return token
    if session_cookie:
        return session_cookie
    if not authorization:
        raise HTTPException(status_code=401, detail="请先登录")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="登录状态无效")
    return token


def revoke_session_token(token: str) -> None:
    with get_db() as db:
        execute_sql(
            db,
            """
            UPDATE sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE token IN (?, ?)
            """,
            (hash_session_token(token), token),
        )


def check_login_rate_limit(email: str) -> None:
    now = time.time()
    failures = [item for item in _login_failures[email] if now - item < LOGIN_WINDOW_SECONDS]
    _login_failures[email] = failures
    if len(failures) >= LOGIN_MAX_FAILURES:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后再试")


def record_failed_login(email: str) -> None:
    _login_failures[email].append(time.time())


def clear_failed_login(email: str) -> None:
    _login_failures.pop(email, None)


def get_current_user(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    token = request_token(authorization, session_cookie)
    token_hash = hash_session_token(token)
    with get_db() as db:
        row = fetchone(
            db,
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token IN (?, ?)
              AND sessions.revoked_at IS NULL
              AND sessions.expires_at > ?
            """,
            (token_hash, token, now_iso()),
        )
    if not row:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return public_user(row)


CurrentUser = Depends(get_current_user)
