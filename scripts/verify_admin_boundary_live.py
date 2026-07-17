#!/usr/bin/env python3
"""LIVE automated check — docs/27-PHASE-7-SECURITY.md ADMIN BOUNDARY section (ADR-021).

This is the AUTOMATED checklist run (same tier as SECRETS/TENANCY/TOKEN MINT/ABUSE/DEPS), run by
the agent as part of Phase 7's automated pass. It is DISTINCT from
tests/test_admin_boundary_live.py, the narrated HUMAN-GATE script reserved for the human to run
personally as item 3 of the human gate -- running this script does not satisfy that gate.

Covers the 5 ADMIN BOUNDARY lines exactly:
  1. admin JWT cannot be used as a tenant/LiveKit token on any control_plane/ endpoint -> rejected
  2. tenant/LiveKit token cannot be used as an admin JWT on any admin/ endpoint -> 401
  3. expired admin JWT -> 401
  4. tampered admin JWT (re-signed with a wrong secret, OR with `video` grafted on) -> 401
  5. admin login without correct TOTP code -> 401 (password alone insufficient)

Spins up BOTH admin.app and control_plane.app as real uvicorn subprocesses, makes real calls to
LiveKit Cloud's own /rtc/validate for line 1's LiveKit-side check. No Uplift calls.

    python scripts/verify_admin_boundary_live.py
"""

import datetime
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import jwt as pyjwt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import psycopg  # noqa: E402
from dotenv import dotenv_values  # noqa: E402
from livekit import api as lk_api  # noqa: E402

from admin.auth import ADMIN_JWT_AUDIENCE, ADMIN_JWT_ISSUER, provision_admin  # noqa: E402
from admin.security import random_base32_secret, totp_now  # noqa: E402
from control_plane.mint import expected_signature  # noqa: E402
from control_plane.secrets import secret_hash  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402

ADMIN_PORT = 8802
CP_PORT = 8803
ADMIN_BASE = f"http://127.0.0.1:{ADMIN_PORT}"
CP_BASE = f"http://127.0.0.1:{CP_PORT}"
CFG = dotenv_values(ROOT / ".env.local")
LK_HTTPS = (
    CFG.get("LIVEKIT_URL", "").replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
)
WRONG_SECRET = "attacker-does-not-have-ADMIN_JWT_SECRET-" + uuid.uuid4().hex

results: list[tuple[str, bool, str]] = []


