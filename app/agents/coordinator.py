# Author: Yogesh Agrawal
"""Coordinator agent — implemented as a LangGraph state graph.

The design's Phase 4 orchestrator, built on **LangGraph**:

    plan ──(conditional fan-out)──> accounts ─┐
                                    transactions ─┼──> aggregate
                                    service ──────┘

Nodes:
  • plan       — a ChatOllama call decides which domain specialists are needed.
  • accounts / transactions / service — each runs the existing domain sub-agent
    (which uses the MCP tool-calling loop and respects the RBAC filter), writes
    its answer into the shared graph state, and records tool invocations/tokens.
  • aggregate  — a ChatOllama call merges the specialist results into one reply.
    If no specialist is selected, a "general" branch answers conversationally.

The LLM is **ChatOllama** (langchain-ollama) pointed at the host Ollama endpoint,
so the whole coordinator is LangGraph-native. The sub-agents still use the
project's OllamaClient + MCP underneath; the graph orchestrates them.

Public surface is unchanged: `run_coordinator(...)` returns a `CoordinatorResult`
with the same fields, so the chat route, eval harness, and tests are unaffected.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from operator import add
from typing import Annotated, Any, Callable, Optional

from typing_extensions import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

from app.agents.domain_agents import SUBAGENTS
from app.config import get_settings
from app.session import store

VALID_DOMAINS = ["accounts", "transactions", "service"]

PLANNER_PROMPT = (
    "You are a routing planner for a bank assistant. Decide which specialist "
    "agents are needed to answer the user's message. The available agents are:\n"
    "- accounts: balance and account information\n"
    "- transactions: listing/inspecting/flagging transactions\n"
    "- service: checkbook, address change, credit-limit increase, waive interest\n\n"
    "Respond with ONLY a JSON array of the agent names needed, in call order. "
    'Examples: ["accounts"]  or  ["accounts","transactions"]  or  ["service"].\n'
    "If none apply, respond with []."
)

AGGREGATOR_PROMPT = (
    "You are a bank assistant. Using the specialist results below, write a "
    "single clear, friendly answer to the user's question. Only use the "
    "information in the results. Do not invent data.\n\n"
)

GENERAL_PROMPT = (
    "You are a friendly bank assistant. The user's message does not require "
    "account data. Answer briefly, and if they asked for account-specific info "
    "you couldn't route, say so."
)


@dataclass
class CoordinatorResult:
    reply: str
    plan: list[str] = field(default_factory=list)
    sub_results: dict[str, Any] = field(default_factory=dict)
    tool_invocations: list[dict] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------
def _merge_dict(a: dict, b: dict) -> dict:
    out = dict(a or {})
    out.update(b or {})
    return out


class CoordinatorState(TypedDict, total=False):
    # Inputs (constant through the run)
    user_message: str
    customer_id: str
    conv_id: Optional[str]
    history: list[dict]

    # Planner output
    plan: list[str]

    # Fan-out accumulation (reducers so parallel branches merge cleanly)
    sub_results: Annotated[dict[str, Any], _merge_dict]
    tool_invocations: Annotated[list[dict], add]
    prompt_tokens: Annotated[int, add]
    completion_tokens: Annotated[int, add]

    # Final
    reply: str

    # Per-request RBAC filter (callable); declared so LangGraph preserves it in
    # state. Not merged/reduced — set once at invocation and read by nodes.
    _rbac_filter: Any


# ---------------------------------------------------------------------------
# LLM factory (ChatOllama) — kept here so tests can monkeypatch it.
# ---------------------------------------------------------------------------
def _make_llm(temperature: float = 0.2) -> ChatOllama:
    s = get_settings()
    return ChatOllama(
        model=s.llm_coordinator,
        base_url=s.ollama_base_url,
        temperature=temperature,
    )


def _tokens(msg: Any) -> tuple[int, int]:
    """Best-effort token extraction from a ChatOllama response message."""
    meta = getattr(msg, "response_metadata", {}) or {}
    usage = getattr(msg, "usage_metadata", None) or {}
    prompt = usage.get("input_tokens") or meta.get("prompt_eval_count") or 0
    completion = usage.get("output_tokens") or meta.get("eval_count") or 0
    return int(prompt), int(completion)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def _plan_node(state: CoordinatorState) -> dict:
    llm = _make_llm(temperature=0.0)
    messages: list[Any] = [SystemMessage(content=PLANNER_PROMPT)]
    for h in (state.get("history") or [])[-6:]:
        # history items are {"role","content"}; feed prior context as Human/AI text
        messages.append(HumanMessage(content=f"[{h['role']}] {h['content']}"))
    messages.append(HumanMessage(content=state["user_message"]))

    resp = llm.invoke(messages)
    text = (resp.content or "").strip()
    p_tok, c_tok = _tokens(resp)

    domains: list[str] = []
    try:
        start = text.index("[")
        end = text.index("]", start) + 1
        parsed = json.loads(text[start:end])
        domains = [d for d in parsed if d in VALID_DOMAINS]
    except (ValueError, json.JSONDecodeError):
        domains = []

    return {"plan": domains, "prompt_tokens": p_tok, "completion_tokens": c_tok}


def _make_subagent_node(domain: str) -> Callable[[CoordinatorState], dict]:
    """Build a graph node that runs one domain sub-agent."""
    def _node(state: CoordinatorState) -> dict:
        agent_fn = SUBAGENTS[domain]
        run = agent_fn(
            state["user_message"],
            state["customer_id"],
            history=state.get("history"),
            allowed_tool_filter=state.get("_rbac_filter"),
        )
        conv_id = state.get("conv_id")
        if conv_id:
            store.set_shared_state(conv_id, f"subagent:{domain}", run.content)
        return {
            "sub_results": {domain: run.content},
            "tool_invocations": list(run.tool_invocations),
            "prompt_tokens": run.prompt_tokens,
            "completion_tokens": run.completion_tokens,
        }
    return _node


def _aggregate_node(state: CoordinatorState) -> dict:
    sub_results = state.get("sub_results") or {}
    llm = _make_llm(temperature=0.2)

    if not state.get("plan"):
        resp = llm.invoke(
            [SystemMessage(content=GENERAL_PROMPT),
             HumanMessage(content=state["user_message"])]
        )
        p_tok, c_tok = _tokens(resp)
        return {"reply": resp.content or "", "prompt_tokens": p_tok, "completion_tokens": c_tok}

    results_block = "\n".join(f"[{d} result]: {c}" for d, c in sub_results.items())
    resp = llm.invoke(
        [SystemMessage(content=AGGREGATOR_PROMPT + results_block),
         HumanMessage(content=state["user_message"])]
    )
    p_tok, c_tok = _tokens(resp)
    return {"reply": resp.content or "", "prompt_tokens": p_tok, "completion_tokens": c_tok}


def _route_after_plan(state: CoordinatorState) -> list[str]:
    """Conditional fan-out: dispatch to the selected domain nodes, else aggregate."""
    plan = state.get("plan") or []
    targets = [d for d in plan if d in VALID_DOMAINS]
    return targets if targets else ["aggregate"]


# ---------------------------------------------------------------------------
# Graph assembly (built once, reused)
# ---------------------------------------------------------------------------
def _build_graph():
    g = StateGraph(CoordinatorState)
    g.add_node("planner", _plan_node)
    for domain in VALID_DOMAINS:
        g.add_node(domain, _make_subagent_node(domain))
    g.add_node("aggregate", _aggregate_node)

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", _route_after_plan,
                            VALID_DOMAINS + ["aggregate"])
    for domain in VALID_DOMAINS:
        g.add_edge(domain, "aggregate")
    g.add_edge("aggregate", END)
    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


# ---------------------------------------------------------------------------
# Public entrypoint (unchanged signature/return shape)
# ---------------------------------------------------------------------------
def run_coordinator(
    user_message: str,
    customer_id: str,
    conv_id: str | None = None,
    history: list[dict] | None = None,
    allowed_tool_filter=None,
) -> CoordinatorResult:
    initial: dict[str, Any] = {
        "user_message": user_message,
        "customer_id": customer_id,
        "conv_id": conv_id,
        "history": history or [],
        "sub_results": {},
        "tool_invocations": [],
        "prompt_tokens": 0,
        "completion_tokens": 0,
        # RBAC filter is passed through state (not a graph-typed key).
        "_rbac_filter": allowed_tool_filter,
    }
    final = _graph().invoke(initial)

    return CoordinatorResult(
        reply=final.get("reply", ""),
        plan=final.get("plan", []),
        sub_results=final.get("sub_results", {}),
        tool_invocations=final.get("tool_invocations", []),
        prompt_tokens=final.get("prompt_tokens", 0),
        completion_tokens=final.get("completion_tokens", 0),
        model=get_settings().llm_coordinator,
    )
