# Author: Yogesh Agrawal
"""Role-based access control (authorization).

Maps roles to the sensitive tools they may invoke. The coordinator passes an
`allowed_tool_filter` built here into the sub-agents; the tool-calling loop
consults it BEFORE executing any tool, blocking unauthorized calls.

Design scenario: only `privileged` customers may increase their credit limit.
"""
from __future__ import annotations

from typing import Callable

# Tools that require elevated authorization. Any tool not listed here is allowed
# for all authenticated roles (read-only / low-risk operations).
SENSITIVE_TOOLS: dict[str, set[str]] = {
    # tool name -> set of roles permitted to call it
    "increase_credit_limit": {"privileged"},
    "waive_interest_charge": {"privileged"},
}


def is_tool_allowed(role: str, tool_name: str) -> tuple[bool, str]:
    allowed_roles = SENSITIVE_TOOLS.get(tool_name)
    if allowed_roles is None:
        return True, ""
    if role in allowed_roles:
        return True, ""
    needed = " or ".join(sorted(allowed_roles))
    return False, (
        f"The '{tool_name}' action requires {needed} access. "
        f"Your role ('{role}') is not permitted to perform it."
    )


def build_allowed_tool_filter(role: str) -> Callable[[str, dict], tuple[bool, str]]:
    """Return a closure(tool_name, arguments) -> (ok, reason) for the given role."""

    def _filter(tool_name: str, _arguments: dict) -> tuple[bool, str]:
        return is_tool_allowed(role, tool_name)

    return _filter
