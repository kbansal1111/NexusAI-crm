"""
Data visibility scoping service — Industry-grade owner+hierarchy scoping.

Determines which records a user can see based on:
1. Super Admin / admin role → sees everything (returns None = no filter)
2. Manager in hierarchy → sees own records + subordinates' records
3. Regular user → sees only own records

This mirrors how Salesforce/Zoho CRM handle data visibility:
- Record ownership determines base visibility
- Hierarchy determines upward visibility (managers see downline)
- Re-assignment immediately transfers visibility to new owner
"""
from typing import List, Optional
from bson import ObjectId

from app.models.user import User
from app.models.role import Role, RoleHierarchy
from app.services import hierarchy_walker
from app.services import scope_cache


async def _is_admin_user(user: User) -> bool:
    """Check if user has any admin role (is_admin=True on the role).

    SECURITY: Roles must be fetched scoped to the user's tenant_id. A role_id
    referencing another tenant's role (whether by accident or attack) must not
    grant admin privileges in this tenant.
    """
    if not user.role_ids:
        return False
    # Single tenant-scoped query for all the user's role_ids — safer and faster
    # than per-id fetches.
    role = await Role.find_one(
        {
            "_id": {"$in": list(user.role_ids)},
            "tenant_id": user.tenant_id,
            "is_admin": True,
            "deleted_at": None,
        }
    )
    return role is not None


async def _collect_descendant_user_ids(tenant_id: ObjectId, hierarchy_node_id: ObjectId) -> List[ObjectId]:
    """Delegates to the shared hierarchy_walker so up/down BFS lives in one place."""
    return await hierarchy_walker.descendant_user_ids(tenant_id, hierarchy_node_id)


async def _compute_visible_owner_ids(user: User) -> Optional[List[ObjectId]]:
    """Uncached computation of the visible owner set (the role-hierarchy walk)."""
    # Admin sees everything
    if await _is_admin_user(user):
        return None

    # Start with the user's own ID
    allowed: set[ObjectId] = {user.id}

    # If user is in a hierarchy, include all subordinate users
    if user.role_hierarchy_id:
        descendant_ids = await _collect_descendant_user_ids(
            user.tenant_id, user.role_hierarchy_id
        )
        allowed.update(descendant_ids)

    return list(allowed)


async def get_visible_owner_ids(user: User) -> Optional[List[ObjectId]]:
    """
    Returns the list of owner_ids whose records the user can see:
    - None → admin, sees everything (no filter applied)
    - [user.id] → regular user with no hierarchy, sees only own records
    - [user.id, sub1, sub2, ...] → manager, sees own + subordinates

    Result is cached in Redis per (tenant_id, user_id) for ~90s (PERF Phase 2)
    so the role-hierarchy walk doesn't run on every list/detail request. The
    cache is type-safe (ObjectIds round-trip correctly) and is invalidated on
    role / hierarchy changes via scope_cache.invalidate_scope_cache.

    Usage in queries:
        visible = await get_visible_owner_ids(current_user)
        if visible is not None:
            query["owner_id"] = {"$in": visible}
    """
    cached = await scope_cache.get_cached_visible_owner_ids(user.tenant_id, user.id)
    if cached is not scope_cache._MISS:
        return cached

    result = await _compute_visible_owner_ids(user)
    await scope_cache.set_cached_visible_owner_ids(user.tenant_id, user.id, result)
    return result


async def opportunity_pool_owner_ids(user: User) -> List[ObjectId]:
    """Extra owner ids a non-admin user may additionally see for opportunities:
    the tenant's "System" pool of unassigned opportunities.

    Only users who can assign opportunities (edit_opportunity permission) get
    the pool, so a regular salesperson's list isn't cluttered with it. Admins
    already see everything (get_visible_owner_ids returns None), so this is for
    the non-admin pre-sales case. Returns [] when there is no System user yet
    or the user can't assign.
    """
    if not await user.has_permission("edit_opportunity"):
        return []
    from app.services.system_user import get_system_user_id
    system_user_id = await get_system_user_id(user.tenant_id)
    return [system_user_id] if system_user_id else []


def apply_visibility_filter(query: dict, visible_owner_ids: Optional[List[ObjectId]]) -> dict:
    """
    Apply visibility scoping to a MongoDB query dict.
    If visible_owner_ids is None (admin), query is unchanged.
    Otherwise, adds owner_id $in filter.
    """
    if visible_owner_ids is not None:
        query["owner_id"] = {"$in": visible_owner_ids}
    return query


def is_record_visible(record_owner_id: ObjectId, visible_owner_ids: Optional[List[ObjectId]]) -> bool:
    """
    Returns True if the user is allowed to see a specific record.
    - None (admin) → always visible
    - List → owner must be in the list
    """
    if visible_owner_ids is None:
        return True
    return record_owner_id in visible_owner_ids


def is_task_visible(task_owner_id: Optional[ObjectId], task_assigned_id: Optional[ObjectId],
                    visible_owner_ids: Optional[List[ObjectId]]) -> bool:
    """
    Tasks have dual ownership: created_by (owner_id) AND assigned_user_id.
    A task is visible if EITHER the creator OR the assignee is in the user's visible scope.
    Admin (visible_owner_ids=None) always sees everything.
    """
    if visible_owner_ids is None:
        return True
    if task_owner_id and task_owner_id in visible_owner_ids:
        return True
    if task_assigned_id and task_assigned_id in visible_owner_ids:
        return True
    return False


