"""
Reconcile BD territory data after collapsing "Territory Manager" and "BD owner"
into a single role (one manager per territory).

BACKGROUND
    Territory-scoped opportunity visibility is now computed from the Territory
    document: a user sees a territory's opportunities iff they are its
    `manager_id`. "Territory Manager" and "BD owner" are the same person; the old
    round-robin BD-user pool (`Territory.users[]`) and the separate
    `Opportunity.bd_owner_id` were removed.

WHAT THIS SCRIPT DOES (idempotent)
    1. Territories: coerce `manager_id` to ObjectId. If a territory has no manager
       but has legacy pooled `users[]`, PROMOTE the first pooled user to manager
       (best effort) so access isn't silently lost. Then `$unset users`.
    2. Users: rebuild the `territory_ids` mirror from `Territory.manager_id`
       (territories the user now manages) and flag managers `is_bd_user`.
    3. `$unset` dead BD fields removed from the models: opportunities'
       `bd_owner_id`/`reporting_manager_id`, and the whole vestigial territory
       block on accounts + contacts (they never held live territory data).

    Territories left without a manager are reported so an admin can assign one.

DRY-RUN by default — prints what WOULD change. Pass --apply to write.

Usage (from apps/backend):
    python scripts/reconcile_bd_territory_membership.py                # dry run
    python scripts/reconcile_bd_territory_membership.py --apply        # write
    python scripts/reconcile_bd_territory_membership.py --tenant <id>  # one tenant
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient


def _as_oid(value):
    """Coerce a str/ObjectId to ObjectId, or None if it isn't a valid id."""
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


async def main():
    parser = argparse.ArgumentParser(description="Reconcile BD territory manager assignment + mirror.")
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
    tq: dict = {}
    if tenant_oid:
        tq["tenant_id"] = tenant_oid

    territories = db["territories"]
    users = db["users"]
    opportunities = db["opportunities"]

    normalized_terr = 0
    promoted = 0
    no_manager = 0
    # user_id -> set(territory_id) built from the (normalized) managers
    mirror: dict = {}

    async for t in territories.find(tq):
        tid = t["_id"]
        raw_mgr = t.get("manager_id")
        raw_users = t.get("users") or []
        has_users_field = "users" in t

        manager = _as_oid(raw_mgr)
        # Promote a pooled user to manager if there's no manager set.
        if manager is None and raw_users:
            manager = _as_oid(raw_users[0])
            if manager is not None:
                promoted += 1

        set_ops = {}
        unset_ops = {}
        if manager != raw_mgr:
            set_ops["manager_id"] = manager
        if has_users_field:
            unset_ops["users"] = ""

        if set_ops or unset_ops:
            normalized_terr += 1
            print(f"  [territory] {t.get('name') or tid!r:24} tenant={t.get('tenant_id')} "
                  f"manager={manager} drop_users={has_users_field}")
            if args.apply:
                update: dict = {}
                if set_ops:
                    update["$set"] = set_ops
                if unset_ops:
                    update["$unset"] = unset_ops
                await territories.update_one({"_id": tid}, update)

        if manager is None:
            no_manager += 1
            print(f"  [WARN] territory {t.get('name') or tid!r} has NO manager — assign one.")
        else:
            mirror.setdefault(manager, set()).add(tid)

    # Rebuild users.territory_ids from managed territories; flag managers BD.
    uq: dict = dict(tq)
    mirror_changes = 0
    async for u in users.find(uq):
        uid = u["_id"]
        want = mirror.get(uid, set())
        have = {_as_oid(x) for x in (u.get("territory_ids") or [])} - {None}
        set_ops = {}
        if want != have:
            set_ops["territory_ids"] = list(want)
        # Only turn the flag ON for managers; never force it off.
        if want and not u.get("is_bd_user"):
            set_ops["is_bd_user"] = True
        if set_ops:
            mirror_changes += 1
            print(f"  [user] {u.get('email') or uid!r:30} tenant={u.get('tenant_id')} "
                  f"territories {sorted(map(str, have))} -> {sorted(map(str, want))}")
            if args.apply:
                await users.update_one({"_id": uid}, {"$set": set_ops})

    # Drop dead BD fields that were removed from the models. Opportunities keep
    # territory_id/region_id/territory_match_source/territory_assigned_at; the
    # per-deal bd_owner_id/reporting_manager_id are gone (manager resolved live).
    # Accounts/contacts never had live territory data — drop the whole vestigial
    # block.
    dead_by_coll = {
        "opportunities": ["bd_owner_id", "reporting_manager_id"],
        "accounts": [
            "territory_state_id", "territory_country_id", "territory_id", "region_id",
            "bd_owner_id", "reporting_manager_id", "territory_match_source",
            "territory_assigned_at",
        ],
        "contacts": [
            "territory_id", "region_id", "bd_owner_id", "reporting_manager_id",
            "territory_match_source", "territory_assigned_at",
        ],
    }
    dead_counts: dict = {}
    for coll_name, fields in dead_by_coll.items():
        coll = db[coll_name]
        cq: dict = dict(tq)
        cq["$or"] = [{f: {"$exists": True}} for f in fields]
        n = await coll.count_documents(cq)
        dead_counts[coll_name] = n
        if n:
            print(f"  [{coll_name}] $unset {len(fields)} dead BD field(s) on {n} doc(s)")
            if args.apply:
                await coll.update_many(cq, {"$unset": {f: "" for f in fields}})

    print(f"\nTerritories normalized:            {normalized_terr}")
    print(f"  of which pooled-user promoted:   {promoted}")
    print(f"  territories still without mgr:   {no_manager}")
    print(f"Users needing mirror reconcile:    {mirror_changes}")
    for coll_name, n in dead_counts.items():
        print(f"{coll_name} with dead BD fields:  {n}")
    if not args.apply and (normalized_terr or mirror_changes or any(dead_counts.values())):
        print("Re-run with --apply to write.")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
