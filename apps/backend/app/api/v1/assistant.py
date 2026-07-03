"""
AI Assistant endpoints — Phase 1 (read-only, Opportunities).

POST /chat streams Server-Sent Events; the assistant acts strictly AS the
authenticated user (tenant + RBAC + visibility all derive from `current_user`).
Conversations are private to their creator within the tenant.
"""
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import check_permission
from app.models.assistant import AssistantAction, AssistantConversation
from app.models.user import User
from app.services.assistant_service import AssistantService

router = APIRouter()

_service = AssistantService()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[str] = None


@router.post("/chat")
async def chat(
    body: ChatRequest,
    current_user: User = Depends(check_permission("view_opportunity")),
):
    """Stream one assistant turn as SSE (events: meta, tool, token, done, error)."""
    return StreamingResponse(
        _service.stream_chat(current_user, body.message, body.conversation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering so tokens flush live
        },
    )


def _owned_query(current_user: User) -> dict:
    return {
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "deleted_at": None,
    }


@router.get("/conversations")
async def list_conversations(
    current_user: User = Depends(check_permission("view_opportunity")),
):
    """The caller's own conversations, newest first (metadata only)."""
    convos = await AssistantConversation.find(
        _owned_query(current_user)
    ).sort("-updated_at").limit(50).to_list()
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "updated_at": c.updated_at,
            "message_count": len(c.messages),
        }
        for c in convos
    ]


async def _get_owned_conversation(conversation_id: str, current_user: User) -> AssistantConversation:
    try:
        cid = ObjectId(conversation_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")
    convo = await AssistantConversation.find_one({"_id": cid, **_owned_query(current_user)})
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return convo


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(check_permission("view_opportunity")),
):
    convo = await _get_owned_conversation(conversation_id, current_user)
    # Only user/assistant text is renderable in the UI; tool plumbing stays internal.
    visible = [
        {"role": m["role"], "content": m.get("content")}
        for m in convo.messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return {"id": str(convo.id), "title": convo.title, "messages": visible}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(check_permission("view_opportunity")),
):
    convo = await _get_owned_conversation(conversation_id, current_user)
    await convo.soft_delete()
    return {"message": "Conversation deleted"}


# ─────────────────── Confirmed write actions (Phase 2) ─────────────────────────
# The assistant only QUEUES writes; these endpoints are the sole execution path,
# driven by an explicit user click on the confirmation card.

async def _get_owned_pending_action(action_id: str, current_user: User) -> AssistantAction:
    from datetime import datetime

    try:
        aid = ObjectId(action_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid action ID")
    action = await AssistantAction.find_one({
        "_id": aid,
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,   # only the proposing user may decide
        "deleted_at": None,
    })
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    if action.status != "pending":
        raise HTTPException(status_code=400, detail=f"Action is already {action.status}.")
    if action.expires_at and action.expires_at < datetime.utcnow():
        action.status = "expired"
        await action.save()
        raise HTTPException(status_code=400, detail="Action expired. Ask the assistant again.")
    return action


async def _append_action_outcome(action: AssistantAction, outcome_text: str):
    """Record the outcome in the conversation as an internal system note so the
    model knows what happened on the next turn (never rendered in the UI)."""
    convo = await AssistantConversation.find_one({
        "_id": action.conversation_id,
        "tenant_id": action.tenant_id,
        "user_id": action.user_id,
        "deleted_at": None,
    })
    if convo:
        convo.messages = convo.messages + [{"role": "system", "content": outcome_text}]
        await convo.save()


@router.post("/actions/{action_id}/confirm")
async def confirm_action(
    action_id: str,
    current_user: User = Depends(check_permission("view_opportunity")),
):
    """Execute a pending action the user explicitly approved."""
    from app.services.assistant_actions import execute_action

    action = await _get_owned_pending_action(action_id, current_user)
    try:
        result = await execute_action(action, current_user)
    except ValueError as exc:
        action.status = "rejected"
        action.result = {"error": str(exc)}
        await action.save()
        raise HTTPException(status_code=400, detail=str(exc))

    action.status = "executed"
    action.result = result
    await action.save()
    await _append_action_outcome(
        action, f"[User APPROVED the proposed action '{action.summary}'. Result: {result}]"
    )
    return {"status": "executed", "result": result}


@router.post("/actions/{action_id}/reject")
async def reject_action(
    action_id: str,
    current_user: User = Depends(check_permission("view_opportunity")),
):
    """Cancel a pending action."""
    action = await _get_owned_pending_action(action_id, current_user)
    action.status = "rejected"
    await action.save()
    await _append_action_outcome(
        action, f"[User CANCELLED the proposed action '{action.summary}'. Do not retry unless asked.]"
    )
    return {"status": "rejected"}
