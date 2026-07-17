# Logging & Audit Trail — Operations Guide

This is the guide for anyone maintaining Tutterfly CRM in production. It explains
**what gets logged, where it goes, how to read it, and how to configure it.**
Read it once before you touch logging or investigate an incident.

The system logs on **three independent layers**, so a lost row in one layer never
means a lost record — you always have a fallback.

| Layer | What it captures | Where it lives | Who reads it |
|-------|------------------|----------------|--------------|
| **1. Application logs** | Every request (access log), every error with a stack trace, startup/health warnings | stdout **+** rotating files `logs/app.log`, `logs/error.log` | Developers / DevOps (server shell, `docker logs`, or a log shipper) |
| **2. API audit trail** | Every data-changing API call — who, what, when, from where, the payload, the result | MongoDB collection `api_audit_logs` | Admins (in-app API) + developers (Mongo) |
| **3. Business activity + login history** | Human-readable per-record timeline (created/updated/deleted/status/assignment) and login/logout/failed-login history | MongoDB collections `activity_logs`, `login_logs` | End users (record "History" tab), admins (login report) |

Everything on all three layers is stamped with the same **`request_id`**, so one
identifier ties a user-visible error, its server stack trace, and its audit row
together.

---

## 1. Application logs (files + stdout)

### What is written
- **One access-log line per request** (logger `app.access`): method, path, status,
  duration in ms, user email, tenant id, client IP.
- **Every warning/error/exception** from anywhere in the code, with full traceback.
- **Startup health warnings**: Redis not reachable, S3/AWS credentials missing, etc.

Every line carries `[req:<request_id>]` (text format) or a `request_id` field
(JSON format).

### Format
- **Development** (`ENVIRONMENT=development`): human-readable text —
  `2026-07-17 10:30:01 [INFO] app.access [req:8f3a…]: POST /api/v1/leads 201 42.1ms user=ada@dook.com tenant=… ip=…`
- **Production** (any other `ENVIRONMENT`): one JSON object per line, ready for
  Datadog / CloudWatch / Loki / `jq`:
  ```json
  {"timestamp":"2026-07-17 10:30:01","level":"INFO","name":"app.access","request_id":"8f3a…","message":"POST /api/v1/leads 201 42.1ms user=ada@dook.com tenant=… ip=…"}
  ```

