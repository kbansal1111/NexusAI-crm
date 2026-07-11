"""
Supplier model for multi-industry CRM — service providers, vendors, etc.
"""
from beanie import Indexed
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from uuid import uuid4
from beanie import PydanticObjectId
from app.models.base import BaseDocument


class EmbeddedSupplierContact(BaseModel):
    """LEGACY embedded contact shape (pre-collection).

    Supplier contacts used to live embedded on the Supplier document as an
    array. They now live in the standalone ``supplier_contacts`` collection
    (see ``SupplierContact`` below) so they can be searched globally and owned
    /assigned independently across suppliers. This class is retained ONLY so the
    one-off migration (``migrate_supplier_contacts_to_collection``) can still
    parse any old embedded arrays. Do not write new code against it.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    designation: Optional[str] = None
    department: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    is_primary: bool = False
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Supplier(BaseDocument):
    """Supplier model for multi-industry service providers"""
    
    # Basic Information
    name: Indexed(str)
    supplier_type: str  # Hotel, Airline, Tour Operator, Transport, etc.
    
    # Contact Information
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None

    # Address
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    
    # Service Areas (Multi-select support)
    services: List[str] = Field(default_factory=list)
    countries: List[str] = Field(default_factory=list)
    states: List[str] = Field(default_factory=list)
    service_cities: List[str] = Field(default_factory=list)
    destinations: List[str] = Field(default_factory=list)
    
    # Business Details
    tax_id: Optional[str] = None
    registration_number: Optional[str] = None
    
    # Contact Person (legacy single-contact fields; seeds the primary contact)
    contact_person_name: Optional[str] = None
    contact_person_email: Optional[EmailStr] = None
    contact_person_phone: Optional[str] = None

    # NOTE: Contact persons now live in the standalone `supplier_contacts`
    # collection (SupplierContact document), not embedded here. The API still
    # exposes them on SupplierResponse.contacts, populated from that collection.

    # Finance
    credit_limit: Optional[float] = None

    # Status
    is_active: bool = True
    is_preferred: bool = False

    # Tenant & Ownership
    tenant_id: Indexed(PydanticObjectId)
    owner_id: Indexed(PydanticObjectId)
    created_by: PydanticObjectId
    last_modified_by_id: Optional[PydanticObjectId] = None
    
    # Metadata
    notes: Optional[str] = None
    
    class Settings:
        name = "suppliers"
        # indexes = [
        # "tenant_id",
        # "owner_id",
        # "supplier_type",
        # [("tenant_id", 1), ("name", 1)],
            # [("tenant_id", 1), ("supplier_type", 1)],
        # ]


class SupplierContact(BaseDocument):
    """Contact person for a supplier — one row per contact in its own collection.

    Standalone (rather than embedded on the supplier) so contacts can be:
      - searched globally / cross-supplier from the universal search, and
      - owned / assigned independently of the parent supplier.

    Exactly one supplier per contact (1→N): ``supplier_id`` points to the owner
    supplier. Tenant isolation via ``tenant_id`` (every query MUST scope by it).
    Soft-deleted via ``deleted_at`` (inherited from BaseDocument).
    """
    supplier_id: Indexed(PydanticObjectId)
    tenant_id: Indexed(PydanticObjectId)
    owner_id: Optional[PydanticObjectId] = None

    name: str
    designation: Optional[str] = None
    department: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    is_primary: bool = False
    notes: Optional[str] = None

    class Settings:
        name = "supplier_contacts"
        # Indexes are created out-of-band via scripts/create_indexes.py
        # (model-level indexes are disabled project-wide). Recommended:
        #   [("tenant_id", 1), ("supplier_id", 1), ("deleted_at", 1)]
        #   [("tenant_id", 1), ("name", 1)]  -- global search


class OpportunitySupplier(BaseDocument):
    """Pivot table for Opportunity-Supplier many-to-many relationship"""
    
    opportunity_id: Indexed(PydanticObjectId)
    supplier_id: Indexed(PydanticObjectId)
    tenant_id: Indexed(PydanticObjectId)
    
    # Supplier-specific details for this opportunity
    cost: Optional[float] = None
    notes: Optional[str] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    
    class Settings:
        name = "opp_suppliers"
        # indexes = [
        # [("opportunity_id", 1), ("supplier_id", 1)],
            # "tenant_id"
        # ]
