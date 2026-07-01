"""
Pydantic schemas for Itinerary API — simple PDF-upload model.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Union
from datetime import datetime, date


class ItineraryBase(BaseModel):
    """Base schema for Itinerary"""
    name: str
    description: Optional[str] = None

    total_days: Optional[int] = None
    total_nights: Optional[int] = None

    start_date: Optional[Union[datetime, date]] = None
    end_date: Optional[Union[datetime, date]] = None

    destination_ids: List[str] = Field(default_factory=list)
    destination_names: List[str] = Field(default_factory=list)
    tour_starts_from: Optional[str] = None
    tour_ends_same: bool = False
    inclusions: List[str] = Field(default_factory=list)
    feature_image: Optional[str] = None
    overview: Optional[str] = None

    is_template: bool = False
    notes: Optional[str] = None

    @field_validator('start_date', 'end_date', mode='before')
    @classmethod
    def convert_date_to_datetime(cls, v):
        """Convert date to datetime if needed"""
        if isinstance(v, date):
            return datetime.combine(v, datetime.min.time())
        return v


class ItineraryUpdate(BaseModel):
    """Schema for updating itinerary metadata"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class ItineraryResponse(ItineraryBase):
    """Schema for itinerary response"""
    id: str
    tenant_id: str
    owner_id: str
    is_active: bool

    pdf_file_id: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        """Convert ObjectId fields to strings for API response"""
        if hasattr(obj, 'id'):
            data = obj.model_dump()
            # Convert ObjectId fields to strings
            data['id'] = str(obj.id)
            if hasattr(obj, 'tenant_id') and obj.tenant_id:
                data['tenant_id'] = str(obj.tenant_id)
            if hasattr(obj, 'owner_id') and obj.owner_id:
                data['owner_id'] = str(obj.owner_id)
            if getattr(obj, 'pdf_file_id', None):
                data['pdf_file_id'] = str(obj.pdf_file_id)
            # Convert destination_ids to strings
            if hasattr(obj, 'destination_ids') and obj.destination_ids:
                data['destination_ids'] = [str(dest_id) for dest_id in obj.destination_ids]

            return cls(**data)
        return cls()


class ItineraryListResponse(BaseModel):
    """Schema for list of itineraries"""
    itineraries: List[ItineraryResponse]
    total: int