def hr(t: str) -> None:
    print("\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78)


def record(name: str, passed: bool, detail: str) -> None:
    results.append((name, passed, detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name} :: {detail}")


def wait_ready(base: str) -> bool:
    for _ in range(60):
        try:
            httpx.get(base + "/docs", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    kw = conn_kwargs()
    admin_conn = psycopg.connect(**kw, connect_timeout=30, autocommit=True)
    admin_srv = cp_srv = None
    admin_id = None
    tid = str(uuid.uuid4())
    aid = str(uuid.uuid4())
    email = f"gate-abcheck-{uuid.uuid4().hex[:8]}@uva-dev.local"
    password = "abcheck-pw-" + uuid.uuid4().hex
    totp_secret = random_base32_secret()
    try:
        hr("SETUP")
        admin_id = provision_admin(
            admin_conn, email=email, password=password, totp_secret=totp_secret
        )
        tenant_secret = "abcheck-tenant-secret-" + uuid.uuid4().hex
        admin_conn.execute(
            "insert into tenants (id, name, hmac_secret_hash, allowed_origins) values (%s,'abcheck',%s,%s)",
            (tid, secret_hash(tenant_secret), ["https://abcheck.example"]),
        )
        admin_conn.execute(
            "insert into agents (id, tenant_id, name, prompt, voice_id) values (%s,%s,'a','p','v_meklc281')",
            (aid, tid),
        )
        print(f"admin_id={admin_id} tenant_id={tid}")

        admin_srv = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "admin.app:app", "--host", "127.0.0.1",
             "--port", str(ADMIN_PORT), "--log-level", "warning"],
            cwd=str(ROOT), env=os.environ.copy(),
        )
        cp_env = os.environ.copy()
        cp_env["CP_TENANT_SECRETS"] = json.dumps({tid: tenant_secret})
        cp_srv = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "control_plane.app:app", "--host", "127.0.0.1",
             "--port", str(CP_PORT), "--log-level", "warning"],
            cwd=str(ROOT), env=cp_env,
        )
        print(f"admin.app ready: {wait_ready(ADMIN_BASE)} | control_plane.app ready: {wait_ready(CP_BASE)}")

        real_secret = dotenv_values(ROOT / ".env.local").get("ADMIN_JWT_SECRET")
        assert real_secret, "ADMIN_JWT_SECRET must already exist in .env.local (Phase 6 set it)"

        code = totp_now(totp_secret)
        login_r = httpx.post(
            ADMIN_BASE + "/admin/login",
            json={"email": email, "password": password, "totp_code": code},
            timeout=15,
        )
        genuine_admin_jwt = login_r.json()["token"]
        print(f"real admin login: {login_r.status_code}")

        # ---- LINE 1: admin JWT used as a tenant/LiveKit token on a control_plane/ endpoint ----
        hr("LINE 1a — admin JWT presented to control_plane's own endpoint (as a header value)")
        # control_plane/app.py's ONLY endpoint (POST /v1/session) authenticates via HMAC headers,
        # never a Bearer JWT -- there is no code path that would even try to interpret an admin
        # JWT as tenant auth here. Confirm precisely what happens: the request is missing the
        # required HMAC headers regardless of what's in Authorization, so it must be rejected,
        # not silently accepted.
        r = httpx.post(
            CP_BASE + "/v1/session",
            json={"agent_id": aid},
            headers={"Authorization": f"Bearer {genuine_admin_jwt}"},
            timeout=15,
        )
        print(f"POST /v1/session with admin JWT as Authorization Bearer (no HMAC headers): {r.status_code} | {r.text[:150]}")
        ok = r.status_code in (401, 422)
        record("line1a: admin JWT alone (no HMAC headers) rejected by control_plane", ok, f"{r.status_code}")

        hr("LINE 1b — admin JWT's claims used to forge an HMAC signature (attacker tries anyway)")
        # Even generously assuming an attacker tries to sign a request using the admin JWT's
        # RAW STRING as if it were the tenant's HMAC secret (a category-confusion attempt), the
        # mint computes HMAC against the tenant's REAL stored secret hash -- unrelated to any JWT.
        ts, nonce = str(int(time.time())), str(uuid.uuid4())
        bogus_sig = expected_signature(genuine_admin_jwt, tid, ts, nonce, aid)
        r = httpx.post(
            CP_BASE + "/v1/session",
            json={"agent_id": aid},
            headers={
                "X-Tenant-Id": tid, "X-Timestamp": ts, "X-Nonce": nonce,
                "X-Signature": bogus_sig, "Origin": "https://abcheck.example",
            },
            timeout=15,
        )
        print(f"POST /v1/session, HMAC computed using the admin JWT as the 'secret': {r.status_code} | {r.text[:150]}")
        ok = r.status_code == 401
        record("line1b: admin-JWT-as-HMAC-secret forgery rejected", ok, f"{r.status_code}")

        hr("LINE 1c — admin JWT presented to LiveKit Cloud's OWN /rtc/validate (the real tenant/room gate)")
        r = httpx.get(f"{LK_HTTPS}/rtc/validate", params={"access_token": genuine_admin_jwt}, timeout=20)
        print(f"LiveKit /rtc/validate(admin JWT): {r.status_code} | {r.text.strip()[:150]}")
        ok = r.status_code != 200
        record("line1c: admin JWT rejected by LiveKit's own token validator", ok, f"{r.status_code} {r.text.strip()[:100]}")

        # ---- LINE 2: tenant/LiveKit token used as an admin JWT ----
        hr("LINE 2 — real tenant/LiveKit AccessToken used as admin bearer token")
        tenant_token = (
            lk_api.AccessToken(CFG.get("LIVEKIT_API_KEY", "devkey"), CFG.get("LIVEKIT_API_SECRET", "devsecret0123456789012345678901234567"))
            .with_identity(str(uuid.uuid4()))
            .with_ttl(datetime.timedelta(seconds=120))
            .with_metadata(json.dumps({"tenant_id": tid, "agent_id": aid}))
            .with_grants(lk_api.VideoGrants(room_join=True, room=str(uuid.uuid4()), can_publish=True))
            .to_jwt()
        )
        r = httpx.get(ADMIN_BASE + "/admin/tenants", headers={"Authorization": f"Bearer {tenant_token}"}, timeout=15)
        print(f"GET /admin/tenants with real tenant/LiveKit token: {r.status_code} | {r.text[:150]}")
        ok = r.status_code == 401
        record("line2: tenant/LiveKit token rejected by admin/ endpoint", ok, f"{r.status_code}")

        # ---- LINE 3: expired admin JWT ----
        hr("LINE 3 — correctly-signed but EXPIRED admin JWT")
        now = datetime.datetime.now(datetime.UTC)
        expired = pyjwt.encode(
            {"sub": admin_id, "aud": ADMIN_JWT_AUDIENCE, "iss": ADMIN_JWT_ISSUER, "email": email,
             "iat": now - datetime.timedelta(hours=10), "exp": now - datetime.timedelta(hours=2)},
            real_secret, algorithm="HS256",
        )
        r = httpx.get(ADMIN_BASE + "/admin/tenants", headers={"Authorization": f"Bearer {expired}"}, timeout=15)
        print(f"GET /admin/tenants with expired admin JWT: {r.status_code} | {r.text[:150]}")
        ok = r.status_code == 401
        record("line3: expired admin JWT rejected", ok, f"{r.status_code}")

        # ---- LINE 4a: tampered, re-signed with WRONG secret ----
        hr("LINE 4a — admin JWT claims tampered, re-signed with a secret the attacker does not have")
        tampered_wrong_secret = pyjwt.encode(
            {"sub": str(uuid.uuid4()), "aud": ADMIN_JWT_AUDIENCE, "iss": ADMIN_JWT_ISSUER,
             "email": "attacker@evil.example", "iat": now, "exp": now + datetime.timedelta(hours=8)},
            WRONG_SECRET, algorithm="HS256",
        )
        r = httpx.get(ADMIN_BASE + "/admin/tenants", headers={"Authorization": f"Bearer {tampered_wrong_secret}"}, timeout=15)
        print(f"GET /admin/tenants, tampered claims + wrong secret: {r.status_code} | {r.text[:150]}")
        ok = r.status_code == 401
        record("line4a: tampered admin JWT (wrong secret) rejected", ok, f"{r.status_code}")

        # ---- LINE 4b: `video` grafted on, re-signed with the REAL secret (structural check, not just signature) ----
        hr("LINE 4b — genuine claims + `video` grants GRAFTED ON, re-signed with the REAL admin secret")
        real_claims = pyjwt.decode(genuine_admin_jwt, real_secret, algorithms=["HS256"], audience=ADMIN_JWT_AUDIENCE)
        grafted = dict(real_claims)
        grafted["video"] = {"roomJoin": True, "room": "attacker-room"}
        grafted_jwt = pyjwt.encode(grafted, real_secret, algorithm="HS256")  # attacker CANNOT do this (needs real_secret) -- proves the structural check independent of signature validity
        r = httpx.get(ADMIN_BASE + "/admin/tenants", headers={"Authorization": f"Bearer {grafted_jwt}"}, timeout=15)
        print(f"GET /admin/tenants, `video` grafted on + CORRECTLY signed: {r.status_code} | {r.text[:150]}")
        ok = r.status_code == 401
        record("line4b: admin JWT carrying `video` rejected even with a correct signature (structural check)", ok, f"{r.status_code}")

        # ---- LINE 5: login without correct TOTP ----
        hr("LINE 5 — real login attempt: correct password, WRONG TOTP code")
        r = httpx.post(
            ADMIN_BASE + "/admin/login",
            json={"email": email, "password": password, "totp_code": "000000"},
            timeout=15,
        )
        print(f"POST /admin/login, correct password + wrong TOTP: {r.status_code} | {r.text[:150]}")
        ok = r.status_code == 401
        record("line5a: correct password + wrong TOTP rejected", ok, f"{r.status_code}")

        hr("LINE 5 (control) — real login: correct password + CORRECT TOTP must still WORK")
        r = httpx.post(
            ADMIN_BASE + "/admin/login",
            json={"email": email, "password": password, "totp_code": totp_now(totp_secret)},
            timeout=15,
        )
        print(f"POST /admin/login, correct password + correct TOTP: {r.status_code}")
        ok = r.status_code == 200
        record("line5b (sanity control): correct password + correct TOTP succeeds", ok, f"{r.status_code}")

        hr("VERDICT")
        fails = [r for r in results if not r[1]]
        for name, passed, detail in results:
            print(f"  [{'PASS' if passed else 'FAIL'}] {name} :: {detail}")
        if fails:
            print(f"\n{len(fails)} check(s) FAILED.")
            return 2
        print(f"\nAll {len(results)} ADMIN BOUNDARY checks passed.")
        return 0
    finally:
        if admin_srv is not None:
            admin_srv.terminate()
        if cp_srv is not None:
            cp_srv.terminate()
        if admin_id is not None:
            admin_conn.execute("delete from admin_audit_log where admin_id = %s", (admin_id,))
            admin_conn.execute("delete from admin_users where id = %s", (admin_id,))
        for t in ("used_nonces", "sessions", "quota_state", "agents"):
            admin_conn.execute(f"delete from {t} where tenant_id = %s", (tid,))
        admin_conn.execute("delete from tenants where id = %s", (tid,))
        admin_conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
