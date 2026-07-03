"""
AI Assistant — read-only tool surface (Phase 1: Opportunities).

Every tool here is a thin wrapper over existing tenant-scoped services. The
security contract:

  * `dispatch_tool` is the ONLY entry point, and it always receives the
    authenticated `current_user`. Tenant id is re-derived from it — the model
    can never name a tenant, owner set, or visibility scope.
  * Reads are visibility-scoped via `get_visible_owner_ids`, identical to the
    REST list endpoints.
  * There are NO write tools in this module. Phase 1 is read-only by design.

Tool schemas use the OpenAI function-calling shape (we call the LLM through
OpenRouter, an OpenAI-compatible gateway).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.models.account import Account
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.opportunity_financial import (
    OpportunityCosting, OpportunityTransaction, PaymentScheduleItem,
)
from app.models.user import User
from app.services.visibility_scope import apply_visibility_filter, get_visible_owner_ids

MAX_SEARCH_RESULTS = 25

# ─────────────────────────── Tool schemas (OpenAI shape) ───────────────────────

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_opportunities",
            "description": (
                "Search the user's opportunities. Call this whenever the user asks to find, "
                "list, or count deals/opportunities — by name, account, stage, destination, "
                "amount range, or close date. Returns up to 25 matches. Use resolve_picklist "
                "first to turn a stage or destination NAME into its id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_text": {"type": "string", "description": "Free text matched against opportunity name and account name."},
                    "sales_stage_id": {"type": "string", "description": "Stage id from resolve_picklist(sales_stage)."},
                    "destination_id": {"type": "string", "description": "Destination picklist id from resolve_picklist(destination)."},
                    "min_amount": {"type": "number"},
                    "max_amount": {"type": "number"},
                    "close_after": {"type": "string", "description": "ISO date (YYYY-MM-DD); close_date on/after this."},
                    "close_before": {"type": "string", "description": "ISO date (YYYY-MM-DD); close_date on/before this."},
                    "limit": {"type": "integer", "description": "Max results, default 10, cap 25."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_opportunity",
            "description": (
                "Fetch full detail for ONE opportunity by its id (from a previous "
                "search_opportunities result). Call this when the user asks about a specific deal."
            ),
            "parameters": {
                "type": "object",
                "properties": {"opportunity_id": {"type": "string"}},
                "required": ["opportunity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_opportunity_financials",
            "description": (
                "Fetch the financial picture of one opportunity: costing totals (sell/cost/"
                "profit), payment schedule with received status, and received/paid/balance "
                "totals. Call this for questions about money, payments, dues, or profit on a deal."
            ),
            "parameters": {
                "type": "object",
                "properties": {"opportunity_id": {"type": "string"}},
                "required": ["opportunity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_opportunity_transactions",
            "description": (
                "List the ledger transactions (Receive/Pay/Refund) of one opportunity, "
                "including each transaction's approval status (pending_verification/verified/"
                "approved/rejected). Call this for questions about transactions or approvals on a deal."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {"type": "string"},
                    "approval_status": {
                        "type": "string",
                        "enum": ["pending_verification", "verified", "approved", "rejected"],
                        "description": "Optional filter.",
                    },
                },
                "required": ["opportunity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pipeline_summary",
            "description": (
                "Aggregate the user's visible pipeline: count and total amount grouped by "
                "stage, owner, or close month. Call this for questions like 'total pipeline', "
                "'deals per stage', 'how is each owner doing', 'revenue closing this quarter'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "group_by": {"type": "string", "enum": ["stage", "owner", "month"]},
                    "close_after": {"type": "string", "description": "ISO date lower bound on close_date."},
                    "close_before": {"type": "string", "description": "ISO date upper bound on close_date."},
                },
                "required": ["group_by"],
            },
        },
    },
    # ── Leads & Accounts (read-only — VIEW mode, no write proposals) ───────────
    {
        "type": "function",
        "function": {
            "name": "search_leads",
            "description": (
                "Search the user's leads. Call this when the user asks to find, list, or "
                "count leads — by name, email, company, city, status, or created date. "
                "Returns up to 25 matches. Use resolve_picklist(lead_status) for a status name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_text": {"type": "string", "description": "Matched against lead name, email, and company."},
                    "lead_status_id": {"type": "string", "description": "Status id from resolve_picklist(lead_status)."},
                    "city": {"type": "string"},
                    "is_converted": {"type": "boolean"},
                    "created_after": {"type": "string", "description": "ISO date (YYYY-MM-DD)."},
                    "created_before": {"type": "string", "description": "ISO date (YYYY-MM-DD)."},
                    "limit": {"type": "integer", "description": "Max results, default 10, cap 25."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lead",
            "description": "Fetch full detail for ONE lead by id (from search_leads). Read-only.",
            "parameters": {
                "type": "object",
                "properties": {"lead_id": {"type": "string"}},
                "required": ["lead_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_accounts",
            "description": (
                "Search the user's accounts (companies AND person accounts). Call this when "
                "the user asks to find, list, or count accounts/customers — by name, email, "
                "phone, city, or type. Returns up to 25 matches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_text": {"type": "string", "description": "Matched against account name, email, and phone."},
                    "is_person_account": {"type": "boolean", "description": "true = B2C person accounts, false = companies."},
                    "acc_type_id": {"type": "string", "description": "Type id from resolve_picklist(account_type)."},
                    "billing_city": {"type": "string"},
                    "limit": {"type": "integer", "description": "Max results, default 10, cap 25."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_account",
            "description": "Fetch full detail for ONE account by id (from search_accounts). Read-only.",
            "parameters": {
                "type": "object",
                "properties": {"account_id": {"type": "string"}},
                "required": ["account_id"],
            },
        },
    },
    # ── Write proposals (Phase 2) ──────────────────────────────────────────────
    # These tools NEVER write. They validate + queue a pending action that the
    # user must approve via a confirmation card in the chat UI.
    {
        "type": "function",
        "function": {
            "name": "propose_update_opportunity",
            "description": (
                "Propose changing fields on ONE opportunity (name, amount, probability, "
                "close date, stage, description). The change is NOT applied — the user gets "
                "a confirmation card and must press Approve. Call this when the user asks to "
                "change/update/move a deal. Use resolve_picklist first for a stage name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {"type": "string"},
                    "name": {"type": "string"},
                    "amount": {"type": "number"},
                    "probability": {"type": "integer", "description": "0–100"},
                    "close_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)."},
                    "sales_stage_id": {"type": "string", "description": "Stage id from resolve_picklist(sales_stage)."},
                    "description": {"type": "string"},
                },
                "required": ["opportunity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_create_task",
            "description": (
                "Propose creating a task (optionally linked to an opportunity), e.g. a "
                "follow-up or reminder. NOT applied until the user presses Approve on the "
                "confirmation card."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Task title."},
                    "description": {"type": "string"},
                    "due_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)."},
                    "priority": {"type": "string", "enum": ["Low", "Normal", "High", "Urgent"]},
                    "opportunity_id": {"type": "string", "description": "Optional opportunity to attach the task to."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_create_note",
            "description": (
                "Propose adding a note to an opportunity. NOT applied until the user presses "
                "Approve on the confirmation card."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "opportunity_id": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["opportunity_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_picklist",
            "description": (
                "Look up picklist options visible to this tenant — use it to translate a name "
                "the user said (e.g. destination 'Bali', stage 'Closed Won') into an id for "
                "search_opportunities, or to list the available options."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "picklist_type": {
                        "type": "string",
                        "enum": ["sales_stage", "destination", "source", "opportunity_type", "account_type", "lead_status"],
                    },
                    "name": {"type": "string", "description": "Optional case-insensitive name filter."},
                },
                "required": ["picklist_type"],
            },
        },
    },
]


# ─────────────────────────────── Helpers ───────────────────────────────────────

def _parse_date(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _opp_row(o: Opportunity) -> Dict[str, Any]:
    return {
        "id": str(o.id),
        "name": o.name,
        "account_name": o.account_name,
        "owner_name": o.owner_name,
        "amount": o.amount,
        "probability": o.probability,
        "expected_revenue": round(((o.amount or 0) * (o.probability or 0)) / 100, 2),
        "close_date": o.close_date.date().isoformat() if o.close_date else None,
        "sales_stage_id": str(o.sales_stage_id) if o.sales_stage_id else None,
    }


async def _base_query(current_user: User) -> Dict[str, Any]:
    """Tenant + soft-delete + visibility scope — applied to every read."""
    query: Dict[str, Any] = {"tenant_id": current_user.tenant_id, "deleted_at": None}
    visible = await get_visible_owner_ids(current_user)
    apply_visibility_filter(query, visible)
    return query


async def _stage_name_map(tenant_id) -> Dict[str, str]:
    from app.models.opportunity_picklists import SalesStage
    stages = await SalesStage.find({"tenant_id": tenant_id}).to_list()
    return {str(s.id): s.name for s in stages}


async def _get_visible_opp_or_error(opportunity_id: str, current_user: User):
    """Fetch one opportunity, tenant- AND visibility-scoped. Returns (opp, error)."""
    try:
        oid = ObjectId(opportunity_id)
    except Exception:
        return None, "Invalid opportunity id."
    query = await _base_query(current_user)
    query["_id"] = oid
    opp = await Opportunity.find_one(query)
    if not opp:
        return None, "Opportunity not found."
    return opp, None


# ─────────────────────────────── Tool implementations ─────────────────────────

async def _search_opportunities(args: Dict[str, Any], current_user: User) -> Any:
    query = await _base_query(current_user)

    text = (args.get("query_text") or "").strip()
    if text:
        rx = {"$regex": re.escape(text), "$options": "i"}
        query["$or"] = [{"name": rx}, {"account_name": rx}]

    for key, field in (("sales_stage_id", "sales_stage_id"),):
        if args.get(key):
            try:
                query[field] = ObjectId(str(args[key]))
            except Exception:
                return {"error": f"Invalid {key}."}

    if args.get("destination_id"):
        dest = str(args["destination_id"])
        vals: List[Any] = [dest]
        try:
            vals.append(ObjectId(dest))
        except Exception:
            pass
        query["industry_data.destination_ids"] = {"$in": vals}

    amount_cond: Dict[str, Any] = {}
    if args.get("min_amount") is not None:
        amount_cond["$gte"] = float(args["min_amount"])
    if args.get("max_amount") is not None:
        amount_cond["$lte"] = float(args["max_amount"])
    if amount_cond:
        query["amount"] = amount_cond

    close_cond: Dict[str, Any] = {}
    if (d := _parse_date(args.get("close_after"))):
        close_cond["$gte"] = d
    if (d := _parse_date(args.get("close_before"))):
        close_cond["$lte"] = d
    if close_cond:
        query["close_date"] = close_cond

    limit = min(int(args.get("limit") or 10), MAX_SEARCH_RESULTS)
    opps = await Opportunity.find(query).sort("-created_at").limit(limit).to_list()
    total = await Opportunity.find(query).count()

    stage_names = await _stage_name_map(current_user.tenant_id)
    rows = []
    for o in opps:
        row = _opp_row(o)
        row["stage"] = stage_names.get(row.pop("sales_stage_id") or "", None)
        rows.append(row)
    return {"total_matches": total, "returned": len(rows), "opportunities": rows}


async def _get_opportunity(args: Dict[str, Any], current_user: User) -> Any:
    opp, err = await _get_visible_opp_or_error(str(args.get("opportunity_id", "")), current_user)
    if err:
        return {"error": err}

    stage_names = await _stage_name_map(current_user.tenant_id)
    detail = _opp_row(opp)
    detail["stage"] = stage_names.get(detail.pop("sales_stage_id") or "", None)
    detail["description"] = opp.description
    detail["created_at"] = opp.created_at.date().isoformat() if opp.created_at else None

    ind = dict(opp.industry_data or {})
    # Resolve destination ids → names for readability (tenant-visible picklists).
    if ind.get("destination_ids"):
        from app.api.v1.opportunities import _resolve_destinations
        ind = await _resolve_destinations(ind)
        ind.pop("destination_ids", None)
    detail["industry_data"] = ind
    return detail


async def _get_opportunity_financials(args: Dict[str, Any], current_user: User) -> Any:
    opp, err = await _get_visible_opp_or_error(str(args.get("opportunity_id", "")), current_user)
    if err:
        return {"error": err}

    scoped = {"opportunity_id": opp.id, "tenant_id": current_user.tenant_id}

    costing = await OpportunityCosting.find_one(scoped)
    schedule = await PaymentScheduleItem.find(scoped).sort("+due_date").to_list()
    txns = await OpportunityTransaction.find(scoped).to_list()

    received = sum(t.amount for t in txns if t.transaction_type == "Receive")
    paid = sum(t.amount for t in txns if t.transaction_type == "Pay")
    refunded = sum(t.amount for t in txns if t.transaction_type == "Refund")

    return {
        "opportunity": {"id": str(opp.id), "name": opp.name, "amount": opp.amount},
        "costing": {
            "total_amount": costing.total_amount,
            "total_cost": costing.total_cost,
            "profit": costing.profit,
            "profit_percent": costing.profit_percent,
        } if costing else None,
        "payment_schedule": [
            {
                "description": i.description,
                "due_date": i.due_date.date().isoformat() if i.due_date else None,
                "amount": i.amount,
                "status": i.status,
            }
            for i in schedule
        ],
        "totals": {
            "received": received,
            "paid": paid,
            "refunded": refunded,
            "balance": (opp.amount or 0) - received + refunded,
        },
    }


async def _list_opportunity_transactions(args: Dict[str, Any], current_user: User) -> Any:
    opp, err = await _get_visible_opp_or_error(str(args.get("opportunity_id", "")), current_user)
    if err:
        return {"error": err}

    query: Dict[str, Any] = {"opportunity_id": opp.id, "tenant_id": current_user.tenant_id}
    if args.get("approval_status"):
        query["approval_status"] = str(args["approval_status"])

    txns = await OpportunityTransaction.find(query).sort("+created_at").to_list()
    return {
        "opportunity": {"id": str(opp.id), "name": opp.name},
        "transactions": [
            {
                "type": t.transaction_type,
                "amount": t.amount,
                "date": t.transaction_date.date().isoformat() if t.transaction_date else None,
                "payment_mode": t.payment_mode,
                "reference_id": t.reference_id,
                # Legacy rows (pre-approval-workflow) read as approved.
                "approval_status": getattr(t, "approval_status", None) or "approved",
            }
            for t in txns
        ],
    }


async def _pipeline_summary(args: Dict[str, Any], current_user: User) -> Any:
    query = await _base_query(current_user)
    close_cond: Dict[str, Any] = {}
    if (d := _parse_date(args.get("close_after"))):
        close_cond["$gte"] = d
    if (d := _parse_date(args.get("close_before"))):
        close_cond["$lte"] = d
    if close_cond:
        query["close_date"] = close_cond

    group_by = str(args.get("group_by") or "stage")
    key = {"stage": "$sales_stage_id", "owner": "$owner_name",
           "month": {"$dateToString": {"format": "%Y-%m", "date": "$close_date"}}}.get(group_by)
    if key is None:
        return {"error": "group_by must be stage, owner, or month."}

    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": key,
            "count": {"$sum": 1},
            "total_amount": {"$sum": {"$ifNull": ["$amount", 0]}},
            "expected_revenue": {"$sum": {"$divide": [
                {"$multiply": [{"$ifNull": ["$amount", 0]}, {"$ifNull": ["$probability", 0]}]}, 100]}},
        }},
        {"$sort": {"total_amount": -1}},
    ]
    rows = await Opportunity.aggregate(pipeline).to_list()

    if group_by == "stage":
        stage_names = await _stage_name_map(current_user.tenant_id)
        for r in rows:
            r["group"] = stage_names.get(str(r.pop("_id")), "Unknown stage")
    else:
        for r in rows:
            r["group"] = r.pop("_id") or "Unassigned"
    for r in rows:
        r["expected_revenue"] = round(r["expected_revenue"], 2)
    return {"group_by": group_by, "groups": rows}


async def _resolve_picklist(args: Dict[str, Any], current_user: User) -> Any:
    from app.core.picklist_query import build_picklist_query, dedup_picklist_items
    from app.models.consolidated_picklists import BasePicklist
    from app.services.industry_service import get_tenant_industry

    ptype = str(args.get("picklist_type") or "")
    if ptype not in ("sales_stage", "destination", "source", "opportunity_type", "account_type", "lead_status"):
        return {"error": "Unsupported picklist_type."}

    industry = await get_tenant_industry(current_user.tenant_id)
    query = build_picklist_query(current_user.tenant_id, industry=industry, picklist_type=ptype)
    if args.get("name"):
        query["name"] = {"$regex": re.escape(str(args["name"])), "$options": "i"}

    items = await BasePicklist.find(query).sort("+sorting").limit(100).to_list()
    items = dedup_picklist_items(items)
    return {"options": [{"id": str(i.id), "name": i.name} for i in items]}


# ─────────────────── Leads & Accounts (read-only) ──────────────────────────────

def _lead_row(l: Lead) -> Dict[str, Any]:
    return {
        "id": str(l.id),
        "name": f"{l.first_name} {l.last_name}".strip(),
        "email": l.email,
        "phone": l.phone,
        "company": l.company,
        "city": l.city,
        "owner_name": l.owner_name,
        "is_converted": l.is_converted,
        "created_at": l.created_at.date().isoformat() if l.created_at else None,
    }


async def _search_leads(args: Dict[str, Any], current_user: User) -> Any:
    query = await _base_query(current_user)

    text = (args.get("query_text") or "").strip()
    if text:
        rx = {"$regex": re.escape(text), "$options": "i"}
        query["$or"] = [{"first_name": rx}, {"last_name": rx}, {"email": rx}, {"company": rx}]

    if args.get("lead_status_id"):
        try:
            query["lead_status_id"] = ObjectId(str(args["lead_status_id"]))
        except Exception:
            return {"error": "Invalid lead_status_id."}
    if args.get("city"):
        query["city"] = {"$regex": re.escape(str(args["city"])), "$options": "i"}
    if args.get("is_converted") is not None:
        query["is_converted"] = bool(args["is_converted"])

    created_cond: Dict[str, Any] = {}
    if (d := _parse_date(args.get("created_after"))):
        created_cond["$gte"] = d
    if (d := _parse_date(args.get("created_before"))):
        created_cond["$lte"] = d
    if created_cond:
        query["created_at"] = created_cond

    limit = min(int(args.get("limit") or 10), MAX_SEARCH_RESULTS)
    leads = await Lead.find(query).sort("-created_at").limit(limit).to_list()
    total = await Lead.find(query).count()
    return {"total_matches": total, "returned": len(leads), "leads": [_lead_row(l) for l in leads]}


async def _get_lead(args: Dict[str, Any], current_user: User) -> Any:
    try:
        lid = ObjectId(str(args.get("lead_id", "")))
    except Exception:
        return {"error": "Invalid lead id."}
    query = await _base_query(current_user)
    query["_id"] = lid
    lead = await Lead.find_one(query)
    if not lead:
        return {"error": "Lead not found."}

    detail = _lead_row(lead)
    detail.update({
        "title": lead.title,
        "website": lead.website,
        "address": ", ".join(x for x in (lead.street, lead.city, lead.state, lead.country) if x) or None,
        "creation_type": lead.creation_type,
    })
    return detail


def _account_row(a: Account) -> Dict[str, Any]:
    return {
        "id": str(a.id),
        "name": a.name,
        "email": a.email,
        "phone": a.phone,
        "is_person_account": a.is_person_account,
        "segment": a.segment,
        "billing_city": a.billing_city,
        "owner_name": a.owner_name,
    }


async def _search_accounts(args: Dict[str, Any], current_user: User) -> Any:
    query = await _base_query(current_user)

    text = (args.get("query_text") or "").strip()
    if text:
        rx = {"$regex": re.escape(text), "$options": "i"}
        query["$or"] = [{"name": rx}, {"email": rx}, {"phone": rx}]

    if args.get("is_person_account") is not None:
        query["is_person_account"] = bool(args["is_person_account"])
    if args.get("acc_type_id"):
        try:
            query["acc_type_id"] = ObjectId(str(args["acc_type_id"]))
        except Exception:
            return {"error": "Invalid acc_type_id."}
    if args.get("billing_city"):
        query["billing_city"] = {"$regex": re.escape(str(args["billing_city"])), "$options": "i"}

    limit = min(int(args.get("limit") or 10), MAX_SEARCH_RESULTS)
    accounts = await Account.find(query).sort("-created_at").limit(limit).to_list()
    total = await Account.find(query).count()
    return {"total_matches": total, "returned": len(accounts),
            "accounts": [_account_row(a) for a in accounts]}


async def _get_account(args: Dict[str, Any], current_user: User) -> Any:
    try:
        aid = ObjectId(str(args.get("account_id", "")))
    except Exception:
        return {"error": "Invalid account id."}
    query = await _base_query(current_user)
    query["_id"] = aid
    account = await Account.find_one(query)
    if not account:
        return {"error": "Account not found."}

    detail = _account_row(account)
    detail.update({
        "website": account.website,
        "description": account.description,
        "billing_address": ", ".join(x for x in (
            account.billing_street, account.billing_city, account.billing_state,
            account.billing_zip, account.billing_country) if x) or None,
        "created_at": account.created_at.date().isoformat() if account.created_at else None,
    })
    return detail


_TOOL_IMPLS = {
    "search_opportunities": _search_opportunities,
    "get_opportunity": _get_opportunity,
    "get_opportunity_financials": _get_opportunity_financials,
    "list_opportunity_transactions": _list_opportunity_transactions,
    "pipeline_summary": _pipeline_summary,
    "resolve_picklist": _resolve_picklist,
    "search_leads": _search_leads,
    "get_lead": _get_lead,
    "search_accounts": _search_accounts,
    "get_account": _get_account,
}

# Per-tool view permission, enforced in dispatch_tool. The endpoint gate admits
# anyone with at least one CRM view permission; this map keeps a leads-only user
# from reading opportunities through the assistant (and vice versa). None means
# any user past the endpoint gate may call it (picklist names only).
_TOOL_PERMISSIONS: Dict[str, Optional[str]] = {
    "search_opportunities": "view_opportunity",
    "get_opportunity": "view_opportunity",
    "get_opportunity_financials": "view_opportunity",
    "list_opportunity_transactions": "view_opportunity",
    "pipeline_summary": "view_opportunity",
    "resolve_picklist": None,
    "search_leads": "view_lead",
    "get_lead": "view_lead",
    "search_accounts": "view_account",
    "get_account": "view_account",
}

# Write-proposal tools: mapped to action types in assistant_actions. They queue
# a pending action for user confirmation — they never write directly.
_PROPOSAL_TOOLS = {
    "propose_update_opportunity": "update_opportunity",
    "propose_create_task": "create_task",
    "propose_create_note": "create_note",
}


async def dispatch_tool(
    name: str, args: Dict[str, Any], current_user: User, conversation_id=None
) -> str:
    """Execute one tool call, tenant-bound to `current_user`. Returns a JSON string.

    Never raises: errors come back as {"error": ...} so the model can recover
    and the agent loop keeps streaming.
    """
    try:
        if name in _PROPOSAL_TOOLS:
            from app.services.assistant_actions import propose_action  # lazy: avoid circular import
            result = await propose_action(_PROPOSAL_TOOLS[name], args or {}, current_user, conversation_id)
        else:
            impl = _TOOL_IMPLS.get(name)
            if impl is None:
                return json.dumps({"error": f"Unknown tool: {name}"})
            # Per-entity RBAC: the endpoint gate admits any CRM viewer; each tool
            # additionally requires ITS entity's view permission.
            perm = _TOOL_PERMISSIONS.get(name)
            if perm and not await current_user.has_permission(perm):
                return json.dumps({"error": f"You don't have the '{perm}' permission for this data."})
            result = await impl(args or {}, current_user)
    except Exception as exc:  # noqa: BLE001 — surfaced to the model, logged by caller
        result = {"error": f"Tool failed: {type(exc).__name__}"}
    return json.dumps(result, default=str)
