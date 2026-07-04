"""
Hermetic security tests for the public web-to-lead endpoint
(POST /api/v1/integrations/leads).

No DB / no server: the handler coroutine is invoked directly with a stub
starlette Request, and every DB-touching seam in app.api.v1.integrations is
monkeypatched (pattern: tests/test_industry_guard.py).

CLAUDE.md §1 requirement: tenant-isolation coverage for every new endpoint —
see test_tenant_isolation_hostile_fields / test_token_tenant_binding.
"""
import asyncio
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1 import integrations
from app.core.validators import normalize_loose_phone
from app.schemas.integration import WebToLeadRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stub_request(api_key: str | None = None) -> Request:
    headers = [(b"x-api-key", api_key.encode())] if api_key else []
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/integrations/leads",
        "headers": headers,
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


VALID_KEY = "a" * 64


class FakeToken(SimpleNamespace):
    def is_valid(self):
        return getattr(self, "_valid", True)

    async def set(self, *_args, **_kwargs):
        return None


def _fake_token(tenant_id, valid=True, scopes=None):
    return FakeToken(
        id=ObjectId(),
        tenant_id=tenant_id,
        scopes=scopes if scopes is not None else ["leads:write"],
        _valid=valid,
    )


def _fake_tenant(industry="travel"):
    return SimpleNamespace(id=ObjectId(), industry=industry, is_active=True)


TRAVEL_LEAD = {
    "first_name": "",
    "last_name": "Rahul Sharma",
    "email": "rahul@example.com",
    "mobile": "9876543210",
    "city": "New Delhi",
    "state": "Delhi",
    "country": "India",
    "industry_data": {
        "travel_date": "2026-09-15",
        "no_of_nights": "5",
        "no_of_pax": "4",
        "is_fixed": "0",
        "destinations": "Bali, Singapore",
    },
    "custom_fields": {"segment": "b2c", "campaign_name": "summer", "experience": "Honeymoon"},
}


@pytest.fixture
def pipeline(monkeypatch):
    """Patch every DB seam; return the capture dict."""
    tenant = _fake_tenant()
    token = _fake_token(tenant.id)
    owner = SimpleNamespace(id=ObjectId(), name="Admin User")
    website_source_id = str(ObjectId())
    experience_id = str(ObjectId())
    destination_id = str(ObjectId())
    created_lead = SimpleNamespace(id=ObjectId())
    captured: dict = {
        "tenant": tenant, "token": token, "owner": owner,
        "website_source_id": website_source_id, "experience_id": experience_id,
        "destination_id": destination_id, "created_lead": created_lead,
    }

    # Limiter must never consult external storage in tests.
    monkeypatch.setattr(integrations.limiter, "enabled", False, raising=False)

    async def fake_auth(raw_key):
        if raw_key and raw_key.strip() == VALID_KEY:
            return token, tenant
        raise HTTPException(status_code=401, detail="Invalid integration token")

    async def fake_source(t):
        captured["source_resolved_for"] = t.id
        return website_source_id

    async def fake_experience(name, t):
        captured["experience_name"] = name
        return experience_id if name else None

    async def fake_destinations(names, tid):
        captured["destination_names"] = list(names)
        return [destination_id]

    async def fake_status(tid):
        return str(ObjectId())

    async def fake_owner(tid):
        captured["owner_resolved_for"] = tid
        return owner

    async def fake_guard(tenant_id, data, *, mode, require_for_travel=False):
        if require_for_travel and not data:
            raise HTTPException(status_code=422, detail="Travel details are required.")
        return data

    async def fake_dest_names(industry_data, tenant_id=None):
        return industry_data

    async def fake_create_lead(lead_data, user_id, tenant_id, **kwargs):
        captured["lead_data"] = lead_data
        captured["create_kwargs"] = {"user_id": user_id, "tenant_id": tenant_id, **kwargs}
        return created_lead

    async def fake_convert(lead_id, conversion_data, user_id, tenant_id):
        captured["convert_args"] = {
            "lead_id": lead_id, "user_id": user_id, "tenant_id": tenant_id,
        }
        return {"opportunity_id": "opp123", "lead_id": lead_id}

    monkeypatch.setattr(integrations, "_authenticate", fake_auth)
    monkeypatch.setattr(integrations, "_resolve_website_source_id", fake_source)
    monkeypatch.setattr(integrations, "_resolve_experience_id", fake_experience)
    monkeypatch.setattr(integrations, "_resolve_destination_ids", fake_destinations)
    monkeypatch.setattr(integrations, "_default_lead_status_id", fake_status)
    monkeypatch.setattr(integrations, "_resolve_admin_owner", fake_owner)
    monkeypatch.setattr("app.core.industry_guard.resolve_industry_data", fake_guard)
    monkeypatch.setattr("app.api.v1.leads._resolve_destinations", fake_dest_names)
    monkeypatch.setattr(integrations.lead_service, "create_lead", fake_create_lead)
    monkeypatch.setattr(integrations.lead_service, "convert_lead", fake_convert)
    return captured


