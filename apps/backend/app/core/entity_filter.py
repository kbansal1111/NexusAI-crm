"""
Structured "Edit List Filters" → MongoDB query translator.

A saved EntityView stores `filter_rules`: an ordered list of
``{"field": <field_key>, "operator": <op>, "value": <value>}`` rows produced by
the frontend filter builder. This module turns those rows into Mongo clauses
that are ANDed into a list query's base filter (which always keeps tenant +
visibility scoping).

Security (multi-tenant): only field_keys present in the per-entity WHITELIST are
honored. Any unknown field OR unknown operator causes the row to be skipped, so
raw client-supplied keys can never be injected into the query.

v1 scope: filtering is restricted to whitelisted STANDARD fields. Custom /
additional fields can be chosen for *display* but their values live in separate
`*CustomField` collections and are not filterable here yet.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId


# ── Field whitelists ─────────────────────────────────────────────────────────
# field_key -> logical type. Types drive which operators are valid and how the
# value is coerced. account (B2B) and personal_account (B2C) are DISTINCT
# schemas even though both live in the `accounts` collection.
_ACCOUNT_FIELDS: Dict[str, str] = {
    "name": "string",
    "email": "string",
    "phone": "string",
    "website": "string",
    "segment": "string",
    "billing_street": "string",
    "billing_city": "string",
    "billing_state": "string",
    "billing_zip": "string",
    "billing_country": "string",
    "industry_id": "lookup",
    "acc_type_id": "lookup",
    "acc_parent_id": "lookup",
    "category_id": "lookup",
    "owner_id": "lookup",
    "created_by": "lookup",
    "last_modified_by_id": "lookup",
    "created_at": "date",
    "updated_at": "date",
    "id": "lookup",
    "is_favorite": "bool",
}

_PERSONAL_ACCOUNT_FIELDS: Dict[str, str] = {
    "salutation": "string",
    "first_name": "string",
    "last_name": "string",
    "email": "string",
    "phone": "string",
    "mobile": "string",  # B2C-only field (see CLAUDE.md)
    "segment": "string",
    "billing_street": "string",
    "billing_city": "string",
    "billing_state": "string",
    "billing_zip": "string",
    "billing_country": "string",
    "category_id": "lookup",
    "owner_id": "lookup",
    "created_by": "lookup",
    "last_modified_by_id": "lookup",
    "created_at": "date",
    "updated_at": "date",
    "id": "lookup",
    "is_favorite": "bool",
}

_CONTACT_FIELDS: Dict[str, str] = {
    "salutation": "string",
    "first_name": "string",
    "last_name": "string",
    "email": "string",
    "phone": "string",
    "mobile": "string",
    "title": "string",
    "account_id": "lookup",
    # Mailing address — mirrors the contact form's "Address Information" section.
    "mailing_street": "string",
    "mailing_city": "string",
    "mailing_state": "string",
    "mailing_zip": "string",
    "mailing_country": "string",
    "owner_id": "lookup",
    "created_by": "lookup",
    "last_modified_by_id": "lookup",
    "created_at": "date",
    "updated_at": "date",
    "id": "lookup",
}

_LEAD_FIELDS: Dict[str, str] = {
    "salutation": "string",
    "first_name": "string",
    "last_name": "string",
    "company": "string",
    "email": "string",
    "phone": "string",
    "mobile": "string",
    "no_employees": "number",
    "website": "string",
    "title": "string",
    "lead_status_id": "lookup",
    "source_id": "lookup",
    "industry_id": "lookup",
    "street": "string",
    "city": "string",
    "state": "string",
    "zip": "string",
    "country": "string",
    # Additional Information — stored in the lead's custom_fields dict.
    "custom_fields.campaign_name": "string",
    "custom_fields.segment": "string",   # stored as "B2C"/"B2B" — string match (UI: select)
    "custom_fields.experience_id": "strlookup",  # single id stored as a string
    "creation_type": "string",  # stored as "manual"/"auto" — string match (UI: select)
    # Travel industry_data fields (nested) — only meaningful for the travel industry.
    # Leads persist travel_date as an ISO string (TravelLeadData.travel_date: str).
    "industry_data.travel_date": "datestr",
    "industry_data.destination_ids": "strlookup",
    "industry_data.no_of_pax": "number",
    "industry_data.no_of_nights": "number",
    "industry_data.no_of_adults": "number",
    "industry_data.no_of_childs": "number",
    "industry_data.no_of_infants": "number",
    "owner_id": "lookup",
    "created_by": "lookup",
    "last_modified_by_id": "lookup",
    "created_at": "date",
    "updated_at": "date",
    "id": "lookup",
}

_OPPORTUNITY_FIELDS: Dict[str, str] = {
    "name": "string",
    "amount": "number",
    "probability": "number",
    "sales_stage_id": "lookup",
    "opportunity_type_id": "lookup",
    "source_id": "lookup",
    "account_id": "lookup",
    "contact_id": "lookup",
    "owner_id": "lookup",
    "segment": "string",
    "creation_type": "string",  # stored as "Manual"/"Auto"
    "created_by": "lookup",
    "last_modified_by_id": "lookup",
    "close_lost_reason": "string",
    "close_date": "date",
    # Opportunities persist travel_date as a BSON Date (TravelOpportunityData
    # .travel_date: datetime), but converted/migrated rows may hold a string —
    # so match either representation. (Leads, by contrast, are always strings.)
    "industry_data.travel_date": "datemixed",
    "industry_data.destination_ids": "strlookup",
    "industry_data.no_of_pax": "number",
    # Additional Information — stored in the opportunity's custom_fields dict.
    "custom_fields.starting_city": "string",
    "created_at": "date",
    "updated_at": "date",
    "id": "lookup",
}

_TASK_FIELDS: Dict[str, str] = {
    "name": "string",
    "status": "string",        # stored as "Not Started"/"In Progress"/… — string match
    "priority": "string",      # stored as "Normal"/"High"/… — string match
    "due_date": "date",
    "assigned_user_id": "lookup",
    "account_id": "lookup",
    "contact_id": "lookup",
    "owner_id": "lookup",
    "created_by": "lookup",
    "created_at": "date",
    "updated_at": "date",
    "id": "lookup",
}

_SUPPLIER_FIELDS: Dict[str, str] = {
    # Kept in lock-step with the Supplier FORM (SUPPLIER_STANDARD_FIELDS on the
    # frontend) — only fields the form can actually set are filterable.
    "name": "string",
    "supplier_type": "string",
    "contact_person_name": "string",
    "email": "string",
    "phone": "string",
    "mobile": "string",
    # List[str] fields — a plain {field: regex} clause matches any array element.
    "services": "string",
    "countries": "string",
    "states": "string",
    "service_cities": "string",
    # destinations is a List[str] of NAMES; strlookup's {field: {$in: [...]}}
    # array-contains match lets a multi-select pick any of several destinations.
    "destinations": "strlookup",
    "street": "string",
    "city": "string",
    "state": "string",
    "zip": "string",
    "country": "string",
    "owner_id": "lookup",
    "created_by": "lookup",
    "created_at": "date",
    "updated_at": "date",
    "id": "lookup",
}

FIELD_WHITELISTS: Dict[str, Dict[str, str]] = {
    "account": _ACCOUNT_FIELDS,
    "personal_account": _PERSONAL_ACCOUNT_FIELDS,
    "contact": _CONTACT_FIELDS,
    "lead": _LEAD_FIELDS,
    "opportunity": _OPPORTUNITY_FIELDS,
    "task": _TASK_FIELDS,
    "supplier": _SUPPLIER_FIELDS,
}

# field_key -> Mongo document field, when they differ (e.g. the "Account ID"
# filter targets the _id column).
_MONGO_FIELD_OVERRIDES: Dict[str, str] = {"id": "_id"}

# Operators each logical type accepts (used to reject unknown/mismatched ops).
OPERATORS_BY_TYPE: Dict[str, set] = {
    "string": {"equals", "not_equals", "contains", "starts_with", "is_empty", "is_not_empty"},
    "lookup": {"equals", "not_equals", "is_empty", "is_not_empty"},
    "bool": {"equals", "not_equals"},
    "number": {"equals", "not_equals", "greater_than", "less_than", "between", "is_empty", "is_not_empty"},
    "date": {"equals", "not_equals", "greater_than", "less_than", "between", "is_empty", "is_not_empty"},
    # ISO date stored as a STRING (e.g. lead industry_data.travel_date) —
    # lexicographic comparison works because "YYYY-MM-DD" sorts chronologically.
    "datestr": {"equals", "not_equals", "greater_than", "less_than", "between", "is_empty", "is_not_empty"},
    # A date that may be stored as a BSON Date (opportunity travel_date) OR an ISO
    # string (lead / converted / migrated). Matches both representations.
    "datemixed": {"equals", "not_equals", "greater_than", "less_than", "between", "is_empty", "is_not_empty"},
    # String/ObjectId id that may live in a scalar OR an array field
    # (e.g. industry_data.destination_ids). {field: value} is array-contains in Mongo.
    "strlookup": {"equals", "not_equals", "is_empty", "is_not_empty"},
}

_EMPTY_VALUES = (None, "", [], {})


# ── Relative date literals ───────────────────────────────────────────────────
# A saved view may store a *relative* date token (e.g. "YESTERDAY",
# "CURRENT_MONTH") instead of a concrete date, so a view like "Leads created
# yesterday" stays correct as time passes. Each token resolves to a half-open
# [start, end) day range at query time. Weeks are Monday-based (ISO 8601); "now"
# is server UTC, matching how the rest of this engine builds naive-UTC bounds.
_RELATIVE_TOKENS = {
    "TODAY", "YESTERDAY", "TOMORROW",
    "CURRENT_WEEK", "LAST_WEEK",
    "CURRENT_MONTH", "PREVIOUS_MONTH",
}


def _month_start(d: datetime, delta_months: int = 0) -> datetime:
    """First day of the month `delta_months` away from `d` (at midnight)."""
    m = d.month - 1 + delta_months
    year = d.year + m // 12
    month = m % 12 + 1
    return datetime(year, month, 1)


def _relative_range(value: Any) -> Optional[tuple]:
    """Resolve a relative date token to a half-open [start, end) datetime range.

    Returns None for anything that isn't a recognized token, so concrete dates
    fall through to normal parsing.
    """
    if not isinstance(value, str):
        return None
    token = value.strip().upper()
    if token not in _RELATIVE_TOKENS:
        return None
    now = datetime.utcnow()
    today = datetime(now.year, now.month, now.day)
    day = timedelta(days=1)
    if token == "TODAY":
        return (today, today + day)
    if token == "YESTERDAY":
        return (today - day, today)
    if token == "TOMORROW":
        return (today + day, today + 2 * day)
    if token == "CURRENT_WEEK":
        start = today - timedelta(days=today.weekday())
        return (start, start + timedelta(days=7))
    if token == "LAST_WEEK":
        start = today - timedelta(days=today.weekday() + 7)
        return (start, start + timedelta(days=7))
    if token == "CURRENT_MONTH":
        return (_month_start(today), _month_start(today, 1))
    if token == "PREVIOUS_MONTH":
        return (_month_start(today, -1), _month_start(today))
    return None


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.strip().lower() in ("true", "1", "yes"):
            return True
        if value.strip().lower() in ("false", "0", "no"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _coerce_number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_date(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            try:
                return datetime.fromisoformat(raw[:10])
            except ValueError:
                return None
    return None


def _rx(value: str, anchored_start: bool = False, anchored_full: bool = False) -> Dict[str, Any]:
    pat = re.escape(str(value))
    if anchored_full:
        pat = f"^{pat}$"
    elif anchored_start:
        pat = f"^{pat}"
    return {"$regex": pat, "$options": "i"}


def _string_clause(field: str, op: str, value: Any) -> Optional[dict]:
    if op == "is_empty":
        return {field: {"$in": [None, ""]}}
    if op == "is_not_empty":
        return {field: {"$nin": [None, ""]}}
    if value in _EMPTY_VALUES:
        return None
    if op == "equals":
        return {field: _rx(value, anchored_full=True)}
    if op == "not_equals":
        return {field: {"$not": re.compile(f"^{re.escape(str(value))}$", re.IGNORECASE)}}
    if op == "contains":
        return {field: _rx(value)}
    if op == "starts_with":
        return {field: _rx(value, anchored_start=True)}
    return None


def _lookup_clause(field: str, op: str, value: Any) -> Optional[dict]:
    if op == "is_empty":
        return {field: None}
    if op == "is_not_empty":
        return {field: {"$ne": None}}
    if value in _EMPTY_VALUES or not ObjectId.is_valid(str(value)):
        return None
    oid = ObjectId(str(value))
    if op == "equals":
        return {field: oid}
    if op == "not_equals":
        return {field: {"$ne": oid}}
    return None


def _bool_clause(field: str, op: str, value: Any) -> Optional[dict]:
    b = _coerce_bool(value)
    if b is None:
        return None
    if op == "equals":
        return {field: b}
    if op == "not_equals":
        return {field: {"$ne": b}}
    return None


def _number_clause(field: str, op: str, value: Any) -> Optional[dict]:
    if op == "is_empty":
        return {field: {"$in": [None, ""]}}
    if op == "is_not_empty":
        return {field: {"$nin": [None, ""]}}
    if op == "between":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return None
        lo, hi = _coerce_number(value[0]), _coerce_number(value[1])
        if lo is None or hi is None:
            return None
        return {field: {"$gte": lo, "$lte": hi}}
    num = _coerce_number(value)
    if num is None:
        return None
    if op == "equals":
        return {field: num}
    if op == "not_equals":
        return {field: {"$ne": num}}
    if op == "greater_than":
        return {field: {"$gt": num}}
    if op == "less_than":
        return {field: {"$lt": num}}
    return None


def _date_clause(field: str, op: str, value: Any) -> Optional[dict]:
    if op == "is_empty":
        return {field: None}
    if op == "is_not_empty":
        return {field: {"$ne": None}}

    # Relative token (YESTERDAY / CURRENT_MONTH / …) → resolve to a day range.
    rng = _relative_range(value)
    if rng is not None:
        start, end = rng
        if op == "equals":
            return {field: {"$gte": start, "$lt": end}}
        if op == "not_equals":
            return {"$or": [{field: {"$lt": start}}, {field: {"$gte": end}}]}
        if op == "less_than":       # before the range
            return {field: {"$lt": start}}
        if op == "greater_than":    # after the range
            return {field: {"$gte": end}}
        return None  # "between" isn't meaningful for a single token

    if op == "between":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return None
        lo, hi = _coerce_date(value[0]), _coerce_date(value[1])
        if lo is None or hi is None:
            return None
        lo_day = datetime(lo.year, lo.month, lo.day)
        hi_next = datetime(hi.year, hi.month, hi.day) + timedelta(days=1)  # inclusive end day
        return {field: {"$gte": lo_day, "$lt": hi_next}}

    d = _coerce_date(value)
    if d is None:
        return None
    day = datetime(d.year, d.month, d.day)
    next_day = day + timedelta(days=1)
    if op == "equals":              # the whole selected day
        return {field: {"$gte": day, "$lt": next_day}}
    if op == "not_equals":          # any day but the selected one
        return {"$or": [{field: {"$lt": day}}, {field: {"$gte": next_day}}]}
    if op == "greater_than":        # strictly after the selected day
        return {field: {"$gte": next_day}}
    if op == "less_than":           # strictly before the selected day
        return {field: {"$lt": day}}
    return None


def _datestr_clause(field: str, op: str, value: Any) -> Optional[dict]:
    """ISO date stored as a string (lead industry_data.travel_date).

    Compared as strings — "YYYY-MM-DD" sorts chronologically. Some rows persist a
    time component ("YYYY-MM-DDTHH:MM:SS"); whole-day half-open ranges
    ([day, next_day) as date strings) match both that and the bare date form, so
    "equals" no longer silently misses time-stamped rows.
    """
    if op == "is_empty":
        return {field: {"$in": [None, ""]}}
    if op == "is_not_empty":
        return {field: {"$nin": [None, ""]}}

    # Relative token → resolve to a day range, compared as date strings.
    rng = _relative_range(value)
    if rng is not None:
        start, end = rng
        s_start, s_end = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        if op == "equals":
            return {field: {"$gte": s_start, "$lt": s_end}}
        if op == "not_equals":
            return {"$or": [{field: {"$lt": s_start}}, {field: {"$gte": s_end}}]}
        if op == "less_than":
            return {field: {"$lt": s_start}}
        if op == "greater_than":
            return {field: {"$gte": s_end}}
        return None

    if op == "between":
        if not isinstance(value, (list, tuple)) or len(value) != 2 or not value[0] or not value[1]:
            return None
        lo, hi = _coerce_date(value[0]), _coerce_date(value[1])
        if lo is None or hi is None:
            return None
        s_lo = datetime(lo.year, lo.month, lo.day).strftime("%Y-%m-%d")
        s_hi_next = (datetime(hi.year, hi.month, hi.day) + timedelta(days=1)).strftime("%Y-%m-%d")
        return {field: {"$gte": s_lo, "$lt": s_hi_next}}

    if value in _EMPTY_VALUES:
        return None
    d = _coerce_date(value)
    if d is None:
        return None
    day = datetime(d.year, d.month, d.day)
    s_day = day.strftime("%Y-%m-%d")
    s_next = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    if op == "equals":
        return {field: {"$gte": s_day, "$lt": s_next}}
    if op == "not_equals":
        return {"$or": [{field: {"$lt": s_day}}, {field: {"$gte": s_next}}]}
    if op == "greater_than":
        return {field: {"$gte": s_next}}
    if op == "less_than":
        return {field: {"$lt": s_day}}
    return None


def _datemixed_clause(field: str, op: str, value: Any) -> Optional[dict]:
    """A date that may be persisted as a BSON Date OR an ISO string.

    The product stores ``industry_data.travel_date`` inconsistently — Opportunities
    persist it as a ``datetime`` (BSON Date), Leads as a ``str``, and converted /
    migrated records may be either. A single-type comparison silently fails for the
    other representation because MongoDB *brackets* range comparisons by BSON type
    (a string bound never matches a Date value, and vice-versa) — which is exactly
    why the opportunity "Travel Date between …" filter didn't filter. We OR a Date
    branch and a String branch; type bracketing keeps each branch to its own
    representation, so together they cover both without double counting.
    """
    if op == "is_empty":
        return {field: {"$in": [None, ""]}}
    if op == "is_not_empty":
        return {field: {"$nin": [None, ""]}}

    def _both(date_cond: dict, str_cond: Any) -> dict:
        return {"$or": [{field: date_cond}, {field: str_cond}]}

    def _outside(start: datetime, end: datetime, s_start: str, s_end: str) -> dict:
        # "not within [start, end)" across BOTH representations. Type bracketing
        # keeps each bound to its own type, so the four branches together cover a
        # value stored as either a Date or a string without double counting.
        return {"$or": [
            {field: {"$lt": start}}, {field: {"$gte": end}},
            {field: {"$lt": s_start}}, {field: {"$gte": s_end}},
        ]}

    # Relative token → resolve to a day range (covering Date + string storage).
    rng = _relative_range(value)
    if rng is not None:
        start, end = rng
        s_start, s_end = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        if op == "equals":
            return _both({"$gte": start, "$lt": end}, {"$gte": s_start, "$lt": s_end})
        if op == "not_equals":
            return _outside(start, end, s_start, s_end)
        if op == "less_than":
            return _both({"$lt": start}, {"$lt": s_start})
        if op == "greater_than":
            return _both({"$gte": end}, {"$gte": s_end})
        return None

    if op == "between":
        if not isinstance(value, (list, tuple)) or len(value) != 2 or not value[0] or not value[1]:
            return None
        lo, hi = _coerce_date(value[0]), _coerce_date(value[1])
        if lo is None or hi is None:
            return None
        lo_day = datetime(lo.year, lo.month, lo.day)
        hi_next = datetime(hi.year, hi.month, hi.day) + timedelta(days=1)  # inclusive end day
        return _both(
            {"$gte": lo_day, "$lt": hi_next},
            {"$gte": lo_day.strftime("%Y-%m-%d"), "$lt": hi_next.strftime("%Y-%m-%d")},
        )

    d = _coerce_date(value)
    if d is None:
        return None
    day = datetime(d.year, d.month, d.day)
    next_day = day + timedelta(days=1)
    s_day, s_next = day.strftime("%Y-%m-%d"), next_day.strftime("%Y-%m-%d")
    if op == "equals":
        return _both({"$gte": day, "$lt": next_day}, {"$gte": s_day, "$lt": s_next})
    if op == "not_equals":
        return _outside(day, next_day, s_day, s_next)
    if op == "greater_than":  # strictly after the selected calendar day
        return _both({"$gte": next_day}, {"$gte": s_next})
    if op == "less_than":     # strictly before the selected calendar day
        return _both({"$lt": day}, {"$lt": s_day})
    return None


def _strlookup_clause(field: str, op: str, value: Any) -> Optional[dict]:
    """Id stored as a string and/or inside an array (industry_data.destination_ids).

    {field: v} is an array-contains match in Mongo. We match both the string and
    the ObjectId form so it works regardless of how the id was persisted.

    `value` may be a single id (legacy single-select) OR a list of ids
    (multi-select destination filter). For a list, "equals" matches a record that
    holds ANY of the selected ids, and "not_equals" one holding NONE of them.
    """
    if op == "is_empty":
        return {field: {"$in": [None, [], ""]}}
    if op == "is_not_empty":
        return {field: {"$nin": [None, [], ""]}}
    if value in _EMPTY_VALUES:
        return None
    raw = value if isinstance(value, (list, tuple)) else [value]
    candidates: list = []
    for v in raw:
        s = str(v).strip()
        if not s:
            continue
        candidates.append(s)
        if ObjectId.is_valid(s):
            candidates.append(ObjectId(s))
    if not candidates:
        return None
    if op == "equals":
        return {field: {"$in": candidates}}
    if op == "not_equals":
        return {field: {"$nin": candidates}}
    return None


_CLAUSE_BUILDERS = {
    "string": _string_clause,
    "lookup": _lookup_clause,
    "bool": _bool_clause,
    "number": _number_clause,
    "date": _date_clause,
    "datestr": _datestr_clause,
    "datemixed": _datemixed_clause,
    "strlookup": _strlookup_clause,
}


def _clause_for_rule(whitelist: Dict[str, str], rule: Dict[str, Any]) -> Optional[dict]:
    if not isinstance(rule, dict):
        return None
    field = str(rule.get("field", "")).strip()
    op = str(rule.get("operator", "")).strip()
    value = rule.get("value")

    ftype = whitelist.get(field)
    if not ftype:  # unknown field -> skip (no injection)
        return None
    if op not in OPERATORS_BY_TYPE.get(ftype, set()):  # unknown/mismatched op -> skip
        return None
    mongo_field = _MONGO_FIELD_OVERRIDES.get(field, field)
    return _CLAUSE_BUILDERS[ftype](mongo_field, op, value)


def build_filter_clauses(
    entity_type: str,
    filter_rules: Optional[List[Dict[str, Any]]],
    *,
    scope: Optional[str] = None,
    current_user_id: Optional[ObjectId] = None,
) -> List[dict]:
    """Translate a view's filter_rules (+ scope) into Mongo clauses.

    Returns a list of conditions meant to be ANDed into the caller's base query,
    so tenant + data-visibility scoping is always preserved. Unknown fields and
    operators are silently dropped.
    """
    whitelist = FIELD_WHITELISTS.get(entity_type)
    if whitelist is None:
        return []

    clauses: List[dict] = []
    for rule in (filter_rules or []):
        cond = _clause_for_rule(whitelist, rule)
        if cond:
            clauses.append(cond)

    # "Show me" scope: "mine" narrows to records the current user owns.
    if scope == "mine" and current_user_id is not None:
        clauses.append({"owner_id": current_user_id})

    return clauses
