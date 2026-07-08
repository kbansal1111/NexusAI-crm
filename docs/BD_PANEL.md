# BD Panel — Territory-Based Sales Cockpit

How the **BD (Business Development) panel** works end to end: what a BD user is,
how territories drive what they see and edit, and how the panel UI is wired.
This replaced the old field-ops BD feature (visits, GPS tracking, expenses,
approvals, automation rules), which was removed entirely.

---

## 1. Concepts & data model

| Thing | Where | Purpose |
|---|---|---|
| **`is_bd_user`** flag | `User.is_bd_user` (`app/models/user.py`) | Marks a user as a BD user. Drives territory-scoped visibility. |
| **`territory_ids`** | `User.territory_ids` (list) | The BD user's assigned territories. **Authoritative** per-user assignment, read on every scoped request (zero extra query — the user is already loaded). |
| **Territory / Region** | `app/models/territory.py` | Geographic sales territories (countries/states/postal codes). `Territory.users[]` is kept in sync with `User.territory_ids`. Managed at **Settings → Territory**. |
| **`Opportunity.territory_id`** | `app/models/opportunity.py` | The territory a deal belongs to. Auto-resolved from the linked **account's billing address**. This is the field BD visibility matches on. |

Leads are **not** part of BD/territory anymore — all BD fields were stripped
from the Lead model. Territory lives at the **opportunity** level only.

---

## 2. Flow: making a user a BD user + assigning a territory

**Where:** Admin → Users → create/edit user (`user-form.tsx`).

1. Set **BD User = Yes** (`is_bd_user`).
2. Pick one or more **Assigned Territories** (multi-select, appears only when BD User = Yes).
3. Save.

**Backend** (`user_service.sync_user_territories`):
- Validates every territory id belongs to the caller's **tenant** (rejects forged/cross-tenant ids → `400`).
- Sets `user.territory_ids` (authoritative).
- Reconciles `Territory.users[]` (adds to selected, `$pull`s from deselected) so the Territory admin UI stays consistent.
- Tenant scope cache is invalidated so visibility recomputes immediately.

---

## 3. Flow: how an opportunity gets its territory

**Automatic, on opportunity create** (`opportunity_service.create_opportunity`):
- If the opportunity is linked to an **account**, its billing `country / state / zip`
  is matched against territories via `bd_assignment_service.resolve_for_address()`
  (postal exact → postal wildcard → state → country).
- On a match, the opportunity is stamped with `territory_id`, `region_id`, and
  `reporting_manager_id` (the territory's manager — this is the **"Territory Manager"**
  shown on the opportunity detail page).
- Opportunities with **no account** (or no matching territory) stay unstamped —
  a BD user still sees those only if they personally own them.

**Manual override:** `POST /opportunities/{id}/reassign-bd` and
`POST /opportunities/{id}/resolve-territory` remain available.

---

## 4. Flow: what a BD user sees and can edit ("Territory + own")

A BD user's scope is **their own/hierarchy opportunities OR any opportunity in
their assigned territories**. This applies **everywhere** opportunities appear —
the main Opportunities module, the BD panel, tasks, and dashboard numbers.

Implemented in `app/services/visibility_scope.py`:
- `bd_territory_ids(user)` → the user's territories if `is_bd_user`, else `None`.
- List query (`opportunity_repository.get_filtered_opportunities`): the owner
  filter is re-expressed as `{$or: [{owner_id ∈ visible}, {territory_id ∈ bd_territories}]}`,
  **ANDed** with the always-present `tenant_id` filter (so it composes safely
  with search/saved-view filters and never leaks across tenants).
- Detail / **edit / delete / change-stage / lock / unlock / change-owner / history**
  all use `is_opportunity_visible(owner_id, territory_id, visible, bd_territories)` —
  so a BD user can **fully work** a territory deal, not just view it. Each action
  is still gated by its own role permission (e.g. `edit_opportunity`).

| User type | Sees | Can edit |
|---|---|---|
| **Admin** (`is_admin` role) | **Everything in the tenant** (owner + territory scoping bypassed) | Everything |
| **BD user** | Own/hierarchy **+** all opportunities in assigned territories | Own **+** territory deals (subject to role permissions) |
| **Regular user** | Own/hierarchy only | Own only |

