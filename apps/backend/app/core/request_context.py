"""
Per-request activity context.

Holds the authenticated user + request metadata for the duration of a single
request so that any service using ActivityMixin can log activity without the
endpoint having to call set_request_context() explicitly.

Populated in get_current_user() (see app/api/deps.py). Because each request runs
in its own asyncio task, the ContextVar is isolated per request — there is no
cross-request leakage.
"""
from contextvars import ContextVar
from typing import Optional, Dict, Any

_activity_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "activity_context", default=None
)

# Request id for log correlation. Set by ActivityContextMiddleware at the very
# start of each request; injected into every log record by the logging filter
# in app/core/logging_config.py and echoed to clients as X-Request-ID.
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_activity_context(context: Dict[str, Any]) -> None:
    """Store the current request's activity context."""
    _activity_context.set(context)


def get_activity_context() -> Optional[Dict[str, Any]]:
    """Return the current request's activity context, or None if unset."""
    return _activity_context.get()


def set_request_id(request_id: str) -> None:
    """Store the current request's id for log correlation."""
    _request_id.set(request_id)


def get_request_id() -> Optional[str]:
    """Return the current request's id, or None outside a request."""
    return _request_id.get()
