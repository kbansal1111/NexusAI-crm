"""Hermetic test: same-level (peer) users cannot see each other's records.

This locks the "point 2" requirement: two users at the SAME hierarchy level
(siblings under a common manager) each see only their own records — never each
other's — while the shared manager sees both. Because every domain list/detail
endpoint (accounts, leads, opportunities, contacts, ...) funnels through the
SAME engine — get_visible_owner_ids() → owner_id ∈ {visible} — proving the
owner-set computation and the filter helper here proves peer isolation for all
of them. A real Account collection query is exercised end-to-end as the
representative entity.

Tree:
    Manager (root)
      ├── PeerA   (user a)
      └── PeerB   (user b)

Expected visible-owner sets:
    a       -> {a}            (no descendants; sibling b excluded)
    b       -> {b}
    manager -> {manager, a, b}
"""
import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from beanie import init_beanie

from app.models.account import Account
from app.models.role import Role, RoleHierarchy
from app.models.user import User
from app.services.visibility_scope import (
    get_visible_owner_ids,
    apply_visibility_filter,
    is_record_visible,
)


TENANT = ObjectId()


async def _init():
    client = AsyncMongoMockClient()
    await init_beanie(
        database=client[f"peer_iso_{ObjectId()}"],
        document_models=[Account, Role, RoleHierarchy, User],
    )


async def _node(name, parent_id=None, level=0):
    n = RoleHierarchy(name=name, tenant_id=TENANT, parent_id=parent_id, level=level)
    await n.insert()
    return n


async def _user(node_id):
    u = User(
        name="U", email=f"{ObjectId()}@t.com", password="x",
        tenant_id=TENANT, is_active=True, role_hierarchy_id=node_id,
    )
    await u.insert()
    return u


async def _account(owner):
    a = Account(
        name=f"Acct-{ObjectId()}", tenant_id=TENANT,
        owner_id=owner.id, created_by=owner.id,
    )
    await a.insert()
    return a


async def _seed():
    mgr_node = await _node("Manager", level=0)
    a_node = await _node("PeerA", parent_id=mgr_node.id, level=1)
    b_node = await _node("PeerB", parent_id=mgr_node.id, level=1)

    manager = await _user(mgr_node.id)
    a = await _user(a_node.id)
    b = await _user(b_node.id)
    return manager, a, b


# --- The shared engine: correct owner sets per user ------------------------

@pytest.mark.asyncio
async def test_peer_sees_only_self():
    await _init()
    _, a, b = await _seed()
    assert set(await get_visible_owner_ids(a)) == {a.id}
    assert set(await get_visible_owner_ids(b)) == {b.id}
    # The crux: neither peer's visible set contains the other.
    assert b.id not in set(await get_visible_owner_ids(a))
    assert a.id not in set(await get_visible_owner_ids(b))


@pytest.mark.asyncio
async def test_manager_sees_both_peers():
    await _init()
    manager, a, b = await _seed()
    assert set(await get_visible_owner_ids(manager)) == {manager.id, a.id, b.id}


# --- Real Account query: a peer's list excludes the sibling's records ------

@pytest.mark.asyncio
async def test_peer_account_list_excludes_sibling():
    await _init()
    manager, a, b = await _seed()
    acct_a = await _account(a)
    acct_b = await _account(b)

    # Build the exact query shape every list endpoint uses.
    visible_a = await get_visible_owner_ids(a)
    query_a = apply_visibility_filter({"tenant_id": TENANT, "deleted_at": None}, visible_a)
    rows_a = await Account.find(query_a).to_list()
    ids_a = {r.id for r in rows_a}
    assert acct_a.id in ids_a
    assert acct_b.id not in ids_a          # sibling's account never leaks in

    # Manager's query returns both peers' accounts.
    visible_m = await get_visible_owner_ids(manager)
    query_m = apply_visibility_filter({"tenant_id": TENANT, "deleted_at": None}, visible_m)
    ids_m = {r.id for r in await Account.find(query_m).to_list()}
    assert {acct_a.id, acct_b.id} <= ids_m


# --- Detail-view parity: is_record_visible agrees with the list filter -----

@pytest.mark.asyncio
async def test_detail_view_peer_isolation():
    await _init()
    manager, a, b = await _seed()
    acct_b = await _account(b)

    visible_a = await get_visible_owner_ids(a)
    visible_m = await get_visible_owner_ids(manager)
    # a cannot open b's record; manager can.
    assert is_record_visible(acct_b.owner_id, visible_a) is False
    assert is_record_visible(acct_b.owner_id, visible_m) is True
