# Author: Yogesh Agrawal
"""Chat API routes.

The authenticated identity (JWT) supplies the customer_id and role. The
customer_id used for ALL data access comes from the token — never from the
request body — so a customer can only access their own data. The role drives
the RBAC filter passed into the coordinator/sub-agents.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.agents.coordinator import run_coordinator
from app.auth.jwt_auth import Identity, get_current_identity
from app.auth.rbac import build_allowed_tool_filter
from app.observability.cost import record_cost
from app.observability.langfuse_trace import log_span, trace
from app.pii.redactor import redact
from app.session import store

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    session_id: str | None = None  # Langfuse session: stable from login→logout


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    plan: list[str] = []


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    identity: Identity = Depends(get_current_identity),
) -> ChatResponse:
    customer_id = identity.customer_id  # from verified token, not user input
    conv_id = req.conversation_id or store.create_conversation(customer_id)
    history = store.get_history(conv_id)
    store.add_message(conv_id, "user", req.message)

    # PII redaction: mask sensitive data BEFORE any LLM call (even local).
    redaction = redact(req.message)

    rbac_filter = build_allowed_tool_filter(identity.role)

    with trace(
        name="chat",
        user_id=customer_id,
        session_id=req.session_id,
        metadata={"role": identity.role, "pii_entities": redaction.entities},
    ) as tr:
        log_span(tr, "input", inputs={"masked_message": redaction.text})
        result = run_coordinator(
            user_message=redaction.text,
            customer_id=customer_id,
            conv_id=conv_id,
            history=history,
            allowed_tool_filter=rbac_filter,
        )
        log_span(tr, "plan", outputs={"plan": result.plan})
        for inv in result.tool_invocations:
            log_span(
                tr,
                f"tool:{inv['name']}",
                inputs=inv.get("arguments", {}),
                outputs={"result": inv.get("result")},
            )

    # De-mask the final answer for the authenticated customer only.
    reply = redaction.unmask(result.reply)

    store.add_message(conv_id, "assistant", reply)
    cost = record_cost(
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        conv_id=conv_id,
    )
    return ChatResponse(reply=reply, conversation_id=conv_id, plan=result.plan)
