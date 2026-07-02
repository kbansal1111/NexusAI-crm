"""
Cleanup stale `source_medium_id` references from saved LEAD views/columns.

The Lead module's ``source_medium`` / ``source_medium_id`` fields were fully
removed (Source is kept in their place). Any saved EntityView that a user had
configured with "Source Medium" as a display column or filter rule now carries a
dead ``source_medium_id`` key:

  - EntityView.display_columns: a stale "source_medium_id" renders a harmless but
    ugly empty column ("-") in the list view.
  - EntityView.filter_rules:    a stale rule on "source_medium_id" is silently
    dropped by the backend whitelist (no effect), but is clutter.
  - EntityColumn.field_key:     a per-tenant column config pointing at the removed
    field.

This script strips those dead keys. It is tenant-scoped and entity-scoped to
``lead`` only. (source_medium has since been removed from the whole system —
for Opportunity + picklist remnants see cleanup_source_medium_remnants.py.)

DRY-RUN by default — prints what WOULD change. Pass --apply to write.

Usage:
    cd apps/backend
    python scripts/cleanup_lead_source_medium_views.py                 # dry run, all tenants
    python scripts/cleanup_lead_source_medium_views.py --apply         # write, all tenants
    python scripts/cleanup_lead_source_medium_views.py --tenant <id>   # scope to one tenant
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

DEAD_KEY = "source_medium_id"
ENTITY = "lead"


async def main():
    parser = argparse.ArgumentParser(description="Strip dead source_medium_id from saved lead views/columns.")
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
    views = db["entity_views"]
    columns = db["entity_columns"]

    base: dict = {"entity_type": ENTITY}
    if args.tenant:
        base["tenant_id"] = ObjectId(args.tenant)

    views_changed = 0
    cols_deleted = 0

    # ---- entity_views: strip from display_columns + filter_rules ----
    cursor = views.find(base)
    async for doc in cursor:
        display_columns = doc.get("display_columns") or []
        filter_rules = doc.get("filter_rules") or []

        new_columns = [c for c in display_columns if c != DEAD_KEY]
        new_rules = [r for r in filter_rules if str((r or {}).get("field", "")) != DEAD_KEY]

        col_hit = len(new_columns) != len(display_columns)
        rule_hit = len(new_rules) != len(filter_rules)
        if not (col_hit or rule_hit):
            continue

        views_changed += 1
        name = doc.get("name", "(unnamed)")
        tid = doc.get("tenant_id")
        parts = []
        if col_hit:
            parts.append(f"display_columns -{len(display_columns) - len(new_columns)}")
        if rule_hit:
            parts.append(f"filter_rules -{len(filter_rules) - len(new_rules)}")
        print(f"  [view] {name!r:30} tenant={tid}  {', '.join(parts)}")

        if args.apply:
            await views.update_one(
                {"_id": doc["_id"]},
                {"$set": {"display_columns": new_columns, "filter_rules": new_rules}},
            )

    # ---- entity_columns: delete per-tenant column config for the dead field ----
    col_q = {**base, "field_key": DEAD_KEY}
    n_cols = await columns.count_documents(col_q)
    if n_cols:
        cols_deleted = n_cols
        print(f"  [columns] {n_cols} entity_columns row(s) with field_key={DEAD_KEY!r}")
        if args.apply:
            await columns.delete_many(col_q)

    print(
        f"\n{'Updated' if args.apply else 'Would update'}: "
        f"{views_changed} view(s); "
        f"{'deleted' if args.apply else 'would delete'} {cols_deleted} column row(s)."
    )
    if not args.apply and (views_changed or cols_deleted):
        print("Re-run with --apply to perform the cleanup.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
