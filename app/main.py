# Author: Yogesh Agrawal
"""FastAPI application: API gateway + coordinator + agents entrypoint.

M0 provides the app factory and a health endpoint. Later milestones add
auth, chat, agents, PII, and observability routers.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Banking Multi-Agent Chatbot", version="0.1.0")

    # Ensure session store schema exists.
    from app.session import store
    store.init_db()

    # Routers
    from app.api.chat import router as chat_router
    from app.auth.jwt_auth import router as auth_router
    app.include_router(auth_router)
    app.include_router(chat_router)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "env": settings.app_env}

    return app


app = create_app()
