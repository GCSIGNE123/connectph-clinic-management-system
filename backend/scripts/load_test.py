"""Phase 16 (Production Hardening) real, runnable load test.

Fires N concurrent logins and N concurrent queue-ticket creations against a
dedicated, obviously-labeled synthetic test tenant (never the real seeded
demo clinic `CONNECT.PH Demo Clinic`) and reports real p50/p95/max response
times plus success/failure counts.

Usage (from `backend/`, against a live dev server - defaults to :8006):

    python scripts/load_test.py --base-url http://localhost:8006 --concurrency 30

What it does, in order:
  1. Registers a fresh clinic (`LOADTEST-<random suffix>`) via the real
     `POST /auth/register` endpoint - a real Owner user, real DB rows,
     completely isolated from every other tenant by `clinic_id` scoping.
  2. Creates the minimum master data a queue ticket needs (branch,
     department, doctor, service) and N patients (one per concurrent
     ticket, to avoid the real "duplicate active ticket" 409 business rule
     tripping every concurrent request against the same patient).
  3. Fires `--concurrency` concurrent `POST /auth/login` calls, all against
     the same seeded Owner login - the realistic "many receptionists log
     in at shift start" scenario.
  4. Fires `--concurrency` concurrent `POST /queues` calls (one per
     pre-created patient) - the realistic "many reception desks creating
     tickets at once" scenario, and the one this app's own tests
     (`test_queues.py`) already prove is safe under real concurrency at the
     `QueueNumberGenerator` level; this script proves it end-to-end through
     the HTTP API instead of a direct repository call.
  5. Prints p50/p95/max/mean latency and success/failure counts for each
     phase, and does NOT delete the test clinic itself (multi-tenant
     isolation means it can never be seen by/leak into the real demo
     clinic's data) - whoever runs this can archive it afterward via the
     platform-admin API/portal if they want it fully removed, documented in
     the script's own final printout.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import string
import time

import httpx


def _rand_suffix(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * pct
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def _report(name: str, durations: list[float], failures: int, total: int) -> None:
    print(f"\n--- {name} ---")
    print(f"  total: {total}   success: {total - failures}   failed: {failures}")
    if durations:
        print(f"  p50: {_percentile(durations, 0.50) * 1000:.1f} ms")
        print(f"  p95: {_percentile(durations, 0.95) * 1000:.1f} ms")
        print(f"  max: {max(durations) * 1000:.1f} ms")
        print(f"  mean: {statistics.mean(durations) * 1000:.1f} ms")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8006")
    parser.add_argument("--concurrency", type=int, default=25)
    args = parser.parse_args()

    base = args.base_url.rstrip("/") + "/api/v1"
    suffix = _rand_suffix()
    clinic_name = f"LOADTEST-{suffix} Clinic"
    owner_email = f"loadtest-owner-{suffix.lower()}@connectph.dev"
    password = "LoadTest123!"

    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"Registering synthetic test clinic: {clinic_name!r} ({owner_email})")
        resp = await client.post(
            f"{base}/auth/register",
            json={
                "clinic_name": clinic_name,
                "clinic_slug": f"loadtest-{suffix.lower()}",
                "email": owner_email,
                "username": f"loadtest{suffix.lower()}",
                "password": password,
                "first_name": "Load",
                "last_name": "Test",
            },
        )
        resp.raise_for_status()
        access_token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        print("Creating minimal master data (branch, department, doctor, service)...")
        r = await client.post(f"{base}/branches", headers=headers, json={
            "name": "Main Branch", "code": "MAIN", "address": "N/A",
        })
        r.raise_for_status()
        branch = r.json()
        r = await client.post(f"{base}/departments", headers=headers, json={
            "name": "General", "department_code": "GEN",
        })
        r.raise_for_status()
        department = r.json()
        r = await client.post(f"{base}/doctors", headers=headers, json={
            "first_name": "Load", "last_name": "Doctor", "specialization": "General Medicine",
            "consultation_fee": 500, "department_id": department["id"],
        })
        r.raise_for_status()
        doctor = r.json()
        r = await client.post(f"{base}/services", headers=headers, json={
            "service_name": "Consultation", "service_code": "CONS", "default_price": 500,
            "department_id": department["id"],
        })
        r.raise_for_status()
        service = r.json()

        n = args.concurrency
        print(f"Creating {n} synthetic patients (one per concurrent queue-ticket request)...")
        patients = []
        for i in range(n):
            r = await client.post(f"{base}/patients", headers=headers, json={
                "first_name": f"LoadTest{i}", "last_name": "Patient",
                "birth_date": "1990-01-01", "gender": "Male", "civil_status": "Single",
                "mobile_number": f"09{random.randint(100000000, 999999999)}",
            })
            r.raise_for_status()
            patients.append(r.json()["patient"])

        # --- Phase A: concurrent logins ---
        async def do_login() -> float:
            start = time.perf_counter()
            r = await client.post(f"{base}/auth/login", json={
                "email_or_username": owner_email, "password": password,
            })
            elapsed = time.perf_counter() - start
            if r.status_code != 200:
                raise RuntimeError(f"login failed: {r.status_code} {r.text}")
            return elapsed

        login_durations: list[float] = []
        login_failures = 0
        results = await asyncio.gather(*(do_login() for _ in range(n)), return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                login_failures += 1
            else:
                login_durations.append(r)
        _report(f"Concurrent logins (n={n})", login_durations, login_failures, n)
        if login_failures:
            print(
                "  NOTE: failures here are very likely the real login rate limiter "
                "(RATE_LIMIT_LOGIN_MAX_ATTEMPTS, see app/core/config.py) correctly rejecting "
                "attempts beyond its per-IP window when this many logins fire from one machine "
                "in a burst - a real, working defense, not a load-test bug. Re-run with a lower "
                "--concurrency (<= the configured max attempts) to measure pure login latency "
                "without tripping it."
            )

        # --- Phase B: concurrent queue-ticket creations, one per patient ---
        async def do_create_queue(patient_id: str) -> float:
            start = time.perf_counter()
            r = await client.post(f"{base}/queues", headers=headers, json={
                "patient_id": patient_id, "branch_id": branch["id"],
                "department_id": department["id"], "doctor_id": doctor["id"],
                "service_id": service["id"], "priority": "Normal",
            })
            elapsed = time.perf_counter() - start
            if r.status_code not in (200, 201):
                raise RuntimeError(f"queue create failed: {r.status_code} {r.text}")
            return elapsed

        queue_durations: list[float] = []
        queue_failures = 0
        results = await asyncio.gather(*(do_create_queue(p["id"]) for p in patients), return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                queue_failures += 1
                print(f"  queue creation error: {r}")
            else:
                queue_durations.append(r)
        _report(f"Concurrent queue-ticket creations (n={n})", queue_durations, queue_failures, n)

    print(
        f"\nDone. Synthetic test clinic '{clinic_name}' left in the database, fully isolated by "
        "clinic_id (never visible from any other tenant's queries) - archive it via the "
        "platform-admin API/portal (`PATCH /platform-admin/tenants/{clinic_id}/archive`) if you "
        "want it fully removed; it does not affect the real seeded demo clinic's data or counts."
    )


if __name__ == "__main__":
    asyncio.run(main())
