"""
AI Assistant conversation storage.

Each conversation belongs to one tenant AND one user — a conversation is only
ever readable by its creator (assistant answers are scoped to that user's
visibility, so sharing them across users would leak records the viewer can't
see through the normal UI).

Messages are stored in the OpenAI chat shape (role/content/tool_calls/
tool_call_id) so a turn can be replayed verbatim to OpenRouter.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from beanie import Indexed, PydanticObjectId
from pydantic import Field

from app.models.base import BaseDocument


class AssistantConversation(BaseDocument):
    """A user's chat thread with the AI assistant."""

    tenant_id: Indexed(PydanticObjectId)
    user_id: Indexed(PydanticObjectId)

    # First user message, truncated — shown in the conversation list.
    title: Optional[str] = None

    # OpenAI-shaped message dicts (system prompt is NOT stored; it is rebuilt
    # per request so prompt changes apply to old conversations too).
    messages: List[Dict[str, Any]] = Field(default_factory=list)

    class Settings:
        name = "assistant_conversations"
        indexes = [
            [("tenant_id", 1), ("user_id", 1), ("updated_at", -1)],
        ]


class AssistantAction(BaseDocument):
    """A write the assistant PROPOSED and the user must explicitly confirm.

    Security contract:
      * The model can only queue one of these (validated + previewed). It is
        executed exclusively by an authenticated HTTP call from the SAME user
        (POST /assistant/actions/{id}/confirm) — never by model output.
      * `args` are frozen at propose time; confirm executes exactly what was
        previewed, ignoring anything the model says later.
      * Single-use and expiring: status pending → executed | rejected | expired.
    """

    tenant_id: Indexed(PydanticObjectId)
    user_id: Indexed(PydanticObjectId)
    conversation_id: PydanticObjectId

    action_type: str                       # e.g. "update_opportunity"
    args: Dict[str, Any] = Field(default_factory=dict)   # validated at propose time
    summary: str                           # human-readable preview shown in chat
    permission: str                        # RBAC string re-checked at execute time

    status: str = "pending"                # pending | executed | rejected | expired
    result: Optional[Dict[str, Any]] = None
    expires_at: Optional[datetime] = None

    class Settings:
        name = "assistant_actions"
        indexes = [
            [("tenant_id", 1), ("user_id", 1), ("status", 1)],
        ]
