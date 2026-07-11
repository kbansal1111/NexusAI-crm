"""RBAC baseline: infrastructure endpoints must NEVER carry a permission gate.

Regression guard for the 2026-07-11 "Access Denied" bug: `GET /users/` and
`GET /users/search` were gated by `view_user`, but the tenant user directory
powers Assigned-To / owner dropdowns and owner-name rendering on EVERY module
page — so any role without the User *admin* module got 403 toasts on every
detail page (the axios interceptor toasts on any 403).

The rule this test locks in:

    An endpoint that shared UI calls on every page (user directory, picklists,
    notifications, tags, templates, reminders, timeline, geo data, search)
    must require ONLY an authenticated tenant user (get_current_user) —
    module/admin permissions gate module/admin endpoints, not infrastructure.

Tenant isolation is unaffected: all of these endpoints scope their queries by
current_user.tenant_id internally.

How it works: hermetic route introspection — no DB, no HTTP. We walk the
FastAPI dependency tree of each baseline route and fail if any dependency is a
`check_permission(...)` / `check_any_permission(...)` closure. A canary
asserts the detector still finds gates on an admin route, so the test can
never pass vacuously.
"""
import pytest

from app.main import app

# (method, path) pairs that must stay permission-gate-free (auth only).
# Paths are the FastAPI route paths (no trailing-slash redirects involved).
BASELINE_ROUTES = [
    # Tenant user directory — owner/assignee dropdowns, ChangeOwnerDialog.
    ("GET", "/api/v1/users/"),
    ("GET", "/api/v1/users/search"),
    ("GET", "/api/v1/users/directory"),
    # Picklists — every form renders these.
    ("GET", "/api/v1/picklists/{type_key}"),
    # Record timeline — Activities Log tab on every detail page.
    ("GET", "/api/v1/timeline/events"),
    ("GET", "/api/v1/timeline/events/entity/{entity_type}/{entity_id}"),
    # Shared page furniture.
    ("GET", "/api/v1/notifications/"),
    ("GET", "/api/v1/tags/"),
    ("GET", "/api/v1/templates/"),
    ("GET", "/api/v1/reminders/"),
    # Geo reference data — country/state/city pickers.
    ("GET", "/api/v1/countries/"),
    # Universal search (bar + Ctrl+K palette).
    ("GET", "/api/v1/search/"),
    ("GET", "/api/v1/search/by-module"),
]

# Admin routes that MUST keep their permission gate (canary: proves the
# detector works AND that we didn't accidentally open admin surfaces).
GATED_ROUTES = [
    ("GET", "/api/v1/roles/"),
    ("POST", "/api/v1/users/"),
    ("DELETE", "/api/v1/users/{user_id}"),
]


def _iter_dependency_calls(dependant):
    """Yield every dependency callable in a route's dependant tree."""
    for dep in dependant.dependencies:
        if dep.call is not None:
            yield dep.call
        yield from _iter_dependency_calls(dep)


def _find_route(method: str, path: str):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route
    return None


def _permission_gates(route) -> list[str]:
    """Qualnames of check_permission/check_any_permission closures on a route."""
    gates = []
    for call in _iter_dependency_calls(route.dependant):
        qualname = getattr(call, "__qualname__", "")
        if "check_permission" in qualname or "check_any_permission" in qualname:
            gates.append(qualname)
    return gates


@pytest.mark.parametrize("method,path", BASELINE_ROUTES)
def test_baseline_endpoint_has_no_permission_gate(method, path):
    route = _find_route(method, path)
    assert route is not None, (
        f"{method} {path} not found — if the route moved, update BASELINE_ROUTES "
        f"so the baseline guarantee follows it."
    )
    gates = _permission_gates(route)
    assert not gates, (
        f"{method} {path} is INFRASTRUCTURE used by every module page but has "
        f"permission gate(s) {gates}. Roles without that permission will get "
        f"403 'Access Denied' toasts on unrelated pages. Use get_current_user "
        f"(tenant-scoped) instead — see this file's docstring."
    )


@pytest.mark.parametrize("method,path", GATED_ROUTES)
def test_admin_endpoint_keeps_permission_gate(method, path):
    route = _find_route(method, path)
    assert route is not None, f"{method} {path} not found"
    assert _permission_gates(route), (
        f"{method} {path} is an admin/module endpoint but has NO permission "
        f"gate — either a security regression or the gate detector broke."
    )
