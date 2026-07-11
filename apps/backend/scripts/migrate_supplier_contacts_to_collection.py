"""
Migrate embedded ``Supplier.contacts[]`` -> standalone ``supplier_contacts`` collection.

1->N model: each embedded contact becomes ONE ``supplier_contacts`` document
pointing at its parent supplier (``supplier_id``), inheriting ``tenant_id`` and
``owner_id`` from that supplier so it stays tenant-isolated and independently
owned/assignable.

SAFETY
------
* Dry-run by DEFAULT — prints a report and writes NOTHING. Pass ``--apply``.
* Idempotent: every migrated doc carries ``_migrated_embedded_id`` (the old
  embedded UUID). Re-runs skip contacts that were already migrated, so running
  it twice never duplicates.
* The embedded ``contacts`` arrays are LEFT IN PLACE (harmless dead data that
  the app no longer reads) so rollback is just reverting the code. A later
  cleanup script can ``$unset`` them once the collection is trusted.

Run from apps/backend:
    python scripts/migrate_supplier_contacts_to_collection.py            # dry-run
    python scripts/migrate_supplier_contacts_to_collection.py --apply     # migrate
"""
import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def main(apply: bool):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    cli = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=10000)
    db = cli[settings.MONGODB_DB_NAME]
    await cli.admin.command("ping")

    print("=" * 72)
    print(f"MIGRATE supplier contacts -> collection | DB={settings.MONGODB_DB_NAME} "
          f"| mode={'APPLY (writes!)' if apply else 'DRY-RUN (no writes)'}")
    print("=" * 72)

    suppliers_coll = db["suppliers"]
    contacts_coll = db["supplier_contacts"]

    # Idempotency: collect embedded UUIDs already migrated.
    migrated_ids = set()
    async for d in contacts_coll.find(
        {"_migrated_embedded_id": {"$ne": None}}, {"_migrated_embedded_id": 1}
    ):
        migrated_ids.add(d.get("_migrated_embedded_id"))
    print(f"Already-migrated embedded contacts: {len(migrated_ids)}")

    total_suppliers = 0
    total_embedded = 0
    to_insert = []
    async for s in suppliers_coll.find({"contacts.0": {"$exists": True}}):
        total_suppliers += 1
        sid = s["_id"]
        tenant_id = s.get("tenant_id")
        owner_id = s.get("owner_id")
        for c in (s.get("contacts") or []):
            total_embedded += 1
            emb_id = c.get("id")
            if emb_id and emb_id in migrated_ids:
                continue
            to_insert.append({
                "supplier_id": sid,
                "tenant_id": tenant_id,
                "owner_id": owner_id,
                "name": c.get("name") or "",
                "designation": c.get("designation"),
                "department": c.get("department"),
                "email": c.get("email"),
                "phone": c.get("phone"),
                "mobile": c.get("mobile"),
                "is_primary": bool(c.get("is_primary", False)),
                "notes": c.get("notes"),
                "created_at": c.get("created_at") or _now(),
                "updated_at": c.get("updated_at") or _now(),
                "deleted_at": None,
                "_migrated_embedded_id": emb_id,
            })

    skipped = total_embedded - len(to_insert)
    print(f"Suppliers with embedded contacts: {total_suppliers}")
    print(f"Embedded contacts found:          {total_embedded}")
    print(f"New docs to insert:               {len(to_insert)}  (already-migrated, skipped: {skipped})")

    if not apply:
        print("\n[DRY-RUN] no writes. Re-run with --apply to migrate.")
        for d in to_insert[:5]:
            print(f"   would insert: name={d['name']!r} primary={d['is_primary']} "
                  f"supplier={d['supplier_id']} tenant={d['tenant_id']}")
        cli.close()
        return

    if to_insert:
        res = await contacts_coll.insert_many(to_insert, ordered=False)
        print(f"\nInserted {len(res.inserted_ids)} supplier_contacts docs.")
    else:
        print("\nNothing to insert (all up to date).")

    print("supplier_contacts total now:", await contacts_coll.count_documents({}))
    cli.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write (default dry-run)")
    asyncio.run(main(apply=ap.parse_args().apply))
