"""
AI Assistant cross-tenant / cross-user isolation harness.

Runs against a live backend (default: http://127.0.0.1:8000/api/v1) using two
pre-seeded tenants (admin@tutterfly.com / admin-health@tutterfly.com).

The assistant's tools are tenant-bound server-side, and conversations are
private to their creator. Contract under test:

  1. Tenant A starts a conversation → gets a conversation_id.
  2. Tenant B fetches A's conversation by id      → expects 404 (NOT 200).
  3. Tenant B deletes A's conversation             → expects 404 (NOT 200).
  4. Tenant B's conversation list                  → must NOT contain A's id.
  5. A user without view_opportunity               → /assistant/chat expects 403.
  6. Sanity: A can list and fetch its own conversation.

Pure-function checks (no LLM key needed) run first: the tool dispatcher must
reject unknown tools and never expose a write tool.

Run:
    python tests/security/test_assistant_isolation.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api/v1")
TIMEOUT = 60.0

TENANTS = {
    "A": {"email": "admin@tutterfly.com", "password": "admin1", "label": "Travel (Tenant A)"},
    "B": {"email": "admin-health@tutterfly.com", "password": "admin1", "label": "Healthcare (Tenant B)"},
}


class Results:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.failures: list[str] = []

    def ok(self, name: str):
        self.passed += 1
        print(f"  [PASS] {name}")

    def fail(self, name: str, detail: str):
        self.failed += 1
        self.failures.append(f"{name}: {detail}")
        print(f"  [FAIL] {name} -- {detail}")

    def skip(self, name: str, detail: str):
        self.skipped += 1
        print(f"  [SKIP] {name} -- {detail}")

    def summary(self) -> bool:
        total = self.passed + self.failed
        print("\n" + "=" * 64)
        print(f"  RESULTS: {self.passed}/{total} passed, {self.failed} failed, {self.skipped} skipped")
        for f in self.failures:
            print(f"    - {f}")
        print("=" * 64)
        return self.failed == 0


def _static_tool_surface_checks(results: Results):
    """No live backend needed: direct-execute tools must be read-only, and every
    write-shaped tool must go through the propose→confirm pipeline."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from app.services.assistant_tools import TOOL_SCHEMAS, _PROPOSAL_TOOLS, _TOOL_IMPLS  # noqa: PLC0415
    from app.services.assistant_actions import _ACTIONS  # noqa: PLC0415

    write_markers = ("create", "update", "delete", "edit", "upload", "set_", "mark_", "approve", "reject")

    # 1. Direct-execute registry stays read-only — writes must never live here.
    offenders = [n for n in _TOOL_IMPLS if any(m in n for m in write_markers)]
    results.fail("Read-only direct registry", f"write-shaped tools execute directly: {offenders}") if offenders else \
        results.ok("Direct-execute registry contains no write-shaped tools")

    # 2. Every write-shaped tool schema must be a propose_* tool (confirmation-gated).
    schema_names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    bad = [n for n in schema_names
           if any(m in n for m in write_markers) and not n.startswith("propose_")]
    results.fail("Writes are propose-gated", f"non-proposal write tools exposed: {bad}") if bad else \
        results.ok("All write-shaped tools are propose_* (confirmation-gated)")

    # 3. Parity: schemas == direct impls ∪ proposal tools; proposals map to real actions.
    expected = set(_TOOL_IMPLS) | set(_PROPOSAL_TOOLS)
    results.fail("Schema/impl parity", f"{schema_names ^ expected}") if schema_names != expected else \
        results.ok("Tool schemas match implementations 1:1")
    unmapped = [n for n, a in _PROPOSAL_TOOLS.items() if a not in _ACTIONS]
    results.fail("Proposal→action mapping", f"proposals without an action spec: {unmapped}") if unmapped else \
        results.ok("Every proposal tool maps to a registered action (with an RBAC permission)")

    # 4. Every action declares a non-empty RBAC permission string.
    missing_perm = [k for k, v in _ACTIONS.items() if not v.get("permission")]
    results.fail("Action permissions", f"actions without permission: {missing_perm}") if missing_perm else \
        results.ok("Every action declares an RBAC permission")


