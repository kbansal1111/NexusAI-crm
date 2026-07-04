"""
Schemas for the public web-to-lead integration endpoint.

Design: the external website (PHP) is not a trusted, well-typed client — the
payload schema is deliberately LENIENT. Every field is optional, unknown keys
are ignored (`extra="ignore"` also drops hostile tenant_id/owner_id
injections), and coercers convert sloppy input ("5", "0", "Bali, Singapore")
instead of rejecting it. Requiredness is enforced later by
`validate_lead_record` with clean human-readable messages.
"""
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator
from typing import Any, Dict, List, Optional, Annotated


def _clean_str(v: Any) -> Optional[str]:
    """Coerce to trimmed string; empty/None -> None. Never raises."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _safe_int(v: Any) -> Optional[int]:
    """'5'/'5.0'/5 -> 5; garbage/negatives -> None (drop, never reject)."""
    if v is None or v == "":
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _safe_bool(v: Any) -> bool:
    """PHP-friendly bool: ''/'0'/'false'/'no'/0/None -> False; else truthy."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s not in ("", "0", "false", "no", "none", "null")


def _as_name_list(v: Any) -> List[str]:
    """['Bali'] passthrough; 'Bali, Singapore' -> ['Bali', 'Singapore']."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [s for s in (str(x).strip() for x in v) if s]
    return [s for s in (part.strip() for part in str(v).split(",")) if s]


def _as_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


CleanStr = Annotated[Optional[str], BeforeValidator(_clean_str)]


class WebToLeadRequest(BaseModel):
    """Outer envelope. Auth is the X-API-Key HEADER — a legacy `token` key in
    the body is ignored (extra keys dropped), never accepted for auth."""
    model_config = ConfigDict(extra="ignore")
    lead: Annotated[Dict[str, Any], BeforeValidator(_as_dict)] = Field(default_factory=dict)


class WebLeadPayload(BaseModel):
    """Lenient view of the `lead` object. All optional; unknown keys ignored."""
    model_config = ConfigDict(extra="ignore")

    salutation: CleanStr = None
    first_name: CleanStr = None
    last_name: CleanStr = None
    email: CleanStr = None
    mobile: CleanStr = None
    phone: CleanStr = None
    company: CleanStr = None
    title: CleanStr = None
    no_employees: Annotated[Optional[int], BeforeValidator(_safe_int)] = None
    website: CleanStr = None
    street: CleanStr = None
    city: CleanStr = None
    state: CleanStr = None
    zip: CleanStr = None
    country: CleanStr = None
    industry_data: Annotated[Dict[str, Any], BeforeValidator(_as_dict)] = Field(default_factory=dict)
    custom_fields: Annotated[Dict[str, Any], BeforeValidator(_as_dict)] = Field(default_factory=dict)
    # NOTE: payload's `source` is intentionally NOT modeled — web leads are
    # always stamped source="Website" (the flag that drives auto-conversion).