def _post(lead: dict, key: str | None = VALID_KEY):
    body = WebToLeadRequest(lead=lead)
    return _run(integrations.create_web_lead(_stub_request(api_key=key), body))


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_key_401(pipeline):
    body = WebToLeadRequest(lead=dict(TRAVEL_LEAD))
    with pytest.raises(HTTPException) as exc:
        await integrations.create_web_lead(_stub_request(api_key="wrong-key-wrong-key"), body)
    assert exc.value.status_code == 401
    assert "lead_data" not in pipeline  # create_lead never reached


@pytest.mark.asyncio
async def test_missing_header_401(pipeline):
    body = WebToLeadRequest(lead=dict(TRAVEL_LEAD))
    with pytest.raises(HTTPException) as exc:
        await integrations.create_web_lead(_stub_request(), body)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_body_token_is_ignored_for_auth(pipeline):
    """Legacy body 'token' must NOT authenticate — header only."""
    body = WebToLeadRequest(**{"token": VALID_KEY, "lead": dict(TRAVEL_LEAD)})
    assert not hasattr(body, "token") or getattr(body, "token", None) is None
    with pytest.raises(HTTPException) as exc:
        await integrations.create_web_lead(_stub_request(), body)
    assert exc.value.status_code == 401


def test_header_auth_works(pipeline):
    result = _post(dict(TRAVEL_LEAD))
    assert result["success"] is True


def test_real_authenticate_rejects_invalid_variants(monkeypatch):
    """_authenticate itself: revoked/expired/wrong-scope tokens all 401."""
    tenant = _fake_tenant()

    async def find_token(query):
        return find_token.token

    async def find_tenant(query):
        return tenant

    monkeypatch.setattr(integrations.IntegrationToken, "find_one", find_token)
    monkeypatch.setattr(integrations.Tenant, "find_one", find_tenant)

    # Valid token passes.
    find_token.token = _fake_token(tenant.id)
    tok, ten = _run(integrations._authenticate(VALID_KEY))
    assert ten is tenant

    # Revoked/expired (is_valid False) → 401.
    find_token.token = _fake_token(tenant.id, valid=False)
    with pytest.raises(HTTPException) as exc:
        _run(integrations._authenticate(VALID_KEY))
    assert exc.value.status_code == 401

    # Missing scope → 401.
    find_token.token = _fake_token(tenant.id, scopes=["other:scope"])
    with pytest.raises(HTTPException) as exc:
        _run(integrations._authenticate(VALID_KEY))
    assert exc.value.status_code == 401

    # No match at all → 401.
    find_token.token = None
    with pytest.raises(HTTPException) as exc:
        _run(integrations._authenticate(VALID_KEY))
    assert exc.value.status_code == 401

    # Too-short key rejected before any lookup.
    with pytest.raises(HTTPException):
        _run(integrations._authenticate("short"))


# ---------------------------------------------------------------------------
# Tenant isolation (CLAUDE.md §1)
# ---------------------------------------------------------------------------

