# Author: Yogesh Agrawal
"""Shared helper for MCP servers to call the Mock Bank API over HTTP.

Keeping all API/HTTP/error-handling logic here (and in the MCP servers) is the
whole point of MCP in this design: tools are decoupled from the agents.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings


def _base() -> str:
    return get_settings().mock_bank_url.rstrip("/")


def bank_get(path: str, params: dict | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=30) as client:
        r = client.get(f"{_base()}{path}", params=params or {})
        if r.status_code == 404:
            return {"error": "not_found", "detail": r.json().get("detail", "not found")}
        r.raise_for_status()
        return r.json()


def bank_post(path: str, json: dict | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=30) as client:
        r = client.post(f"{_base()}{path}", json=json or {})
        if r.status_code == 404:
            return {"error": "not_found", "detail": r.json().get("detail", "not found")}
        r.raise_for_status()
        return r.json()