> **Explicit owner filter:** when a user filters the list by a specific owner,
> that filter is respected as-is (no territory widening) — the widening applies
> to the default "everything I can see" view.

---

## 5. Flow: the BD Panel UI

**Entry:** sidebar **"BD Panel"** (gated by the `view_bd_panel` permission).
A BD user **lands on the normal dashboard** after login; the panel is a
destination they navigate to.

Route: `/bd` (`app/(dashboard)/bd/`), a tabbed shell (`layout.tsx`):

| Tab | Route | What it shows |
|---|---|---|
| **Dashboard** | `/bd` | Closed / Open / Target cards, **Monthly Sales** area chart (this vs last month), **Sales Stages** pie — all territory-scoped. |
| **Opportunities** | `/bd/opportunities` | The full opportunities list, territory-scoped server-side. |
| **Tasks** | `/bd/tasks` | The BD user's tasks. |
| **Departure** | `/bd/departure` | The departure report. |

The dashboard is fed by three territory-scoped endpoints in
`dashboards_extra.py` (gated by `view_bd_panel`):
- `GET /dashboards/bd/summary` — closed (won this month), open pipeline, monthly target.
- `GET /dashboards/bd/revenue-chart` — cumulative daily won revenue, this vs last month.
- `GET /dashboards/bd/stage-breakdown` — opportunity count/value per sales stage.

All three use the same `owner OR territory` match (`_bd_opportunity_match`), so
the numbers match the Opportunities tab exactly.

---

## 6. Permissions & access

- **`view_bd_panel`** — gates the BD Panel UI + the BD dashboard endpoints.
- **`manage_territory`** — gates the Territory settings admin.
- The four tabs call the underlying module APIs, so a functional BD role needs
  `view_bd_panel` **plus** `view_opportunity`, `view_task`, and dashboard/departure
  access. Territory only **widens the scope** of those permissions from "own" to
  "own + territory"; it does not grant new module access.
- All other BD field-ops permissions (`*_bd_visit`, `*_expense`, `*_live_tracking`,
  `manage_automation_rules`, `manage_bd_panel`) were **removed** from the registry
  and stripped from existing roles.

---

## 7. Tenant isolation (non-negotiable)

Every BD query is tenant-scoped first. A BD user's `territory_ids` are validated
to their tenant on assignment, and every opportunity query ANDs `tenant_id`
before the territory `$or`. Result: a BD user can **never** see another tenant's
opportunities — even if a territory id were forged or reused across tenants.
This is locked by hermetic tests (below).

---

## 8. What was removed

- Field-ops backend: `bd_visit`, `bd_visit_route`, `location_ping`, `expense`,
  `automation_rule` models; their services, routers, schemas, tasks, and seed
  scripts; `BDActivityType` / `ExpenseCategory` picklists.
- Field-ops frontend: `/bd/visits`, `/bd/approvals`, `/bd/expenses`,
  `/bd/tracking`, `/settings/automation`, the legacy `/dashboard/bd` page, and
  their feature folders/services.
- Lead BD fields (`territory_id`, `bd_owner_id`, `reporting_manager_id`,
  `requires_field_meeting`, …) and lead-level territory auto-resolution.

**Migrations applied (prod, `tutterfly_crm`):**
- `scripts/strip_removed_bd_permissions.py --apply` → 6 role docs cleaned.
- `scripts/drop_bd_field_ops_collections.py --apply` → dropped `bd_visits`,
  `bd_visit_routes`, `location_pings`, `expenses`, `automation_rules`.

---

## 9. Verification

- Backend imports clean (754 routes); registry BD perms = `view_bd_panel`, `manage_territory`.
- **Hermetic data-level E2E** (`tests/security/test_bd_territory_visibility_e2e.py`,
  mongomock + Beanie, real documents):
  - BD user sees own + territory, not other-territory, not cross-tenant. ✅
  - Regular user is owner-scoped only. ✅
  - Admin sees the whole tenant, not another tenant. ✅
  - Cross-tenant territory-id spoof is blocked. ✅
- Unit tests (`tests/security/test_bd_territory_visibility.py`): 12 cases on the
  scoping logic. ✅
- Full relevant suite: 65 passed, 0 failures. Frontend `tsc --noEmit`: 0 errors.
