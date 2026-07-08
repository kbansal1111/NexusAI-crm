"""
Drop the dead MongoDB collections left behind by the removed BD field-ops
feature (visits, GPS tracking, expenses, automation rules).

These collections are no longer registered as Beanie documents and no code
reads or writes them. Dropping them frees headroom against the Atlas
500-collection cap.

DRY-RUN by default — lists collections + document counts. Pass --apply to drop.

Usage:
    cd apps/backend
    python scripts/drop_bd_field_ops_collections.py            # dry run
    python scripts/drop_bd_field_ops_collections.py --apply    # drop them
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient

DEAD_COLLECTIONS = [
    "bd_visits",
    "bd_visit_routes",
    "location_pings",
    "expenses",
    "automation_rules",
]


async def main():
    parser = argparse.ArgumentParser(description="Drop dead BD field-ops collections.")
    parser.add_argument("--apply", action="store_true", help="Actually drop (default: dry run).")
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

    mode = "APPLY (dropping)" if args.apply else "DRY RUN (no changes)"
    print(f"Connecting to {db_name} ...  [{mode}]")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    existing = set(await db.list_collection_names())
    dropped = 0
    for name in DEAD_COLLECTIONS:
        if name not in existing:
            print(f"  [skip] {name} — not present")
            continue
        count = await db[name].estimated_document_count()
        print(f"  [{'drop' if args.apply else 'would drop'}] {name} ({count} docs)")
        if args.apply:
            await db.drop_collection(name)
            dropped += 1

    if args.apply:
        print(f"\nDropped {dropped} collection(s).")
    else:
        print("\nRe-run with --apply to drop.")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
