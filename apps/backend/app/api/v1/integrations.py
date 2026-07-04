"""
Public integration endpoints (no JWT) — web-to-lead capture.

POST /api/v1/integrations/leads
  Auth: X-API-Key header ONLY (no body token — user decision 2026-07-04).
  The tenant is resolved ONLY from the matched IntegrationToken document —
  never from the request body (multi-tenant isolation, CLAUDE.md §1).

Pipeline: auth → parse (lenient) → normalize → resolve names→ids →
validate → create lead (owner = tenant admin) → auto-convert to opportunity
(owner = System pool) → minimal 201 response.

Business rules (user-locked 2026-07-04):
  - source is ALWAYS "Website" — the flag marking web-origin leads.
  - duplicates: every submission creates a NEW lead (skip_duplicate_check).
  - conversion failure never loses the lead (201 with converted:false).
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.rate_limiter import limiter
from app.core.validators import normalize_loose_phone
from app.models.integration_token import IntegrationToken, SCOPE_LEADS_WRITE
from app.models.tenant import Tenant
from app.schemas.integration import (
    WebLeadPayload,
    WebToLeadRequest,
    _as_name_list,
    _safe_bool,
    _safe_int,
)
from app.schemas.lead import LeadConvert, LeadCreate
from app.services.lead_service import LeadService

logger = logging.getLogger(__name__)

router = APIRouter()
lead_service = LeadService()  # module-level seam for tests

WEB_SOURCE_NAME = "Website"
_VALID_SEGMENTS = {"B2C", "B2B", "CORPORATE"}
_TRAVEL_INT_KEYS = ("no_of_nights", "no_of_pax", "no_of_adults", "no_of_childs", "no_of_infants")
_email_adapter = TypeAdapter(EmailStr)


# ---------------------------------------------------------------------------
# Helpers — module-level async defs so hermetic tests can monkeypatch each.
# ---------------------------------------------------------------------------

async def _authenticate(raw_key: Optional[str]) -> tuple[IntegrationToken, Tenant]:
    """Resolve API key → (token doc, tenant). Raises 401 on any failure."""
    unauthorized = HTTPException(status_code=401, detail="Invalid integration token")
    if not raw_key or len(raw_key.strip()) < 16:
        raise unauthorized

    token_hash = hashlib.sha256(raw_key.strip().encode()).hexdigest()
    token = await IntegrationToken.find_one({"token_hash": token_hash})
    if not token or not token.is_valid() or SCOPE_LEADS_WRITE not in (token.scopes or []):
        raise unauthorized

    tenant = await Tenant.find_one({"_id": token.tenant_id, "is_active": True})
    if not tenant:
        raise unauthorized

    # Fire-and-forget usage audit — never blocks or fails the request.
    try:
        await token.set({IntegrationToken.last_used_at: datetime.now(timezone.utc)})
    except Exception:
        pass

    return token, tenant


async def _resolve_admin_owner(tenant_id) -> Any:
    """Web leads are owned by the tenant admin (oldest active admin-role user).

    Falls back to the System user so a lead is never dropped for lack of an
    owner. Pattern: user_service.get_super_admin_user_ids.
    """
    from app.models.role import Role
    from app.models.user import User
    from app.services.system_user import get_or_create_system_user

    admin_roles = await Role.find(
        {"tenant_id": tenant_id, "is_admin": True, "deleted_at": None}
    ).to_list()
    admin_role_ids = [r.id for r in admin_roles]
    if admin_role_ids:
        admins = await User.find(
            {
                "tenant_id": tenant_id,
                "is_active": True,
                "deleted_at": None,
                "role_ids": {"$in": admin_role_ids},
            }
        ).sort("+created_at").limit(1).to_list()
        if admins:
            return admins[0]
    return await get_or_create_system_user(tenant_id)


async def _resolve_website_source_id(tenant: Tenant) -> str:
    """Every web lead is stamped source="Website" (the web-origin flag).

    Resolves case-insensitively against tenant+platform Source picklists;
    auto-creates a tenant-scoped "Website" source once if missing so a lead
    is never rejected over picklist state.
    """
    from app.models.consolidated_picklists import Source
    from app.services.import_export_service import _picklist_name_map

    name_map = await _picklist_name_map(Source, tenant.id, tenant.industry, "source")
    source_id = name_map.get(WEB_SOURCE_NAME.lower())
    if source_id:
        return str(source_id)

    source = Source(name=WEB_SOURCE_NAME, tenant_id=tenant.id, is_active=True)
    await source.insert()
    logger.info("web-to-lead: auto-created 'Website' source for tenant %s", tenant.id)
    return str(source.id)


async def _resolve_experience_id(name: Optional[str], tenant: Tenant) -> Optional[str]:
    """Experience NAME → picklist id; unknown/missing → None (optional field)."""
    if not name:
        return None
    from app.models.consolidated_picklists import Experience
    from app.services.import_export_service import _picklist_name_map

    name_map = await _picklist_name_map(Experience, tenant.id, tenant.industry, "experience")
    exp_id = name_map.get(str(name).strip().lower())
    return str(exp_id) if exp_id else None


async def _resolve_destination_ids(names: List[str], tenant_id) -> List[str]:
    """Destination NAMES → picklist ids (case-insensitive, tenant or platform).

    Unmatched names are skipped — validate_lead_record accepts names OR ids,
    so unknown destinations never block capture (names stay on the lead).
    """
    import re as _re
    from app.models.consolidated_picklists import DestinationPicklist

    ids: List[str] = []
    for dname in names:
        item = await DestinationPicklist.find_one(
            {
                "name": {"$regex": f"^{_re.escape(dname)}$", "$options": "i"},
                "picklist_type": "destination",
                "$or": [{"tenant_id": tenant_id}, {"tenant_id": None}],
            }
        )
        if item:
            ids.append(str(item.id))
        else:
            logger.warning("web-to-lead: unknown destination %r (tenant %s)", dname, tenant_id)
    return ids


async def _default_lead_status_id(tenant_id) -> Optional[str]:
    """Default LeadStatus — 4-step fallback (mirrors the SalesStage pattern
    in lead_service.convert_lead). None is acceptable: status isn't required."""
    from app.models.consolidated_picklists import LeadStatus

    base = {"picklist_type": "lead_status", "is_active": True}
    for query in (
        {**base, "tenant_id": tenant_id, "is_default": True},
        {**base, "tenant_id": tenant_id},
        {**base, "tenant_id": None, "is_default": True},
        {**base, "tenant_id": None},
    ):
        status = await LeadStatus.find_one(query)
        if status:
            return str(status.id)
    return None


