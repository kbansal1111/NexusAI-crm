"""Unit tests for the system preset-view registry.

Verifies that each list "preset" is a real filter (created_at relative-token rule)
that the shared filter engine resolves correctly — i.e. "Today" genuinely filters
to today's records — for every supported module.
"""
import asyncio
from datetime import datetime, timedelta

from bson import ObjectId

from app.core.system_views import (
    preset_defs,
    PRESET_ENTITY_TYPES,
    PRESET_ORDER,
    _OPPORTUNITY_STAGE_PRESETS,
    _opportunity_stage_defs,
)
from app.core.entity_filter import build_filter_clauses, FIELD_WHITELISTS

_DATE_KEYS = ["today", "yesterday", "this_week", "this_month"]


def test_preset_defs_lead_has_standard_date_set():
    defs = preset_defs("lead")
    keys = [d["preset_key"] for d in defs]
    # The standard date set comes first, in order.
    assert keys[:4] == _DATE_KEYS
    today = next(d for d in defs if d["preset_key"] == "today")
    assert today["is_default"] is True  # the landing view
    # Each date preset is a real created_at filter (not an opaque flag).
    for d in defs:
        if d["preset_key"] not in _DATE_KEYS:
            continue
        rule = d["filter_rules"][0]
        assert rule["field"] == "created_at"
        assert rule["operator"] == "equals"
        assert rule["value"] in {"TODAY", "YESTERDAY", "CURRENT_WEEK", "CURRENT_MONTH"}
    # Leads also carry the WhatsApp Enquiry saved-view preset.
    assert "whatsapp_enquiry" in keys


def test_preset_defs_unsupported_entity_is_empty():
    assert preset_defs("itinerary") == []


def test_every_preset_entity_supported_and_filterable():
    # The standard set is applied to all list modules, and created_at must be a
    # whitelisted date field for each so the engine can actually apply the rule.
    for et in PRESET_ENTITY_TYPES:
        keys = [d["preset_key"] for d in preset_defs(et)]
        assert keys[:4] == _DATE_KEYS
        assert FIELD_WHITELISTS[et]["created_at"] == "date"


def test_lead_whatsapp_preset_is_campaign_name_equals():
    # campaign_name lives in the lead's custom_fields dict (Additional Information).
    wa = next(d for d in preset_defs("lead") if d["preset_key"] == "whatsapp_enquiry")
    assert wa["filter_rules"] == [
        {"field": "custom_fields.campaign_name", "operator": "equals", "value": "WhatsApp Enquiry"}
    ]
    # The engine turns it into an anchored, case-insensitive match.
    clauses = build_filter_clauses("lead", wa["filter_rules"])
    assert clauses == [{"custom_fields.campaign_name": {"$regex": r"^WhatsApp\ Enquiry$", "$options": "i"}}]


def test_opportunity_stage_presets_are_closed_won_and_lost():
    assert [p["preset_key"] for p in _OPPORTUNITY_STAGE_PRESETS] == ["closed_won", "closed_lost"]


def test_opportunity_stage_defs_resolve_to_sales_stage_equals(monkeypatch):
    # Stage ids are per-tenant, resolved by name at seed time. Stub the lookup.
    from app.models import consolidated_picklists as cp

    ids = {"Closed Won": ObjectId(), "Closed Lost": ObjectId()}

    class _Stage:
        def __init__(self, _id):
            self.id = _id

    async def fake_find_one(query):
        name = query.get("name")
        return _Stage(ids[name]) if name in ids else None

    monkeypatch.setattr(cp.SalesStage, "find_one", staticmethod(fake_find_one))
    defs = asyncio.run(_opportunity_stage_defs(ObjectId(), _OPPORTUNITY_STAGE_PRESETS))

    assert [d["preset_key"] for d in defs] == ["closed_won", "closed_lost"]
    for d, name in zip(defs, ["Closed Won", "Closed Lost"]):
        assert d["filter_rules"] == [
            {"field": "sales_stage_id", "operator": "equals", "value": str(ids[name])}
        ]
        # The engine resolves the equals rule back to that tenant's stage ObjectId.
        assert build_filter_clauses("opportunity", d["filter_rules"]) == [
            {"sales_stage_id": ids[name]}
        ]


def test_opportunity_stage_defs_skips_unseeded_stage(monkeypatch):
    from app.models import consolidated_picklists as cp

    async def fake_find_one(query):
        return None  # stage picklist not seeded yet for this tenant

    monkeypatch.setattr(cp.SalesStage, "find_one", staticmethod(fake_find_one))
    assert asyncio.run(_opportunity_stage_defs(ObjectId(), _OPPORTUNITY_STAGE_PRESETS)) == []


def test_today_preset_filters_created_at_to_today_range():
    rules = preset_defs("lead")[0]["filter_rules"]  # today
    clauses = build_filter_clauses("lead", rules)
    assert len(clauses) == 1
    cond = clauses[0]["created_at"]
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    assert cond["$gte"] == today
    assert cond["$lt"] == today + timedelta(days=1)


def test_preset_order_matches_registry_keys():
    assert PRESET_ORDER == {"today": 0, "yesterday": 1, "this_week": 2, "this_month": 3}
