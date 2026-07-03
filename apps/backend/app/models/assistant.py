"""
AI Assistant conversation storage.

Each conversation belongs to one tenant AND one user — a conversation is only
ever readable by its creator (assistant answers are scoped to that user's
visibility, so sharing them across users would leak records the viewer can't
see through the normal UI).

Messages are stored in the OpenAI chat shape (role/content/tool_calls/
tool_call_id) so a turn can be replayed verbatim to OpenRouter.
"""
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
