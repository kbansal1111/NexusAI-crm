"""
Reconcile `segment` with account structure on ACCOUNTS and OPPORTUNITIES.

A person account is B2C; a company account is B2B (or CORPORATE, preserved).
Records could drift out of this invariant two ways, both fixed in code now:

  1. Lead conversion copied the lead's guessed segment (B2C, inferred from a
     public email domain) onto a *company* account — lead_service.convert_lead.
  2. Opportunity.segment defaulted to "B2C" at the model AND schema level, so
     every UI-created opportunity stored B2C regardless of its account. That
     truthy default also pre-empted the API's read-path fallback, which had
     been deriving the right value all along but never got the chance.

Complements scripts/backfill_account_segment.py, which handles accounts only
and additionally infers CORPORATE from linked opportunities. This script uses
Segment.reconcile_with_account_type — the same helper the application calls —
so a backfilled row is byte-identical to a freshly-created one.

Writes with a bare $set, deliberately: it does NOT touch updated_at, so a data
correction doesn't masquerade as a user edit and reshuffle "Recently Viewed"
or any recently-updated ordering.

Idempotent. Dry-run by default:

    python scripts/backfill_segment_consistency.py            # report only
    python scripts/backfill_segment_consistency.py --apply    # write
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

from app.core.segment_constants import Segment  # noqa: E402

MONGO_URL = os.getenv("MONGODB_URL", os.getenv("MONGO_URL", "mongodb://localhost:27017"))
DB_NAME = os.getenv("MONGODB_DB_NAME", os.getenv("MONGO_DB", "tutterfly"))


async def run(apply: bool) -> int:
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=15000)
    db = client[DB_NAME]

    host = MONGO_URL.split("@")[-1].split("/")[0]
    print(f"cluster : {host}")
    print(f"database: {DB_NAME}")
    print(f"mode    : {'APPLY (writing)' if apply else 'DRY RUN (no writes)'}\n")

    # Every account, including deleted ones — a deleted account is still the
    # authority for whether its opportunities are B2C or B2B.
    accounts = {a["_id"]: a async for a in db.accounts.find({})}

    acc_changed = opp_changed = 0

    print("=== ACCOUNTS ===")
    for acc in accounts.values():
        if acc.get("deleted_at"):
            continue
        current = acc.get("segment")
        wanted = Segment.reconcile_with_account_type(
            current, bool(acc.get("is_person_account"))
        )
        if current == wanted:
            print(f"  ok     {acc.get('name')!r}: {current!r}")
            continue
        acc_changed += 1
        print(f"  CHANGE {acc.get('name')!r}: {current!r} -> {wanted!r}")
        if apply:
            await db.accounts.update_one({"_id": acc["_id"]}, {"$set": {"segment": wanted}})

    print("\n=== OPPORTUNITIES ===")
    async for opp in db.opportunities.find({}):
        if opp.get("deleted_at"):
            continue
        acc = accounts.get(opp.get("account_id"))
        if not acc:
            print(f"  SKIP   {opp.get('name')!r}: linked account not found")
            continue
        current = opp.get("segment")
        wanted = Segment.reconcile_with_account_type(
            current, bool(acc.get("is_person_account"))
        )
        if current == wanted:
            print(f"  ok     {opp.get('name')!r}: {current!r}")
            continue
        opp_changed += 1
        kind = "person" if acc.get("is_person_account") else "company"
        print(
            f"  CHANGE {opp.get('name')!r}: {current!r} -> {wanted!r}"
            f"   (account {acc.get('name')!r} is {kind})"
        )
        if apply:
            await db.opportunities.update_one({"_id": opp["_id"]}, {"$set": {"segment": wanted}})

    verb = "UPDATED" if apply else "WOULD UPDATE"
    print(f"\n{verb}: {acc_changed} account(s), {opp_changed} opportunity(ies).")
    if not apply and (acc_changed or opp_changed):
        print("Nothing written. Re-run with --apply to commit.")

    client.close()
    return acc_changed + opp_changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit changes (default: dry run)")
    asyncio.run(run(parser.parse_args().apply))
