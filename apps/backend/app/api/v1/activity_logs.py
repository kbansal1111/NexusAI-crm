"""
Activity Log API endpoints
"""
import logging
import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from app.models.user import User
from app.schemas.activity_log import (
    ActivityLogResponse, ActivityLogListResponse,
    LoginLogResponse, LoginLogListResponse
)
from app.services.activity_log_service import ActivityLogService
from app.api.deps import get_current_user, check_permission


_logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/events/", response_model=ActivityLogListResponse)
@router.get("/events", response_model=ActivityLogListResponse)
async def get_activity_logs(
    user_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    days: int = 30,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get activity logs with filters.

    Visibility-scoped: non-admin users only see activity performed by users in
    their visible scope (own + subordinates) — the dashboard stream must not
    reveal the whole tenant's actions to every rep.
    """
    try:
        from app.services.visibility_scope import get_visible_owner_ids
        visible = await get_visible_owner_ids(current_user)
        service = ActivityLogService()
        logs = await service.get_activity_logs(
            current_user.tenant_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            days=days,
            skip=skip,
            limit=limit,
            visible_user_ids=visible,
        )
        return ActivityLogListResponse(
            logs=[ActivityLogResponse.from_orm(l) for l in logs],
            total=len(logs)
        )
    except Exception:
        _logger.exception("Error in get_activity_logs for user %s", current_user.id)
        return ActivityLogListResponse(logs=[], total=0)  # Empty fallback to avoid crash


@router.get("/events/entity/{entity_type}/{entity_id}")
async def get_entity_history(
    entity_type: str,
    entity_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get activity history for an entity"""
    service = ActivityLogService()
    logs = await service.get_entity_history(entity_type, entity_id, current_user.tenant_id)
    return {"logs": [ActivityLogResponse.from_orm(l) for l in logs], "total": len(logs)}


@router.get("/events/user/{user_id}")
async def get_user_activity(
    user_id: str,
    limit: int = 50,
    current_user: User = Depends(check_permission("view_user"))
):
    """Get recent activity for a user"""
    service = ActivityLogService()
    logs = await service.get_user_activity(user_id, current_user.tenant_id, limit=limit)
    return {"logs": [ActivityLogResponse.from_orm(l) for l in logs], "total": len(logs)}


@router.get("/audit")
async def get_api_audit_logs(
    method: Optional[str] = None,
    status_min: Optional[int] = None,
    path_prefix: Optional[str] = None,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    days: int = 7,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
):
    """Raw API audit trail (every mutating request) — ADMIN ONLY.

    Tenant-scoped: an admin only ever sees their own tenant's rows. Rows with
    no tenant (unauthenticated calls such as failed logins) are intentionally
    NOT exposed here — inspect them directly in Mongo / the log files.
    """
    from bson import ObjectId
    from app.models.activity_log import ApiAuditLog
    from app.services.visibility_scope import _is_admin_user

    if not await _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="Admin access required")

    query: dict = {
        "tenant_id": current_user.tenant_id,
        "created_at": {"$gte": datetime.utcnow() - timedelta(days=min(days, 400))},
    }
    if method:
        query["method"] = method.upper()
    if status_min:
        query["status_code"] = {"$gte": status_min}
    if path_prefix:
        # Anchored prefix regex — index-friendly, never a contains-scan.
        query["path"] = {"$regex": f"^{re.escape(path_prefix)}"}
    if user_id:
        query["user_id"] = ObjectId(user_id)
    if request_id:
        query["request_id"] = request_id

    limit = min(max(limit, 1), 200)
    logs = (
        await ApiAuditLog.find(query)
        .sort("-created_at")
        .skip(max(skip, 0))
        .limit(limit)
        .to_list()
    )
    return {
        "logs": [
            {
                "id": str(l.id),
                "request_id": l.request_id,
                "method": l.method,
                "path": l.path,
                "route": l.route,
                "query": l.query,
                "body": l.body,
                "status_code": l.status_code,
                "duration_ms": l.duration_ms,
                "response_error": l.response_error,
                "user_id": str(l.user_id) if l.user_id else None,
                "user_name": l.user_name,
                "user_email": l.user_email,
                "ip_address": l.ip_address,
                "user_agent": l.user_agent,
                "created_at": l.created_at,
            }
            for l in logs
        ],
        "total": len(logs),
    }


@router.get("/logins", response_model=LoginLogListResponse)
async def get_login_logs(
    user_id: Optional[str] = None,
    success: Optional[bool] = None,
    days: int = 30,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(check_permission("view_report"))
):
    """Get login logs with filters"""
    service = ActivityLogService()
    logs = await service.get_login_logs(
        current_user.tenant_id,
        user_id=user_id,
        success=success,
        days=days,
        skip=skip,
        limit=limit
    )
    return LoginLogListResponse(
        logs=[LoginLogResponse.from_orm(l) for l in logs],
        total=len(logs)
    )


@router.get("/logins/user/{user_id}")
async def get_user_login_history(
    user_id: str,
    limit: int = 20,
    current_user: User = Depends(check_permission("view_user"))
):
    """Get login history for a user"""
    service = ActivityLogService()
    logs = await service.get_user_login_history(user_id, current_user.tenant_id, limit=limit)
    return {"logs": [LoginLogResponse.from_orm(l) for l in logs], "total": len(logs)}
