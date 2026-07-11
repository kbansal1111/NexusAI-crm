"""
Territory service for managing sales territories and regions.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from beanie import PydanticObjectId
from bson import ObjectId

from app.models.territory import Region, Territory
from app.models.user import User
from app.core.cache import invalidate_tenant_cache
from app.schemas.territory import (
    RegionCreate, RegionUpdate,
    TerritoryCreate, TerritoryUpdate,
    TerritoryAssignmentResponse
)


class TerritoryService:
    """Service for territory and region management."""
    
    # ==================== Region CRUD ====================
    
    async def create_region(
        self,
        data: RegionCreate,
        user_id: str,
        tenant_id: str
    ) -> Region:
        """Create a new region."""
        region = Region(
            **data.model_dump(),
            created_by=user_id,
            owner_id=user_id,
            tenant_id=tenant_id
        )
        await region.insert()
        return region
    
    async def get_region(
        self,
        region_id: str,
        tenant_id: str
    ) -> Optional[Region]:
        """Get a region by ID."""
        return await Region.find_one(
            {"_id": PydanticObjectId(region_id), "tenant_id": tenant_id}
        )
    
    async def update_region(
        self,
        region_id: str,
        data: RegionUpdate,
        tenant_id: str
    ) -> Optional[Region]:
        """Update a region."""
        region = await self.get_region(region_id, tenant_id)
        if not region:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        update_data["updated_at"] = datetime.utcnow()
        
        for key, value in update_data.items():
            setattr(region, key, value)
        
        await region.save()
        return region
    
    async def delete_region(
        self,
        region_id: str,
        tenant_id: str
    ) -> bool:
        """Delete a region."""
        region = await self.get_region(region_id, tenant_id)
        if not region:
            return False
        
        # Check for child territories
        child_territories = await Territory.find(
            {"region_id": region_id, "tenant_id": tenant_id}
        ).count()
        if child_territories > 0:
            raise ValueError("Cannot delete region with associated territories")

        # Check for child regions
        child_regions = await Region.find(
            {"parent_id": region_id, "tenant_id": tenant_id}
        ).count()
        if child_regions > 0:
            raise ValueError("Cannot delete region with child regions")
            
        await region.delete()
        return True
    
    async def list_regions(
        self,
        tenant_id: str,
        parent_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> tuple[List[Region], int]:
        """List regions with filtering."""
        query = {"tenant_id": tenant_id}
        
        if parent_id:
            query["parent_id"] = parent_id
            
        if is_active is not None:
            query["is_active"] = is_active
            
        if search:
            query["name"] = {"$regex": search, "$options": "i"}
            
        total = await Region.find(query).count()
        
        regions = await Region.find(query)\
            .sort(Region.name)\
            .skip((page - 1) * per_page)\
            .limit(per_page)\
            .to_list()
            
        return regions, total
    
    # ==================== Territory CRUD ====================

    async def _validate_manager(
        self,
        tenant_oid: PydanticObjectId,
        manager_id_str: Optional[str],
    ) -> Optional[ObjectId]:
        """Validate + coerce a territory's manager id for this tenant.

        SECURITY (CLAUDE.md non-negotiable): the manager comes from the request
        body — it must NOT be trusted. It is checked to reference a real,
        non-deleted user in the caller's tenant (a forged/cross-tenant id is
        rejected) and coerced to ObjectId so the stored `Territory.manager_id` is
        always an ObjectId (setattr on a Beanie doc does not coerce), which the
        visibility query relies on to match `_id`.
        """
        if not manager_id_str:
            return None
        manager_oid = ObjectId(str(manager_id_str))
        exists = await User.find_one(
            {"_id": manager_oid, "tenant_id": tenant_oid, "deleted_at": None}
        )
        if not exists:
            raise ValueError(
                "Territory manager is invalid or does not belong to this tenant"
            )
        return manager_oid

    async def _reconcile_manager_mirror(
        self,
        tenant_oid: PydanticObjectId,
        territory_id: PydanticObjectId,
        old_manager: Optional[ObjectId],
        new_manager: Optional[ObjectId],
    ) -> None:
        """Keep the denormalized `User.territory_ids` / `is_bd_user` mirror in
        step with a territory's manager, so the User-form picker reflects reality.

        Visibility is computed from the Territory doc directly, so this is a
        UX-consistency convenience, not a correctness gate. The new manager gains
        the territory + the BD flag; a replaced manager loses the territory from
        their mirror (the flag is left as-is).
        """
        if old_manager == new_manager:
            return
        if new_manager:
            await User.find(
                {"_id": new_manager, "tenant_id": tenant_oid, "deleted_at": None}
            ).update({"$addToSet": {"territory_ids": territory_id}, "$set": {"is_bd_user": True}})
        if old_manager:
            await User.find(
                {"_id": old_manager, "tenant_id": tenant_oid, "deleted_at": None}
            ).update({"$pull": {"territory_ids": territory_id}})

    async def create_territory(
        self,
        data: TerritoryCreate,
        user_id: str,
        tenant_id: str
    ) -> Territory:
        """Create a new territory."""
        # Region is optional in the simplified flow — verify only when supplied.
        if data.region_id:
            region = await self.get_region(data.region_id, tenant_id)
            if not region:
                raise ValueError("Region not found")

        tenant_oid = PydanticObjectId(str(tenant_id))
        manager_oid = await self._validate_manager(tenant_oid, data.manager_id)

        payload = data.model_dump()
        payload["manager_id"] = manager_oid
        territory = Territory(
            **payload,
            created_by=user_id,
            owner_id=user_id,
            tenant_id=tenant_id
        )
        await territory.insert()

        await self._reconcile_manager_mirror(tenant_oid, territory.id, None, manager_oid)
        # BD visibility widens for the new territory's manager — clear the cached
        # scopes so they see its opportunities immediately.
        await invalidate_tenant_cache(str(tenant_id))
        return territory
    
    async def get_territory(
        self,
        territory_id: str,
        tenant_id: str
    ) -> Optional[Territory]:
        """Get a territory by ID."""
        return await Territory.find_one(
            {"_id": PydanticObjectId(territory_id), "tenant_id": tenant_id}
        )
    
    async def update_territory(
        self,
        territory_id: str,
        data: TerritoryUpdate,
        tenant_id: str
    ) -> Optional[Territory]:
        """Update a territory."""
        territory = await self.get_territory(territory_id, tenant_id)
        if not territory:
            return None

        tenant_oid = PydanticObjectId(str(tenant_id))
        update_data = data.model_dump(exclude_unset=True)

        old_manager = territory.manager_id
        manager_changing = "manager_id" in update_data

        # Tenant-validate + coerce the manager only when it is being changed, so
        # an unrelated edit (e.g. renaming) never re-validates a stale manager.
        if manager_changing:
            update_data["manager_id"] = await self._validate_manager(
                tenant_oid, update_data.get("manager_id")
            )

        update_data["updated_at"] = datetime.utcnow()
        for key, value in update_data.items():
            setattr(territory, key, value)

        await territory.save()

        if manager_changing:
            await self._reconcile_manager_mirror(
                tenant_oid, territory.id, old_manager, update_data["manager_id"]
            )
            # A manager change moves the BD visibility boundary — clear the cached
            # scopes so gained/lost access takes effect immediately.
            await invalidate_tenant_cache(str(tenant_id))
        return territory

    async def delete_territory(
        self,
        territory_id: str,
        tenant_id: str
    ) -> bool:
        """Delete a territory."""
        territory = await self.get_territory(territory_id, tenant_id)
        if not territory:
            return False

        # Check parent relationship
        child_territories = await Territory.find(
            {"parent_territory_id": territory_id, "tenant_id": tenant_id}
        ).count()
        if child_territories > 0:
            raise ValueError("Cannot delete territory with child territories")

        tenant_oid = PydanticObjectId(str(tenant_id))
        # Detach the territory from every user's mirror so stale ids don't linger
        # in the User-form multiselect. (Visibility recomputes from Territory, so
        # a deleted territory already grants no one access.)
        await User.find(
            {"tenant_id": tenant_oid, "territory_ids": territory.id, "deleted_at": None}
        ).update({"$pull": {"territory_ids": territory.id}})

        await territory.delete()
        await invalidate_tenant_cache(str(tenant_id))
        return True
    
    async def list_territories(
        self,
        tenant_id: str,
        region_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> tuple[List[Territory], int]:
        """List territories with filtering."""
        query = {"tenant_id": tenant_id}
        
        if region_id:
            query["region_id"] = region_id
            
        if parent_id:
            query["parent_territory_id"] = parent_id
            
        if user_id:
            query["manager_id"] = user_id

        if search:
            query["name"] = {"$regex": search, "$options": "i"}
            
        total = await Territory.find(query).count()
        
        territories = await Territory.find(query)\
            .sort(Territory.name)\
            .skip((page - 1) * per_page)\
            .limit(per_page)\
            .to_list()
            
        return territories, total
    
    # ==================== Assignment Logic ====================
    
    async def find_territory_for_address(
        self,
        tenant_id: str,
        country: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None
    ) -> Optional[TerritoryAssignmentResponse]:
        """Find matching territory based on address."""
        if not any([country, state, postal_code]):
            return None
            
        # Fetch active territories with rules
        territories = await Territory.find(
            {"tenant_id": tenant_id, "is_active": True}
        ).to_list()
        
        # Priority 1: Postal Code Match (Exact)
        if postal_code:
            for t in territories:
                if postal_code in t.postal_codes:
                    return await self._build_assignment_response(t, "postal_code")
        
        # Priority 2: Postal Code Wildcard
        if postal_code:
            for t in territories:
                for pc in t.postal_codes:
                    if pc.endswith("*") and postal_code.startswith(pc[:-1]):
                        return await self._build_assignment_response(t, "postal_code_pattern")
        
        # Priority 3: State Match
        if state:
            for t in territories:
                if state in t.states:
                    return await self._build_assignment_response(t, "state")
                    
        # Priority 4: Country Match
        if country:
            for t in territories:
                if country in t.countries:
                    return await self._build_assignment_response(t, "country")
                    
        return None

    async def _build_assignment_response(
        self,
        territory: Territory,
        matched_by: str
    ) -> TerritoryAssignmentResponse:
        """Helper to build assignment response — region scoped to territory's tenant."""
        region = None
        if territory.region_id:
            region = await Region.find_one(
                {"_id": territory.region_id, "tenant_id": territory.tenant_id}
            )
        return TerritoryAssignmentResponse(
            territory_id=str(territory.id),
            territory_name=territory.name,
            region_id=str(region.id) if region else None,
            region_name=region.name if region else None,
            matched_by=matched_by
        )


# Singleton instance
territory_service = TerritoryService()
