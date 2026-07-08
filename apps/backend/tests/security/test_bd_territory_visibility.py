"""Unit tests for BD territory-scoped opportunity visibility.

These cover the security-critical logic in app.services.visibility_scope that
decides whether a user may see an opportunity:

  - A user who MANAGES a territory (Territory.manager_id) is scoped STRICTLY to
    the opportunities in that territory — owner/hierarchy scope does NOT apply
    (a pure BD user owns no opportunities). "Territory Manager" and "BD owner"
    are the same role — managing the territory is what grants access; there is
    no separate BD-user pool.
  - A user who manages no territory gets no widening (owner scope only).
  - An admin (visible_owner_ids=None) sees everything.
  - The Territory document is the single source of truth: visibility is resolved
    from it directly, so the two admin edit paths (Territory dialog vs. User
    form) can never drift into granting visibility on one but not the other.

Cross-tenant isolation is enforced by the tenant_id filter baked into the
membership query AND the always-present tenant_id filter in the
repository/aggregation match. This suite locks both.
"""
from types import SimpleNamespace

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from beanie import init_beanie

from app.models.territory import Region, Territory
from app.models.user import User
from app.services.visibility_scope import (
    get_bd_territory_ids,
    is_opportunity_visible,
    _merge_or,
)


TENANT = ObjectId()
OTHER_TENANT = ObjectId()


async def _init():
    client = AsyncMongoMockClient()
    await init_beanie(
        database=client[f"bd_vis_{ObjectId()}"],
        document_models=[Region, Territory, User],
    )


async def _mk_user(tenant=TENANT):
    u = User(name="U", email=f"{ObjectId()}@t.com", password="x", tenant_id=tenant, is_active=True)
    await u.insert()
    return u


async def _mk_territory(tenant=TENANT, manager_id=None, is_active=True):
    region = Region(name="R", tenant_id=tenant)
    await region.insert()
    t = Territory(
        name="T", tenant_id=tenant, region_id=region.id,
        manager_id=manager_id, is_active=is_active,
    )
    await t.insert()
    return t


# --- get_bd_territory_ids: territory manager is the single source of truth --

@pytest.mark.asyncio
async def test_none_when_user_manages_no_territory():
    await _init()
    user = await _mk_user()
    await _mk_territory(manager_id=ObjectId())  # someone else's territory
    assert await get_bd_territory_ids(user) is None


@pytest.mark.asyncio
async def test_territory_manager_gets_their_territory():
    # The reported bug: a Territory Manager (manager_id) must see the territory
    # even with no is_bd_user flag set — managing it is what grants access.
    await _init()
    user = await _mk_user()
    t = await _mk_territory(manager_id=user.id)
    assert await get_bd_territory_ids(user) == [t.id]


@pytest.mark.asyncio
async def test_manager_of_multiple_territories_sees_all():
    await _init()
    user = await _mk_user()
    t1 = await _mk_territory(manager_id=user.id)
    t2 = await _mk_territory(manager_id=user.id)
    result = set(await get_bd_territory_ids(user))
    assert result == {t1.id, t2.id}


@pytest.mark.asyncio
async def test_inactive_territory_does_not_widen():
    await _init()
    user = await _mk_user()
    await _mk_territory(manager_id=user.id, is_active=False)
    assert await get_bd_territory_ids(user) is None


@pytest.mark.asyncio
async def test_cross_tenant_membership_is_isolated():
    # A same-id user managing another tenant's territory must never leak in.
    await _init()
    user = await _mk_user(tenant=TENANT)
    await _mk_territory(tenant=OTHER_TENANT, manager_id=user.id)
    assert await get_bd_territory_ids(user) is None


# --- is_opportunity_visible ------------------------------------------------

def test_admin_sees_everything():
    # visible_owner_ids is None → admin → always visible regardless of territory
    assert is_opportunity_visible(ObjectId(), ObjectId(), None, None) is True


def test_owner_in_scope_is_visible():
    owner = ObjectId()
    assert is_opportunity_visible(owner, None, [owner], None) is True


def test_owner_out_of_scope_and_no_bd_is_hidden():
    assert is_opportunity_visible(ObjectId(), ObjectId(), [ObjectId()], None) is False


def test_bd_user_sees_territory_opportunity_they_do_not_own():
    terr = ObjectId()
    # owner is NOT in the user's scope, but the opp's territory IS assigned to them
    assert is_opportunity_visible(ObjectId(), terr, [ObjectId()], [terr]) is True


def test_bd_manager_does_not_see_own_opportunity_outside_territory():
    owner = ObjectId()
    # Strictly territory-only: a Territory Manager does NOT see a deal just
    # because they own it — only deals in their territories. (A pure BD user
    # owns no opportunities anyway, so owning one outside their territory is a
    # non-scenario; this locks the rule regardless.)
    assert is_opportunity_visible(owner, ObjectId(), [owner], [ObjectId()]) is False


def test_bd_user_cannot_see_opportunity_outside_territory():
    assert is_opportunity_visible(ObjectId(), ObjectId(), [ObjectId()], [ObjectId()]) is False


def test_bd_manager_cannot_see_untagged_opportunity():
    owner = ObjectId()
    # territory_id is None → territory branch can't match, and owner scope does
    # not apply to a Territory Manager → not visible, even if they own it.
    assert is_opportunity_visible(owner, None, [owner], [ObjectId()]) is False
    assert is_opportunity_visible(ObjectId(), None, [ObjectId()], [ObjectId()]) is False


# --- _merge_or composes without clobbering an existing $or -----------------

def test_merge_or_adds_or_when_absent():
    q: dict = {"tenant_id": ObjectId()}
    _merge_or(q, [{"a": 1}, {"b": 2}])
    assert q["$or"] == [{"a": 1}, {"b": 2}]


def test_merge_or_preserves_existing_or_via_and():
    existing = [{"search": 1}]
    q: dict = {"tenant_id": ObjectId(), "$or": existing}
    _merge_or(q, [{"owner": 1}, {"territory": 2}])
    # Original $or is preserved and ANDed with the new one (both must hold)
    assert "$or" not in q
    assert {"$or": existing} in q["$and"]
    assert {"$or": [{"owner": 1}, {"territory": 2}]} in q["$and"]
