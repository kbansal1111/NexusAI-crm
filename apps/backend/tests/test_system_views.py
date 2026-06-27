"""Unit tests for the system preset-view registry.

Verifies that each list "preset" is a real filter (created_at relative-token rule)
that the shared filter engine resolves correctly — i.e. "Today" genuinely filters
to today's records — for every supported module.
"""
from datetime import datetime, timedelta

from app.core.system_views import preset_defs, PRESET_ENTITY_TYPES, PRESET_ORDER
from app.core.entity_filter import build_filter_clauses, FIELD_WHITELISTS


def test_preset_defs_lead_has_standard_date_set():
    defs = preset_defs("lead")
    assert [d["preset_key"] for d in defs] == ["today", "yesterday", "this_week", "this_month"]
    today = next(d for d in defs if d["preset_key"] == "today")
    assert today["is_default"] is True  # the landing view
    # Every preset is a real created_at filter (not an opaque flag).
    for d in defs:
        rule = d["filter_rules"][0]
        assert rule["field"] == "created_at"
        assert rule["operator"] == "equals"
        assert rule["value"] in {"TODAY", "YESTERDAY", "CURRENT_WEEK", "CURRENT_MONTH"}


def test_preset_defs_unsupported_entity_is_empty():
    assert preset_defs("itinerary") == []


def test_every_preset_entity_supported_and_filterable():
    # The standard set is applied to all list modules, and created_at must be a
    # whitelisted date field for each so the engine can actually apply the rule.
    for et in PRESET_ENTITY_TYPES:
        assert len(preset_defs(et)) == 4
        assert FIELD_WHITELISTS[et]["created_at"] == "date"


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
