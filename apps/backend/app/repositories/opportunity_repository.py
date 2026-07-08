from typing import List, Optional, Dict, Any, Tuple
from beanie import PydanticObjectId

from app.models.opportunity import Opportunity
from app.repositories.base_repository import BaseRepository

class OpportunityRepository(BaseRepository[Opportunity]):
    """
    Repository for Opportunity data access.
    Enforces tenant_id isolation automatically via BaseRepository.
    """
    
    def __init__(self):
        super().__init__(Opportunity)

    async def get_filtered_opportunities(
        self,
        tenant_id: str | PydanticObjectId,
        skip: int = 0,
        limit: int = 10,
        owner_id: Optional[str | PydanticObjectId] = None,
        sales_stage_id: Optional[str | PydanticObjectId] = None,
        cursor: Optional[str] = None,
        bd_territory_ids: Optional[List[PydanticObjectId]] = None,
        **kwargs
    ) -> Tuple[List[Opportunity], Optional[int], Optional[str], bool]:
        """Get opportunities with multiple filters and pagination.

        Returns (opportunities, total, next_cursor, has_more). When `cursor` is
        given, uses keyset pagination (O(1) deep paging, COUNT skipped → total is
        None). Otherwise offset pagination with a total count, plus a cursor for
        the next page so the caller can switch to "load more".

        `bd_territory_ids` widens visibility for BD users: results match the
        owner filter OR any opportunity in the user's territories ("Territory +
        own"). It's ANDed via $and so it never clobbers a search $or.
        """
        tenant_obj_id = PydanticObjectId(tenant_id) if isinstance(tenant_id, str) else tenant_id

        query: Dict[str, Any] = {
            "tenant_id": tenant_obj_id,
            "deleted_at": None
        }

        if owner_id:
            query["owner_id"] = PydanticObjectId(owner_id) if isinstance(owner_id, str) else owner_id

        if sales_stage_id:
            query["sales_stage_id"] = PydanticObjectId(sales_stage_id) if isinstance(sales_stage_id, str) else sales_stage_id

        # Merge keyword filters securely
        for k, v in kwargs.items():
            query[k] = v

        # BD territory widening: (owner-scoped) OR (territory in user's set).
        # Pull the owner clause out and re-express it as an $or ANDed into the
        # query so it composes with an existing search $or / view $and. The
        # tenant_id filter above still applies, so cross-tenant territory ids
        # can never surface another tenant's opportunities.
        if bd_territory_ids:
            owner_clause = query.pop("owner_id", None)
            bd_or: List[Dict[str, Any]] = []
            if owner_clause is not None:
                bd_or.append({"owner_id": owner_clause})
            bd_or.append({"territory_id": {"$in": bd_territory_ids}})
            query.setdefault("$and", []).append({"$or": bd_or})

        from app.core.pagination import keyset_page, encode_cursor

        if cursor is not None:
            pr = await keyset_page(
                self.model, query, sort_field="created_at",
                direction="desc", limit=limit, cursor=cursor,
            )
            return pr["items"], None, pr["next_cursor"], pr["has_more"]

        import asyncio as _asyncio
        total, opportunities = await _asyncio.gather(
            self.model.find(query).count(),
            self.model.find(query).sort(
                [("created_at", -1), ("_id", -1)]
            ).skip(skip).limit(limit).to_list(),
        )
        next_cursor = encode_cursor(
            opportunities[-1].created_at, opportunities[-1].id
        ) if opportunities else None
        has_more = len(opportunities) == limit
        return opportunities, total, next_cursor, has_more
