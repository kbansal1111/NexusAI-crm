"""End-to-end (hermetic) test of territory manager → BD visibility wiring.

This locks the fix for the reported bug: "Territory Manager" and "BD owner" are
the same role, and assigning a user as a territory's manager must grant them
territory-scoped opportunity visibility. Previously the Territory settings dialog
wrote the assignment without touching the user's visibility source, so managers
saw nothing (a silent desync).

Now the Territory document is the single source of truth; these tests drive the
real territory_service and assert both the visibility resolution and the
denormalized User.territory_ids mirror + tenant validation.
"""
import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from beanie import init_beanie

from app.models.territory import Region, Territory
from app.models.user import User
from app.schemas.territory import TerritoryCreate, TerritoryUpdate
from app.services.territory_service import territory_service
from app.services.visibility_scope import get_bd_territory_ids


TENANT = ObjectId()
OTHER_TENANT = ObjectId()


async def _init():
    client = AsyncMongoMockClient()
    await init_beanie(
        database=client[f"terr_ms_{ObjectId()}"],
        document_models=[Region, Territory, User],
    )


async def _user(tenant=TENANT):
    u = User(name="U", email=f"{ObjectId()}@t.com", password="x", tenant_id=tenant, is_active=True)
    await u.insert()
    return u


async def _region():
    r = Region(name="R", tenant_id=TENANT)
    await r.insert()
    return r


@pytest.mark.asyncio
async def test_manager_assignment_grants_visibility_and_mirror():
    await _init()
    region = await _region()
    manager = await _user()

    territory = await territory_service.create_territory(
        data=TerritoryCreate(name="North", region_id=str(region.id), manager_id=str(manager.id)),
        user_id=str(ObjectId()),
        tenant_id=TENANT,
    )

    # Visibility: the territory manager now sees the territory (the desync bug).
    assert await get_bd_territory_ids(manager) == [territory.id]

    # Mirror: User.territory_ids reflects the assignment + the BD flag so the
    # User form reveals it.
    refreshed = await User.get(manager.id)
    assert territory.id in refreshed.territory_ids
    assert refreshed.is_bd_user is True


@pytest.mark.asyncio
async def test_forged_cross_tenant_manager_is_rejected():
    await _init()
    region = await _region()
    foreign = await _user(tenant=OTHER_TENANT)  # not in TENANT

    with pytest.raises(ValueError):
        await territory_service.create_territory(
            data=TerritoryCreate(name="X", region_id=str(region.id), manager_id=str(foreign.id)),
            user_id=str(ObjectId()),
            tenant_id=TENANT,
        )


@pytest.mark.asyncio
async def test_reassigning_manager_moves_visibility_and_mirror():
    await _init()
    region = await _region()
    first = await _user()
    second = await _user()

    territory = await territory_service.create_territory(
        data=TerritoryCreate(name="North", region_id=str(region.id), manager_id=str(first.id)),
        user_id=str(ObjectId()),
        tenant_id=TENANT,
    )
    assert await get_bd_territory_ids(first) == [territory.id]

    await territory_service.update_territory(
        territory_id=str(territory.id),
        data=TerritoryUpdate(manager_id=str(second.id)),
        tenant_id=TENANT,
    )
    # Access transfers cleanly: new manager gains it, old manager loses it.
    assert await get_bd_territory_ids(second) == [territory.id]
    assert await get_bd_territory_ids(first) is None
    assert territory.id not in (await User.get(first.id)).territory_ids
    assert territory.id in (await User.get(second.id)).territory_ids


@pytest.mark.asyncio
async def test_clearing_manager_revokes_visibility():
    await _init()
    region = await _region()
    manager = await _user()

    territory = await territory_service.create_territory(
        data=TerritoryCreate(name="North", region_id=str(region.id), manager_id=str(manager.id)),
        user_id=str(ObjectId()),
        tenant_id=TENANT,
    )
    assert await get_bd_territory_ids(manager) == [territory.id]

    await territory_service.update_territory(
        territory_id=str(territory.id),
        data=TerritoryUpdate(manager_id=None),
        tenant_id=TENANT,
    )
    assert await get_bd_territory_ids(manager) is None
    assert territory.id not in (await User.get(manager.id)).territory_ids


@pytest.mark.asyncio
async def test_delete_territory_detaches_mirror():
    await _init()
    region = await _region()
    manager = await _user()

    territory = await territory_service.create_territory(
        data=TerritoryCreate(name="North", region_id=str(region.id), manager_id=str(manager.id)),
        user_id=str(ObjectId()),
        tenant_id=TENANT,
    )
    await territory_service.delete_territory(str(territory.id), TENANT)

    refreshed = await User.get(manager.id)
    assert territory.id not in refreshed.territory_ids
    assert await get_bd_territory_ids(manager) is None
