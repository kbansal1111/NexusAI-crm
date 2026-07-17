"""
Activity Log models for tracking user actions and system events
"""
from beanie import Document, Indexed
from pydantic import Field
from typing import Optional, Dict, Any
from beanie import PydanticObjectId
from datetime import datetime, timezone
from app.models.base import BaseDocument


class ActivityLog(BaseDocument):
    """Activity log for tracking user actions"""
    
    # Who
    user_id: Indexed(PydanticObjectId)
    user_name: str
    
    # What
    action: Indexed(str)  # create, update, delete, view, login, logout, etc.
    entity_type: Indexed(str)  # account, contact, lead, opportunity, etc.
    entity_id: Optional[PydanticObjectId] = None
    entity_name: Optional[str] = None
    
    # Details
    description: str
    changes: Optional[Dict[str, Any]] = None  # For updates: {field: {old: x, new: y}}
    metadata: Optional[Dict[str, Any]] = None
    
    # Context
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Tenant
    tenant_id: Indexed(PydanticObjectId)
    
    class Settings:
        name = "activity_logs"
        # This is the permanent audit / module-history store (never auto-deleted),
        # so it grows over time — these indexes keep its queries fast.
        indexes = [
            # Dashboard "Recent Activity" + activity page: tenant-wide, newest first.
            [("tenant_id", 1), ("created_at", -1)],
            # Module History tabs: per-entity lookups.
            [("entity_type", 1), ("entity_id", 1)],
        ]


class LoginLog(BaseDocument):
    """Login history tracking"""
    
    user_id: Indexed(PydanticObjectId)
    user_name: str
    user_email: str
    
    # Status
    success: bool = True
    failure_reason: Optional[str] = None
    
    # Context
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_type: Optional[str] = None  # desktop, mobile, tablet
    browser: Optional[str] = None
    os: Optional[str] = None
    location: Optional[str] = None
    
    # Session
    session_id: Optional[str] = None
    logout_at: Optional[datetime] = None
    
    # Tenant
    tenant_id: Indexed(PydanticObjectId)
    
    class Settings:
        name = "login_logs"
        # indexes = [
        # "user_id", "tenant_id", "success",
        # [("tenant_id", 1), ("created_at", -1)],
            # [("user_id", 1), ("created_at", -1)],
        # ]


class ApiAuditLog(Document):
    """Automatic audit record of every mutating API request.

    Written by ActivityContextMiddleware (app/middleware/activity_context.py)
    for all POST/PUT/PATCH/DELETE calls under /api/v1 — no endpoint opts in or
    out, so coverage can never drift as new routes are added. This is the
    "who changed what, when, from where" safety net; the human-curated
    per-entity timeline stays in `activity_logs`.

    NOT a BaseDocument on purpose: audit entries are never soft-deleted, and
    tenant_id must stay optional (failed logins / public integration calls have
    no authenticated tenant). Retention is a Mongo TTL index on `created_at`
    (see scripts/create_indexes.py), sized by settings.AUDIT_LOG_RETENTION_DAYS.
    """

    # Correlation — same id as the X-Request-ID response header and the
    # [req:...] field on every log line for this request.
    request_id: Optional[str] = None

    # Request
    method: str
    path: str
    route: Optional[str] = None       # matched route template, e.g. /api/v1/leads/{lead_id}
    query: Optional[str] = None
    body: Optional[Any] = None        # sanitized (secrets redacted, size-capped)

    # Outcome
    status_code: int
    duration_ms: Optional[float] = None
    response_error: Optional[Any] = None  # error payload when status >= 400

    # Actor (absent for unauthenticated calls, e.g. failed logins)
    user_id: Optional[PydanticObjectId] = None
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    tenant_id: Optional[PydanticObjectId] = None

    # Origin
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "api_audit_logs"
        # Indexes (incl. the TTL index) are managed out-of-band by
        # scripts/create_indexes.py — see that file.
