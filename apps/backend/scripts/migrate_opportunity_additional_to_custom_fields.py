"""
Migrate the Opportunity form's "Additional Information" field into custom_fields.

starting_city (previously industry_data.starting_city) now lives inside the
opportunity's `custom_fields` dict:

    { "starting_city": "New Delhi" }

(close_lost_reason stays top-level — it is a close-lost workflow field, not a
free-form Additional Information value.)

This script:
  1. opportunities:  copies industry_data.starting_city into
                     custom_fields.starting_city and $unsets the old location.
                     Existing custom_fields keys win (idempotent re-run safe).
  2. entity_views:   rewrites opportunity view display_columns + filter_rules:
                       industry_data.starting_city -> custom_fields.starting_city
  3. entity_columns: rewrites opportunity field_key values the same way.

DRY-RUN by default — prints what WOULD change. Pass --apply to write.

Usage:
    cd apps/backend
    python scripts/migrate_opportunity_additional_to_custom_fields.py           # dry run
    python scripts/migrate_opportunity_additional_to_custom_fields.py --apply   # write
    python scripts/migrate_opportunity_additional_to_custom_fields.py --tenant <id>
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

KEY_MAP = {
    "industry_data.starting_city": "custom_fields.starting_city",
}


async def main():
    parser = argparse.ArgumentParser(description="Move opportunity Additional Information into custom_fields.")
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
    base_scope: dict = {"tenant_id": tenant_oid} if tenant_oid else {}

    # ---- 1. opportunities: move starting_city into custom_fields ----
    opp_q = {**base_scope, "industry_data.starting_city": {"$exists": True}}
    opps_migrated = 0
    async for doc in db["opportunities"].find(opp_q):
        cf = dict(doc.get("custom_fields") or {})
        city = (doc.get("industry_data") or {}).get("starting_city")

        update: dict = {"$unset": {"industry_data.starting_city": ""}}
        # Existing custom_fields value wins — re-run safe; empty strings dropped.
        if city and "starting_city" not in cf:
            update["$set"] = {"custom_fields.starting_city": city}

        opps_migrated += 1
        if args.apply:
            await db["opportunities"].update_one({"_id": doc["_id"]}, update)
    print(f"  [opportunities] {opps_migrated} doc(s) migrated")

    # ---- 2. entity_views (opportunity): rewrite column/filter keys ----
    views_q = {**base_scope, "entity_type": "opportunity"}
    views_changed = 0
    async for doc in db["entity_views"].find(views_q):
        display_columns = doc.get("display_columns") or []
        filter_rules = doc.get("filter_rules") or []

        new_columns = [KEY_MAP.get(c, c) for c in display_columns]
        new_rules = [
            {**r, "field": KEY_MAP.get(str((r or {}).get("field", "")), (r or {}).get("field"))}
            if isinstance(r, dict) else r
            for r in filter_rules
        ]

        if new_columns == display_columns and new_rules == filter_rules:
            continue
        views_changed += 1
        print(f"  [view] {doc.get('name', '(unnamed)')!r:30} tenant={doc.get('tenant_id')}")
        if args.apply:
            await db["entity_views"].update_one(
                {"_id": doc["_id"]},
                {"$set": {"display_columns": new_columns, "filter_rules": new_rules}},
            )
    print(f"  [entity_views] {views_changed} view(s) rewritten")

    # ---- 3. entity_columns (opportunity): rewrite field_key ----
    cols_changed = 0
    for old_key, new_key in KEY_MAP.items():
        col_q = {**base_scope, "entity_type": "opportunity", "field_key": old_key}
        n = await db["entity_columns"].count_documents(col_q)
        if n:
            cols_changed += n
            if args.apply:
                await db["entity_columns"].update_many(col_q, {"$set": {"field_key": new_key}})
    print(f"  [entity_columns] {cols_changed} row(s) rewritten")

    verb = "Migrated" if args.apply else "Would migrate"
    print(f"\n{verb}: {opps_migrated} opportunity(ies), {views_changed} view(s), {cols_changed} column row(s).")
    if not args.apply and (opps_migrated or views_changed or cols_changed):
        print("Re-run with --apply to perform the migration.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
