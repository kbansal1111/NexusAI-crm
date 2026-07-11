"""
API endpoints for Dashboards and Widgets.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, check_permission
from app.models.user import User
from app.services.dashboard_service import dashboard_service
from app.schemas.dashboard import (
    DashboardCreate, DashboardUpdate, DashboardResponse, DashboardListResponse,
    WidgetCreate, WidgetUpdate, WidgetResponse, WidgetDataResponse,
    DashboardPreferenceUpdate, DashboardPreferenceResponse,
    AnalyticsSummary, PipelineAnalytics, KeyDeal, TaskSummary
)

router = APIRouter()


# ==================== Widget CRUD ====================

@router.post("/widgets", response_model=WidgetResponse)
async def create_widget(
    data: WidgetCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new widget."""
    widget = await dashboard_service.create_widget(
        data=data,
        user_id=str(current_user.id),
        tenant_id=str(current_user.tenant_id)
    )
    return WidgetResponse(
        id=str(widget.id),
        **widget.model_dump(exclude={"id"})
    )


@router.get("/widgets", response_model=list[WidgetResponse])
async def list_widgets(
    widget_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """List available widgets."""
    widgets = await dashboard_service.list_widgets(
        tenant_id=str(current_user.tenant_id),
        widget_type=widget_type,
        user_id=str(current_user.id)
    )
    return [
        WidgetResponse(id=str(w.id), **w.model_dump(exclude={"id"}))
        for w in widgets
    ]


@router.get("/widgets/{widget_id}", response_model=WidgetResponse)
async def get_widget(
    widget_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a widget by ID."""
    widget = await dashboard_service.get_widget(widget_id, str(current_user.tenant_id))
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    return WidgetResponse(
        id=str(widget.id),
        **widget.model_dump(exclude={"id"})
    )


@router.get("/widgets/{widget_id}/data", response_model=WidgetDataResponse)
async def get_widget_data(
    widget_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get widget data by executing its query."""
    try:
        data = await dashboard_service.get_widget_data(
            widget_id=widget_id,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        return WidgetDataResponse(**data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/widgets/{widget_id}", response_model=WidgetResponse)
async def update_widget(
    widget_id: str,
    data: WidgetUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a widget."""
    widget = await dashboard_service.update_widget(
        widget_id=widget_id,
        data=data,
        tenant_id=str(current_user.tenant_id)
    )
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    return WidgetResponse(
        id=str(widget.id),
        **widget.model_dump(exclude={"id"})
    )


@router.delete("/widgets/{widget_id}")
async def delete_widget(
    widget_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a widget."""
    deleted = await dashboard_service.delete_widget(widget_id, str(current_user.tenant_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Widget not found")
    return {"message": "Widget deleted successfully"}


# ==================== User Preferences ====================

@router.get("/preferences", response_model=DashboardPreferenceResponse)
async def get_preferences(
    current_user: User = Depends(get_current_user)
):
    """Get dashboard preferences for current user."""
    preference = await dashboard_service.get_or_create_preferences(
        user_id=str(current_user.id),
        tenant_id=str(current_user.tenant_id)
    )
    return DashboardPreferenceResponse(
        **preference.model_dump()
    )


@router.put("/preferences", response_model=DashboardPreferenceResponse)
async def update_preferences(
    data: DashboardPreferenceUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update dashboard preferences for current user."""
    preference = await dashboard_service.update_user_preferences(
        user_id=str(current_user.id),
        data=data,
        tenant_id=str(current_user.tenant_id)
    )
    return DashboardPreferenceResponse(
        **preference.model_dump()
    )




# ==================== Dashboard CRUD ====================

@router.post("", response_model=DashboardResponse)
async def create_dashboard(
    data: DashboardCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new dashboard."""
    dashboard = await dashboard_service.create_dashboard(
        data=data,
        user_id=str(current_user.id),
        tenant_id=str(current_user.tenant_id)
    )
    return DashboardResponse(
        id=str(dashboard.id),
        **dashboard.model_dump(exclude={"id"})
    )


@router.get("", response_model=DashboardListResponse)
async def list_dashboards(
    current_user: User = Depends(get_current_user)
):
    """List all dashboards for current user."""
    dashboards = await dashboard_service.list_dashboards(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id)
    )
    return DashboardListResponse(
        dashboards=[
            DashboardResponse(id=str(d.id), **d.model_dump(exclude={"id"}))
            for d in dashboards
        ],
        total=len(dashboards)
    )


@router.get("/default", response_model=DashboardResponse)
async def get_default_dashboard(
    current_user: User = Depends(get_current_user)
):
    """Get the default dashboard for current user."""
    dashboard = await dashboard_service.get_default_dashboard(
        user_id=str(current_user.id),
        tenant_id=str(current_user.tenant_id)
    )
    if not dashboard:
        raise HTTPException(status_code=404, detail="No default dashboard found")
    return DashboardResponse(
        id=str(dashboard.id),
        **dashboard.model_dump(exclude={"id"})
    )


async def _monthly_target_for_scope(current_user: User, scope: str) -> float:
    """Real revenue target for the scope — never a hardcoded placeholder.

    scope="my"   → the user's own monthly_revenue_target.
    scope="team" → the summed targets of every active user the caller can see
                   (whole tenant for admins, own+subordinates for managers).
    """
    if scope == "my":
        return float(current_user.monthly_revenue_target or 0)
    from app.services.visibility_scope import get_visible_owner_ids
    visible = await get_visible_owner_ids(current_user)
    q: dict = {"tenant_id": current_user.tenant_id, "deleted_at": None, "is_active": True}
    if visible is not None:
        q["_id"] = {"$in": visible}
    rows = await User.aggregate([
        {"$match": q},
        # monthly_revenue_target is a typed float on User — plain $ifNull suffices.
        {"$group": {"_id": None, "target": {"$sum": {"$ifNull": ["$monthly_revenue_target", 0]}}}},
    ]).to_list()
    return float(rows[0]["target"]) if rows else 0.0


@router.get("/stats", response_model=AnalyticsSummary)
async def get_dashboard_stats(
    scope: str = Query("team", pattern="^(my|team)$"),
    current_user: User = Depends(get_current_user)
):
    """Dashboard analytics statistics, visibility-scoped.

    scope=team (default) → what the user is allowed to see: whole tenant for
    admins, territory for BD users, own+subordinates otherwise.
    scope=my → strictly the user's own records.
    """
    from app.services.visibility_scope import (
        opportunity_scope_match, entity_scope_match, get_visible_owner_ids,
    )
    result = await dashboard_service.get_analytics_summary(
        tenant_id=str(current_user.tenant_id),
        entity_match=await entity_scope_match(current_user, scope),
        opp_match=await opportunity_scope_match(current_user, scope),
        monthly_target=await _monthly_target_for_scope(current_user, scope),
    )
    # Admins see the whole tenant; the frontend hides the My/Team toggle for them.
    result["viewer_is_admin"] = (await get_visible_owner_ids(current_user)) is None
    return result


@router.get("/team-sales")
async def get_team_sales(
    current_user: User = Depends(get_current_user)
):
    """Per-salesperson sales breakdown over the caller's visibility (the legacy
    CRM's "Team Sales" chart): for every visible active user, their closed
    (won this month) revenue, open pipeline value, and monthly target.
    Admin sees every user; a manager their own+subordinates; a rep themselves.
    """
    from datetime import datetime
    from beanie import PydanticObjectId
    from app.models.opportunity import Opportunity
    from app.models.opportunity_picklists import SalesStage
    from app.services.visibility_scope import opportunity_scope_match, get_visible_owner_ids

    tenant_oid = current_user.tenant_id
    match = await opportunity_scope_match(current_user, "team")

    won_ids = [s.id for s in await SalesStage.find(
        {"tenant_id": tenant_oid, "is_won": True}).to_list()]
    lost_ids = [s.id for s in await SalesStage.find(
        {"tenant_id": tenant_oid, "is_lost": True}).to_list()]

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    amount = {"$convert": {"input": "$amount", "to": "double", "onError": 0, "onNull": 0}}

    closed_rows = await Opportunity.aggregate([
        {"$match": {**match, "sales_stage_id": {"$in": won_ids},
                    "close_date": {"$gte": month_start}}},
        {"$group": {"_id": "$owner_id", "v": {"$sum": amount}}},
    ]).to_list()
    open_rows = await Opportunity.aggregate([
        {"$match": {**match, "sales_stage_id": {"$nin": won_ids + lost_ids}}},
        {"$group": {"_id": "$owner_id", "v": {"$sum": amount}}},
    ]).to_list()
    closed_by = {str(r["_id"]): r.get("v", 0) or 0 for r in closed_rows if r.get("_id")}
    open_by = {str(r["_id"]): r.get("v", 0) or 0 for r in open_rows if r.get("_id")}

    # Visible ACTIVE users — visibility-scoped so a rep never sees colleagues'
    # numbers. Only SALESPEOPLE make the chart, decided by role + department:
    #   - admin-role users are NEVER bars (they oversee, they don't sell);
    #   - users in a "Sales" department (User.department_id or the department's
    #     mapping) always appear, even at zero — that's the sales team roster;
    #   - otherwise a non-admin appears only with real sales signals (owns
    #     closed/open deals or has a revenue target set), which keeps
    #     accounts/ops/handler test users out of the chart.
    from app.models.role import Role
    from app.models.department import Department
    from app.models.consolidated_settings import DepartmentMapping

    visible = await get_visible_owner_ids(current_user)
    user_query: dict = {"tenant_id": tenant_oid, "deleted_at": None, "is_active": True}
    if visible is not None:
        user_query["_id"] = {"$in": visible}
    users = await User.find(user_query).to_list()

    admin_role_ids = {
        r.id for r in await Role.find(
            {"tenant_id": tenant_oid, "is_admin": True, "deleted_at": None}
        ).to_list()
    }

    sales_depts = await Department.find({
        "tenant_id": tenant_oid,
        "deleted_at": None,
        "is_active": True,
        "name": {"$regex": "sales", "$options": "i"},
    }).to_list()
    sales_dept_ids = {d.id for d in sales_depts}
    sales_dept_user_ids: set = set()
    if sales_dept_ids:
        mappings = await DepartmentMapping.find({
            "tenant_id": tenant_oid,
            "department_id": {"$in": list(sales_dept_ids)},
        }).to_list()
        for mp in mappings:
            sales_dept_user_ids.update(mp.user_ids or [])

    def _is_salesperson(u: User, closed: float, opened: float, target: float) -> bool:
        if u.role_ids and admin_role_ids.intersection(u.role_ids):
            return False
        if (u.department_id and u.department_id in sales_dept_ids) or u.id in sales_dept_user_ids:
            return True
        return closed > 0 or opened > 0 or target > 0

    members = []
    for u in users:
        closed_v = closed_by.get(str(u.id), 0)
        open_v = open_by.get(str(u.id), 0)
        target_v = float(u.monthly_revenue_target or 0)
        if _is_salesperson(u, closed_v, open_v, target_v):
            members.append({
                "user_id": str(u.id),
                "name": u.name,
                "closed": closed_v,
                "open": open_v,
                "target": target_v,
            })
    members.sort(key=lambda m: (m["closed"] + m["open"]), reverse=True)

    # Totals come from the aggregation rows (not the member list) so deals
    # owned by deactivated users still count toward the honest total.
    return {
        "members": members,
        "closed": sum(closed_by.values()),
        "open": sum(open_by.values()),
        "target": sum(m["target"] for m in members),
    }


@router.get("/recent-sales")
async def get_recent_sales(
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    """Get recent sales data (visibility-scoped)."""
    from app.services.visibility_scope import opportunity_scope_match
    return await dashboard_service.get_recent_sales(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        limit=limit,
        scope_key="team",
        match=await opportunity_scope_match(current_user, "team"),
    )


@router.get("/revenue-chart")
async def get_revenue_chart(
    period: str = Query("month", pattern="^(week|month|year)$"),
    scope: str = Query("team", pattern="^(my|team)$"),
    current_user: User = Depends(get_current_user)
):
    """Get revenue chart data (visibility-scoped; scope=my|team)."""
    from app.services.visibility_scope import opportunity_scope_match
    return await dashboard_service.get_revenue_chart(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        period=period,
        scope_key=scope,
        match=await opportunity_scope_match(current_user, scope),
    )


@router.get("/opportunities-by-stage")
async def get_opportunities_by_stage(
    scope: str = Query("team", pattern="^(my|team)$"),
    current_user: User = Depends(get_current_user)
):
    """Get opportunities grouped by sales stage (visibility-scoped)."""
    from app.services.visibility_scope import opportunity_scope_match
    return await dashboard_service.get_opportunities_by_stage(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        scope_key=scope,
        match=await opportunity_scope_match(current_user, scope),
    )


@router.get("/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(
    dashboard_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get a dashboard by ID."""
    dashboard = await dashboard_service.get_dashboard(dashboard_id, str(current_user.tenant_id))
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return DashboardResponse(
        id=str(dashboard.id),
        **dashboard.model_dump(exclude={"id"})
    )


@router.put("/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: str,
    data: DashboardUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update a dashboard."""
    dashboard = await dashboard_service.update_dashboard(
        dashboard_id=dashboard_id,
        data=data,
        tenant_id=str(current_user.tenant_id)
    )
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return DashboardResponse(
        id=str(dashboard.id),
        **dashboard.model_dump(exclude={"id"})
    )


@router.delete("/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a dashboard."""
    deleted = await dashboard_service.delete_dashboard(dashboard_id, str(current_user.tenant_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return {"message": "Dashboard deleted successfully"}


@router.post("/{dashboard_id}/set-default")
async def set_default_dashboard(
    dashboard_id: str,
    current_user: User = Depends(get_current_user)
):
    """Set a dashboard as the user's default."""
    success = await dashboard_service.set_default_dashboard(
        dashboard_id=dashboard_id,
        user_id=str(current_user.id),
        tenant_id=str(current_user.tenant_id)
    )
    if not success:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return {"message": "Default dashboard set successfully"}


# ==================== Analytics ====================

@router.get("/analytics/summary")
async def get_analytics_summary(
    scope: str = Query("my", pattern="^(my|team)$"),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive analytics summary (visibility-scoped; defaults to own records)."""
    from app.services.visibility_scope import opportunity_scope_match, entity_scope_match
    return await dashboard_service.get_analytics_summary(
        tenant_id=str(current_user.tenant_id),
        entity_match=await entity_scope_match(current_user, scope),
        opp_match=await opportunity_scope_match(current_user, scope),
        monthly_target=await _monthly_target_for_scope(current_user, scope),
    )


@router.get("/analytics/pipeline")
async def get_pipeline_analytics(
    current_user: User = Depends(get_current_user)
):
    """Get opportunity pipeline analytics (visibility-scoped)."""
    from app.services.visibility_scope import opportunity_scope_match
    return await dashboard_service.get_pipeline_analytics(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        scope_key="team",
        match=await opportunity_scope_match(current_user, "team"),
    )


@router.get("/analytics/key-deals", response_model=List[KeyDeal])
async def get_key_deals(
    limit: int = 5,
    current_user: User = Depends(get_current_user)
):
    """Get key deals (high value opportunities, visibility-scoped)."""
    from app.services.visibility_scope import opportunity_scope_match
    return await dashboard_service.get_key_deals(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        limit=limit,
        scope_key="team",
        match=await opportunity_scope_match(current_user, "team"),
    )


@router.get("/analytics/tasks-summary", response_model=TaskSummary)
async def get_tasks_summary(
    current_user: User = Depends(get_current_user)
):
    """Get summary of tasks."""
    return await dashboard_service.get_task_summary(
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id)
    )
