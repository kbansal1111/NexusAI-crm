"""End-to-end (hermetic) test of BD territory-scoped opportunity visibility.

Seeds real Opportunity documents into an in-memory Mongo (mongomock_motor +
Beanie) and drives the actual repository query used by the opportunities list
endpoint. This proves the whole scoping mechanism at the data layer:

  - A BD user (Territory Manager) sees STRICTLY the opportunities in their
    assigned territories — owner scope does not apply (a pure BD user owns none).
  - A regular user is owner-scoped only.
  - An admin (no owner filter, no BD filter) sees the whole tenant.
  - Cross-tenant isolation holds: a BD user never sees another tenant's
    opportunities even when that tenant reuses the same territory id.
"""
import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from beanie import init_beanie

from app.models.opportunity import Opportunity
from app.repositories.opportunity_repository import OpportunityRepository


TENANT_A = ObjectId()
TENANT_B = ObjectId()
TERRITORY_A = ObjectId()      # assigned to the BD user (tenant A)
TERRITORY_OTHER = ObjectId()  # a different tenant-A territory

BD_USER = ObjectId()
OTHER_USER = ObjectId()       # a tenant-A colleague outside the BD user's hierarchy
B_USER = ObjectId()

STAGE = ObjectId()


async def _seed():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["bd_e2e"], document_models=[Opportunity])

    async def mk(name, tenant, owner, territory):
        # owner_name is preset so the Insert denormalization hook is skipped.
        await Opportunity(
            name=name, amount=1000.0, sales_stage_id=STAGE,
            owner_id=owner, owner_name="seed", territory_id=territory,
            tenant_id=tenant, created_by=owner,
        ).insert()

    # Tenant A
    await mk("A-own-no-territory", TENANT_A, BD_USER, None)          # BD owns, no territory
    await mk("A-territory-other-owner", TENANT_A, OTHER_USER, TERRITORY_A)  # in BD territory
    await mk("A-other-territory", TENANT_A, OTHER_USER, TERRITORY_OTHER)    # NOT BD territory
    # Tenant B — reuses TERRITORY_A id to attempt a cross-tenant leak
    await mk("B-same-territory-id", TENANT_B, B_USER, TERRITORY_A)


def _names(opps):
    return {o.name for o in opps}


@pytest.mark.asyncio
async def test_bd_user_sees_only_territory_deals():
    await _seed()
    repo = OpportunityRepository()
    opps, total, _, _ = await repo.get_filtered_opportunities(
        tenant_id=TENANT_A,
        owner_id={"$in": [BD_USER]},
        bd_territory_ids=[TERRITORY_A],
        limit=100,
    )
    names = _names(opps)
    # Strictly territory-only: ONLY the deal stamped to their territory.
    assert names == {"A-territory-other-owner"}
    assert "A-own-no-territory" not in names       # owned by BD but not in their territory
    assert "A-other-territory" not in names        # a different territory
    assert "B-same-territory-id" not in names       # cross-tenant blocked by tenant filter
    assert total == 1


@pytest.mark.asyncio
async def test_regular_user_is_owner_scoped_only():
    await _seed()
    repo = OpportunityRepository()
    opps, _, _, _ = await repo.get_filtered_opportunities(
        tenant_id=TENANT_A,
        owner_id={"$in": [OTHER_USER]},
        bd_territory_ids=None,  # not a BD user
        limit=100,
    )
    # Sees both opps they own, and nothing by territory.
    assert _names(opps) == {"A-territory-other-owner", "A-other-territory"}


@pytest.mark.asyncio
async def test_admin_sees_whole_tenant_not_other_tenant():
    await _seed()
    repo = OpportunityRepository()
    # Admin path: no owner filter, no BD filter (visible_owner_ids is None).
    opps, _, _, _ = await repo.get_filtered_opportunities(
        tenant_id=TENANT_A,
        owner_id=None,
        bd_territory_ids=None,
        limit=100,
    )
    names = _names(opps)
    assert names == {"A-own-no-territory", "A-territory-other-owner", "A-other-territory"}
    assert "B-same-territory-id" not in names  # still tenant-isolated


@pytest.mark.asyncio
async def test_cross_tenant_territory_spoof_is_blocked():
    await _seed()
    repo = OpportunityRepository()
    # A BD user in tenant A whose territory_ids (somehow) contains TERRITORY_A,
    # which tenant B ALSO tagged an opportunity with. The tenant_id filter must
    # still exclude tenant B's opportunity.
    opps, _, _, _ = await repo.get_filtered_opportunities(
        tenant_id=TENANT_A,
        owner_id={"$in": [BD_USER]},
        bd_territory_ids=[TERRITORY_A],
        limit=100,
    )
    assert all(o.tenant_id == TENANT_A for o in opps)
    assert "B-same-territory-id" not in _names(opps)