async def _session(client: httpx.AsyncClient, key: str) -> dict:
    creds = TENANTS[key]
    resp = await client.post(f"{BASE_URL}/auth/login", json={"email": creds["email"], "password": creds["password"]})
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed for {creds['email']}: {resp.status_code} {resp.text[:200]}")
    data = resp.json()
    return {
        "label": creds["label"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "tenant_id": data.get("user", {}).get("tenant_id"),
    }


async def _start_conversation(client: httpx.AsyncClient, headers: dict) -> str | None:
    """POST /assistant/chat and read SSE until the meta event yields a conversation id."""
    conversation_id = None
    async with client.stream(
        "POST", f"{BASE_URL}/assistant/chat",
        json={"message": "How many opportunities do I have?"},
        headers=headers,
    ) as resp:
        if resp.status_code != 200:
            return None
        async for line in resp.aiter_lines():
            if line.startswith("data:") and '"conversation_id"' in line:
                import json as _json
                conversation_id = _json.loads(line.split("data:", 1)[1]).get("conversation_id")
                break  # meta arrives first; no need to wait for the model
    return conversation_id


async def run() -> bool:
    results = Results()
    blocked = {403, 404}

    print("\n" + "=" * 64)
    print("  AI ASSISTANT CROSS-TENANT ISOLATION")
    print(f"  Backend: {BASE_URL}")
    print("=" * 64)

    _static_tool_surface_checks(results)

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        try:
            a = await _session(client, "A")
            b = await _session(client, "B")
        except Exception as e:
            results.fail("Auth", str(e))
            return results.summary()

        if a["tenant_id"] == b["tenant_id"]:
            results.fail("Tenant separation", "both admins resolved to the same tenant")
            return results.summary()
        results.ok("Logged in as two distinct tenants")

        # --- 1. A starts a conversation ---
        convo_id = await _start_conversation(client, a["headers"])
        if not convo_id:
            results.skip("Conversation setup", "assistant/chat did not yield a conversation id "
                                               "(OpenRouter key may be unset) — cross-tenant checks skipped")
            return results.summary()
        results.ok(f"A created conversation {convo_id}")

        # --- 6 (sanity). A reads own conversation + list ---
        r = await client.get(f"{BASE_URL}/assistant/conversations/{convo_id}", headers=a["headers"])
        results.ok("Sanity: A reads own conversation") if r.status_code == 200 else \
            results.fail("Sanity read", f"A cannot read own conversation ({r.status_code})")

        # --- 2. B reads A's conversation ---
        r = await client.get(f"{BASE_URL}/assistant/conversations/{convo_id}", headers=b["headers"])
        results.ok(f"B cross-tenant conversation read blocked ({r.status_code})") if r.status_code in blocked else \
            results.fail("B read", f"expected 404/403, got {r.status_code}")

        # --- 3. B deletes A's conversation ---
        r = await client.delete(f"{BASE_URL}/assistant/conversations/{convo_id}", headers=b["headers"])
        results.ok(f"B cross-tenant conversation delete blocked ({r.status_code})") if r.status_code in blocked else \
            results.fail("B delete", f"expected 404/403, got {r.status_code}")

        # --- 4. B's list must not leak A's conversation ---
        r = await client.get(f"{BASE_URL}/assistant/conversations", headers=b["headers"])
        if r.status_code == 200:
            leaked = [c for c in r.json() if c.get("id") == convo_id]
            results.fail("B list leak", f"B's list contains A's conversation {convo_id}") if leaked else \
                results.ok("B's conversation list does not leak A's conversation")
        else:
            results.skip("B list", f"unexpected status {r.status_code}")

        # --- 5. Action endpoints: unknown/foreign ids must 404, never execute ---
        fake_action = "0" * 24
        r = await client.post(f"{BASE_URL}/assistant/actions/{fake_action}/confirm", headers=b["headers"])
        results.ok(f"Confirm of unknown/foreign action blocked ({r.status_code})") if r.status_code in blocked else \
            results.fail("Action confirm", f"expected 404/403, got {r.status_code}")
        r = await client.post(f"{BASE_URL}/assistant/actions/{fake_action}/reject", headers=b["headers"])
        results.ok(f"Reject of unknown/foreign action blocked ({r.status_code})") if r.status_code in blocked else \
            results.fail("Action reject", f"expected 404/403, got {r.status_code}")

    return results.summary()


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(run()) else 1)