### Where the files are
Controlled by settings (see [§5](#5-configuration)). Defaults:
- `apps/backend/logs/app.log` — everything at INFO and above.
- `apps/backend/logs/error.log` — WARNING and above only (fast triage of "what broke").

Files **rotate daily at UTC midnight** and keep `LOG_RETENTION_DAYS` (default 30)
days of history: `app.log`, `app.log.2026-07-16`, `app.log.2026-07-15`, …
Older files are deleted automatically. `logs/` is git-ignored.

> Secrets are redacted before anything is written — see [§6](#6-what-is-redacted).
> If the log directory is not writable, the app **still runs** and logs to stdout;
> file logging simply disables itself with one warning.

### How a developer reads them

**On the server (EC2 / container shell):**
```bash
cd apps/backend

# Live tail of everything
tail -f logs/app.log

# Only errors, live
tail -f logs/error.log

# Find one request across both files by its id (from the X-Request-ID header
# the client received, or from an error the user reported)
grep "8f3a2b1c" logs/app.log logs/error.log

# All failed requests today
grep -E ' (4[0-9][0-9]|5[0-9][0-9]) ' logs/app.log

# Production JSON: pretty-print and filter with jq
grep "8f3a2b1c" logs/app.log | jq .
cat logs/app.log | jq 'select(.level=="ERROR")'
```

**If running under Docker / systemd** (stdout is captured by the platform):
```bash
docker logs -f <container>            # or: docker compose logs -f backend
journalctl -u tutterfly-backend -f    # systemd
```

**With a log shipper (recommended for long-term prod):** because prod emits JSON
lines on stdout, point Datadog Agent / AWS CloudWatch Logs / Grafana Loki /
Vector at the container stdout (or at `logs/*.log`) with **zero code changes**.
Index on `request_id`, `level`, and `name` for fast search and alerting.

---

## 2. API audit trail (`api_audit_logs` collection)

**This is the "who changed what" safety net and the heart of the audit system.**

### Coverage — nothing is missed
A single ASGI middleware
([`app/middleware/activity_context.py`](../apps/backend/app/middleware/activity_context.py))
writes one audit row for **every** `POST` / `PUT` / `PATCH` / `DELETE` request
under `/api/v1/*` or `/auth/*`. **No endpoint opts in or out** — it is enforced at
the transport layer, so coverage cannot drift as new routes are added. All ~360
mutating endpoints across every module (leads, opportunities, accounts, settings,
billing, roles, files, imports, admin, healthcare/education/manufacturing
verticals, …) are covered by construction.

Deliberately **not** audited (documented decisions, not gaps):
- **GET / read requests** — auditing reads would multiply log volume ~10× and is
  not required for change-tracking. They still get an access-log line in Layer 1.
  (If PII read-auditing is ever mandated, e.g. for healthcare compliance, add the
  `GET` case in the middleware — the plumbing is already there.)
- **`/auth/refresh`** — fires every few minutes for every open session; pure noise.
- **Health checks** (`/`, `/health`, `/health/redis`, `/favicon.ico`).
- **Uploaded file bytes** — multipart bodies store metadata only, never the file.

### What each row contains
| Field | Meaning |
|-------|---------|
| `request_id` | Correlates to the `X-Request-ID` header and every Layer-1 log line for this request |
| `method`, `path`, `route` | `POST`, `/api/v1/leads/663…`, and the route template `/api/v1/leads/{lead_id}` |
| `query`, `body` | Query string and request body — **secrets redacted, size-capped at 8 KB** |
| `status_code`, `duration_ms` | Outcome and latency |
| `response_error` | The error payload, captured **only** when status ≥ 400 |
| `user_id`, `user_name`, `user_email` | The actor (absent for unauthenticated calls such as failed logins) |
| `tenant_id` | Owning tenant — every read is scoped by this |
| `ip_address`, `user_agent` | Origin of the request |
| `created_at` | Timestamp (drives TTL retention) |

The audit write is **fire-and-forget** — the user's response never waits on it,
and an audit failure can never break a real request.

### Retention
A **MongoDB TTL index** on `created_at` auto-deletes rows after
`AUDIT_LOG_RETENTION_DAYS` (default **365 days**). Retention is enforced by Mongo,
not the app. The TTL index is created by the index script (see [§4](#4-first-time-setup--after-config-changes)).

### How a developer / admin reads it

**In-app (admins only), tenant-scoped:**
```
GET /api/v1/timeline/audit
    ?method=DELETE          # optional: filter by verb
    &status_min=400         # optional: only failures
    &path_prefix=/api/v1/opportunities   # optional: one module
    &user_id=<id>           # optional: one user
    &request_id=<id>        # optional: pinpoint one request
    &days=7&skip=0&limit=100
```
Requires an admin role (`is_admin`). It returns **only the caller's tenant's**
rows — one tenant can never read another's audit trail.

**Directly in MongoDB** (full power, all tenants — for developers/DevOps):
```javascript
// Everything a user did in the last day
db.api_audit_logs.find({ user_email: "ada@dook.com" })
  .sort({ created_at: -1 }).limit(50)

// All deletes this week, newest first
db.api_audit_logs.find({ method: "DELETE" }).sort({ created_at: -1 })

// All server errors (500s)
db.api_audit_logs.find({ status_code: { $gte: 500 } })

// Trace one request end-to-end (same id as the log files + X-Request-ID)
db.api_audit_logs.findOne({ request_id: "8f3a2b1c-…" })
```

---

## 3. Business activity & login history

### Per-record timeline — `activity_logs`
Rich, human-readable entries ("Ada updated Lead *Acme Corp*: status Qualified →
Won") for the core CRM entities: **accounts, contacts, leads, opportunities,
tasks, quotes, invoices, users, roles, suppliers**. Produced by services that use
`ActivityMixin`, surfaced in each record's **History / Activities** tab and the
dashboard "Recent Activity" feed. Read via `/api/v1/timeline/events`
(visibility-scoped: reps see only their own + subordinates' activity).

> Note: this rich layer intentionally covers the *core* entities users care about
> on a timeline. Every other mutation (settings, billing, webhooks, custom fields,
> etc.) is still fully captured by the **Layer-2 API audit trail** above — so
> "changed but no timeline entry" never means "untracked".

### Login history — `login_logs`
Every login attempt is recorded — **successful and failed** (wrong password,
inactive account, industry mismatch), with IP, user-agent, and failure reason.
Logout is recorded to `activity_logs`. Failed logins for *unknown* emails (no user
record) are logged to Layer 1 (`app.log`) for brute-force forensics.

Read via:
```
GET /api/v1/timeline/logins?success=false&days=30   # requires view_report
GET /api/v1/timeline/logins/user/{user_id}          # requires view_user
```

---

## 4. First-time setup & after config changes

The audit collection's indexes — **including the TTL retention index** — are
created out-of-band by the index script (same pattern as all other indexes; it is
never done at app boot). Run once after deploying this change, and again any time
you change `AUDIT_LOG_RETENTION_DAYS`:

```bash
cd apps/backend
python scripts/create_indexes.py            # idempotent, safe to re-run
python scripts/create_indexes.py --dry-run  # preview, creates nothing
```

> **Changing the TTL later:** Mongo will not silently alter an existing TTL index.
> If you change `AUDIT_LOG_RETENTION_DAYS` and re-run the script, the line prints
> `[skip]`. To apply the new value, drop and recreate it in Mongo:
> ```javascript
> db.api_audit_logs.dropIndex("created_at_1")
> ```
> then re-run the script.

---

## 5. Configuration

All in `apps/backend/app/core/config.py`, overridable via environment / `.env`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `ENVIRONMENT` | `development` | `development` → text logs; anything else → JSON logs |
| `LOG_LEVEL` | `INFO` | Root log level (`DEBUG`, `INFO`, `WARNING`, …) |
| `LOG_TO_FILE` | `true` | Write rotating files in addition to stdout |
| `LOG_DIR` | `logs` | Log directory (relative paths resolve under `apps/backend`) |
| `LOG_RETENTION_DAYS` | `30` | Days of rotated log files to keep |
| `AUDIT_LOG_RETENTION_DAYS` | `365` | TTL (days) for `api_audit_logs` rows |
| `SENTRY_DSN` | *(empty)* | If set, errors are also sent to Sentry (optional) |

**Typical production:** set `ENVIRONMENT=production` (JSON logs). Keep
`LOG_TO_FILE=true` as a local fallback even when a log shipper reads stdout. If
disk is tight and a shipper already captures stdout, set `LOG_TO_FILE=false`.

---

## 6. What is redacted

Secrets never reach any log or audit row. Two layers of scrubbing:
- **Log records** — a filter drops `password`, `token`, `access_token`,
  `refresh_token`, `authorization`, `api_key`, `secret`, `smtp_password`.
- **Audit bodies** — any field whose key contains `password`, `token`, `secret`,
  `api_key`/`apikey`, `authorization`, `credit_card`, or `cvv` is replaced with
  `[REDACTED]`, recursively, before the body is stored.
- **Sentry** (if enabled) scrubs the same keys from request data and breadcrumbs.

If you add a new sensitive field, add its key substring to `_SENSITIVE_SUBSTRINGS`
in [`app/core/logging_config.py`](../apps/backend/app/core/logging_config.py).

---

## 7. Incident-response cheat-sheet

A user reports an error:
1. Ask for the **request id** — it is returned on every response as the
   `X-Request-ID` header (surface it in the UI's error toast if not already).
2. `grep "<request_id>" apps/backend/logs/app.log logs/error.log` → the exact
   stack trace and the access line (who/when/how long).
3. `db.api_audit_logs.findOne({ request_id: "<request_id>" })` → the exact
   payload they sent, the tenant, the IP, and the status returned.

"Did user X change record Y?"
```javascript
db.api_audit_logs.find({ user_email: "x@…", path: /Y_id/ }).sort({ created_at: -1 })
```

"Is someone brute-forcing logins?"
```javascript
db.login_logs.find({ success: false }).sort({ created_at: -1 })   // known emails
grep "Failed login for unknown email" apps/backend/logs/app.log   // unknown emails
```

---

## 8. Where the code lives

| Concern | File |
|---------|------|
| Log setup (format, files, rotation, redaction, request-id filter) | `app/core/logging_config.py` |
| Request-id + audit + access-log middleware | `app/middleware/activity_context.py` |
| Per-request context (request_id / actor ContextVars) | `app/core/request_context.py` |
| Audit + login + activity models | `app/models/activity_log.py` |
| Audit read API + login/activity read APIs | `app/api/v1/activity_logs.py` |
| Login / logout / failed-login recording | `app/services/auth_service.py`, `app/api/v1/auth.py` |
| Rich per-entity timeline mixin | `app/mixins/activity_mixin.py` |
| Indexes + TTL retention | `scripts/create_indexes.py` |
| Tests | `tests/security/test_audit_logging.py` |
