# Author: Yogesh Agrawal
"""Tool-calling agent loop.

Generic reasoning loop:
  1. Send messages + available tools to the LLM.
  2. If the LLM requests tool calls, execute them via the MCP client manager.
  3. Append tool results and ask the LLM again.
  4. Repeat until the LLM returns a final text answer (or max rounds hit).

Used directly in M3 (single tool agent over all domains) and reused by the
domain sub-agents in M4 (each restricted to its own domain's tools).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.llm.ollama_client import OllamaClient
from app.llm.router import model_for
from app.mcp_clients import manager

MAX_ROUNDS = 5


@dataclass
class AgentRun:
    content: str
    tool_invocations: list[dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""


def run_tool_agent(
    system_prompt: str,
    user_message: str,
    domains: list[str],
    history: list[dict] | None = None,
    role: str = "subagent",
    allowed_tool_filter=None,
) -> AgentRun:
    """Run the tool-calling loop restricted to the given MCP domains.

    allowed_tool_filter: optional callable(tool_name, arguments) -> (ok, reason)
    used by RBAC to block unauthorized tool calls (M5).
    """
    client = OllamaClient()
    model = model_for(role)
    tools = manager.list_ollama_tools(domains)

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    run = AgentRun(content="", model=model)

    for _ in range(MAX_ROUNDS):
        result = client.chat(messages, model=model, tools=tools)
        run.prompt_tokens += result.prompt_tokens
        run.completion_tokens += result.completion_tokens

        if not result.tool_calls:
            run.content = result.content
            return run

        # Record the assistant's tool-call turn.
        messages.append(
            {"role": "assistant", "content": result.content or "", "tool_calls": result.tool_calls}
        )

        for tc in result.tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {}) or {}
            if isinstance(args, str):
                import json
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, ValueError):
                    args = {}

            # RBAC / authorization hook.
            if allowed_tool_filter is not None:
                ok, reason = allowed_tool_filter(name, args)
                if not ok:
                    tool_result: Any = {"error": "not_authorized", "detail": reason}
                else:
                    tool_result = manager.call_tool(name, args)
            else:
                tool_result = manager.call_tool(name, args)

            run.tool_invocations.append({"name": name, "arguments": args, "result": tool_result})

            import json as _json
            messages.append(
                {"role": "tool", "content": _json.dumps(tool_result), "name": name}
            )

    # Max rounds reached: ask once more for a final answer without tools.
    final = client.chat(messages, model=model)
    run.prompt_tokens += final.prompt_tokens
    run.completion_tokens += final.completion_tokens
    run.content = final.content or "I wasn't able to complete that request."
    return run
