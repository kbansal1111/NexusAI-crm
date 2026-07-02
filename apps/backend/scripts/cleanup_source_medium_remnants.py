"""
Cleanup ALL remaining `source_medium` data after its full removal from the system.

source_medium was removed everywhere — Source is the single source-tracking
field (Lead.source_id / Opportunity.source_id). This script removes the data
remnants that the code no longer reads:

  - picklists:        documents with picklist_type="source_medium"
                      (platform defaults tenant_id=None AND tenant overrides)
  - opportunities:    $unset the stale source_medium_id field
  - entity_views:     opportunity views with "source_medium_id" in
                      display_columns / filter_rules
  - entity_columns:   opportunity column configs with field_key="source_medium_id"

Lead views were already handled by cleanup_lead_source_medium_views.py.

DRY-RUN by default — prints what WOULD change. Pass --apply to write.

Usage:
    cd apps/backend
    python scripts/cleanup_source_medium_remnants.py                 # dry run, all tenants
    python scripts/cleanup_source_medium_remnants.py --apply         # write, all tenants
    python scripts/cleanup_source_medium_remnants.py --tenant <id>   # scope to one tenant
                                                                     # (platform-default picklists
                                                                     #  are skipped when scoped)
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

DEAD_FIELD = "source_medium_id"
DEAD_PICKLIST_TYPE = "source_medium"
ENTITY = "opportunity"


async def main():
    parser = argparse.ArgumentParser(description="Remove all source_medium data remnants.")
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

    # ---- picklists: delete source_medium items ----
    pk_q: dict = {"picklist_type": DEAD_PICKLIST_TYPE}
    if tenant_oid:
        pk_q["tenant_id"] = tenant_oid  # scoped run leaves platform defaults alone
    n_picklists = await db["picklists"].count_documents(pk_q)
    print(f"  [picklists] {n_picklists} source_medium item(s)")
    if args.apply and n_picklists:
        await db["picklists"].delete_many(pk_q)

    # ---- opportunities: unset stale source_medium_id ----
    opp_q: dict = {DEAD_FIELD: {"$exists": True}}
    if tenant_oid:
        opp_q["tenant_id"] = tenant_oid
    n_opps = await db["opportunities"].count_documents(opp_q)
    print(f"  [opportunities] {n_opps} doc(s) carrying {DEAD_FIELD}")
    if args.apply and n_opps:
        await db["opportunities"].update_many(opp_q, {"$unset": {DEAD_FIELD: ""}})

    # ---- entity_views (opportunity): strip display_columns + filter_rules ----
    views = db["entity_views"]
    base: dict = {"entity_type": ENTITY}
    if tenant_oid:
        base["tenant_id"] = tenant_oid

    views_changed = 0
    async for doc in views.find(base):
        display_columns = doc.get("display_columns") or []
        filter_rules = doc.get("filter_rules") or []

        new_columns = [c for c in display_columns if c != DEAD_FIELD]
        new_rules = [r for r in filter_rules if str((r or {}).get("field", "")) != DEAD_FIELD]

        if len(new_columns) == len(display_columns) and len(new_rules) == len(filter_rules):
            continue

        views_changed += 1
        print(f"  [view] {doc.get('name', '(unnamed)')!r:30} tenant={doc.get('tenant_id')}")
        if args.apply:
            await views.update_one(
                {"_id": doc["_id"]},
                {"$set": {"display_columns": new_columns, "filter_rules": new_rules}},
            )

    # ---- entity_columns (opportunity): delete dead column config ----
    col_q = {**base, "field_key": DEAD_FIELD}
    n_cols = await db["entity_columns"].count_documents(col_q)
    print(f"  [entity_columns] {n_cols} row(s) with field_key={DEAD_FIELD!r}")
    if args.apply and n_cols:
        await db["entity_columns"].delete_many(col_q)

    verb = "Removed" if args.apply else "Would remove"
    print(
        f"\n{verb}: {n_picklists} picklist item(s), "
        f"{n_opps} opportunity field(s), "
        f"{views_changed} view(s), {n_cols} column row(s)."
    )
    if not args.apply and (n_picklists or n_opps or views_changed or n_cols):
        print("Re-run with --apply to perform the cleanup.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
