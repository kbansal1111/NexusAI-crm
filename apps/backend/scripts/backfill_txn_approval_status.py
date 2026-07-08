"""One-time backfill: mark PRE-WORKFLOW opportunity transactions as approved.

Transactions created before the sales→accounts approval workflow have no
``approval_status`` field in MongoDB. Beanie then loads them with the model
default (``pending_verification``), which would retroactively flag every
historical ledger row — and every historical payment-schedule receipt — as
awaiting verification after deploy.

This script stamps ``approval_status="approved"`` ONLY on documents where the
field does not exist yet, matching the workflow's documented intent that
legacy rows are treated as approved. Safe to re-run (idempotent).

Usage:
  cd apps/backend
  python scripts/backfill_txn_approval_status.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings


async def main():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    coll = db["opportunity_transactions"]

    missing = await coll.count_documents({"approval_status": {"$exists": False}})
    print(f"Transactions without approval_status: {missing}")
    if missing:
        result = await coll.update_many(
            {"approval_status": {"$exists": False}},
            {"$set": {"approval_status": "approved"}},
        )
        print(f"Backfilled {result.modified_count} legacy transactions as approved.")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
