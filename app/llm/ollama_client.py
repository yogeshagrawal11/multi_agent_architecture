# Author: Yogesh Agrawal
"""Ollama HTTP client.

Wraps the host Ollama /api/chat endpoint, supporting tool/function calling.
Used by all agents. Model names come from config (default gpt-oss:120b).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import get_settings


@dataclass
class ChatResult:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class OllamaClient:
    def __init__(self, base_url: str | None = None, timeout: int | None = None) -> None:
        s = get_settings()
        self.base_url = (base_url or s.ollama_base_url).rstrip("/")
        self.timeout = timeout or s.llm_timeout_seconds

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        """Send a chat request. Returns content + any tool calls + token usage."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if tools:
            payload["tools"] = tools

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        message = data.get("message", {}) or {}
        return ChatResult(
            content=message.get("content", "") or "",
            tool_calls=message.get("tool_calls", []) or [],
            prompt_tokens=data.get("prompt_eval_count", 0) or 0,
            completion_tokens=data.get("eval_count", 0) or 0,
            model=data.get("model", model),
            raw=data,
        )

    def embed(self, text: str, model: str | None = None) -> list[float]:
        """Return an embedding vector for text (used by the eval suite)."""
        s = get_settings()
        model = model or s.llm_embed
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json().get("embedding", [])