def test_tenant_isolation_hostile_fields(pipeline):
    """Injected tenant_id/owner_id in the body must be ignored — the write
    lands in the token's tenant with the resolved admin owner."""
    hostile = dict(TRAVEL_LEAD)
    hostile["tenant_id"] = str(ObjectId())   # attacker-chosen tenant
    hostile["owner_id"] = str(ObjectId())    # attacker-chosen owner
    hostile["is_converted"] = True
    hostile["junk_field"] = {"x": 1}

    result = _post(hostile)
    assert result["success"] is True
    kwargs = pipeline["create_kwargs"]
    assert kwargs["tenant_id"] == pipeline["tenant"].id
    assert kwargs["user_id"] == pipeline["owner"].id
    # LeadCreate itself carries no tenant/owner from the wire.
    lead_data = pipeline["lead_data"]
    assert not getattr(lead_data, "tenant_id", None)


def test_token_tenant_binding(monkeypatch, pipeline):
    """Tenant B's token must write into tenant B — never A."""
    tenant_b = _fake_tenant()
    token_b = _fake_token(tenant_b.id)
    key_b = "b" * 64

    async def fake_auth(raw_key):
        if raw_key and raw_key.strip() == key_b:
            return token_b, tenant_b
        raise HTTPException(status_code=401, detail="Invalid integration token")

    monkeypatch.setattr(integrations, "_authenticate", fake_auth)
    result = _post(dict(TRAVEL_LEAD), key=key_b)
    assert result["success"] is True
    assert pipeline["create_kwargs"]["tenant_id"] == tenant_b.id


# ---------------------------------------------------------------------------
# Business rules
# ---------------------------------------------------------------------------

def test_source_always_website_even_if_payload_sends_other(pipeline):
    lead = dict(TRAVEL_LEAD)
    lead["source"] = "Instagram"  # must be ignored — web leads are "Website"
    result = _post(lead)
    assert result["success"] is True
    assert pipeline["lead_data"].source_id == pipeline["website_source_id"]
    assert pipeline["source_resolved_for"] == pipeline["tenant"].id


def test_always_creates_new_lead(pipeline):
    _post(dict(TRAVEL_LEAD))
    assert pipeline["create_kwargs"]["skip_duplicate_check"] is True


def test_autoconvert_called_with_admin(pipeline):
    result = _post(dict(TRAVEL_LEAD))
    assert result["converted"] is True
    assert result["opportunity_id"] == "opp123"
    conv = pipeline["convert_args"]
    assert conv["lead_id"] == str(pipeline["created_lead"].id)
    assert conv["user_id"] == pipeline["owner"].id
    assert conv["tenant_id"] == pipeline["tenant"].id


def test_conversion_failure_never_loses_lead(pipeline, monkeypatch):
    async def broken_convert(*a, **k):
        raise RuntimeError("conversion exploded")

    monkeypatch.setattr(integrations.lead_service, "convert_lead", broken_convert)
    result = _post(dict(TRAVEL_LEAD))
    assert result["success"] is True
    assert result["lead_id"] == str(pipeline["created_lead"].id)
    assert result["converted"] is False
    assert result["opportunity_id"] is None


def test_creation_type_auto_and_owner(pipeline):
    _post(dict(TRAVEL_LEAD))
    assert pipeline["lead_data"].creation_type == "auto"
    assert pipeline["create_kwargs"]["user_name"] == "Admin User"


# ---------------------------------------------------------------------------
# Normalization / coercion
# ---------------------------------------------------------------------------

def test_php_style_string_casts(pipeline):
    _post(dict(TRAVEL_LEAD))
    idata = pipeline["lead_data"].industry_data
    assert idata["no_of_nights"] == 5
    assert idata["no_of_pax"] == 4
    assert idata["is_fixed"] is False
    assert idata["destinations"] == ["Bali", "Singapore"]
    assert idata["destination_ids"] == [pipeline["destination_id"]]
    assert pipeline["destination_names"] == ["Bali", "Singapore"]


