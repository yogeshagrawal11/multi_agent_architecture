# Author: Yogesh Agrawal
"""Simple single agent (Phase 1 of the design).

No bank tools yet. It answers conversationally and, by design, has no access
to any account data — matching the "Sorry, I don't have access to your bank
accounts" behavior from the architecture's first demo.
"""
from __future__ import annotations

from app.llm.ollama_client import ChatResult, OllamaClient
from app.llm.router import model_for

SIMPLE_SYSTEM_PROMPT = (
    "You are a helpful banking customer-support assistant for a demo bank. "
    "You are at an early stage and have NO access to any bank systems, account "
    "balances, or customer data. If a user asks for account-specific "
    "information (balance, transactions, etc.), politely explain that you don't "
    "yet have access to their bank accounts. Keep answers short and friendly."
)


def run_simple_agent(user_message: str, history: list[dict] | None = None) -> ChatResult:
    client = OllamaClient()
    messages: list[dict] = [{"role": "system", "content": SIMPLE_SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return client.chat(messages, model=model_for("coordinator"))
