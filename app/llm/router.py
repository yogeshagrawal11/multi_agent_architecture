# Author: Yogesh Agrawal
"""Model routing.

By default every role uses the same model (gpt-oss:120b per user choice).
The simple/complex seam is kept so a lighter sub-agent model can be swapped in
via env without code changes. The third-party path stays disabled (free/offline).
"""
from __future__ import annotations

from app.config import get_settings


def model_for(role: str) -> str:
    """Return the model name for a role: 'coordinator' or 'subagent'."""
    s = get_settings()
    if role == "coordinator":
        return s.llm_coordinator
    return s.llm_subagent
