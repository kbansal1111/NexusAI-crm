"""
Grant old-CRM parity permissions to existing Role documents.

The permission registry (app/services/role_service.py) gained new permissions
to match the old CRM's matrix, and endpoints now ENFORCE them:

  upload_account / download_account        -> account CSV import / export
  upload_contact / download_contact        -> contact CSV import / export
  upload_lead / download_lead              -> lead CSV import / export
  upload_opportunity / download_opportunity-> opportunity import / export
  view/create/edit/delete_file_folder      -> file folder CRUD
  export_report                            -> report data export
  owner_change_opportunity                 -> opportunity change-owner
  lock_opportunity                         -> opportunity lock (now enforced)

Without this migration, existing roles would 403 on flows they could use
yesterday (import was gated by create_X, export by view_X, folders/report
export had no gate). Each derived permission is granted only to roles that
hold the permission that previously gated (or implied) the ability, so
day-one behavior is unchanged — admins can then untick checkboxes in
Profiles & Permissions to tighten to the old CRM matrix.

The legacy bare "owner_change" string (if still stored anywhere) is renamed
to owner_change_opportunity, and owner_change_opportunity is derived from
edit_opportunity (the permission that gated change-owner until now).
lock_opportunity is not auto-granted — roles already carry it where the
client intended; enforcement just makes that checkbox effective.

DRY-RUN by default — prints what WOULD change. Pass --apply to write.

Usage:
    cd apps/backend
    python scripts/grant_parity_permissions.py                 # dry run, all tenants
    python scripts/grant_parity_permissions.py --apply         # write, all tenants
    python scripts/grant_parity_permissions.py --tenant <id>   # scope to one tenant
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

# (source permission the role already has) -> (new permission to grant)
PARITY_DERIVED = [
    ("create_account", "upload_account"),
    ("view_account", "download_account"),
    ("create_contact", "upload_contact"),
    ("view_contact", "download_contact"),
    ("create_lead", "upload_lead"),
    ("view_lead", "download_lead"),
    ("create_opportunity", "upload_opportunity"),
    ("view_opportunity", "download_opportunity"),
    ("view_file", "view_file_folder"),
    ("upload_file", "create_file_folder"),
    ("upload_file", "edit_file_folder"),
    ("delete_file", "delete_file_folder"),
    ("view_report", "export_report"),
    # Change-owner was gated by edit_opportunity until now, and no stored role
    # carries the legacy bare "owner_change" string — derive from edit so no
    # role loses the ability at cutover. lock_opportunity is NOT derived: roles
    # already carry it where intended; enforcement just makes it real.
    ("edit_opportunity", "owner_change_opportunity"),
]

PARITY_RENAMES = {"owner_change": "owner_change_opportunity"}


def compute_new_perms(perms: list) -> list:
    out = set(perms)
    for old, new in PARITY_RENAMES.items():
        if old in out:
            out.discard(old)
            out.add(new)
    for source, derived in PARITY_DERIVED:
        if source in out:
            out.add(derived)
    return sorted(out)


async def main():
    parser = argparse.ArgumentParser(description="Grant old-CRM parity permissions to roles.")
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

    q: dict = {"deleted_at": None}
    if args.tenant:
        q["tenant_id"] = ObjectId(args.tenant)

    roles = db["roles"]
    changed = 0
    async for role in roles.find(q):
        current = role.get("permissions") or []
        updated = compute_new_perms(current)
        added = sorted(set(updated) - set(current))
        removed = sorted(set(current) - set(updated))
        if not added and not removed:
            continue
        changed += 1
        name = role.get("display_name") or role.get("name") or str(role["_id"])
        print(f"  [role] {name:30} tenant={role.get('tenant_id')}")
        if added:
            print(f"      + {', '.join(added)}")
        if removed:
            print(f"      - {', '.join(removed)}")
        if args.apply:
            await roles.update_one(
                {"_id": role["_id"]},
                {"$set": {"permissions": updated}},
            )

    print(f"\n{changed} role(s) {'updated' if args.apply else 'would change'}.")
    if not args.apply and changed:
        print("Re-run with --apply to write.")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
