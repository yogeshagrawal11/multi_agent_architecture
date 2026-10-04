# Author: Yogesh Agrawal
"""Tests for the session store (history, shared state, cost log)."""
from app.session import store


def test_conversation_and_history():
    store.init_db()
    conv = store.create_conversation("C1")
    store.add_message(conv, "user", "hello")
    store.add_message(conv, "assistant", "hi there")
    hist = store.get_history(conv)
    assert [m["role"] for m in hist] == ["user", "assistant"]
    assert hist[0]["content"] == "hello"


def test_shared_state():
    store.init_db()
    conv = store.create_conversation("C1")
    store.set_shared_state(conv, "subagent:accounts", {"balance": 100})
    assert store.get_shared_state(conv, "subagent:accounts") == {"balance": 100}
    # Upsert overwrites.
    store.set_shared_state(conv, "subagent:accounts", {"balance": 200})
    assert store.get_shared_state(conv, "subagent:accounts") == {"balance": 200}


def test_shared_state_missing_returns_none():
    store.init_db()
    conv = store.create_conversation("C1")
    assert store.get_shared_state(conv, "nope") is None


def test_cost_log_accumulates():
    store.init_db()
    before = store.total_cost()
    store.log_cost("gpt-oss:120b", 100, 50, 1.25)
    assert store.total_cost() == before + 1.25
