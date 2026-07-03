"""
AI Assistant — confirmed write actions (Phase 2).

The model never writes directly. A write flows in two halves:

  propose_action(...)   — called from a tool. Checks the user's OWN RBAC
                          permission, validates + freezes the args, builds a
                          human-readable summary, and queues an AssistantAction
                          (single-use, expiring). The model only ever gets
                          {"status": "pending_confirmation", ...} back.

  execute_action(...)   — called ONLY from the authenticated confirm endpoint
                          (POST /assistant/actions/{id}/confirm), i.e. by an
                          explicit user click. Re-checks permission and executes
                          exactly the frozen args.

Both halves are tenant-bound to `current_user`; validation re-fetches every
referenced record tenant- AND visibility-scoped.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple

from app.models.assistant import AssistantAction
from app.models.user import User
from app.services.assistant_tools import _get_visible_opp_or_error, _parse_date

ACTION_TTL_MINUTES = 15

VALID_PRIORITIES = ("Low", "Normal", "High", "Urgent")

# Opportunity fields the assistant may change, with per-field validation.
_UPDATABLE_OPP_FIELDS = ("name", "amount", "probability", "close_date", "sales_stage_id", "description")


# ─────────────────────────── Validators (propose time) ─────────────────────────
# Each returns (frozen_args, summary) or raises ValueError with a user-safe message.

async def _validate_update_opportunity(args: Dict[str, Any], current_user: User) -> Tuple[Dict[str, Any], str]:
    opp, err = await _get_visible_opp_or_error(str(args.get("opportunity_id", "")), current_user)
    if err:
        raise ValueError(err)
    if getattr(opp, "is_locked", False):
        raise ValueError("This opportunity is locked and cannot be edited.")

    frozen: Dict[str, Any] = {"opportunity_id": str(opp.id)}
    changes: list[str] = []

    if args.get("name") is not None:
        name = str(args["name"]).strip()
        if not (1 <= len(name) <= 300):
            raise ValueError("Name must be 1–300 characters.")
        frozen["name"] = name
        changes.append(f"name → '{name}'")

    if args.get("amount") is not None:
        amount = float(args["amount"])
        if amount < 0:
            raise ValueError("Amount cannot be negative.")
        frozen["amount"] = amount
        changes.append(f"amount {opp.amount if opp.amount is not None else '—'} → {amount}")

    if args.get("probability") is not None:
        prob = int(args["probability"])
        if not 0 <= prob <= 100:
            raise ValueError("Probability must be 0–100.")
        frozen["probability"] = prob
        changes.append(f"probability {opp.probability}% → {prob}%")

    if args.get("close_date") is not None:
        d = _parse_date(str(args["close_date"]))
        if d is None:
            raise ValueError("close_date must be an ISO date (YYYY-MM-DD).")
        frozen["close_date"] = d.isoformat()
        changes.append(f"close date → {d.date().isoformat()}")

    if args.get("sales_stage_id") is not None:
        from bson import ObjectId
        from app.models.opportunity_picklists import SalesStage
        try:
            sid = ObjectId(str(args["sales_stage_id"]))
        except Exception:
            raise ValueError("Invalid sales_stage_id.")
        stage = await SalesStage.find_one({"_id": sid, "tenant_id": current_user.tenant_id})
        if not stage:
            raise ValueError("Sales stage not found for this tenant.")
        frozen["sales_stage_id"] = str(sid)
        changes.append(f"stage → '{stage.name}'")

    if args.get("description") is not None:
        desc = str(args["description"])[:5000]
        frozen["description"] = desc
        changes.append("description updated")

    if not changes:
        raise ValueError("No updatable fields were provided.")
    return frozen, f"Update opportunity '{opp.name}': " + "; ".join(changes)


async def _validate_create_task(args: Dict[str, Any], current_user: User) -> Tuple[Dict[str, Any], str]:
    name = str(args.get("name") or "").strip()
    if not (1 <= len(name) <= 300):
        raise ValueError("Task name is required (1–300 characters).")

    frozen: Dict[str, Any] = {"name": name}
    parts = [f"Create task '{name}'"]

    if args.get("description"):
        frozen["description"] = str(args["description"])[:5000]

    if args.get("due_date"):
        d = _parse_date(str(args["due_date"]))
        if d is None:
            raise ValueError("due_date must be an ISO date (YYYY-MM-DD).")
        frozen["due_date"] = d.isoformat()
        parts.append(f"due {d.date().isoformat()}")

    priority = str(args.get("priority") or "Normal")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {VALID_PRIORITIES}.")
    frozen["priority"] = priority

    if args.get("opportunity_id"):
        opp, err = await _get_visible_opp_or_error(str(args["opportunity_id"]), current_user)
        if err:
            raise ValueError(err)
        frozen["opportunity_id"] = str(opp.id)
        parts.append(f"on opportunity '{opp.name}'")

    return frozen, ", ".join(parts)


async def _validate_create_note(args: Dict[str, Any], current_user: User) -> Tuple[Dict[str, Any], str]:
    content = str(args.get("content") or "").strip()
    if not (1 <= len(content) <= 10000):
        raise ValueError("Note content is required (1–10000 characters).")

    opp, err = await _get_visible_opp_or_error(str(args.get("opportunity_id", "")), current_user)
    if err:
        raise ValueError(err)

    frozen: Dict[str, Any] = {"content": content, "opportunity_id": str(opp.id)}
    if args.get("title"):
        frozen["title"] = str(args["title"])[:300]
    return frozen, f"Add a note to opportunity '{opp.name}'"


# ─────────────────────────── Executors (confirm time) ──────────────────────────

async def _execute_update_opportunity(action: AssistantAction, current_user: User) -> Dict[str, Any]:
    args = action.args
    opp, err = await _get_visible_opp_or_error(args["opportunity_id"], current_user)
    if err:
        raise ValueError(err)
    if getattr(opp, "is_locked", False):
        raise ValueError("This opportunity is locked and cannot be edited.")

    from bson import ObjectId
    for field in _UPDATABLE_OPP_FIELDS:
        if field not in args:
            continue
        value = args[field]
        if field == "sales_stage_id":
            value = ObjectId(value)
        elif field == "close_date":
            value = datetime.fromisoformat(value)
        setattr(opp, field, value)
    opp.last_modified_by_id = current_user.id
    await opp.save()
    return {"opportunity_id": str(opp.id), "name": opp.name, "message": "Opportunity updated."}


async def _execute_create_task(action: AssistantAction, current_user: User) -> Dict[str, Any]:
    from bson import ObjectId
    from app.models.task import Task

    args = action.args
    task = Task(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        owner_id=current_user.id,
        assigned_user_id=current_user.id,
        name=args["name"],
        description=args.get("description"),
        due_date=datetime.fromisoformat(args["due_date"]) if args.get("due_date") else None,
        priority=args.get("priority", "Normal"),
        taskable_type="Opportunity" if args.get("opportunity_id") else None,
        taskable_id=ObjectId(args["opportunity_id"]) if args.get("opportunity_id") else None,
    )
    await task.insert()
    return {"task_id": str(task.id), "name": task.name, "message": "Task created."}


async def _execute_create_note(action: AssistantAction, current_user: User) -> Dict[str, Any]:
    from bson import ObjectId
    from app.models.note import Note

    args = action.args
    note = Note(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        owner_id=current_user.id,
        title=args.get("title"),
        content=args["content"],
        noteable_type="Opportunity",
        noteable_id=ObjectId(args["opportunity_id"]),
    )
    await note.insert()
    return {"note_id": str(note.id), "message": "Note added."}


# ─────────────────────────── Registry + public API ─────────────────────────────

_ACTIONS: Dict[str, Dict[str, Any]] = {
    "update_opportunity": {
        "permission": "edit_opportunity",
        "validate": _validate_update_opportunity,
        "execute": _execute_update_opportunity,
    },
    "create_task": {
        "permission": "create_task",
        "validate": _validate_create_task,
        "execute": _execute_create_task,
    },
    "create_note": {
        "permission": "create_note",
        "validate": _validate_create_note,
        "execute": _execute_create_note,
    },
}


async def propose_action(
    action_type: str,
    args: Dict[str, Any],
    current_user: User,
    conversation_id,
) -> Dict[str, Any]:
    """Validate + queue a write for user confirmation. Returns the tool result."""
    spec = _ACTIONS.get(action_type)
    if spec is None:
        return {"error": f"Unknown action: {action_type}"}

    if not await current_user.has_permission(spec["permission"]):
        return {"error": f"You don't have the '{spec['permission']}' permission, so this change isn't possible."}

    try:
        frozen, summary = await spec["validate"](args or {}, current_user)
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception:
        return {"error": "Could not validate that change."}

    action = AssistantAction(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        conversation_id=conversation_id,
        action_type=action_type,
        args=frozen,
        summary=summary,
        permission=spec["permission"],
        expires_at=datetime.utcnow() + timedelta(minutes=ACTION_TTL_MINUTES),
    )
    await action.insert()

    return {
        "status": "pending_confirmation",
        "action_id": str(action.id),
        "summary": summary,
        "note": (
            "The change is QUEUED, not applied. A confirmation card was shown to the "
            "user — tell them to press Approve to apply it (or Cancel). Do not claim "
            "the change happened."
        ),
    }


async def execute_action(action: AssistantAction, current_user: User) -> Dict[str, Any]:
    """Run a confirmed action. Caller (the confirm endpoint) owns status checks."""
    spec = _ACTIONS.get(action.action_type)
    if spec is None:
        raise ValueError("Unknown action type.")
    # Re-check permission at execute time — roles may have changed since propose.
    if not await current_user.has_permission(spec["permission"]):
        raise ValueError(f"Missing permission: {spec['permission']}")
    return await spec["execute"](action, current_user)
