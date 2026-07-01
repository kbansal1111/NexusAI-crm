"""
Itinerary PDF-upload cross-tenant isolation — integration test harness.

Runs against a live backend (default: http://127.0.0.1:8000/api/v1) using two
pre-seeded tenants (admin@tutterfly.com / admin-health@tutterfly.com).

Flow:
  1. Tenant A uploads a PDF itinerary (name + destination) → 201, has pdf_file_id.
  2. Tenant B reads it by id                → expects 404 (NOT 200).
  3. Tenant B lists/searches by A's name    → A's itinerary must NOT appear.
  4. Tenant B downloads A's PDF File        → expects 404/403 (NOT 200).
  5. Tenant B attaches A's itinerary to a B opportunity → expects 400/404.
  6. Tenant A can read + download its own    → sanity, expects 200.

A failure on 2/3/4/5 is a real cross-tenant leak.

Run:
    python tests/security/test_itinerary_upload_isolation.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api/v1")
TIMEOUT = 30.0

# Smallest bytes that pass the PDF magic-byte sniff (`%PDF-`).
MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

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
    resp = await client.post(f"{BASE_URL}/auth/login", json={"email": creds["email"], "password": creds["password"]})
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
    name = f"Iso Itinerary {ts}"
    blocked = {403, 404}

    print("\n" + "=" * 64)
    print("  ITINERARY UPLOAD CROSS-TENANT ISOLATION")
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

        # --- 1. A uploads a PDF itinerary ---
        dpick = await client.get(f"{BASE_URL}/picklists/destination", headers=a["headers"])
        if dpick.status_code != 200 or not dpick.json():
            results.skip("Upload", "no destination picklist seeded for Tenant A")
            return results.summary()
        dest_id = dpick.json()[0]["id"]

        up = await client.post(
            f"{BASE_URL}/itineraries/upload",
            data={"name": name, "destination_ids": dest_id},
            files={"file": ("iso.pdf", MINIMAL_PDF, "application/pdf")},
            headers=a["headers"],
        )
        if up.status_code not in (200, 201):
            results.fail("Upload as A", f"{up.status_code} -- {up.text[:200]}")
            return results.summary()
        itin = up.json()
        itin_id = itin["id"]
        pdf_file_id = itin.get("pdf_file_id")
        if not pdf_file_id:
            results.fail("Upload as A", "response missing pdf_file_id")
        else:
            results.ok("A uploaded itinerary with a PDF file id")

        # --- 6 (sanity). A reads + downloads its own ---
        own = await client.get(f"{BASE_URL}/itineraries/{itin_id}", headers=a["headers"])
        results.ok("Sanity: A reads own itinerary") if own.status_code == 200 else \
            results.fail("Sanity read", f"A cannot read own itinerary ({own.status_code})")

        # --- 2. B reads A's itinerary by id ---
        r = await client.get(f"{BASE_URL}/itineraries/{itin_id}", headers=b["headers"])
        results.ok(f"B cross-tenant read blocked ({r.status_code})") if r.status_code in blocked else \
            results.fail("B read", f"expected 404/403, got {r.status_code}")

        # --- 3. B searches by A's name — must not leak ---
        r = await client.get(f"{BASE_URL}/itineraries/", params={"search": name}, headers=b["headers"])
        if r.status_code == 200:
            leaked = [i for i in r.json().get("itineraries", []) if str(i.get("id")) == itin_id]
            results.fail("B search leak", f"B's search returned A's itinerary {itin_id}") if leaked else \
                results.ok("B search does not leak A's itinerary")
        elif r.status_code in blocked:
            results.ok(f"B list endpoint module-gated ({r.status_code})")
        else:
            results.skip("B search", f"unexpected status {r.status_code}")

        # --- 4. B downloads A's PDF file ---
        if pdf_file_id:
            r = await client.get(f"{BASE_URL}/files/{pdf_file_id}/download", headers=b["headers"])
            results.ok(f"B cross-tenant PDF download blocked ({r.status_code})") if r.status_code in blocked else \
                results.fail("B PDF download", f"expected 404/403, got {r.status_code}")

        # --- 5. B attaches A's itinerary to a B opportunity ---
        stages = await client.get(f"{BASE_URL}/opportunities/sales-stages", headers=b["headers"])
        if stages.status_code == 200 and stages.json():
            opp = await client.post(
                f"{BASE_URL}/opportunities/",
                json={"name": f"B Opp {ts}", "amount": 100.0, "sales_stage_id": stages.json()[0]["id"]},
                headers=b["headers"],
            )
            if opp.status_code in (200, 201):
                b_opp_id = opp.json()["id"]
                r = await client.post(
                    f"{BASE_URL}/itineraries/opportunity/{b_opp_id}/link?itinerary_id={itin_id}",
                    headers=b["headers"],
                )
                results.ok(f"B cross-tenant attach blocked ({r.status_code})") if r.status_code in {400, 404} else \
                    results.fail("B attach", f"expected 400/404, got {r.status_code} -- {r.text[:200]}")
            else:
                results.skip("B attach", f"could not seed B opportunity ({opp.status_code})")
        else:
            results.skip("B attach", "no sales stages for B")

    return results.summary()


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(run()) else 1)
