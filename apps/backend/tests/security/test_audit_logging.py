"""Hermetic tests for the automatic API audit trail + auth logging.

Covers the logging/audit hardening added for client handover:

1. `redact_sensitive` never lets a secret-looking key reach a persisted body.
2. `ApiAuditLog` rows written by the middleware helper round-trip through the DB.
3. The admin `/timeline/audit` endpoint is tenant-scoped — an admin in tenant A
   can never read tenant B's audit rows (CLAUDE.md non-negotiable #1), and a
   non-admin is refused outright.
4. `AuthService._log_login` records BOTH successful and failed attempts.

All hermetic: mongomock-motor, no network, no real Atlas.
"""
import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from beanie import init_beanie

from app.models.activity_log import ActivityLog, LoginLog, ApiAuditLog
from app.models.role import Role, RoleHierarchy
from app.models.user import User
from app.core.logging_config import redact_sensitive
from app.middleware.activity_context import _write_audit_row, _decode_body


TENANT_A = ObjectId()
TENANT_B = ObjectId()


async def _init():
    client = AsyncMongoMockClient()
    await init_beanie(
        database=client[f"audit_{ObjectId()}"],
        document_models=[ActivityLog, LoginLog, ApiAuditLog, Role, RoleHierarchy, User],
    )


async def _admin(tenant_id):
    role = Role(name="Admin", display_name="Admin", tenant_id=tenant_id,
                is_admin=True, permissions=[])
    await role.insert()
    u = User(
        name="Admin", email=f"{ObjectId()}@t.com", password="x",
        tenant_id=tenant_id, is_active=True, role_ids=[role.id],
    )
    await u.insert()
    return u


async def _regular(tenant_id):
    u = User(
        name="Rep", email=f"{ObjectId()}@t.com", password="x",
        tenant_id=tenant_id, is_active=True, role_ids=[],
    )
    await u.insert()
    return u


# --- 1. Redaction --------------------------------------------------------------

def test_redact_sensitive_scrubs_nested_secrets():
    payload = {
        "email": "a@b.com",
        "password": "hunter2",
        "profile": {"apiToken": "abc", "name": "X"},
        "items": [{"credit_card": "4111111111111111"}, {"ok": 1}],
    }
    out = redact_sensitive(payload)
    assert out["email"] == "a@b.com"           # kept
    assert out["password"] == "[REDACTED]"
    assert out["profile"]["apiToken"] == "[REDACTED]"
    assert out["profile"]["name"] == "X"
    assert out["items"][0]["credit_card"] == "[REDACTED]"
    assert out["items"][1]["ok"] == 1


def test_decode_body_redacts_and_flags_truncation():
    raw = b'{"password": "s3cret", "name": "Ada"}'
    out = _decode_body(raw, truncated=False)
    assert out["password"] == "[REDACTED]"
    assert out["name"] == "Ada"
    flagged = _decode_body(raw, truncated=True)
    assert flagged["_truncated"] is True


# --- 2. Audit row persistence --------------------------------------------------

@pytest.mark.asyncio
async def test_write_audit_row_roundtrips():
    await _init()
    await _write_audit_row({
        "request_id": "req-1",
        "method": "POST",
        "path": "/api/v1/leads",
        "status_code": 201,
        "tenant_id": TENANT_A,
        "user_email": "a@b.com",
        "body": {"password": "[REDACTED]", "name": "L"},
    })
    rows = await ApiAuditLog.find({"request_id": "req-1"}).to_list()
    assert len(rows) == 1
    assert rows[0].method == "POST"
    assert rows[0].status_code == 201
    assert rows[0].body["password"] == "[REDACTED]"


# --- 3. Admin audit endpoint: tenant isolation + admin gate --------------------

@pytest.mark.asyncio
async def test_audit_endpoint_is_tenant_scoped():
    await _init()
    admin_a = await _admin(TENANT_A)
    admin_b = await _admin(TENANT_B)

    await ApiAuditLog(request_id="a1", method="DELETE", path="/api/v1/accounts/x",
                      status_code=200, tenant_id=TENANT_A).insert()
    await ApiAuditLog(request_id="b1", method="DELETE", path="/api/v1/accounts/y",
                      status_code=200, tenant_id=TENANT_B).insert()

    from app.api.v1.activity_logs import get_api_audit_logs

    res_a = await get_api_audit_logs(current_user=admin_a)
    paths_a = {r["request_id"] for r in res_a["logs"]}
    assert paths_a == {"a1"}               # only tenant A's row
    assert "b1" not in paths_a             # never leaks tenant B

    res_b = await get_api_audit_logs(current_user=admin_b)
    assert {r["request_id"] for r in res_b["logs"]} == {"b1"}


@pytest.mark.asyncio
async def test_audit_endpoint_refuses_non_admin():
    await _init()
    rep = await _regular(TENANT_A)
    from fastapi import HTTPException
    from app.api.v1.activity_logs import get_api_audit_logs

    with pytest.raises(HTTPException) as exc:
        await get_api_audit_logs(current_user=rep)
    assert exc.value.status_code == 403


# --- 4. Login logging: success AND failure -------------------------------------

@pytest.mark.asyncio
async def test_log_login_records_success_and_failure():
    await _init()
    user = await _regular(TENANT_A)
    from app.services.auth_service import AuthService
    svc = AuthService()

    await svc._log_login(user, success=True, ip_address="1.2.3.4")
    await svc._log_login(user, success=False, failure_reason="Invalid password",
                         ip_address="9.9.9.9")

    logs = await LoginLog.find({"user_id": user.id}).sort("+created_at").to_list()
    assert len(logs) == 2
    assert logs[0].success is True
    assert logs[0].ip_address == "1.2.3.4"
    assert logs[1].success is False
    assert logs[1].failure_reason == "Invalid password"
