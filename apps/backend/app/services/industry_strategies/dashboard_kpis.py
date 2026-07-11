"""
Per-industry dashboard KPI strategies.

The shared dashboard endpoint computes a generic set of KPIs (accounts, leads,
opportunities, this month's revenue) that apply to every industry. Each
industry can additionally surface a few vertical-specific KPIs — for travel
that's "tomorrow's departures" and "today's checkouts". Healthcare might add
"today's appointments"; manufacturing might add "production orders in progress".

Adding a new industry: subclass IndustryDashboardKPIs, implement compute(),
and register it in _STRATEGIES.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Protocol

_logger = logging.getLogger(__name__)


class IndustryDashboardKPIs(Protocol):
    """Compute industry-specific KPI fields to merge into the dashboard response."""

    async def compute(
        self,
        *,
        base_query: Dict[str, Any],
        today_start: datetime,
        today_end: datetime,
        tomorrow_start: datetime,
        tomorrow_end: datetime,
    ) -> Dict[str, Any]:
        """Return a dict of {kpi_name: value} to merge into the dashboard payload."""
        ...


class DefaultDashboardKPIs:
    """No industry-specific KPIs — returns an empty dict."""

    async def compute(self, **_kwargs) -> Dict[str, Any]:
        return {}


class TravelDashboardKPIs:
    """Travel-specific KPIs: tomorrow's departures and today's checkouts.

    Both are derived from industry_data on Opportunity (travel_date string +
    no_of_nights). The query is intentionally scoped to base_query, which the
    caller has already constrained to a single tenant.
    """

    async def compute(
        self,
        *,
        base_query: Dict[str, Any],
        today_start: datetime,
        today_end: datetime,
        tomorrow_start: datetime,
        tomorrow_end: datetime,
    ) -> Dict[str, Any]:
        from app.models.opportunity import Opportunity

        # Tomorrow's departures — travel_date is stored as an ISO string in
        # industry_data, so a range comparison is a string comparison.
        # That's safe for ISO-8601 since those sort lexicographically by date.
        tomorrow_dep_query = {
            **base_query,
            "industry_data.travel_date": {
                "$gte": tomorrow_start.isoformat(),
                "$lt": tomorrow_end.isoformat(),
            },
        }
        tomorrow_departures = await Opportunity.find(tomorrow_dep_query).count()

        # Today's checkouts — checkout = travel_date + no_of_nights, which
        # Mongo can't compute on a string field, so the final filter runs
        # in-app. SCALE: the candidate set MUST be bounded — this previously
        # fetched EVERY opportunity with a travel_date (full documents, no
        # window), which grows without limit as data scales. A checkout can
        # only fall today if the departure was within the last stay-length;
        # bound departures to the past year (no stay realistically exceeds
        # that) and project just the two industry_data fields we compute on.
        today_checkout = 0
        try:
            window_start = today_start - timedelta(days=366)
            # travel_date is written as an ISO string (validated schema), but
            # legacy rows may hold real datetimes — Mongo range predicates are
            # type-bracketed, so match both representations.
            date_window = {
                "$or": [
                    {"industry_data.travel_date": {
                        "$gte": window_start.isoformat(), "$lt": today_end.isoformat(),
                    }},
                    {"industry_data.travel_date": {
                        "$gte": window_start, "$lt": today_end,
                    }},
                ]
            }
            checkout_query = (
                {"$and": [base_query, date_window]}
                if "$or" in base_query else {**base_query, **date_window}
            )
            cursor = Opportunity.get_motor_collection().find(
                checkout_query,
                {"industry_data.travel_date": 1, "industry_data.no_of_nights": 1},
            )
            async for doc in cursor:
                industry_data = doc.get("industry_data") or {}
                td = industry_data.get("travel_date")
                nights = industry_data.get("no_of_nights", 0) or 0
                if not td or not nights:
                    continue
                try:
                    if isinstance(td, str):
                        td_dt = datetime.fromisoformat(td.replace("Z", "+00:00")).replace(tzinfo=None)
                    elif isinstance(td, datetime):
                        td_dt = td
                    else:
                        continue
                    checkout_dt = td_dt + timedelta(days=int(nights))
                    if today_start <= checkout_dt < today_end:
                        today_checkout += 1
                except (ValueError, TypeError):
                    continue
        except Exception:  # noqa: BLE001
            _logger.warning("travel today_checkout computation failed", exc_info=True)

        return {
            "today_checkout": today_checkout,
            "tomorrow_departures": tomorrow_departures,
        }


_DEFAULT_STRATEGY = DefaultDashboardKPIs()
_STRATEGIES: Dict[str, IndustryDashboardKPIs] = {
    "travel": TravelDashboardKPIs(),
    "healthcare": _DEFAULT_STRATEGY,
    "education": _DEFAULT_STRATEGY,
    "manufacturing": _DEFAULT_STRATEGY,
}


def get_dashboard_kpis_strategy(industry: str) -> IndustryDashboardKPIs:
    """Return the dashboard-KPI strategy for the given industry."""
    return _STRATEGIES.get(industry, _DEFAULT_STRATEGY)


__all__ = [
    "IndustryDashboardKPIs",
    "DefaultDashboardKPIs",
    "TravelDashboardKPIs",
    "get_dashboard_kpis_strategy",
]
