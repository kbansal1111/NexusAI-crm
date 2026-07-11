"""
Scrub the retired `view_count` counter from record documents.

The user-visible view counter was removed from the whole system (models,
schemas, increment-on-detail-GET endpoints, and the frontend display) on
2026-07-11. Code no longer reads or writes it; this script removes the stale
values still sitting in Atlas documents.

Collections scrubbed: leads, accounts, contacts, opportunities, events, tasks,
plus the per-user recency rows (user_lead_views / user_account_views /
user_contact_views / user_opportunity_views) — their internal `view_count`
counter was also retired. "Recently Viewed" is unaffected: it orders those
rows by `updated_at`, which stays.

DRY-RUN by default — prints what WOULD change. Pass --apply to write.

Usage:
    cd apps/backend
    python scripts/scrub_view_count.py                 # dry run, all tenants
    python scripts/scrub_view_count.py --apply         # write, all tenants
    python scripts/scrub_view_count.py --tenant <id>   # scope to one tenant
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

DEAD_FIELD = "view_count"
COLLECTIONS = [
    "leads", "accounts", "contacts", "opportunities", "events", "tasks",
    # per-user recency rows — keep the rows (updated_at drives "Recently
    # Viewed"), drop only their internal counter
    "user_lead_views", "user_account_views", "user_contact_views", "user_opportunity_views",
]


async def main():
    parser = argparse.ArgumentParser(description="Unset the retired view_count field.")
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

    total = 0
    for coll in COLLECTIONS:
        q: dict = {DEAD_FIELD: {"$exists": True}}
        if tenant_oid:
            q["tenant_id"] = tenant_oid
        n = await db[coll].count_documents(q)
        total += n
        print(f"  [{coll}] {n} doc(s) carrying {DEAD_FIELD}")
        if args.apply and n:
            res = await db[coll].update_many(q, {"$unset": {DEAD_FIELD: ""}})
            print(f"      -> unset on {res.modified_count} doc(s)")

    if not args.apply:
        print(f"\nDry run only — {total} doc(s) would be updated. Re-run with --apply to write.")
    else:
        print(f"\nDone — {DEAD_FIELD} scrubbed.")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
