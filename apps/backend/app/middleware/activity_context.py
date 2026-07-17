"""
Request logging + audit middleware.

Responsibilities (single pure-ASGI middleware so the request is walked once):

1. Stamp each request with a ``request_id`` (echoed back as ``X-Request-ID``
   and injected into every log line via app/core/logging_config.py).
2. Emit one structured access-log line per request — method, path, status,
   duration, user, tenant, client IP — through the ``app.access`` logger, so
   it lands on stdout AND the rotating log files with the same request_id.
3. Persist an ApiAuditLog row for EVERY mutating API call
   (POST/PUT/PATCH/DELETE) with the sanitized request body and, for failures,
   the error payload. No endpoint opts in — coverage cannot drift.
4. Log unhandled exceptions with traceback + request_id, then re-raise so the
   normal 500 handling still applies.

Implemented as a *pure ASGI* middleware (not Starlette's ``BaseHTTPMiddleware``)
on purpose: ``BaseHTTPMiddleware`` raises ``RuntimeError("No response
returned.")`` whenever the downstream response is interrupted — e.g. the client
disconnects or the dev server reloads mid-request. A pure ASGI middleware simply
forwards the ASGI events, so a cancelled request flows through cleanly instead of
crashing the middleware stack.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Any, Optional

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging_config import redact_sensitive
from app.core.request_context import set_request_id

_access_logger = logging.getLogger("app.access")
_logger = logging.getLogger(__name__)

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths that never produce an access-log line or audit row (load-balancer
# health checks would otherwise flood the logs).
_SILENT_PATHS = {"/", "/health", "/health/redis", "/favicon.ico"}

# High-frequency, low-signal mutations excluded from the DB audit trail (they
# still get an access-log line). /auth/refresh fires every few minutes for
# every open session.
_AUDIT_EXCLUDED_PATHS = {"/api/v1/auth/refresh", "/auth/refresh"}

_MAX_BODY_CAPTURE = 8 * 1024        # request body kept for the audit row
_MAX_ERROR_CAPTURE = 4 * 1024       # response body kept when status >= 400


def _header(scope: Scope, name: bytes) -> str:
    for k, v in scope.get("headers") or []:
        if k == name:
            return v.decode("latin-1")
    return ""


def _client_ip(scope: Scope) -> str:
    fwd = _header(scope, b"x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = _header(scope, b"x-real-ip")
    if real:
        return real
    client = scope.get("client")
    return client[0] if client else "unknown"


def _decode_body(raw: bytes, truncated: bool) -> Optional[Any]:
    """Best-effort parse of a captured request body, secrets redacted."""
    if not raw:
        return None
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return "[BINARY]"
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = text[:2048]
    parsed = redact_sensitive(parsed)
    if truncated:
        return {"_truncated": True, "data": parsed}
    return parsed


async def _write_audit_row(doc: dict) -> None:
    """Insert the audit row; never let audit failures affect the request."""
    try:
        from app.models.activity_log import ApiAuditLog

        await ApiAuditLog(**doc).insert()
    except Exception as e:
        _logger.warning("Failed to persist api audit log for %s %s: %s",
                        doc.get("method"), doc.get("path"), e)


class ActivityContextMiddleware:
    """Request-id stamping + access logging + automatic mutation audit."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # Pass through lifespan / websocket events untouched.
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        method: str = scope.get("method", "GET").upper()
        path: str = scope.get("path", "")
        start = time.time()

        # ``request.state`` is backed by ``scope["state"]`` — populate it here so
        # downstream handlers (activity_mixin, deps) can read request_id/start_time.
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["start_time"] = start
        # ContextVar copy: makes request_id available to the logging filter for
        # every log line emitted while this request is being served.
        set_request_id(request_id)

        audit_this = (
            method in _MUTATING_METHODS
            and path not in _SILENT_PATHS
            and path not in _AUDIT_EXCLUDED_PATHS
            and (path.startswith("/api/v1") or path.startswith("/auth"))
        )

        # ── Request body capture (audited mutations only) ───────────────────
        # Multipart uploads are skipped — auditing stores metadata, not files.
        content_type = _header(scope, b"content-type").lower()
        capture_body = audit_this and not content_type.startswith("multipart/")
        body_chunks: list[bytes] = []
        body_size = 0

        async def receive_tee() -> Message:
            nonlocal body_size
            message = await receive()
            if capture_body and message["type"] == "http.request":
                chunk = message.get("body", b"")
                if chunk and body_size < _MAX_BODY_CAPTURE:
                    body_chunks.append(chunk[: _MAX_BODY_CAPTURE - body_size])
                    body_size += len(chunk)
            return message

        # ── Response capture ────────────────────────────────────────────────
        status_code: int = 500  # if the app never sends a response, it blew up
        error_chunks: list[bytes] = []
        error_size = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, error_size
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
            elif (
                message["type"] == "http.response.body"
                and audit_this
                and status_code >= 400
                and error_size < _MAX_ERROR_CAPTURE
            ):
                chunk = message.get("body", b"")
                if chunk:
                    error_chunks.append(chunk[: _MAX_ERROR_CAPTURE - error_size])
                    error_size += len(chunk)
            await send(message)

        try:
            await self.app(scope, receive_tee, send_wrapper)
        except Exception:
            # Unhandled exception — log it WITH the request id so the stack
            # trace in error.log lines up with the 500 the client saw, then
            # re-raise for the standard 500 handling.
            _logger.exception("Unhandled error on %s %s", method, path)
            self._finalize(scope, request_id, method, path, 500, start,
                           audit_this, body_chunks, body_size, error_chunks)
            raise

        self._finalize(scope, request_id, method, path, status_code, start,
                       audit_this, body_chunks, body_size, error_chunks)

    def _finalize(
        self,
        scope: Scope,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        start: float,
        audit_this: bool,
        body_chunks: list[bytes],
        body_size: int,
        error_chunks: list[bytes],
    ) -> None:
        """Emit the access-log line and (for mutations) queue the audit row."""
        if path in _SILENT_PATHS:
            return

        duration_ms = round((time.time() - start) * 1000, 1)
        # Populated by get_current_user() while the request was being handled;
        # absent for unauthenticated calls.
        user = (scope.get("state") or {}).get("audit_user") or {}
        ip = _client_ip(scope)

        _access_logger.info(
            "%s %s %s %sms user=%s tenant=%s ip=%s",
            method,
            path,
            status_code,
            duration_ms,
            user.get("user_email") or "-",
            user.get("tenant_id") or "-",
            ip,
        )

        if not audit_this:
            return

        raw_error = b"".join(error_chunks) if error_chunks else b""
        error_payload: Optional[Any] = None
        if raw_error:
            try:
                error_payload = json.loads(raw_error.decode("utf-8", errors="replace"))
            except Exception:
                error_payload = raw_error.decode("utf-8", errors="replace")[:2048]

        route = scope.get("route")
        doc = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "route": getattr(route, "path", None),
            "query": (scope.get("query_string") or b"").decode("latin-1") or None,
            "body": _decode_body(b"".join(body_chunks), body_size > _MAX_BODY_CAPTURE),
            "status_code": status_code,
            "duration_ms": duration_ms,
            "response_error": error_payload,
            "user_id": user.get("user_id"),
            "user_name": user.get("user_name"),
            "user_email": user.get("user_email"),
            "tenant_id": user.get("tenant_id"),
            "ip_address": ip,
            "user_agent": _header(scope, b"user-agent") or None,
        }
        try:
            # Fire-and-forget: the client's response must never wait on Mongo.
            asyncio.get_running_loop().create_task(_write_audit_row(doc))
        except RuntimeError:
            # No running loop (shouldn't happen inside ASGI) — drop silently.
            pass
