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
from app.models.assistant import AssistantConversation
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
