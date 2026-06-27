"""System preset list-views.

A standard set of saved views — **Today / Yesterday / This Week / This Month** —
lazily seeded per tenant + entity. They are ordinary ``EntityView`` rows
(``is_system=True``) so they ride the entire saved-view stack unchanged: selected
by ``view_id``, applied via ``build_filter_clauses`` (app/core/entity_filter.py),
shown & edited in the "Edit List Filters" dialog, and pinnable. The selector just
groups them under "Presets".

Each preset filters ``created_at`` with a *relative-date token* (resolved to a day
range at query time by entity_filter.py), so the definitions are entity-agnostic
and never go stale. Keep the tokens in sync with ``_RELATIVE_TOKENS`` there.

Besides the date set, an entity may declare *extra* presets that carry their own
concrete ``filter_rules`` (see ``_EXTRA_PRESETS``). Lead "WhatsApp Enquiry Leads"
is one such preset — it mirrors the client's legacy CRM saved view (Campaign Name
equals "WhatsApp Enquiry") and rides the same saved-view stack as the date presets.

Note: "Recently Viewed" is intentionally NOT here — it is an *ordering* (by view
recency), not a filter, and stays a special ``?view=recent`` preset on the modules
that track views (lead / opportunity). The opportunity "Closed" special likewise
remains a ``?view=`` preset for now, since it matches a *set* of stage ids that a
single ``equals`` rule can't express.
"""
from __future__ import annotations

from typing import Any, Dict, List

from beanie import PydanticObjectId

from app.models.entity_views import EntityView

# Entity types that receive the standard preset views.
PRESET_ENTITY_TYPES = (
    "account", "personal_account", "contact",
    "lead", "opportunity", "supplier", "task",
)

# Ordered "unified standard set". Every preset filters created_at via a relative
# token. `order` drives the dropdown ordering; `is_default` is the landing view.
_DATE_PRESETS: List[Dict[str, Any]] = [
    {"preset_key": "today",      "name": "Today",      "token": "TODAY",         "order": 0, "is_default": True},
    {"preset_key": "yesterday",  "name": "Yesterday",  "token": "YESTERDAY",     "order": 1, "is_default": False},
    {"preset_key": "this_week",  "name": "This Week",  "token": "CURRENT_WEEK",  "order": 2, "is_default": False},
    {"preset_key": "this_month", "name": "This Month", "token": "CURRENT_MONTH", "order": 3, "is_default": False},
]

# Stable ordering for the frontend (preset_key -> position).
PRESET_ORDER: Dict[str, int] = {p["preset_key"]: p["order"] for p in _DATE_PRESETS}

# Entity-specific non-date presets. Unlike the date set, these carry their own
# concrete ``filter_rules`` (a real equality match), so they are stored inline
# rather than derived from a relative-date token. Lead "WhatsApp Enquiry Leads"
# mirrors the client's legacy CRM saved view: Campaign Name equals "WhatsApp
# Enquiry". They have no PRESET_ORDER entry, so the selector sorts them after the
# date presets.
_EXTRA_PRESETS: Dict[str, List[Dict[str, Any]]] = {
    "lead": [
        {
            "preset_key": "whatsapp_enquiry",
            "name": "WhatsApp Enquiry Leads",
            "filter_rules": [
                {"field": "campaign_name", "operator": "equals", "value": "WhatsApp Enquiry"},
            ],
            "is_default": False,
        },
    ],
}


def _created_at_rule(token: str) -> List[Dict[str, Any]]:
    return [{"field": "created_at", "operator": "equals", "value": token}]


def preset_defs(entity_type: str) -> List[Dict[str, Any]]:
    """Standard preset view definitions for an ``entity_type`` (empty if unsupported)."""
    if entity_type not in PRESET_ENTITY_TYPES:
        return []
    date_defs = [
        {
            "preset_key": p["preset_key"],
            "name": p["name"],
            "filter_rules": _created_at_rule(p["token"]),
            "is_default": p["is_default"],
        }
        for p in _DATE_PRESETS
    ]
    extra_defs = [dict(p) for p in _EXTRA_PRESETS.get(entity_type, [])]
    return date_defs + extra_defs


async def seed_preset_views(
    entity_type: str,
    tenant_id: PydanticObjectId,
    created_by: PydanticObjectId,
) -> int:
    """Idempotently seed the standard preset views for a tenant + entity.

    Only inserts presets that don't already exist for this tenant+entity (keyed by
    ``preset_key``), so it is safe to call on every list load and never clobbers a
    user's edits to an existing preset. Returns the number of presets created.
    """
    defs = preset_defs(entity_type)
    if not defs:
        return 0

    existing = await EntityView.find(
        {"tenant_id": tenant_id, "entity_type": entity_type, "is_system": True}
    ).to_list()
    have = {v.preset_key for v in existing if v.preset_key}

    created = 0
    for d in defs:
        if d["preset_key"] in have:
            continue
        await EntityView(
            entity_type=entity_type,
            name=d["name"],
            filter_rules=d["filter_rules"],
            is_system=True,
            is_public=True,         # visible to the whole tenant
            is_default=d["is_default"],
            preset_key=d["preset_key"],
            tenant_id=tenant_id,
            created_by=created_by,
        ).insert()
        created += 1
    return created
