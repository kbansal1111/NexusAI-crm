"""End-to-end (hermetic) test of the BD assignment chain.

Proves the exact behaviour described for the opportunity right panel:

  - resolve_for_address matches a territory from an address.
  - BD Owner is round-robin picked from Territory.users (oldest last_assigned_at
    first) and the pick is rotated on the next call.
  - Reporting Manager is the BD owner's manager walked UP the RoleHierarchy.
  - Territory Manager (Territory.manager_id) is a SEPARATE field and can be a
    different person than the Reporting Manager.
  - With no reps pooled, BD Owner falls back to the Territory Manager.
  - An unmatched address yields an empty assignment.
"""
from datetime import datetime

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from beanie import init_beanie

from app.models.territory import Region, Territory
from app.models.user import User
from app.models.role import RoleHierarchy
from app.services.bd_assignment_service import bd_assignment_service


TENANT = ObjectId()


async def _init():
    client = AsyncMongoMockClient()
    await init_beanie(
        database=client[f"bd_assign_{ObjectId()}"],
        document_models=[Region, Territory, User, RoleHierarchy],
    )


async def _user(name, email, hierarchy_id=None, last_assigned=None):
    u = User(
        name=name, email=email, password="x", tenant_id=TENANT,
        is_active=True, is_available_for_assignment=True,
        role_hierarchy_id=hierarchy_id, last_assigned_at=last_assigned,
    )
    await u.insert()
    return u


@pytest.mark.asyncio
async def test_assignment_chain_bd_owner_reporting_and_territory_manager_are_distinct():
    await _init()

    # Role hierarchy: manager node (Reporting Manager) is parent of the rep node.
    node_mgr = RoleHierarchy(name="Managers", tenant_id=TENANT, parent_id=None, level=0)
    await node_mgr.insert()
    node_rep = RoleHierarchy(name="Reps", tenant_id=TENANT, parent_id=node_mgr.id, level=1)
    await node_rep.insert()

    reporting_mgr = await _user("Reporting Boss", "boss@t.com", hierarchy_id=node_mgr.id)
    node_mgr.user_ids = [reporting_mgr.id]
    await node_mgr.save()

    rep1 = await _user("Rep One", "rep1@t.com", hierarchy_id=node_rep.id,
                       last_assigned=datetime(2020, 1, 1))
    rep2 = await _user("Rep Two", "rep2@t.com", hierarchy_id=node_rep.id,
                       last_assigned=datetime(2021, 1, 1))
    node_rep.user_ids = [rep1.id, rep2.id]
    await node_rep.save()

    # Territory Manager is a DIFFERENT person from the reporting manager.
    territory_mgr = await _user("Territory Head", "thead@t.com")

    region = Region(name="North", tenant_id=TENANT)
    await region.insert()
    territory = Territory(
        name="North India", tenant_id=TENANT, region_id=region.id,
        countries=["India"], users=[rep1.id, rep2.id], manager_id=territory_mgr.id,
        is_active=True,
    )
    await territory.insert()

    # --- First resolve: oldest last_assigned_at (rep1) is picked ---
    a1 = await bd_assignment_service.resolve_for_address(tenant_id=TENANT, country="India")
    assert not a1.is_empty()
    assert a1.territory_id == territory.id
    assert a1.bd_owner_id == rep1.id                      # round-robin: oldest first
    assert a1.reporting_manager_id == reporting_mgr.id    # rep1's hierarchy manager
    assert a1.match_source == "country"

    # BD Owner (rep1) is NOT the Territory Manager, and the Reporting Manager
    # (reporting_mgr) is ALSO distinct from the Territory Manager.
    assert a1.bd_owner_id != territory.manager_id
    assert a1.reporting_manager_id != territory.manager_id
    assert territory.manager_id == territory_mgr.id

    # --- Second resolve: rep1 was bumped, so rep2 (now oldest) is picked ---
    a2 = await bd_assignment_service.resolve_for_address(tenant_id=TENANT, country="India")
    assert a2.bd_owner_id == rep2.id


@pytest.mark.asyncio
async def test_bd_owner_falls_back_to_territory_manager_when_no_reps():
    await _init()
    territory_mgr = await _user("Solo Head", "solo@t.com")
    region = Region(name="West", tenant_id=TENANT)
    await region.insert()
    territory = Territory(
        name="West", tenant_id=TENANT, region_id=region.id,
        states=["Goa"], users=[], manager_id=territory_mgr.id, is_active=True,
    )
    await territory.insert()

    a = await bd_assignment_service.resolve_for_address(tenant_id=TENANT, state="Goa")
    assert a.territory_id == territory.id
    assert a.bd_owner_id == territory_mgr.id   # fallback to the territory manager
    assert a.match_source == "state"


@pytest.mark.asyncio
async def test_unmatched_address_yields_empty_assignment():
    await _init()
    region = Region(name="R", tenant_id=TENANT)
    await region.insert()
    await Territory(
        name="Only-India", tenant_id=TENANT, region_id=region.id,
        countries=["India"], users=[], is_active=True,
    ).insert()

    a = await bd_assignment_service.resolve_for_address(tenant_id=TENANT, country="Narnia")
    assert a.is_empty()
    assert a.territory_id is None
    assert a.bd_owner_id is None
