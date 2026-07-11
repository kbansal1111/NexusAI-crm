"""
System service-user — owns the unassigned "System" opportunity pool.

When a lead is converted to an opportunity without an owner, the opportunity
is assigned to this per-tenant service account so it shows up as owner
"System" (matching the legacy CRM). The pre-sales team then reassigns it to a
real employee. The account is created inactive and not assignable, so it can
never log in or enter auto-assignment — it only holds ownership.
"""
import secrets
import time
from typing import Dict, Optional, Tuple

from bson import ObjectId

from app.models.user import User

SYSTEM_USER_NAME = "System"

# PERF: the System user's id is effectively immutable per tenant, yet
# opportunity_pool_owner_ids looked it up on every opportunity list/detail
# request. Cache it per process with a TTL (mirrors industry_service's cache).
# A cached None ("tenant has no System user yet") also short-circuits the
# lookup; get_or_create_system_user overwrites it the moment one is created.
_TTL_SECONDS = 600
_system_user_id_cache: Dict[str, Tuple[Optional[ObjectId], float]] = {}


def _system_email(tenant_id: ObjectId) -> str:
    # User.email is globally unique — scope the sentinel by tenant id.
    # NOTE: the domain must NOT be a reserved/special-use name (.local, .invalid,
    # .test, .example, localhost). Pydantic's EmailStr validator rejects those,
    # which would make this service account impossible to create and break lead
    # conversion. `.app` is a normal public gTLD and validates cleanly.
    return f"system+{tenant_id}@system.tutterfly.app"


async def get_system_user(tenant_id: ObjectId) -> User | None:
    """Return the tenant's System user, or None if it hasn't been created yet."""
    return await User.find_one(
        {"tenant_id": tenant_id, "is_system": True, "deleted_at": None}
    )


async def get_system_user_id(tenant_id: ObjectId) -> Optional[ObjectId]:
    """Return the tenant's System user id (process-cached, ~10 min TTL).

    Use this on hot read paths (visibility widening) where only the id is
    needed — it skips the per-request DB lookup entirely on a cache hit.
    """
    key = str(tenant_id)
    hit = _system_user_id_cache.get(key)
    if hit is not None and hit[1] > time.monotonic():
        return hit[0]

    user = await get_system_user(tenant_id)
    user_id = user.id if user else None
    _system_user_id_cache[key] = (user_id, time.monotonic() + _TTL_SECONDS)
    return user_id


async def get_or_create_system_user(tenant_id: ObjectId) -> User:
    """Find-or-create the tenant's System service user (race-safe)."""
    existing = await get_system_user(tenant_id)
    if existing:
        return existing

    user = User(
        name=SYSTEM_USER_NAME,
        email=_system_email(tenant_id),
        password=User.hash_password(secrets.token_urlsafe(32)),  # unusable
        tenant_id=tenant_id,
        is_active=False,                     # cannot log in
        is_verified=False,
        is_available_for_assignment=False,   # excluded from auto-assignment
        is_system=True,
        role_ids=[],                         # no permissions
    )
    try:
        await user.insert()
        _system_user_id_cache[str(tenant_id)] = (user.id, time.monotonic() + _TTL_SECONDS)
        return user
    except Exception:
        # Concurrent conversion already created it (unique email) — re-fetch.
        again = await get_system_user(tenant_id)
        if again:
            _system_user_id_cache[str(tenant_id)] = (again.id, time.monotonic() + _TTL_SECONDS)
            return again
        raise
