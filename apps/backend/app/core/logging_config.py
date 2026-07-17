"""
Centralized logging configuration.

Output targets:
- stdout — always. Human-readable text in development, JSON lines in
  production (parseable by Datadog / CloudWatch / Loki / `jq`).
- Rotating files (optional, on by default) — `app.log` (INFO+) and
  `error.log` (WARNING+) in LOG_DIR, rotated daily, keeping
  LOG_RETENTION_DAYS days. Same format as stdout.

Every record carries the current `request_id` (set per-request by
ActivityContextMiddleware and echoed to clients as X-Request-ID), so a user
report of "error id abc-123" can be grepped across all log files and matched
to its row in the api_audit_logs collection.

A custom filter strips fields commonly used to carry secrets (`password`,
`token`, `access_token`, `authorization`, etc.) from log records — so even if
a developer accidentally logs a dict containing a token, it gets redacted
before hitting stdout. Sentry separately captures `error` and above via its
own integration.

See docs/LOGGING_AND_AUDIT.md for the full operations guide.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Optional

_SENSITIVE_KEYS: tuple[str, ...] = (
    "password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "secret",
    "smtp_password",
)

# Substrings — any dict key containing one of these is redacted wholesale.
# Broader than _SENSITIVE_KEYS (exact matches) because request bodies are
# arbitrary client input ("newPassword", "apiToken", ...).
_SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "credit_card",
    "cvv",
)


def redact_sensitive(data: Any, _depth: int = 0) -> Any:
    """Recursively redact secret-looking keys from dicts/lists.

    Used by the audit middleware before persisting request bodies and by
    anything else that needs to log user-supplied payloads.
    """
    if _depth > 8:  # defend against pathological nesting
        return "[TRUNCATED]"
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if isinstance(k, str) and any(s in k.lower() for s in _SENSITIVE_SUBSTRINGS):
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_sensitive(v, _depth + 1)
        return out
    if isinstance(data, list):
        return [redact_sensitive(v, _depth + 1) for v in data]
    return data


class _RedactingFilter(logging.Filter):
    """Redact sensitive values from log record `args` and `extra` fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact dict args (e.g., logger.info("...", {"password": "x"}))
        if isinstance(record.args, dict):
            record.args = self._redact_mapping(record.args)
        # Redact tuple args containing dicts
        elif isinstance(record.args, tuple):
            new_args = tuple(
                self._redact_mapping(a) if isinstance(a, dict) else a
                for a in record.args
            )
            record.args = new_args

        # Redact extra fields set via logger.info("...", extra={...})
        for key in list(vars(record).keys()):
            if key.lower() in _SENSITIVE_KEYS:
                setattr(record, key, "[REDACTED]")
        return True

    @staticmethod
    def _redact_mapping(d: dict) -> dict:
        out = {}
        for k, v in d.items():
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS:
                out[k] = "[REDACTED]"
            elif isinstance(v, dict):
                out[k] = _RedactingFilter._redact_mapping(v)
            else:
                out[k] = v
        return out


class _RequestContextFilter(logging.Filter):
    """Stamp every record with the current request_id (or "-" outside requests).

    Makes cross-file correlation possible: every log line produced while
    serving a request shares the id echoed to the client in X-Request-ID.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from app.core.request_context import get_request_id

            record.request_id = get_request_id() or "-"
        except Exception:
            record.request_id = "-"
        return True


def _build_formatter(use_json: bool) -> logging.Formatter:
    if use_json:
        try:
            from pythonjsonlogger import jsonlogger

            return jsonlogger.JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s",
                rename_fields={"levelname": "level", "asctime": "timestamp"},
            )
        except Exception:
            # If python-json-logger isn't installed, fall back to text format
            pass
    return logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s [req:%(request_id)s]: %(message)s"
    )


def configure_logging(
    environment: str,
    level: str = "INFO",
    log_dir: Optional[str] = None,
    retention_days: int = 30,
) -> None:
    """Configure root logger. Idempotent — safe to call multiple times.

    `environment` is the deployment env name (e.g. "development", "production").
    JSON output is used everywhere except development/testing.
    When `log_dir` is set, daily-rotating `app.log` (INFO+) and `error.log`
    (WARNING+) files are written there too, kept `retention_days` days.
    """
    root = logging.getLogger()

    # Clear default handlers so we don't double-log
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    use_json = environment not in ("development", "testing", "test")
    formatter = _build_formatter(use_json)
    redacting = _RedactingFilter()
    request_ctx = _RequestContextFilter()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(redacting)
    handler.addFilter(request_ctx)
    handler.setFormatter(formatter)
    root.addHandler(handler)

    # ── Rotating log files ──────────────────────────────────────────────────
    # Never let file-logging problems (read-only FS, permissions) take the
    # app down — stdout logging always survives.
    if log_dir:
        try:
            dir_path = Path(log_dir)
            if not dir_path.is_absolute():
                # Resolve relative to the backend root (apps/backend), not cwd.
                dir_path = Path(__file__).resolve().parent.parent.parent / dir_path
            dir_path.mkdir(parents=True, exist_ok=True)

            app_file = TimedRotatingFileHandler(
                dir_path / "app.log",
                when="midnight",
                backupCount=retention_days,
                encoding="utf-8",
                delay=True,
                utc=True,
            )
            app_file.addFilter(redacting)
            app_file.addFilter(request_ctx)
            app_file.setFormatter(formatter)
            root.addHandler(app_file)

            # Errors also land in their own file so "what broke this week"
            # never requires paging through request noise.
            err_file = TimedRotatingFileHandler(
                dir_path / "error.log",
                when="midnight",
                backupCount=retention_days,
                encoding="utf-8",
                delay=True,
                utc=True,
            )
            err_file.setLevel(logging.WARNING)
            err_file.addFilter(redacting)
            err_file.addFilter(request_ctx)
            err_file.setFormatter(formatter)
            root.addHandler(err_file)
        except Exception:
            logging.getLogger(__name__).exception(
                "Could not set up file logging in %s — continuing with stdout only",
                log_dir,
            )

    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Tame chatty third-party loggers. uvicorn.access stays muted because the
    # request-log middleware emits a richer access line (user, tenant, duration,
    # request id) via the "app.access" logger.
    for noisy in ("uvicorn.access", "passlib", "asyncio", "botocore", "boto3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


__all__ = ["configure_logging", "redact_sensitive"]
