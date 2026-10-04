# Author: Yogesh Agrawal
"""Langfuse v2 tracing.

Captures the AI-specific observability the design calls for: the incoming
prompt, which agent/sub-agent ran, which tools were called with what inputs,
and the LLM token/cost usage.

Tracing is fully gated by LANGFUSE_ENABLED. When disabled (the default) or when
the SDK/keys are not configured, every function here is a safe no-op so the app
runs identically with or without the observability server.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from app.config import get_settings

_client = None
_init_tried = False


def _get_client():
    global _client, _init_tried
    if _init_tried:
        return _client
    _init_tried = True
    settings = get_settings()
    if not settings.langfuse_enabled:
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key or None,
            secret_key=settings.langfuse_secret_key or None,
            host=settings.langfuse_host,
        )
    except Exception:
        _client = None
    return _client


@contextmanager
def trace(
    name: str,
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict | None = None,
) -> Iterator[Any]:
    """Context manager yielding a Langfuse trace (or None when disabled).

    `session_id` groups all traces from one login session together in Langfuse,
    so every chat turn between login and logout appears under the same session.
    """
    client = _get_client()
    if client is None:
        yield None
        return
    tr = client.trace(
        name=name,
        user_id=user_id,
        session_id=session_id,
        metadata=metadata or {},
    )
    try:
        yield tr
    finally:
        try:
            client.flush()
        except Exception:
            pass


def log_span(tr: Any, name: str, inputs: dict | None = None, outputs: dict | None = None) -> None:
    """Record a span (agent/tool/LLM step) under a trace. No-op if tr is None."""
    if tr is None:
        return
    try:
        tr.span(name=name, input=inputs or {}, output=outputs or {})
    except Exception:
        pass
