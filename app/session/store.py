# Author: Yogesh Agrawal
"""Session store backed by SQLite.

Tables:
  users          - seeded login users (username, password_hash, customer_id, role)
  conversations  - one row per conversation
  messages       - conversation history (role, content) for LLM context
  shared_state   - inter-agent shared state (key/value JSON per conversation)
  cost_log       - token + cost accounting per LLM call
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from app.config import get_settings


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    conn = sqlite3.connect(settings.sessions_db)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    customer_id   TEXT NOT NULL,
    role          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    conv_id     TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    msg_id     TEXT PRIMARY KEY,
    conv_id    TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (conv_id) REFERENCES conversations(conv_id)
);

CREATE TABLE IF NOT EXISTS shared_state (
    conv_id    TEXT NOT NULL,
    key        TEXT NOT NULL,
    value_json TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (conv_id, key)
);

CREATE TABLE IF NOT EXISTS cost_log (
    id                TEXT PRIMARY KEY,
    conv_id           TEXT,
    model             TEXT NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    est_cost          REAL NOT NULL DEFAULT 0.0,
    created_at        REAL NOT NULL
);
"""


def init_db() -> None:
    """Create tables if they do not exist."""
    with _conn() as c:
        c.executescript(SCHEMA)


# ---------- Conversations & messages ----------

def create_conversation(customer_id: str) -> str:
    conv_id = str(uuid.uuid4())
    with _conn() as c:
        c.execute(
            "INSERT INTO conversations (conv_id, customer_id, created_at) VALUES (?,?,?)",
            (conv_id, customer_id, time.time()),
        )
    return conv_id


def add_message(conv_id: str, role: str, content: str) -> str:
    msg_id = str(uuid.uuid4())
    with _conn() as c:
        c.execute(
            "INSERT INTO messages (msg_id, conv_id, role, content, created_at) "
            "VALUES (?,?,?,?,?)",
            (msg_id, conv_id, role, content, time.time()),
        )
    return msg_id


def get_history(conv_id: str, limit: int = 50) -> list[dict[str, str]]:
    """Return message history (oldest first) suitable for LLM context."""
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE conv_id=? "
            "ORDER BY created_at ASC LIMIT ?",
            (conv_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


# ---------- Inter-agent shared state ----------

def set_shared_state(conv_id: str, key: str, value: Any) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO shared_state (conv_id, key, value_json, updated_at) "
            "VALUES (?,?,?,?) ON CONFLICT(conv_id, key) DO UPDATE SET "
            "value_json=excluded.value_json, updated_at=excluded.updated_at",
            (conv_id, key, json.dumps(value), time.time()),
        )


def get_shared_state(conv_id: str, key: str) -> Any | None:
    with _conn() as c:
        row = c.execute(
            "SELECT value_json FROM shared_state WHERE conv_id=? AND key=?",
            (conv_id, key),
        ).fetchone()
    return json.loads(row["value_json"]) if row else None


# ---------- Cost log ----------

def log_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    est_cost: float,
    conv_id: str | None = None,
) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO cost_log (id, conv_id, model, prompt_tokens, "
            "completion_tokens, est_cost, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                conv_id,
                model,
                prompt_tokens,
                completion_tokens,
                est_cost,
                time.time(),
            ),
        )


def total_cost() -> float:
    with _conn() as c:
        row = c.execute("SELECT COALESCE(SUM(est_cost),0) AS t FROM cost_log").fetchone()
    return float(row["t"])
