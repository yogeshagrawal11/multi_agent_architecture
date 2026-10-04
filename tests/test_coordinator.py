# Author: Yogesh Agrawal
"""Tests for the LangGraph-based coordinator.

Determinism strategy (no Ollama, no MCP):
  • `coordinator._make_llm` is patched to return a fake LLM whose `.invoke()`
    yields scripted responses (first call = planner, later = aggregator/general).
  • The domain sub-agents (`coordinator.SUBAGENTS`) are patched with fakes that
    return canned AgentRun-like objects — and honor the RBAC filter so the
    blocked-tool path can be asserted without a real tool loop.
"""
from unittest.mock import patch

from app.agents.tool_agent import AgentRun


class _FakeMsg:
    def __init__(self, content):
        self.content = content
        self.response_metadata = {"prompt_eval_count": 5, "eval_count": 7}
        self.usage_metadata = {"input_tokens": 5, "output_tokens": 7}


class _FakeLLM:
    """Returns scripted .invoke() responses in order."""
    def __init__(self, scripts):
        self._it = iter(scripts)

    def invoke(self, messages):
        return _FakeMsg(next(self._it))


def _llm_factory(*scripts):
    """A _make_llm replacement that always returns a fresh scripted LLM.

    The graph calls _make_llm() once per node (plan, aggregate). We hand back a
    single shared iterator so responses are consumed in graph execution order.
    """
    shared = _FakeLLM(list(scripts))

    def _factory(temperature=0.2):
        return shared
    return _factory


def test_coordinator_single_domain_plan_and_aggregate():
    from app.agents import coordinator

    def fake_accounts(user_message, customer_id, history=None, allowed_tool_filter=None):
        return AgentRun(
            content="Your balance is 24,345.",
            tool_invocations=[{"name": "get_balance",
                               "arguments": {"customer_id": customer_id},
                               "result": {"balances": [{"balance": 24345.0}]}}],
            prompt_tokens=10, completion_tokens=5, model="gpt-oss:120b",
        )

    fake_subagents = dict(coordinator.SUBAGENTS)
    fake_subagents["accounts"] = fake_accounts

    with patch.object(coordinator, "_make_llm",
                      _llm_factory('["accounts"]', "Your savings balance is 24,345.")), \
         patch.object(coordinator, "SUBAGENTS", fake_subagents):
        res = coordinator.run_coordinator("What is my balance?", "C1")

    assert res.plan == ["accounts"]
    assert [t["name"] for t in res.tool_invocations] == ["get_balance"]
    assert "24,345" in res.reply


def test_coordinator_rbac_blocks_tool():
    from app.agents import coordinator
    from app.auth.rbac import build_allowed_tool_filter

    def fake_service(user_message, customer_id, history=None, allowed_tool_filter=None):
        # Honor the RBAC filter exactly as the real tool loop would.
        ok, reason = (True, "")
        if allowed_tool_filter is not None:
            ok, reason = allowed_tool_filter("increase_credit_limit", {})
        if ok:
            result = {"status": "done"}
        else:
            result = {"error": "not_authorized", "detail": reason}
        return AgentRun(
            content="Sorry, you're not permitted to do that.",
            tool_invocations=[{"name": "increase_credit_limit",
                               "arguments": {}, "result": result}],
            prompt_tokens=8, completion_tokens=4, model="gpt-oss:120b",
        )

    fake_subagents = dict(coordinator.SUBAGENTS)
    fake_subagents["service"] = fake_service

    with patch.object(coordinator, "_make_llm",
                      _llm_factory('["service"]', "Sorry, you're not permitted.")), \
         patch.object(coordinator, "SUBAGENTS", fake_subagents):
        res = coordinator.run_coordinator(
            "Increase my credit limit to 500000.", "C2",
            allowed_tool_filter=build_allowed_tool_filter("standard"),
        )

    blocked = [t for t in res.tool_invocations
               if isinstance(t["result"], dict) and t["result"].get("error") == "not_authorized"]
    assert blocked, "expected increase_credit_limit to be blocked by RBAC"


def test_coordinator_no_domain_general_answer():
    from app.agents import coordinator

    with patch.object(coordinator, "_make_llm",
                      _llm_factory("[]", "Hello! How can I help you today?")):
        res = coordinator.run_coordinator("Hi there!", "C1")

    assert res.plan == []
    assert "help" in res.reply.lower()


def test_coordinator_waive_interest_blocked_for_standard():
    from app.agents import coordinator
    from app.auth.rbac import build_allowed_tool_filter

    def fake_service(user_message, customer_id, history=None, allowed_tool_filter=None):
        ok, reason = (True, "")
        if allowed_tool_filter is not None:
            ok, reason = allowed_tool_filter("waive_interest_charge", {})
        result = {"status": "done"} if ok else {"error": "not_authorized", "detail": reason}
        reply = ("Done." if ok
                 else "I can't waive that. Please contact a bank representative.")
        return AgentRun(
            content=reply,
            tool_invocations=[{"name": "waive_interest_charge",
                               "arguments": {}, "result": result}],
            prompt_tokens=8, completion_tokens=4, model="gpt-oss:120b",
        )

    fake_subagents = dict(coordinator.SUBAGENTS)
    fake_subagents["service"] = fake_service

    with patch.object(coordinator, "_make_llm",
                      _llm_factory('["service"]',
                                   "Please contact a bank representative.")), \
         patch.object(coordinator, "SUBAGENTS", fake_subagents):
        res = coordinator.run_coordinator(
            "Please waive my interest charge.", "C4",
            allowed_tool_filter=build_allowed_tool_filter("standard"),
        )

    blocked = [t for t in res.tool_invocations
               if isinstance(t["result"], dict) and t["result"].get("error") == "not_authorized"]
    assert blocked
    assert "representative" in res.reply.lower()
