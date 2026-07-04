"""
Manage integration API keys (web-to-lead etc.) for a tenant.

Keys follow the industry-standard pattern: only the SHA-256 hash is stored;
the plaintext is printed EXACTLY ONCE at creation. `token_prefix` (first 8
chars) identifies a key afterwards. Multiple active keys per tenant enable
zero-downtime rotation: create the new key, deploy it to the website, then
revoke the old one.

Usage:
    cd apps/backend
    python scripts/manage_integration_tokens.py create --tenant <subdomain|id> [--label "Website"] [--expires-days N]
    python scripts/manage_integration_tokens.py list   --tenant <subdomain|id>
    python scripts/manage_integration_tokens.py revoke --tenant <subdomain|id> --prefix <8-char-prefix>
"""
import argparse
import asyncio
import hashlib
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

SCOPE_LEADS_WRITE = "leads:write"


def _connect():
    from dotenv import load_dotenv
    load_dotenv()
    mongo_url = os.environ.get("MONGODB_URL") or os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    db_name = os.environ.get("MONGODB_DB_NAME") or os.environ.get("DB_NAME") or "tutterfly_crm"
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


async def _find_tenant(db, ref: str):
    if ObjectId.is_valid(ref):
        tenant = await db["tenants"].find_one({"_id": ObjectId(ref)})
        if tenant:
            return tenant
    return await db["tenants"].find_one({"subdomain": ref})


async def cmd_create(db, tenant: dict, label: str, expires_days: int | None):
    plaintext = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    doc = {
        "tenant_id": tenant["_id"],
        "token_hash": hashlib.sha256(plaintext.encode()).hexdigest(),
        "token_prefix": plaintext[:8],
        "label": label,
        "scopes": [SCOPE_LEADS_WRITE],
        "is_active": True,
        "expires_at": (now + timedelta(days=expires_days)) if expires_days else None,
        "revoked_at": None,
        "last_used_at": None,
        "created_by": None,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    await db["integration_tokens"].insert_one(doc)

    active = await db["integration_tokens"].count_documents(
        {"tenant_id": tenant["_id"], "is_active": True, "revoked_at": None}
    )
    print("=" * 72)
    print(f"  Tenant : {tenant.get('company_name')} ({tenant.get('subdomain')})")
    print(f"  Label  : {label}")
    print(f"  Prefix : {plaintext[:8]}   (identifies this key later)")
    print(f"  Expires: {doc['expires_at'] or 'never'}")
    print("-" * 72)
    print(f"  API KEY (shown ONCE — store securely, cannot be recovered):")
    print(f"\n      {plaintext}\n")
    print("-" * 72)
    print(f"  Active keys for this tenant: {active}")
    if active > 1:
        print("  Rotation tip: deploy this key to the website, verify, then revoke")
        print("  the old key with:  revoke --prefix <old-prefix>")
    print("=" * 72)


async def cmd_list(db, tenant: dict):
    cursor = db["integration_tokens"].find({"tenant_id": tenant["_id"]}).sort("created_at", -1)
    rows = await cursor.to_list(100)
    if not rows:
        print("No integration keys for this tenant.")
        return
    print(f"{'PREFIX':10} {'LABEL':20} {'ACTIVE':7} {'LAST USED':22} {'EXPIRES':22} CREATED")
    for r in rows:
        active = bool(r.get("is_active")) and not r.get("revoked_at")
        print(
            f"{r.get('token_prefix', '?'):10} {str(r.get('label', ''))[:19]:20} "
            f"{('yes' if active else 'no'):7} "
            f"{str(r.get('last_used_at') or '-'):22.21} "
            f"{str(r.get('expires_at') or 'never'):22.21} "
            f"{str(r.get('created_at') or '-'):19.19}"
        )


async def cmd_revoke(db, tenant: dict, prefix: str):
    result = await db["integration_tokens"].update_many(
        {"tenant_id": tenant["_id"], "token_prefix": prefix, "revoked_at": None},
        {"$set": {"is_active": False, "revoked_at": datetime.now(timezone.utc)}},
    )
    if result.modified_count:
        print(f"Revoked {result.modified_count} key(s) with prefix {prefix!r}. Effective immediately.")
    else:
        print(f"No active key with prefix {prefix!r} found for this tenant.")


async def main():
    parser = argparse.ArgumentParser(description="Manage integration API keys.")
    parser.add_argument("command", choices=["create", "list", "revoke"])
    parser.add_argument("--tenant", required=True, help="Tenant subdomain or ObjectId")
    parser.add_argument("--label", default="Website", help="Key label (create)")
    parser.add_argument("--expires-days", type=int, default=None, help="Optional expiry in days (create)")
    parser.add_argument("--prefix", help="8-char key prefix (revoke)")
    args = parser.parse_args()

    client, db = _connect()
    try:
        tenant = await _find_tenant(db, args.tenant)
        if not tenant:
            print(f"Tenant {args.tenant!r} not found.")
            sys.exit(1)
        if not tenant.get("is_active", True):
            print(f"Tenant {args.tenant!r} is INACTIVE — keys would never authenticate.")
            sys.exit(1)

        if args.command == "create":
            await cmd_create(db, tenant, args.label, args.expires_days)
        elif args.command == "list":
            await cmd_list(db, tenant)
        elif args.command == "revoke":
            if not args.prefix:
                print("revoke requires --prefix <8-char-prefix> (see: list)")
                sys.exit(1)
            await cmd_revoke(db, tenant, args.prefix)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
