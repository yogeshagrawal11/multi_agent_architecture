# Author: Yogesh Agrawal
"""Domain sub-agents.

Each sub-agent wraps the generic tool-calling loop but is restricted to ONE
domain's MCP tools. This avoids tool overload / tool confusion (the design's
Phase 3 rationale): a specialized agent only sees the tools relevant to it.
"""
from __future__ import annotations

from app.agents.tool_agent import AgentRun, run_tool_agent

ACCOUNTS_PROMPT = (
    "You are the ACCOUNTS specialist for a bank. You handle balance and account "
    "information requests only. The current customer_id is {customer_id}. "
    "Always pass that customer_id to tools. Be concise and factual."
)
TRANSACTIONS_PROMPT = (
    "You are the TRANSACTIONS specialist for a bank. You handle listing, "
    "inspecting, and flagging transactions only. The current customer_id is "
    "{customer_id}. Always pass that customer_id to tools. Be concise."
)
SERVICE_PROMPT = (
    "You are the SERVICE specialist for a bank. You handle service requests: "
    "checkbooks, address changes, credit-limit increases, and waiving credit-card "
    "interest charges only. The current customer_id is {customer_id}. Always pass "
    "that customer_id to tools. Be concise.\n"
    "IMPORTANT: If a tool call comes back with an error of 'not_authorized' (the "
    "customer's account tier is not permitted to perform that action), do NOT "
    "retry it. Instead, apologize briefly and tell the customer that this request "
    "must be handled by a bank representative — ask them to contact a bank "
    "representative (for example, call customer support or visit a branch)."
)


def run_accounts_agent(user_message: str, customer_id: str, history=None,
                       allowed_tool_filter=None) -> AgentRun:
    return run_tool_agent(
        system_prompt=ACCOUNTS_PROMPT.format(customer_id=customer_id),
        user_message=user_message,
        domains=["accounts"],
        history=history,
        allowed_tool_filter=allowed_tool_filter,
    )


def run_transactions_agent(user_message: str, customer_id: str, history=None,
                           allowed_tool_filter=None) -> AgentRun:
    return run_tool_agent(
        system_prompt=TRANSACTIONS_PROMPT.format(customer_id=customer_id),
        user_message=user_message,
        domains=["transactions"],
        history=history,
        allowed_tool_filter=allowed_tool_filter,
    )


def run_service_agent(user_message: str, customer_id: str, history=None,
                      allowed_tool_filter=None) -> AgentRun:
    return run_tool_agent(
        system_prompt=SERVICE_PROMPT.format(customer_id=customer_id),
        user_message=user_message,
        domains=["service"],
        history=history,
        allowed_tool_filter=allowed_tool_filter,
    )


SUBAGENTS = {
    "accounts": run_accounts_agent,
    "transactions": run_transactions_agent,
    "service": run_service_agent,
}
