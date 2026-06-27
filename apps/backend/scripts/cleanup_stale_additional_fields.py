"""
Cleanup stale "additional fields" from the field_registry.

The list-view column picker and "Edit List Filters" source their *Additional
Fields* from AdditionalField* records (``is_custom != False``) in the
``field_registry`` collection. Some tenants (migrated from the legacy CRM)
carry stale additional-field records that are NOT real custom fields — they
either duplicate a STANDARD field (e.g. "Combined Source", "Source Medium")
or are dead leftovers ("Passport Number"). These surface in the picker but
exist in no form.

This script deletes those stale records (and their stored values in
``custom_field_values``) while KEEPING genuine, tenant-defined custom fields.

A record is considered STALE when, for its ``entity_type``, any of:
  1. its field_key / name / label (normalised) matches a STANDARD field
     (field_key or label) for that entity, or
  2. its field_key / name / label (normalised) is in JUNK_DENYLIST.

Genuine custom fields (e.g. "Deals In") match neither, so they are preserved.

DRY-RUN by default — prints what WOULD be deleted. Pass --apply to delete.

Usage:
    cd apps/backend
    python scripts/cleanup_stale_additional_fields.py                 # dry run, all tenants
    python scripts/cleanup_stale_additional_fields.py --apply         # delete, all tenants
    python scripts/cleanup_stale_additional_fields.py --tenant <id>   # scope to one tenant
    python scripts/cleanup_stale_additional_fields.py --entity lead   # scope to one entity_type
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

# Authoritative per-entity standard field definitions (the form mirror).
from app.services.field_registry_service import DEFAULT_STANDARD_FIELDS

# Custom-field VALUE foreign-key column per entity (cascade delete target).
FIELD_FK_BY_ENTITY = {
    "account": "account_additional_field_id",
    "contact": "contact_additional_field_id",
    "lead": "lead_additional_field_id",
    "opportunity": "opp_additional_field_id",
    "supplier": "supplier_additional_field_id",
    "personal_account": "personal_account_additional_field_id",
    "task": "task_additional_field_id",
}

# Known dead/junk additional fields (normalised). These either duplicate a
# concept already covered by a standard field or were never part of any form.
JUNK_DENYLIST = {
    "passport number", "passport_number", "passport",
    "combined source", "combined_source",
    "source medium", "source_medium",
}


def _normalise(s) -> str:
    """Lowercase, trim, and drop the legacy 'account '/'person account ' prefix."""
    s = (s or "").strip().lower()
    for pre in ("person account ", "account "):
        if s.startswith(pre):
            s = s[len(pre):]
            break
    return s


def _standard_tokens(entity_type: str) -> set:
    """Normalised field_key + label tokens for an entity's STANDARD fields."""
    tokens = set()
    for field_key, label, *_rest in DEFAULT_STANDARD_FIELDS.get(entity_type, []):
        tokens.add(_normalise(field_key))
        tokens.add(_normalise(label))
    return tokens


def _stale_reason(doc: dict, std_tokens: set):
    """Return a human reason string if the doc is stale, else None."""
    candidates = {
        _normalise(doc.get("field_key")),
        _normalise(doc.get("name")),
        _normalise(doc.get("label")),
    }
    candidates.discard("")
    if candidates & JUNK_DENYLIST:
        return "junk denylist"
    if candidates & std_tokens:
        return "duplicates a standard field"
    return None


async def main():
    parser = argparse.ArgumentParser(description="Delete stale additional fields from field_registry.")
    parser.add_argument("--apply", action="store_true", help="Actually delete (default: dry run).")
    parser.add_argument("--tenant", help="Scope to a single tenant_id.")
    parser.add_argument("--entity", help="Scope to a single entity_type (e.g. lead).")
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

    mode = "APPLY (deleting)" if args.apply else "DRY RUN (no changes)"
    print(f"Connecting to {db_name} ...  [{mode}]")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    registry = db["field_registry"]
    values = db["custom_field_values"]

    entities = [args.entity] if args.entity else list(FIELD_FK_BY_ENTITY.keys())

    # Base query: additional (custom) fields only. StandardField rows are written
    # with is_custom=False explicitly, so `$ne: False` excludes them while still
    # catching legacy custom docs that omit the flag.
    base_query: dict = {"is_custom": {"$ne": False}}
    if args.tenant:
        base_query["tenant_id"] = ObjectId(args.tenant)

    total_fields = 0
    total_values = 0

    for entity_type in entities:
        if entity_type not in FIELD_FK_BY_ENTITY:
            print(f"  [skip] unknown entity_type: {entity_type}")
            continue
        std_tokens = _standard_tokens(entity_type)
        field_fk = FIELD_FK_BY_ENTITY[entity_type]

        cursor = registry.find({**base_query, "entity_type": entity_type})
        stale = []
        async for doc in cursor:
            reason = _stale_reason(doc, std_tokens)
            if reason:
                stale.append((doc, reason))

        if not stale:
            continue

        print(f"\n[{entity_type}] {len(stale)} stale additional field(s):")
        for doc, reason in stale:
            label = doc.get("label") or doc.get("name") or "(unnamed)"
            fid = doc.get("_id")
            tid = doc.get("tenant_id")
            n_vals = await values.count_documents({field_fk: fid})
            print(f"  - {label!r:30}  key={doc.get('field_key')!r:20}  "
                  f"tenant={tid}  values={n_vals}  [{reason}]")
            total_fields += 1
            total_values += n_vals

            if args.apply:
                # Tenant-scoped value cascade — never touch another tenant's rows.
                val_q = {field_fk: fid}
                if tid is not None:
                    val_q["tenant_id"] = tid
                await values.delete_many(val_q)
                await registry.delete_one({"_id": fid})

    print(f"\n{'Deleted' if args.apply else 'Would delete'}: "
          f"{total_fields} field(s) + {total_values} value(s).")
    if not args.apply and total_fields:
        print("Re-run with --apply to perform the deletion.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
