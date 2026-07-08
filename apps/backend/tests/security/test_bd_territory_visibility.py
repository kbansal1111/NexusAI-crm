"""Unit tests for BD territory-scoped opportunity visibility.

These cover the security-critical pure logic in app.services.visibility_scope
that decides whether a BD user may see an opportunity:

  - A BD user sees their own/hierarchy opportunities OR any opportunity whose
    territory_id is in their assigned territories ("Territory + own").
  - A non-BD user is unaffected (owner scope only).
  - An admin (visible_owner_ids=None) sees everything.

Cross-tenant isolation is enforced separately by the always-present tenant_id
filter in the repository/aggregation match (a BD user's territory_ids only ever
reference territories in their own tenant, validated on assignment). This suite
locks the membership logic that composes with that tenant filter.
"""
from types import SimpleNamespace

from bson import ObjectId

from app.services.visibility_scope import (
    bd_territory_ids,
    is_opportunity_visible,
    _merge_or,
)


def _user(is_bd_user=False, territory_ids=None):
    return SimpleNamespace(
        id=ObjectId(),
        is_bd_user=is_bd_user,
        territory_ids=territory_ids or [],
    )


# --- bd_territory_ids ------------------------------------------------------

def test_bd_territory_ids_none_for_non_bd_user():
    t = ObjectId()
    assert bd_territory_ids(_user(is_bd_user=False, territory_ids=[t])) is None


def test_bd_territory_ids_none_when_bd_but_no_territories():
    assert bd_territory_ids(_user(is_bd_user=True, territory_ids=[])) is None


def test_bd_territory_ids_returns_assigned_for_bd_user():
    t1, t2 = ObjectId(), ObjectId()
    result = bd_territory_ids(_user(is_bd_user=True, territory_ids=[t1, t2]))
    assert result == [t1, t2]


# --- is_opportunity_visible ------------------------------------------------

def test_admin_sees_everything():
    # visible_owner_ids is None → admin → always visible regardless of territory
    assert is_opportunity_visible(ObjectId(), ObjectId(), None, None) is True


def test_owner_in_scope_is_visible():
    owner = ObjectId()
    assert is_opportunity_visible(owner, None, [owner], None) is True


def test_owner_out_of_scope_and_no_bd_is_hidden():
    assert is_opportunity_visible(ObjectId(), ObjectId(), [ObjectId()], None) is False


def test_bd_user_sees_territory_opportunity_they_do_not_own():
    terr = ObjectId()
    # owner is NOT in the user's scope, but the opp's territory IS assigned to them
    assert is_opportunity_visible(ObjectId(), terr, [ObjectId()], [terr]) is True


def test_bd_user_also_sees_their_own_opportunity_outside_territory():
    owner = ObjectId()
    # "Territory + own": own opp is visible even though its territory isn't theirs
    assert is_opportunity_visible(owner, ObjectId(), [owner], [ObjectId()]) is True


def test_bd_user_cannot_see_opportunity_outside_owner_and_territory():
    assert is_opportunity_visible(ObjectId(), ObjectId(), [ObjectId()], [ObjectId()]) is False


def test_bd_user_with_untagged_opportunity_only_via_owner():
    owner = ObjectId()
    # territory_id is None → territory branch can't match; owner branch must
    assert is_opportunity_visible(owner, None, [owner], [ObjectId()]) is True
    assert is_opportunity_visible(ObjectId(), None, [ObjectId()], [ObjectId()]) is False


# --- _merge_or composes without clobbering an existing $or -----------------

def test_merge_or_adds_or_when_absent():
    q: dict = {"tenant_id": ObjectId()}
    _merge_or(q, [{"a": 1}, {"b": 2}])
    assert q["$or"] == [{"a": 1}, {"b": 2}]


def test_merge_or_preserves_existing_or_via_and():
    existing = [{"search": 1}]
    q: dict = {"tenant_id": ObjectId(), "$or": existing}
    _merge_or(q, [{"owner": 1}, {"territory": 2}])
    # Original $or is preserved and ANDed with the new one (both must hold)
    assert "$or" not in q
    assert {"$or": existing} in q["$and"]
    assert {"$or": [{"owner": 1}, {"territory": 2}]} in q["$and"]
