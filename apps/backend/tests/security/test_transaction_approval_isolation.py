"""
Opportunity-transaction approval-workflow cross-tenant isolation harness.

Runs against a live backend (default: http://127.0.0.1:8000/api/v1) using two
pre-seeded tenants (admin@tutterfly.com / admin-health@tutterfly.com).

The Sales → Accounts approval workflow adds three state-changing endpoints on a
ledger transaction:
    POST /opportunities/{id}/transactions/{txn}/verify
    POST /opportunities/{id}/transactions/{txn}/approve
    POST /opportunities/{id}/transactions/{txn}/reject

Flow:
  1. Tenant A creates an opportunity + a transaction (starts pending_verification).
  2. Sanity: A verifies → approves its OWN transaction (happy path, 200 + states).
  3. Tenant B lists A's transactions            → expects 404 (opportunity hidden).
  4. Tenant B verifies A's transaction          → expects 404 (NOT 200).
  5. Tenant B approves A's transaction           → expects 404 (NOT 200).
  6. Tenant B rejects A's transaction            → expects 404 (NOT 200).

A 200 on 3/4/5/6 is a real cross-tenant leak — one tenant mutating another
tenant's financial records.

Run:
    python tests/security/test_transaction_approval_isolation.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api/v1")
TIMEOUT = 30.0

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


async def _session(client: httpx.AsyncClient, key: str) -> dict:
    creds = TENANTS[key]
    resp = await client.post(
        f"{BASE_URL}/auth/login",
        json={"email": creds["email"], "password": creds["password"]},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed for {creds['email']}: {resp.status_code} {resp.text[:200]}")
    data = resp.json()
    return {
        "label": creds["label"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "tenant_id": data.get("user", {}).get("tenant_id"),
    }


async def run() -> bool:
    results = Results()
    ts = int(time.time())
    blocked = {403, 404}

    print("\n" + "=" * 64)
    print("  OPPORTUNITY-TRANSACTION APPROVAL CROSS-TENANT ISOLATION")
    print(f"  Backend: {BASE_URL}")
    print("=" * 64)

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

        # --- 1. A creates an opportunity + a transaction ---
        stages = await client.get(f"{BASE_URL}/opportunities/sales-stages", headers=a["headers"])
        if stages.status_code != 200 or not stages.json():
            results.skip("Setup", "no sales stages seeded for Tenant A")
            return results.summary()

        opp = await client.post(
            f"{BASE_URL}/opportunities/",
            json={"name": f"A Approval Opp {ts}", "amount": 1000.0, "sales_stage_id": stages.json()[0]["id"]},
            headers=a["headers"],
        )
        if opp.status_code not in (200, 201):
            results.fail("Create opportunity as A", f"{opp.status_code} -- {opp.text[:200]}")
            return results.summary()
        opp_id = opp.json()["id"]

        txn_resp = await client.post(
            f"{BASE_URL}/opportunities/{opp_id}/transactions",
            json={"transaction_type": "Receive", "amount": 500.0},
            headers=a["headers"],
        )
        if txn_resp.status_code not in (200, 201):
            results.fail("Create transaction as A", f"{txn_resp.status_code} -- {txn_resp.text[:200]}")
            return results.summary()
        txn = txn_resp.json()
        txn_id = txn["id"]
        if txn.get("approval_status") == "pending_verification":
            results.ok("A's new transaction starts as pending_verification")
        else:
            results.fail("Initial status", f"expected pending_verification, got {txn.get('approval_status')}")

        # --- 2. Sanity: A verifies then approves its OWN transaction ---
        v = await client.post(
            f"{BASE_URL}/opportunities/{opp_id}/transactions/{txn_id}/verify", headers=a["headers"]
        )
        if v.status_code == 200 and v.json().get("approval_status") == "verified":
            results.ok("Sanity: A can verify own transaction (→ verified)")
        else:
            results.fail("Sanity verify", f"{v.status_code} -- {v.text[:200]}")

        ap = await client.post(
            f"{BASE_URL}/opportunities/{opp_id}/transactions/{txn_id}/approve", headers=a["headers"]
        )
        if ap.status_code == 200 and ap.json().get("approval_status") == "approved":
            results.ok("Sanity: A can approve own transaction (→ approved)")
        else:
            results.fail("Sanity approve", f"{ap.status_code} -- {ap.text[:200]}")

        # Fresh pending transaction for the cross-tenant mutation attempts.
        txn2_resp = await client.post(
            f"{BASE_URL}/opportunities/{opp_id}/transactions",
            json={"transaction_type": "Pay", "amount": 250.0},
            headers=a["headers"],
        )
        if txn2_resp.status_code not in (200, 201):
            results.skip("Cross-tenant setup", "could not create a second transaction")
            return results.summary()
        txn2_id = txn2_resp.json()["id"]

        # --- 3. B lists A's transactions ---
        r = await client.get(f"{BASE_URL}/opportunities/{opp_id}/transactions", headers=b["headers"])
        results.ok(f"B cross-tenant list blocked ({r.status_code})") if r.status_code in blocked else \
            results.fail("B list", f"expected 404/403, got {r.status_code}")

        # --- 4. B verifies A's transaction ---
        r = await client.post(
            f"{BASE_URL}/opportunities/{opp_id}/transactions/{txn2_id}/verify", headers=b["headers"]
        )
        results.ok(f"B cross-tenant verify blocked ({r.status_code})") if r.status_code in blocked else \
            results.fail("B verify", f"expected 404/403, got {r.status_code} -- {r.text[:200]}")

        # --- 5. B approves A's transaction ---
        r = await client.post(
            f"{BASE_URL}/opportunities/{opp_id}/transactions/{txn2_id}/approve", headers=b["headers"]
        )
        results.ok(f"B cross-tenant approve blocked ({r.status_code})") if r.status_code in blocked else \
            results.fail("B approve", f"expected 404/403, got {r.status_code} -- {r.text[:200]}")

        # --- 6. B rejects A's transaction ---
        r = await client.post(
            f"{BASE_URL}/opportunities/{opp_id}/transactions/{txn2_id}/reject",
            json={"reason": "malicious"},
            headers=b["headers"],
        )
        results.ok(f"B cross-tenant reject blocked ({r.status_code})") if r.status_code in blocked else \
            results.fail("B reject", f"expected 404/403, got {r.status_code} -- {r.text[:200]}")

        # --- 7. B's approval queue must not leak A's transactions ---
        r = await client.get(
            f"{BASE_URL}/opportunities/transactions/approval-queue", headers=b["headers"]
        )
        if r.status_code == 200:
            leaked = [t for t in r.json() if t.get("id") in (txn_id, txn2_id)]
            results.fail("B queue leak", f"B's queue returned A's transactions: {[t['id'] for t in leaked]}") if leaked else \
                results.ok("B approval queue does not leak A's transactions")
        elif r.status_code in blocked:
            results.ok(f"B approval queue permission-gated ({r.status_code})")
        else:
            results.skip("B queue", f"unexpected status {r.status_code}")

        # --- Sanity: A's second transaction remains untouched by B's attempts ---
        check = await client.get(f"{BASE_URL}/opportunities/{opp_id}/transactions", headers=a["headers"])
        if check.status_code == 200:
            match = [t for t in check.json() if t["id"] == txn2_id]
            if match and match[0].get("approval_status") == "pending_verification":
                results.ok("A's transaction still pending_verification after B's attempts")
            else:
                results.fail("Integrity", f"A's txn state changed: {match[:1]}")

    return results.summary()


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(run()) else 1)
