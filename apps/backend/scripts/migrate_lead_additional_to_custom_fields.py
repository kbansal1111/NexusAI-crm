"""
Migrate the Lead form's "Additional Information" fields into custom_fields.

segment / campaign_name (top-level Lead fields) and experience_id
(industry_data.experience_id) now live inside the lead's `custom_fields` dict:

    { "segment": "B2C", "campaign_name": "...", "experience_id": "<oid str>" }

This script:
  1. leads:          copies segment / campaign_name / industry_data.experience_id
                     into custom_fields.* and $unsets the old locations.
                     Existing custom_fields keys win (idempotent re-run safe).
  2. entity_views:   rewrites lead view display_columns + filter_rules keys:
                       segment                     -> custom_fields.segment
                       campaign_name               -> custom_fields.campaign_name
                       industry_data.experience_id -> custom_fields.experience_id
                     (covers user-saved views AND the seeded WhatsApp Enquiry view)
  3. entity_columns: rewrites lead field_key values the same way.

DRY-RUN by default — prints what WOULD change. Pass --apply to write.

Usage:
    cd apps/backend
    python scripts/migrate_lead_additional_to_custom_fields.py                 # dry run
    python scripts/migrate_lead_additional_to_custom_fields.py --apply         # write
    python scripts/migrate_lead_additional_to_custom_fields.py --tenant <id>   # one tenant
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

KEY_MAP = {
    "segment": "custom_fields.segment",
    "campaign_name": "custom_fields.campaign_name",
    "industry_data.experience_id": "custom_fields.experience_id",
}


async def main():
    parser = argparse.ArgumentParser(description="Move lead Additional Information into custom_fields.")
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

    # ---- 1. leads: move values into custom_fields ----
    lead_q = {
        **base_scope,
        "$or": [
            {"segment": {"$exists": True}},
            {"campaign_name": {"$exists": True}},
            {"industry_data.experience_id": {"$exists": True}},
        ],
    }
    leads_migrated = 0
    async for doc in db["leads"].find(lead_q):
        cf = dict(doc.get("custom_fields") or {})
        sets = {}
        # Existing custom_fields values win — re-run safe.
        if doc.get("segment") is not None and "segment" not in cf:
            sets["custom_fields.segment"] = doc["segment"]
        if doc.get("campaign_name") is not None and "campaign_name" not in cf:
            sets["custom_fields.campaign_name"] = doc["campaign_name"]
        exp = (doc.get("industry_data") or {}).get("experience_id")
        if exp is not None and "experience_id" not in cf:
            sets["custom_fields.experience_id"] = str(exp)

        unsets = {}
        if "segment" in doc:
            unsets["segment"] = ""
        if "campaign_name" in doc:
            unsets["campaign_name"] = ""
        if "experience_id" in (doc.get("industry_data") or {}):
            unsets["industry_data.experience_id"] = ""

        if not sets and not unsets:
            continue
        leads_migrated += 1
        if args.apply:
            update: dict = {}
            if sets:
                update["$set"] = sets
            if unsets:
                update["$unset"] = unsets
            await db["leads"].update_one({"_id": doc["_id"]}, update)
    print(f"  [leads] {leads_migrated} doc(s) migrated")

    # ---- 2. entity_views (lead): rewrite column/filter keys ----
    views_q = {**base_scope, "entity_type": "lead"}
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

    # ---- 3. entity_columns (lead): rewrite field_key ----
    cols_changed = 0
    for old_key, new_key in KEY_MAP.items():
        col_q = {**base_scope, "entity_type": "lead", "field_key": old_key}
        n = await db["entity_columns"].count_documents(col_q)
        if n:
            cols_changed += n
            if args.apply:
                await db["entity_columns"].update_many(col_q, {"$set": {"field_key": new_key}})
    print(f"  [entity_columns] {cols_changed} row(s) rewritten")

    verb = "Migrated" if args.apply else "Would migrate"
    print(f"\n{verb}: {leads_migrated} lead(s), {views_changed} view(s), {cols_changed} column row(s).")
    if not args.apply and (leads_migrated or views_changed or cols_changed):
        print("Re-run with --apply to perform the migration.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