def test_custom_fields_whitelist_and_segment_normalization(pipeline):
    lead = dict(TRAVEL_LEAD)
    lead["custom_fields"] = {
        "segment": "b2b", "campaign_name": " camp ", "experience": "Honeymoon",
        "evil_key": "x",
    }
    _post(lead)
    cf = pipeline["lead_data"].custom_fields
    assert cf["segment"] == "B2B"
    assert cf["campaign_name"] == "camp"
    assert cf["experience_id"] == pipeline["experience_id"]
    assert "evil_key" not in cf


def test_visitor_ip_captured_in_custom_fields(pipeline):
    """Old contract's top-level `ip` lands in custom_fields.ip_address —
    sales derives the enquirer's country from it."""
    lead = dict(TRAVEL_LEAD)
    lead["ip"] = "203.0.113.7"
    _post(lead)
    assert pipeline["lead_data"].custom_fields["ip_address"] == "203.0.113.7"


def test_no_ip_means_no_ip_key(pipeline):
    _post(dict(TRAVEL_LEAD))
    assert "ip_address" not in pipeline["lead_data"].custom_fields


def test_bad_segment_defaults_b2c(pipeline):
    lead = dict(TRAVEL_LEAD)
    lead["custom_fields"] = {"segment": "WHATEVER"}
    _post(lead)
    assert pipeline["lead_data"].custom_fields["segment"] == "B2C"


def test_phone_normalized_before_leadcreate(pipeline):
    lead = dict(TRAVEL_LEAD)
    lead["mobile"] = "9876543210"
    lead["phone"] = "+919812345678"
    _post(lead)
    assert pipeline["lead_data"].mobile == "+91 9876543210"
    assert pipeline["lead_data"].phone == "+91 9812345678"


def test_garbage_phone_and_email_dropped_not_rejected(pipeline):
    lead = dict(TRAVEL_LEAD)
    lead["mobile"] = "call-me-maybe"
    lead["email"] = "not-an-email"
    result = _post(lead)
    assert result["success"] is True
    assert pipeline["lead_data"].mobile is None
    assert pipeline["lead_data"].email is None


def test_missing_first_name_becomes_empty_string(pipeline):
    lead = dict(TRAVEL_LEAD)
    lead.pop("first_name")
    _post(lead)
    assert pipeline["lead_data"].first_name == ""


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------

def test_travel_tenant_requires_industry_data(pipeline):
    lead = dict(TRAVEL_LEAD)
    lead["industry_data"] = {}
    with pytest.raises(HTTPException) as exc:
        _post(lead)
    assert exc.value.status_code == 422


def test_service_valueerror_maps_to_422(pipeline, monkeypatch):
    async def rejecting_create(*a, **k):
        raise ValueError("Last name is required.")

    monkeypatch.setattr(integrations.lead_service, "create_lead", rejecting_create)
    with pytest.raises(HTTPException) as exc:
        _post(dict(TRAVEL_LEAD))
    assert exc.value.status_code == 422
    assert "Last name is required." in exc.value.detail


def test_unexpected_error_maps_to_500_generic(pipeline, monkeypatch):
    async def exploding_create(*a, **k):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(integrations.lead_service, "create_lead", exploding_create)
    with pytest.raises(HTTPException) as exc:
        _post(dict(TRAVEL_LEAD))
    assert exc.value.status_code == 500
    assert "secret" not in exc.value.detail  # no internal leakage


# ---------------------------------------------------------------------------
# normalize_loose_phone (pure function)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+91 9876543210", "+91 9876543210"),
        ("9876543210", "+91 9876543210"),
        ("09876543210", "+91 9876543210"),
        ("+919876543210", "+91 9876543210"),
        ("919876543210", "+91 9876543210"),
        ("98765-43210", "+91 9876543210"),
        ("(987) 654-3210", "+91 9876543210"),
        ("+1 4155552671", "+1 4155552671"),
        ("+14155552671", "+1 4155552671"),
        ("garbage", None),
        ("12345", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_loose_phone(raw, expected):
    assert normalize_loose_phone(raw) == expected
