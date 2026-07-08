"""
BD Assignment Service — resolves the territory for an opportunity from an address.

A territory has exactly one manager (`Territory.manager_id`), who is the BD user
that sees the territory's opportunities. The opportunity only stores which
territory it belongs to (`territory_id` / `region_id`); the manager is resolved
live from the territory when displayed, so nothing is denormalized onto the deal.

Geographic match priority is delegated to
territory_service.find_territory_for_address (postal exact → postal wildcard →
state → country).
"""
from dataclasses import dataclass
from typing import Optional

from bson import ObjectId

from app.services.territory_service import territory_service


@dataclass
class BDAssignment:
    """Result of resolving an opportunity's territory from an address."""
    territory_id: Optional[ObjectId]
    region_id: Optional[ObjectId]
    match_source: Optional[str]  # postal_code|postal_code_pattern|state|country

    def is_empty(self) -> bool:
        return self.territory_id is None


class BDAssignmentService:
    """Stateless helper — instantiate once and reuse."""

    async def resolve_for_address(
        self,
        tenant_id: ObjectId,
        country: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None,
    ) -> BDAssignment:
        """Resolve the territory an address falls into."""
        match = await territory_service.find_territory_for_address(
            tenant_id=tenant_id,
            country=country,
            state=state,
            postal_code=zip_code,
        )
        if not match:
            return BDAssignment(None, None, None)
        return BDAssignment(
            territory_id=ObjectId(match.territory_id) if match.territory_id else None,
            region_id=ObjectId(match.region_id) if match.region_id else None,
            match_source=match.matched_by,
        )


bd_assignment_service = BDAssignmentService()
