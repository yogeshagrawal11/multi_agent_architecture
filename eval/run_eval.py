# Author: Yogesh Agrawal
"""Non-deterministic agent evaluation harness.

AI flows are non-deterministic: the LLM won't produce identical wording each
run. So instead of exact-match, we score each golden case with:
  - structural assertions (correct plan / tools called / tool blocked)
  - substring checks (expected facts present / forbidden text absent)
  - semantic similarity between the reply and a reference answer, using
    embeddings from Ollama (nomic-embed-text).

Run (with mock bank on :9100 and Ollama reachable):
    python -m eval.run_eval
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from app.agents.coordinator import run_coordinator
from app.auth.rbac import build_allowed_tool_filter
from app.llm.ollama_client import OllamaClient
from app.session import store

DATASET = Path(__file__).parent / "golden_dataset.jsonl"
SIM_THRESHOLD = 0.55  # semantic similarity pass bar for the reference check


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _semantic_sim(client: OllamaClient, a: str, b: str) -> float:
    try:
        return _cosine(client.embed(a), client.embed(b))
    except Exception:
        return 0.0


def _tool_names(result) -> list[str]:
    return [t["name"] for t in result.tool_invocations]


def _blocked_tools(result) -> list[str]:
    blocked = []
    for t in result.tool_invocations:
        res = t.get("result")
        if isinstance(res, dict) and res.get("error") == "not_authorized":
            blocked.append(t["name"])
    return blocked


def run_case(client: OllamaClient, case: dict) -> dict:
    checks: list[tuple[str, bool]] = []
    customer_id = case["customer_id"]
    rbac = build_allowed_tool_filter(case.get("role", "standard"))
    conv = store.create_conversation(customer_id)

    hist = store.get_history(conv)
    store.add_message(conv, "user", case["message"])
    result = run_coordinator(case["message"], customer_id, conv_id=conv,
                             history=hist, allowed_tool_filter=rbac)
    store.add_message(conv, "assistant", result.reply)

    if "expect_plan" in case:
        checks.append(("plan", set(case["expect_plan"]).issubset(set(result.plan))))
    if "expect_tools" in case:
        got = set(_tool_names(result))
        checks.append(("tools", set(case["expect_tools"]).issubset(got)))
    if "expect_blocked_tool" in case:
        checks.append(("blocked", case["expect_blocked_tool"] in _blocked_tools(result)))
    if "expect_contains" in case:
        checks.append(("contains", any(s in result.reply for s in case["expect_contains"])))
    if "expect_contains_any" in case:
        checks.append(("contains_any",
                       any(s.lower() in result.reply.lower() for s in case["expect_contains_any"])))
    if "expect_not_contains" in case:
        checks.append(("not_contains",
                       all(s.lower() not in result.reply.lower() for s in case["expect_not_contains"])))

    # Follow-up turn (context/session scenario).
    if "followup" in case:
        hist2 = store.get_history(conv)
        store.add_message(conv, "user", case["followup"])
        r2 = run_coordinator(case["followup"], customer_id, conv_id=conv,
                             history=hist2, allowed_tool_filter=rbac)
        store.add_message(conv, "assistant", r2.reply)
        if "expect_followup_tools" in case:
            got2 = set(_tool_names(r2))
            checks.append(("followup_tools",
                           set(case["expect_followup_tools"]).issubset(got2)))

    # Semantic similarity to reference.
    sim = _semantic_sim(client, result.reply, case.get("reference", "")) if case.get("reference") else 1.0
    checks.append((f"semantic>={SIM_THRESHOLD}", sim >= SIM_THRESHOLD))

    passed = all(ok for _, ok in checks)
    return {"id": case["id"], "passed": passed, "sim": round(sim, 3), "checks": checks,
            "plan": result.plan, "tools": _tool_names(result)}


def main() -> int:
    store.init_db()
    client = OllamaClient()
    cases = [json.loads(l) for l in DATASET.read_text().splitlines() if l.strip()]
    results = [run_case(client, c) for c in cases]

    print("\n=== Eval Results ===")
    passed = 0
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        if r["passed"]:
            passed += 1
        print(f"[{status}] {r['id']:28s} sim={r['sim']:.3f} plan={r['plan']} "
              f"tools={r['tools']}")
        if not r["passed"]:
            for name, ok in r["checks"]:
                if not ok:
                    print(f"         FAILED CHECK: {name}")

    total = len(results)
    print(f"\nPASSED {passed}/{total} ({100*passed//total}%)")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