def _merge_or(query: dict, or_clauses: list) -> dict:
    """Merge an $or set into a Mongo query without clobbering an existing one.

    If the query already has an $or, both sets are ANDed together so each
    remains independently satisfied; otherwise the $or is added directly.
    """
    existing_or = query.pop("$or", None)
    if existing_or:
        query.setdefault("$and", []).extend([{"$or": existing_or}, {"$or": or_clauses}])
    else:
        query["$or"] = or_clauses
    return query


async def _compute_bd_territory_ids(user: User) -> Optional[List[ObjectId]]:
    """Uncached: the territories this user manages.

    SINGLE SOURCE OF TRUTH is the Territory document: a user "belongs to" a
    territory if they are its manager (`Territory.manager_id`). "Territory
    Manager" and "BD owner" are the same role, so managing a territory is what
    grants territory-scoped opportunity visibility. This deliberately does NOT
    read the denormalized `User.territory_ids`/`is_bd_user` mirror, so the two
    admin edit paths (Territory settings dialog vs. the User form) can never
    drift into a state where one grants visibility and the other doesn't.

    Tenant-scoped: only this tenant's active territories are considered, so a
    forged/stale territory id can never surface another tenant's data.
    """
    from app.models.territory import Territory

    territories = await Territory.find(
        {
            "tenant_id": user.tenant_id,
            "is_active": True,
            "manager_id": user.id,
        }
    ).to_list()
    return [t.id for t in territories] or None


async def get_bd_territory_ids(user: User) -> Optional[List[ObjectId]]:
    """Territory ids that STRICTLY scope a user's opportunity visibility.

    A user who manages any territory is a Territory Manager / BD user: they see
    exactly the opportunities stamped with their territories — this REPLACES
    owner/hierarchy scope for opportunities rather than widening it (a pure BD
    user owns no opportunities). Returns None when the user manages no territory,
    in which case normal owner/hierarchy scope applies.

    Cached per (tenant_id, user_id) alongside the owner-scope cache (same TTL,
    same invalidation on territory / user changes) so the membership lookup
    doesn't run on every list/detail request. Callers only invoke this for
    non-admins (admins already see the whole tenant), so there is no admin
    sentinel to store here.
    """
    cached = await scope_cache.get_cached_bd_territory_ids(user.tenant_id, user.id)
    if cached is not scope_cache._MISS:
        return cached

    result = await _compute_bd_territory_ids(user)
    await scope_cache.set_cached_bd_territory_ids(user.tenant_id, user.id, result)
    return result


async def opportunity_scope_match(user: User, scope: str = "team") -> dict:
    """Build the MongoDB match for opportunity dashboards/aggregations.

    scope="my"   → strictly the user's own opportunities (owner_id == user).
    scope="team" → the same visibility the opportunity LIST enforces:
      - admin → whole tenant;
      - Territory Manager / BD user → STRICTLY their territories' opportunities;
      - regular user → own + subordinates (owner/hierarchy scope).

    The tenant_id filter is always present, so a forged/stale id can never
    surface another tenant's data. Every dashboard number MUST be built from
    this match (or entity_scope_match below) — never from a bare tenant query —
    so a user can never be shown figures for records they cannot open.
    """
    match: dict = {"tenant_id": user.tenant_id, "deleted_at": None}
    if scope == "my":
        match["owner_id"] = user.id
        return match
    visible = await get_visible_owner_ids(user)
    if visible is None:
        return match  # admin — whole tenant
    bd_terr = await get_bd_territory_ids(user)
    if bd_terr:
        match["territory_id"] = {"$in": bd_terr}  # Territory Manager: territory-only
    else:
        match["owner_id"] = {"$in": visible}
    return match


async def entity_scope_match(user: User, scope: str = "team") -> dict:
    """Owner-scoped match for non-opportunity entities (accounts/contacts/leads).

    Territory scope does not apply to these — they are owner/hierarchy scoped
    like their list endpoints. Admin gets the whole tenant.
    """
    match: dict = {"tenant_id": user.tenant_id, "deleted_at": None}
    if scope == "my":
        match["owner_id"] = user.id
        return match
    visible = await get_visible_owner_ids(user)
    if visible is not None:
        match["owner_id"] = {"$in": visible}
    return match


def is_opportunity_visible(
    record_owner_id: ObjectId,
    record_territory_id: Optional[ObjectId],
    visible_owner_ids: Optional[List[ObjectId]],
    bd_territory_ids: Optional[List[ObjectId]] = None,
) -> bool:
    """Detail-view counterpart of the opportunity list filter.

    - Admin (visible_owner_ids is None) → sees everything.
    - Territory Manager / BD user (bd_territory_ids non-empty) → STRICTLY the
      opportunities in their territories; owner/hierarchy scope does not apply
      (a pure BD user owns no opportunities).
    - Regular user → owner/hierarchy scope.
    """
    if visible_owner_ids is None:
        return True
    if bd_territory_ids:
        return record_territory_id is not None and record_territory_id in bd_territory_ids
    return is_record_visible(record_owner_id, visible_owner_ids)