def _clean_email(value: Optional[str]) -> Optional[str]:
    """Invalid email → None (drop, never reject — email is optional)."""
    if not value:
        return None
    try:
        return str(_email_adapter.validate_python(value.strip()))
    except ValidationError:
        return None


def _build_industry_data(payload: WebLeadPayload, is_travel: bool) -> Dict[str, Any]:
    """Coerce the raw industry_data block (PHP sends strings for everything)."""
    data = dict(payload.industry_data or {})
    if not is_travel:
        return data

    for key in _TRAVEL_INT_KEYS:
        if key in data:
            value = _safe_int(data.get(key))
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
    if "is_fixed" in data:
        data["is_fixed"] = _safe_bool(data.get("is_fixed"))
    if "travel_date" in data and data.get("travel_date") is not None:
        data["travel_date"] = str(data["travel_date"]).strip()
        if not data["travel_date"]:
            data.pop("travel_date")
    destinations = _as_name_list(data.get("destinations"))
    if destinations:
        data["destinations"] = destinations
    else:
        # Keep an empty industry_data truly empty so the travel guard's
        # "Travel details are required." check still fires.
        data.pop("destinations", None)
    # Never trust ids from the wire — they're resolved server-side from names.
    data.pop("destination_ids", None)
    return data


def _build_custom_fields(payload: WebLeadPayload, experience_id: Optional[str]) -> Dict[str, Any]:
    """Additional Information block — whitelist only the known keys."""
    raw = payload.custom_fields or {}
    segment = str(raw.get("segment") or "").strip().upper()
    custom_fields: Dict[str, Any] = {
        "segment": segment if segment in _VALID_SEGMENTS else "B2C",
    }
    campaign = str(raw.get("campaign_name") or "").strip()
    if campaign:
        custom_fields["campaign_name"] = campaign
    if experience_id:
        custom_fields["experience_id"] = experience_id
    return custom_fields


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/leads", status_code=201)
@limiter.limit("60/minute")
async def create_web_lead(request: Request, body: WebToLeadRequest):
    """Create (and auto-convert) a lead from the client website."""
    # 1. Auth — X-API-Key header only.
    token, tenant = await _authenticate(request.headers.get("X-API-Key"))

    try:
        # 2. Lenient parse — unknown/hostile fields (tenant_id, owner_id…) dropped.
        payload = WebLeadPayload(**body.lead)

        # 3. Normalize.
        is_travel = (tenant.industry or "").lower() == "travel"
        mobile = normalize_loose_phone(payload.mobile)
        phone = normalize_loose_phone(payload.phone)
        email = _clean_email(payload.email)
        industry_data = _build_industry_data(payload, is_travel)

        # 4. Resolve names → ids (all tenant-scoped).
        source_id = await _resolve_website_source_id(tenant)
        experience_id = await _resolve_experience_id(
            (payload.custom_fields or {}).get("experience"), tenant
        )
        if is_travel and industry_data.get("destinations"):
            industry_data["destination_ids"] = await _resolve_destination_ids(
                industry_data["destinations"], tenant.id
            )
        lead_status_id = await _default_lead_status_id(tenant.id)
        owner = await _resolve_admin_owner(tenant.id)

        # 5. Validate industry block (422 for travel tenants without travel data).
        from app.core.industry_guard import resolve_industry_data

        industry_data = await resolve_industry_data(
            tenant.id, industry_data, mode="lead", require_for_travel=True
        )
        if industry_data:
            from app.api.v1.leads import _resolve_destinations

            industry_data = await _resolve_destinations(industry_data, tenant.id)

        lead_data = LeadCreate(
            salutation=payload.salutation,
            first_name=payload.first_name or "",
            last_name=payload.last_name,
            email=email,
            phone=phone,
            mobile=mobile,
            company=payload.company,
            title=payload.title,
            no_employees=payload.no_employees,
            website=payload.website,
            street=payload.street,
            city=payload.city,
            state=payload.state,
            zip=payload.zip,
            country=payload.country,
            source_id=source_id,
            lead_status_id=lead_status_id,
            creation_type="auto",
            industry_data=industry_data or {},
            custom_fields=_build_custom_fields(payload, experience_id),
        )

        # 6. Create — always a NEW lead (duplicate policy), owner = admin.
        #    create_lead also fires BD assignment, activity log, webhook and
        #    automation dispatch.
        lead = await lead_service.create_lead(
            lead_data=lead_data,
            user_id=owner.id,
            tenant_id=tenant.id,
            user_name=owner.name or "Admin",
            skip_duplicate_check=True,
        )

        # 7. Auto-convert to opportunity (source=Website flag behavior). The
        #    conversion's own owner fallback assigns the opportunity to the
        #    System pool. Failure here must NEVER lose the captured lead.
        opportunity_id: Optional[str] = None
        converted = False
        try:
            conversion = await lead_service.convert_lead(
                str(lead.id), LeadConvert(), user_id=owner.id, tenant_id=tenant.id
            )
            opportunity_id = conversion.get("opportunity_id")
            converted = bool(opportunity_id)
        except Exception:
            logger.error(
                "web-to-lead: auto-conversion failed for lead %s (tenant %s)",
                lead.id, tenant.id, exc_info=True,
            )

        # 8. Minimal response — no internal data leakage.
        return {
            "success": True,
            "lead_id": str(lead.id),
            "opportunity_id": opportunity_id,
            "converted": converted,
        }

    except HTTPException:
        raise
    except ValidationError as e:  # MUST precede ValueError (subclass!)
        messages = "; ".join(
            f"{'.'.join(str(loc) for loc in err.get('loc', []))}: {err.get('msg')}"
            for err in e.errors()
        )
        raise HTTPException(status_code=422, detail=messages or "Invalid lead payload")
    except ValueError as e:
        # validate_lead_record raises clean human-readable messages.
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        logger.error("web-to-lead: unexpected failure (tenant %s)", tenant.id, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
