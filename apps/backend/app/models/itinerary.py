"""
Itinerary models — travel-industry module, day-wise travel planning (guarded by require_module).
"""
from beanie import Indexed
from pydantic import Field
from typing import Optional, List
from beanie import PydanticObjectId
from datetime import datetime
from app.models.base import BaseDocument

class Itinerary(BaseDocument):
    """Itinerary model — a named PDF itinerary organized by destination.

    Simplified from the old day-wise builder: an itinerary is now just metadata
    (name + destinations) plus a single uploaded PDF stored via the polymorphic
    ``File`` model. ``pdf_file_id`` points at that File record.
    """

    # Basic Information
    name: Indexed(str)
    description: Optional[str] = None

    # Duration (optional — no longer collected on the simple upload flow, but
    # retained so pre-existing builder records still deserialize cleanly)
    total_days: Optional[int] = None
    total_nights: Optional[int] = None

    # Dates
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    # Destinations — destination_names is denormalized (selection order; [0] is
    # the primary destination, which drives the S3 folder and display/search).
    destination_ids: List[PydanticObjectId] = Field(default_factory=list)
    destination_names: List[str] = Field(default_factory=list)
    tour_starts_from: Optional[str] = None
    tour_ends_same: bool = False

    # Uploaded PDF (points at a File record; File holds the S3 key/metadata)
    pdf_file_id: Optional[PydanticObjectId] = None

    # Details (legacy builder fields — kept optional for back-compat)
    inclusions: List[str] = Field(default_factory=list)
    feature_image: Optional[str] = None
    overview: Optional[str] = None

    # Status
    is_active: bool = True
    is_template: bool = False  # Template itineraries can be reused

    # Tenant & Ownership
    tenant_id: Indexed(PydanticObjectId)
    owner_id: Indexed(PydanticObjectId)
    created_by: PydanticObjectId
    last_modified_by_id: Optional[PydanticObjectId] = None

    # Metadata
    notes: Optional[str] = None

    class Settings:
        name = "itineraries"
        # indexes = [
        # "tenant_id",
        # "owner_id",
        # [("tenant_id", 1), ("name", 1)],
        # ]


class ItineraryOpportunity(BaseDocument):
    """Pivot table for Itinerary-Opportunity many-to-many relationship"""
    
    itinerary_id: Indexed(PydanticObjectId)
    opportunity_id: Indexed(PydanticObjectId)
    tenant_id: Indexed(PydanticObjectId)
    
    # Customization notes for this specific opportunity
    notes: Optional[str] = None
    
    class Settings:
        name = "itinerary_opportunities"
        # indexes = [
        # [("itinerary_id", 1), ("opportunity_id", 1)],
            # "tenant_id"
        # ]
