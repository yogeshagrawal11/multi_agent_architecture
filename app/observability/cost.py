# Author: Yogesh Agrawal
"""Cost tracking.

Ollama is free to run locally, but the design still requires cost tracking (for
AI apps the spend is non-deterministic and must be monitored). We compute an
estimated cost from token counts using configurable per-1k-token rates (default
0.0) so the mechanism is demonstrable and ready for a paid model.
"""
from __future__ import annotations

from app.config import get_settings
from app.session import store


def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    s = get_settings()
    return (
        prompt_tokens / 1000.0 * s.cost_per_1k_prompt_tokens
        + completion_tokens / 1000.0 * s.cost_per_1k_completion_tokens
    )


def record_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    conv_id: str | None = None,
) -> float:
    """Compute, persist, and return the estimated cost for one interaction."""
    cost = estimate_cost(prompt_tokens, completion_tokens)
    store.log_cost(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        est_cost=cost,
        conv_id=conv_id,
    )
    return cost


def over_budget() -> bool:
    """True if cumulative spend has crossed the configured alert threshold."""
    return store.total_cost() >= get_settings().cost_alert_threshold
