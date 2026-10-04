# Author: Yogesh Agrawal
"""MCP client manager.

Connects to the three domain MCP servers over stdio, discovers their tools,
converts them to Ollama tool schemas, and invokes them on demand.

Design note: MCP's Python SDK is async. We expose a small synchronous facade
(`list_ollama_tools`, `call_tool`) so the synchronous agent code can use it;
each call runs its own short-lived stdio session for robustness in the single
container. Tool definitions are cached to avoid repeated discovery.
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Map a logical domain -> the python module that runs its MCP server.
DOMAIN_SERVERS: dict[str, list[str]] = {
    "accounts": [sys.executable, "-m", "mcp_servers.accounts_server"],
    "transactions": [sys.executable, "-m", "mcp_servers.transactions_server"],
    "service": [sys.executable, "-m", "mcp_servers.service_server"],
}

_tool_cache: dict[str, list[dict[str, Any]]] = {}
# Reverse lookup: tool name -> domain, so we can route a tool call.
_tool_to_domain: dict[str, str] = {}


def _params(domain: str) -> StdioServerParameters:
    cmd, *args = DOMAIN_SERVERS[domain]
    # Pass the current environment through to the spawned MCP server so that
    # configuration (MOCK_BANK_URL, BANK_DB, PYTHONPATH, etc.) propagates.
    # Without this, the MCP stdio client gives the child a minimal env and the
    # server falls back to config defaults (e.g. mock bank on :9100).
    import os
    return StdioServerParameters(command=cmd, args=args, env=dict(os.environ))


async def _list_tools_async(domain: str) -> list[dict[str, Any]]:
    async with stdio_client(_params(domain)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resp = await session.list_tools()
            tools = []
            for t in resp.tools:
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description or "",
                            "parameters": t.inputSchema or {"type": "object", "properties": {}},
                        },
                    }
                )
            return tools


async def _call_tool_async(domain: str, name: str, arguments: dict) -> Any:
    async with stdio_client(_params(domain)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            # result.content is a list of content blocks; extract text/JSON.
            out = []
            for block in result.content:
                text = getattr(block, "text", None)
                if text is not None:
                    out.append(text)
            joined = "\n".join(out) if out else ""
            try:
                return json.loads(joined)
            except (json.JSONDecodeError, ValueError):
                return {"result": joined}


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # Called from within an event loop: run in a new loop in a thread.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(coro)).result()
    return asyncio.run(coro)


def list_ollama_tools(domains: list[str]) -> list[dict[str, Any]]:
    """Return Ollama-format tool schemas for the given domains (cached)."""
    all_tools: list[dict[str, Any]] = []
    for domain in domains:
        if domain not in _tool_cache:
            tools = _run(_list_tools_async(domain))
            _tool_cache[domain] = tools
            for t in tools:
                _tool_to_domain[t["function"]["name"]] = domain
        all_tools.extend(_tool_cache[domain])
    return all_tools


def call_tool(name: str, arguments: dict) -> Any:
    """Invoke a tool by name; routes to the owning domain's MCP server."""
    domain = _tool_to_domain.get(name)
    if domain is None:
        # Ensure caches are warm, then retry.
        list_ollama_tools(list(DOMAIN_SERVERS.keys()))
        domain = _tool_to_domain.get(name)
    if domain is None:
        return {"error": "unknown_tool", "name": name}
    return _run(_call_tool_async(domain, name, arguments))
