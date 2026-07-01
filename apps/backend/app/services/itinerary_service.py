"""
Itinerary service layer - Business logic for itinerary management (simple PDF model)
"""
import re as _re
from typing import List, Optional
from bson import ObjectId
from app.models.itinerary import Itinerary, ItineraryOpportunity
from app.schemas.itinerary import ItineraryUpdate
from app.models.opportunity import Opportunity


class ItineraryService:
    """Service for Itinerary business logic"""

    async def create_uploaded_itinerary(
        self,
        name: str,
        destination_ids: List[ObjectId],
        destination_names: List[str],
        user_id: ObjectId,
        tenant_id: ObjectId,
    ) -> Itinerary:
        """Create a bare itinerary record for an uploaded PDF.

        The PDF File is uploaded separately (it needs this itinerary's id as the
        ``fileable_id``); the caller sets ``pdf_file_id`` afterwards and saves.
        """
        itinerary = Itinerary(
            name=name,
            destination_ids=destination_ids,
            destination_names=destination_names,
            tenant_id=tenant_id,
            owner_id=user_id,
            created_by=user_id,
        )
        await itinerary.insert()
        return itinerary

    async def get_itinerary(
        self,
        itinerary_id: str,
        tenant_id: ObjectId
    ) -> Optional[Itinerary]:
        """Get itinerary by ID, scoped to tenant."""
        try:
            oid = ObjectId(itinerary_id)
        except Exception:
            return None
        return await Itinerary.find_one(
            {"_id": oid, "tenant_id": tenant_id, "deleted_at": None}
        )

    async def update_itinerary(
        self,
        itinerary_id: str,
        itinerary_data: ItineraryUpdate,
        user_id: ObjectId,
        tenant_id: ObjectId
    ) -> Optional[Itinerary]:
        """Update an itinerary"""
        itinerary = await self.get_itinerary(itinerary_id, tenant_id)

        if not itinerary:
            return None

        update_data = itinerary_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(itinerary, field, value)

        itinerary.last_modified_by_id = user_id
        await itinerary.save()

        return itinerary

    async def delete_itinerary(
        self,
        itinerary_id: str,
        tenant_id: ObjectId
    ) -> bool:
        """Soft delete an itinerary"""
        itinerary = await self.get_itinerary(itinerary_id, tenant_id)

        if not itinerary:
            return False

        await itinerary.soft_delete()
        return True

    async def get_itineraries_by_tenant(
        self,
        tenant_id: ObjectId,
        search: Optional[str] = None,
        visible_owner_ids: Optional[List[ObjectId]] = None,
        is_template: Optional[bool] = None,
    ) -> List[Itinerary]:
        """List itineraries for a tenant, honoring visibility scope and search.

        ``search`` matches (case-insensitive) on name OR any destination name.
        """
        query: dict = {
            "tenant_id": tenant_id,
            "deleted_at": None,
            "is_active": True,
        }

        if is_template is not None:
            query["is_template"] = is_template

        # Ownership/hierarchy visibility (None = admin, sees everything)
        if visible_owner_ids is not None:
            query["owner_id"] = {"$in": visible_owner_ids}

        if search and search.strip():
            pattern = {"$regex": _re.compile(f".*{_re.escape(search.strip())}.*", _re.IGNORECASE)}
            query["$or"] = [
                {"name": pattern},
                {"destination_names": pattern},
            ]

        itineraries = await Itinerary.find(query).sort("-created_at").to_list()
        return itineraries

    async def link_to_opportunity(
        self,
        itinerary_id: str,
        opportunity_id: str,
        tenant_id: ObjectId,
        notes: Optional[str] = None
    ) -> ItineraryOpportunity:
        """Link itinerary to opportunity"""

        # Verify both entities exist and belong to the current tenant
        itinerary = await Itinerary.find_one(
            Itinerary.id == ObjectId(itinerary_id),
            Itinerary.tenant_id == tenant_id
        )
        if not itinerary:
            raise ValueError("Itinerary not found or access denied")

        opportunity = await Opportunity.find_one(
            Opportunity.id == ObjectId(opportunity_id),
            Opportunity.tenant_id == tenant_id
        )
        if not opportunity:
            raise ValueError("Opportunity not found or access denied")

        # Check if already linked
        existing = await ItineraryOpportunity.find_one(
            ItineraryOpportunity.itinerary_id == ObjectId(itinerary_id),
            ItineraryOpportunity.opportunity_id == ObjectId(opportunity_id),
            ItineraryOpportunity.tenant_id == tenant_id
        )

        if existing:
            if notes:
                existing.notes = notes
                await existing.save()
            return existing

        # Create new link
        link = ItineraryOpportunity(
            itinerary_id=ObjectId(itinerary_id),
            opportunity_id=ObjectId(opportunity_id),
            tenant_id=tenant_id,
            notes=notes
        )

        await link.insert()
        return link

    async def unlink_from_opportunity(
        self,
        itinerary_id: str,
        opportunity_id: str,
        tenant_id: ObjectId
    ) -> bool:
        """Unlink itinerary from opportunity"""

        link = await ItineraryOpportunity.find_one(
            ItineraryOpportunity.itinerary_id == ObjectId(itinerary_id),
            ItineraryOpportunity.opportunity_id == ObjectId(opportunity_id),
            ItineraryOpportunity.tenant_id == tenant_id
        )

        if link:
            await link.delete()
            return True

        return False

    async def get_itineraries_for_opportunity(
        self,
        opportunity_id: str,
        tenant_id: ObjectId
    ) -> List[dict]:
        """Get all itineraries linked to an opportunity (tenant-scoped end-to-end)."""

        links = await ItineraryOpportunity.find(
            {"opportunity_id": ObjectId(opportunity_id), "tenant_id": tenant_id}
        ).to_list()

        if not links:
            return []

        # Bulk tenant-scoped fetch — no cross-tenant itinerary surfaces even
        # if a link row referenced one.
        itin_ids = [link.itinerary_id for link in links]
        itineraries = await Itinerary.find(
            {"_id": {"$in": itin_ids}, "tenant_id": tenant_id, "deleted_at": None}
        ).to_list()
        itin_map = {i.id: i for i in itineraries}

        result = []
        for link in links:
            itinerary = itin_map.get(link.itinerary_id)
            if itinerary:
                result.append({
                    "itinerary": itinerary,
                    "notes": link.notes
                })

        return result
