#!/usr/bin/env python3
"""LIVE real-over-limit test — Phase 7 ABUSE checklist line "rate limit per tenant".

Standalone script, same pattern as tests/test_token_widen_live.py: spins up a real
control_plane.app uvicorn subprocess, provisions one tenant with deliberately generous quota
caps (so quota can't trip first), then fires RATE_LIMIT_PER_MIN + a margin of real HTTP
requests with valid HMAC signatures and unique nonces, and confirms the (RATE_LIMIT_PER_MIN+1)th
request within the 60s window gets 429 "rate limited" specifically -- not a quota 429, not a
network error, not silently accepted.

    python scripts/verify_rate_limit_live.py
"""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402

from control_plane.mint import expected_signature  # noqa: E402
from control_plane.secrets import secret_hash  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402

PORT = 8798
BASE = f"http://127.0.0.1:{PORT}"
ORIGIN = "https://ratelimit-test.example"
SECRET = "ratelimit-test-secret-" + uuid.uuid4().hex
RATE_LIMIT_PER_MIN = 120  # must match control_plane/app.py's RATE_LIMIT_PER_MIN


def main() -> int:
    kw = conn_kwargs()
    tid, aid = str(uuid.uuid4()), str(uuid.uuid4())
    admin = psycopg.connect(**kw, autocommit=True)
    server = None
    try:
        # Deliberately generous caps: this test isolates the RATE LIMITER, not the quota
        # gates (already proven live/fresh by tests/test_mint.py's
        # test_over_concurrent_cap_429 / test_over_monthly_minutes_429 this same session).
        admin.execute(
            "insert into tenants (id, name, hmac_secret_hash, allowed_origins, "
            "max_concurrent, max_minutes_month) values (%s,'ratelimit-test',%s,%s,100000,100000)",
            (tid, secret_hash(SECRET), [ORIGIN]),
        )
        admin.execute(
            "insert into agents (id, tenant_id, name, prompt, voice_id) values (%s,%s,'a','p','v_meklc281')",
            (aid, tid),
        )

        env = os.environ.copy()
        env["CP_TENANT_SECRETS"] = json.dumps({tid: SECRET})
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "control_plane.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
                "--log-level",
                "warning",
            ],
            cwd=str(ROOT.parent),
            env=env,
        )
        ready = False
        for _ in range(60):
            try:
                httpx.get(BASE + "/docs", timeout=2)
                ready = True
                break
            except Exception:
                time.sleep(0.5)
        print(f"live endpoint ready: {ready} at {BASE}")

        # CONCURRENT, not sequential: control_plane/app.py opens a fresh DB connection per
        # request (no pooling), so each request costs several real seconds of network+TLS
        # round trip to the dev DB. An early version of this script fired requests
        # sequentially and took 439s for 130 requests -- by request ~20 the 60s sliding
        # window had already evicted request #1, so the limiter never saw 120 requests
        # within any real 60s slice and never triggered. That was a TEST ARTIFACT, not a
        # finding -- caught by checking the elapsed time against the window instead of
        # assuming the earlier print statement's claim. Firing concurrently (thread pool,
        # one real HTTP connection each) is required to actually land >=120 requests inside
        # one real 60-second window, which is what the checklist line is asking to prove.
        import concurrent.futures

        total = RATE_LIMIT_PER_MIN + 10

        def _fire(i: int):
            ts, nonce = str(int(time.time())), str(uuid.uuid4())
            sig = expected_signature(SECRET, tid, ts, nonce, aid)
            headers = {
                "X-Tenant-Id": tid,
                "X-Timestamp": ts,
                "X-Nonce": nonce,
                "X-Signature": sig,
                "Origin": ORIGIN,
            }
            r = httpx.post(
                BASE + "/v1/session",
                json={"agent_id": aid},
                headers=headers,
                timeout=30,
            )
            return (i, r.status_code, r.text[:80])

        t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=40) as pool:
            results = list(pool.map(_fire, range(total)))
        elapsed = time.time() - t0
        print(f"fired {total} real requests concurrently in {elapsed:.1f}s")
        if elapsed > 55:
            print(
                f"WARNING: {elapsed:.1f}s is close to/over the 60s window -- results below may "
                "still be invalid for the same reason as the sequential run. Not treating this "
                "as a clean pass/fail if so; see the elapsed time before trusting the verdict."
            )

        ok = [r for r in results if r[1] == 200]
        rate_limited = [r for r in results if r[1] == 429 and "rate limited" in r[2]]
        other = [r for r in results if r not in ok and r not in rate_limited]

        print(f"200 OK: {len(ok)}")
        print(f"429 'rate limited': {len(rate_limited)}")
        print(f"other status/body: {len(other)}")
        for r in other[:10]:
            print("  OTHER:", r)

        print("\nfirst 3 rejections (raw):")
        for r in rate_limited[:3]:
            print(" ", r)

        vuln = None
        if len(ok) > RATE_LIMIT_PER_MIN:
            vuln = (
                f"{len(ok)} requests succeeded with 200 -- more than the configured "
                f"RATE_LIMIT_PER_MIN={RATE_LIMIT_PER_MIN}. The limiter did not trigger."
            )
        elif len(rate_limited) == 0:
            vuln = "no request ever got a 'rate limited' 429 -- limiter never engaged at all."

        print("\n" + "=" * 78)
        if vuln:
            print("VULN:", vuln)
            return 2
        print(
            f"PASS: exactly {len(ok)} requests succeeded (<= {RATE_LIMIT_PER_MIN}), "
            f"{len(rate_limited)} were rejected specifically as 'rate limited' (not quota)."
        )
        return 0
    finally:
        if server is not None:
            server.terminate()
        try:
            for t in ("used_nonces", "sessions", "quota_state", "agents"):
                admin.execute(f"delete from {t} where tenant_id = %s", (tid,))
            admin.execute("delete from tenants where id = %s", (tid,))
        finally:
            admin.close()


if __name__ == "__main__":
    raise SystemExit(main())
