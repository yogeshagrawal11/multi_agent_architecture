# Author: Yogesh Agrawal
"""Tests for role-based access control."""
from app.auth.rbac import build_allowed_tool_filter, is_tool_allowed


def test_privileged_can_increase_credit_limit():
    ok, reason = is_tool_allowed("privileged", "increase_credit_limit")
    assert ok and reason == ""


def test_standard_cannot_increase_credit_limit():
    ok, reason = is_tool_allowed("standard", "increase_credit_limit")
    assert not ok
    assert "privileged" in reason


def test_premium_cannot_increase_credit_limit():
    ok, _ = is_tool_allowed("premium", "increase_credit_limit")
    assert not ok


def test_non_sensitive_tool_allowed_for_all():
    for role in ("standard", "premium", "privileged"):
        ok, _ = is_tool_allowed(role, "get_balance")
        assert ok


def test_filter_closure():
    f_std = build_allowed_tool_filter("standard")
    ok, _ = f_std("increase_credit_limit", {})
    assert not ok
    ok2, _ = f_std("get_balance", {})
    assert ok2


def test_waive_interest_privileged_only():
    ok, _ = is_tool_allowed("privileged", "waive_interest_charge")
    assert ok
    for role in ("premium", "standard"):
        blocked, reason = is_tool_allowed(role, "waive_interest_charge")
        assert not blocked
        assert "privileged" in reason
