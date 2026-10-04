# Author: Yogesh Agrawal
"""Password hashing helpers using bcrypt directly (no passlib).

bcrypt limits inputs to 72 bytes; we pre-hash with sha256 so arbitrarily long
passwords are supported safely.
"""
from __future__ import annotations

import base64
import hashlib

import bcrypt


def _prepare(password: str) -> bytes:
    # sha256 -> base64 keeps us within bcrypt's 72-byte input limit.
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
