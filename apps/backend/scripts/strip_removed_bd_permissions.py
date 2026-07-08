"""
Strip removed BD field-ops permission strings from all stored Role documents.

The field-ops BD feature (visits, expenses, live tracking, automation rules)
was removed and replaced by the territory-scoped BD sales panel. Only
`view_bd_panel` and `manage_territory` survive in the permission registry
(app/services/role_service.py). Existing Role documents may still carry the
dead strings in their `permissions` array; this $pulls them out so the Profiles
& Permissions UI and permission checks stay consistent with the registry.

DRY-RUN by default — prints what WOULD change. Pass --apply to write.

Usage:
    cd apps/backend
    python scripts/strip_removed_bd_permissions.py                 # dry run, all tenants
    python scripts/strip_removed_bd_permissions.py --apply         # write, all tenants
    python scripts/strip_removed_bd_permissions.py --tenant <id>   # scope to one tenant
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

REMOVED_PERMISSIONS = [
    "manage_bd_panel",
    "view_bd_visit", "create_bd_visit", "edit_bd_visit", "delete_bd_visit",
    "approve_bd_visit", "check_in_bd_visit",
    "view_expense", "create_expense", "edit_expense", "delete_expense",
    "approve_expense", "reimburse_expense",
    "view_live_tracking", "manage_live_tracking",
    "manage_automation_rules",
]


async def main():
    parser = argparse.ArgumentParser(description="Strip removed BD permissions from roles.")
    parser.add_argument("--apply", action="store_true", help="Actually write (default: dry run).")
    parser.add_argument("--tenant", help="Scope to a single tenant_id.")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    mongo_url = (
        os.environ.get("MONGODB_URL")
        or os.environ.get("MONGO_URL")
        or "mongodb://localhost:27017"
    )
    db_name = (
        os.environ.get("MONGODB_DB_NAME")
        or os.environ.get("DB_NAME")
        or "tutterfly_crm"
    )

    mode = "APPLY (writing)" if args.apply else "DRY RUN (no changes)"
    print(f"Connecting to {db_name} ...  [{mode}]")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    tenant_oid = ObjectId(args.tenant) if args.tenant else None

    q: dict = {"permissions": {"$in": REMOVED_PERMISSIONS}}
    if tenant_oid:
        q["tenant_id"] = tenant_oid

    roles = db["roles"]
    affected = 0
    async for role in roles.find(q):
        stale = sorted(set(role.get("permissions") or []) & set(REMOVED_PERMISSIONS))
        if not stale:
            continue
        affected += 1
        print(f"  [role] {role.get('display_name') or role.get('name') or role['_id']!r:30} "
              f"tenant={role.get('tenant_id')}  removing: {', '.join(stale)}")

    print(f"\n{affected} role(s) carry removed BD permissions.")
    if args.apply and affected:
        res = await roles.update_many(q, {"$pull": {"permissions": {"$in": REMOVED_PERMISSIONS}}})
        print(f"Updated {res.modified_count} role document(s).")
    elif not args.apply and affected:
        print("Re-run with --apply to write.")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
