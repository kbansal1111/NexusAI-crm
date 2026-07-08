"""End-to-end (hermetic) test of the simplified BD assignment.

An opportunity only records WHICH territory it falls into (territory_id /
region_id). The territory's manager (the BD user) is resolved live from the
territory when displayed — nothing is denormalized onto the deal, and there is
no round-robin BD-owner pool.

  - resolve_for_address matches a territory from an address.
  - It returns territory_id + region_id + match_source.
  - An unmatched address yields an empty assignment.
"""
import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from beanie import init_beanie

from app.models.territory import Region, Territory
from app.models.user import User
from app.services.bd_assignment_service import bd_assignment_service


TENANT = ObjectId()


async def _init():
    client = AsyncMongoMockClient()
    await init_beanie(
        database=client[f"bd_assign_{ObjectId()}"],
        document_models=[Region, Territory, User],
    )


@pytest.mark.asyncio
async def test_resolve_returns_matched_territory_and_region():
    await _init()
    region = Region(name="North", tenant_id=TENANT)
    await region.insert()
    territory = Territory(
        name="North India", tenant_id=TENANT, region_id=region.id,
        countries=["India"], manager_id=ObjectId(), is_active=True,
    )
    await territory.insert()

    a = await bd_assignment_service.resolve_for_address(tenant_id=TENANT, country="India")
    assert not a.is_empty()
    assert a.territory_id == territory.id
    assert a.region_id == region.id
    assert a.match_source == "country"


@pytest.mark.asyncio
async def test_resolve_matches_by_state():
    await _init()
    region = Region(name="West", tenant_id=TENANT)
    await region.insert()
    territory = Territory(
        name="West", tenant_id=TENANT, region_id=region.id,
        states=["Goa"], is_active=True,
    )
    await territory.insert()

    a = await bd_assignment_service.resolve_for_address(tenant_id=TENANT, state="Goa")
    assert a.territory_id == territory.id
    assert a.match_source == "state"


@pytest.mark.asyncio
async def test_unmatched_address_yields_empty_assignment():
    await _init()
    region = Region(name="R", tenant_id=TENANT)
    await region.insert()
    await Territory(
        name="Only-India", tenant_id=TENANT, region_id=region.id,
        countries=["India"], is_active=True,
    ).insert()

    a = await bd_assignment_service.resolve_for_address(tenant_id=TENANT, country="Narnia")
    assert a.is_empty()
    assert a.territory_id is None
