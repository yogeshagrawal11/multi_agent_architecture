# Author: Yogesh Agrawal
"""JWT authentication.

- POST /auth/login validates a user against the session-store `users` table and
  issues a JWT whose claims carry the customer_id (sub) and role.
- get_current_identity is a FastAPI dependency that verifies the Bearer token
  and returns the authenticated identity.

This fixes the design's insecurity demo: the customer_id used for all data
access comes from the verified token, never from user input, so a customer can
only ever see their own data.
"""
from __future__ import annotations

import sqlite3
import time

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth.passwords import verify_password
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer_id: str
    role: str


class Identity(BaseModel):
    customer_id: str
    role: str
    username: str


def _lookup_user(username: str) -> tuple[str, str, str] | None:
    """Return (password_hash, customer_id, role) or None."""
    settings = get_settings()
    conn = sqlite3.connect(settings.sessions_db)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT password_hash, customer_id, role FROM users WHERE username=?",
            (username,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return row["password_hash"], row["customer_id"], row["role"]


def _issue_token(username: str, customer_id: str, role: str) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": customer_id,
        "role": role,
        "username": username,
        "iat": now,
        "exp": now + settings.jwt_expire_minutes * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    found = _lookup_user(req.username)
    if not found or not verify_password(req.password, found[0]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    _, customer_id, role = found
    token = _issue_token(req.username, customer_id, role)
    return LoginResponse(access_token=token, customer_id=customer_id, role=role)


def get_current_identity(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Identity:
    settings = get_settings()
    try:
        payload = jwt.decode(
            creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return Identity(
        customer_id=payload["sub"],
        role=payload.get("role", "standard"),
        username=payload.get("username", ""),
    )
