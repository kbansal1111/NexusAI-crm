"""
IntegrationToken — per-tenant API keys for public integration endpoints
(web-to-lead etc.). Industry-standard API-key pattern:

  - Plaintext key is NEVER stored — only its SHA-256 hash. The plaintext is
    shown exactly once at creation (scripts/manage_integration_tokens.py).
  - `token_prefix` (first 8 chars) is kept so admins can identify a key
    without ever seeing it in full (Stripe-style "a3f8c2e9...").
  - Multiple active keys per tenant → zero-downtime rotation: create a new
    key, deploy it to the website, then revoke the old one.
  - `scopes` gates what a key may do; web-to-lead uses "leads:write".

SECURITY: the tenant a request writes into is resolved ONLY from the matched
token document — never from the request body.
"""
from beanie import Indexed, PydanticObjectId
from pydantic import Field
from typing import List, Optional
from datetime import datetime, timezone

from app.models.base import BaseDocument

SCOPE_LEADS_WRITE = "leads:write"


class IntegrationToken(BaseDocument):
    tenant_id: Indexed(PydanticObjectId)
    token_hash: Indexed(str)  # sha256 hexdigest of the plaintext key
    token_prefix: str  # first 8 chars of plaintext, for identification only
    label: str = "Website"  # human name: which site/partner holds this key
    scopes: List[str] = Field(default_factory=lambda: [SCOPE_LEADS_WRITE])

    is_active: bool = True
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_by: Optional[PydanticObjectId] = None

    class Settings:
        name = "integration_tokens"

    def is_valid(self) -> bool:
        """Active, not revoked, not expired, not soft-deleted."""
        if not self.is_active or self.revoked_at or self.deleted_at:
            return False
        if self.expires_at:
            expires = self.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < datetime.now(timezone.utc):
                return False
        return True
