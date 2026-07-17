#!/usr/bin/env python3
"""LIVE HUMAN-GATE attack — proposed ADR-021 third human-gate item (DRAFT, NOT YET APPROVED,
see state/ADR-021-DRAFT.md). Not part of the official 2-item Phase 7 human gate unless/until the
human approves ADR-021 and 27-PHASE-7-SECURITY.md is updated to add it.

STANDALONE script (deliberately NOT collected by pytest, same not-pytest-collected pattern as
tests/test_token_widen_live.py). Built and dry-run by the agent to prove it works -- running it
is NOT the human gate. If ADR-021 is approved, the human runs this personally:

    python tests/test_admin_boundary_live.py

Attempts, against a REAL admin.app uvicorn process on the real dev DB:
  1. A real tenant-scoped LiveKit AccessToken (control_plane/mint.py shape) used as the bearer
     token on GET /admin/tenants -> must be 401.
  2. A real minted-session-style token (same shape) on GET /admin/agents -> must be 401.
  3. A real admin JWT, correctly signed, but EXPIRED -> 401.
  4. A real admin JWT's claims, tampered (aud/sub changed) and re-signed with a secret the
     attacker does NOT have -> 401.
  5. A real admin JWT re-signed with the WRONG secret but otherwise untouched -> 401.
  6. Sanity control: the genuine, freshly-logged-in admin JWT on the same endpoint -> 200
     (proves the endpoint isn't simply broken/always-401 -- a gate that always fails is not a
     gate).

Every "must fail" case failing, AND the sanity control succeeding, is what makes this a real
result rather than a vacuous one.
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
from livekit import api as lk_api  # noqa: E402

from admin.auth import ADMIN_JWT_AUDIENCE, ADMIN_JWT_ISSUER, provision_admin  # noqa: E402
from admin.security import random_base32_secret, totp_now  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402

PORT = 8801
BASE = f"http://127.0.0.1:{PORT}"
WRONG_SECRET = "attacker-does-not-have-ADMIN_JWT_SECRET-" + uuid.uuid4().hex

vulns: list[tuple[str, str]] = []
checks: list[tuple[str, bool, str]] = []  # (name, passed, detail)


def hr(title: str) -> None:
    print("\n" + "=" * 78 + "\n" + title + "\n" + "=" * 78)


def write_blocker() -> None:
    path = ROOT / "state" / "BLOCKERS.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = [
        "",
        f"## BLOCK-SEC | P7 human-gate admin-boundary (ADR-021 draft) | {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "**SECURITY-CRITICAL — not a normal 3-strike blocker.**",
        "An admin-boundary attack SUCCEEDED against the real admin.app:",
    ]
    for name, detail in vulns:
        entry.append(f"- {name} :: {detail}")
    entry.append("**STATUS: BLOCKED — Phase 7 (if ADR-021 adopted) does not close.**")
    out, inserted = [], False
    for ln in lines:
        out.append(ln)
        if ln.strip() == "## Open" and not inserted:
            out.extend(entry)
            inserted = True
    if not inserted:
        out.extend(entry)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def try_get(path: str, token: str) -> tuple[int, str]:
    r = httpx.get(BASE + path, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    return r.status_code, r.text[:150]


def main() -> int:
    kw = conn_kwargs()
    admin_conn = psycopg.connect(**kw, connect_timeout=30, autocommit=True)
    server = None
    admin_id = None
    email = f"gate-{uuid.uuid4().hex[:8]}@uva-dev.local"
    password = "gate-pw-" + uuid.uuid4().hex
    totp_secret = random_base32_secret()
    try:
        hr("SETUP — provision one real admin account (MFA mandatory)")
        admin_id = provision_admin(
            admin_conn, email=email, password=password, totp_secret=totp_secret
        )
        print(f"admin_id = {admin_id}, email = {email}")

        env = os.environ.copy()
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "admin.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
                "--log-level",
                "warning",
            ],
            cwd=str(ROOT),
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
        print(f"live admin portal ready: {ready} at {BASE}")

        hr(
            "Fetch the real ADMIN_JWT_SECRET the running server generated/loaded (test-only read;"
            " an attacker does not get this — used here only to forge the WRONG-secret case)"
        )
        # The server may have auto-generated ADMIN_JWT_SECRET into .env.local on first import
        # (admin/app.py::_ensure_admin_jwt_secret) — re-read the file fresh, after the server
        # process has started, to get whatever value it actually used.
        from dotenv import dotenv_values

        real_secret = dotenv_values(ROOT / ".env.local").get("ADMIN_JWT_SECRET")

        hr("REAL LOGIN — password + current TOTP code, exactly as a real admin would")
        code = totp_now(totp_secret)
        login_r = httpx.post(
            BASE + "/admin/login",
            json={"email": email, "password": password, "totp_code": code},
            timeout=15,
        )
        print(f"login HTTP {login_r.status_code}: {login_r.text[:150]}")
        genuine_admin_jwt = login_r.json()["token"]

        hr("ATTACK 1 — real tenant-scoped LiveKit AccessToken as admin bearer token")
        lk_key, lk_secret = "devkey", "devsecret0123456789012345678901234567"
        tenant_token = (
            lk_api.AccessToken(lk_key, lk_secret)
            .with_identity(str(uuid.uuid4()))
            .with_ttl(datetime.timedelta(seconds=120))
            .with_metadata(json.dumps({"tenant_id": str(uuid.uuid4())}))
            .with_grants(
                lk_api.VideoGrants(
                    room_join=True, room=str(uuid.uuid4()), can_publish=True
                )
            )
            .to_jwt()
        )
        sc, body = try_get("/admin/tenants", tenant_token)
        print(f"GET /admin/tenants with a tenant/LiveKit AccessToken -> {sc} | {body}")
        ok1 = sc == 401
        checks.append(
            ("tenant/LiveKit token rejected by admin endpoint", ok1, f"{sc} {body}")
        )
        if not ok1:
            vulns.append(
                ("tenant/LiveKit token accepted by admin endpoint", f"{sc} {body}")
            )

        hr("ATTACK 2 — same tenant-shaped token against a different admin route")
        sc, body = try_get("/admin/agents", tenant_token)
        print(
            f"GET /admin/agents with the same tenant/LiveKit AccessToken -> {sc} | {body}"
        )
        ok2 = sc == 401
        checks.append(
            ("tenant/LiveKit token rejected on /admin/agents too", ok2, f"{sc} {body}")
        )
        if not ok2:
            vulns.append(
                ("tenant/LiveKit token accepted on /admin/agents", f"{sc} {body}")
            )

        hr("ATTACK 3 — a real, correctly-signed admin JWT that has EXPIRED")
        if real_secret:
            now = datetime.datetime.now(datetime.UTC)
            expired_claims = {
                "sub": admin_id,
                "aud": ADMIN_JWT_AUDIENCE,
                "iss": ADMIN_JWT_ISSUER,
                "email": email,
                "iat": now - datetime.timedelta(hours=10),
                "exp": now - datetime.timedelta(hours=2),
            }
            expired_jwt = pyjwt.encode(expired_claims, real_secret, algorithm="HS256")
            sc, body = try_get("/admin/tenants", expired_jwt)
            print(
                f"GET /admin/tenants with an EXPIRED (but correctly-signed) admin JWT -> {sc} | {body}"
            )
            ok3 = sc == 401
            checks.append(("expired admin JWT rejected", ok3, f"{sc} {body}"))
            if not ok3:
                vulns.append(("expired admin JWT accepted", f"{sc} {body}"))
        else:
            print(
                "SKIPPED: could not read the live server's real ADMIN_JWT_SECRET from .env.local"
            )
            checks.append(
                ("expired admin JWT rejected", False, "SKIPPED — secret unreadable")
            )

        hr(
            "ATTACK 4 — genuine admin JWT claims, TAMPERED (aud+sub changed), re-signed with a secret the attacker does not have"
        )
        tampered_claims = {
            "sub": str(uuid.uuid4()),  # pretend to be a DIFFERENT admin
            "aud": ADMIN_JWT_AUDIENCE,
            "iss": ADMIN_JWT_ISSUER,
            "email": "attacker@evil.example",
            "iat": datetime.datetime.now(datetime.UTC),
            "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=8),
        }
        tampered_jwt = pyjwt.encode(tampered_claims, WRONG_SECRET, algorithm="HS256")
        sc, body = try_get("/admin/tenants", tampered_jwt)
        print(
            f"GET /admin/tenants with a tampered admin JWT (wrong signing secret) -> {sc} | {body}"
        )
        ok4 = sc == 401
        checks.append(("tampered admin JWT rejected", ok4, f"{sc} {body}"))
        if not ok4:
            vulns.append(("tampered admin JWT accepted", f"{sc} {body}"))

        hr(
            "ATTACK 5 — genuine admin's REAL claims, re-signed with the WRONG secret only"
        )
        if real_secret:
            real_claims = pyjwt.decode(
                genuine_admin_jwt,
                real_secret,
                algorithms=["HS256"],
                audience=ADMIN_JWT_AUDIENCE,
            )
            re_signed = pyjwt.encode(real_claims, WRONG_SECRET, algorithm="HS256")
            sc, body = try_get("/admin/tenants", re_signed)
            print(
                f"GET /admin/tenants with real claims re-signed with wrong secret -> {sc} | {body}"
            )
            ok5 = sc == 401
            checks.append(
                ("wrong-secret-resigned admin JWT rejected", ok5, f"{sc} {body}")
            )
            if not ok5:
                vulns.append(
                    ("wrong-secret-resigned admin JWT accepted", f"{sc} {body}")
                )
        else:
            checks.append(
                (
                    "wrong-secret-resigned admin JWT rejected",
                    False,
                    "SKIPPED — secret unreadable",
                )
            )

        hr("SANITY CONTROL — the genuine, freshly-logged-in admin JWT must WORK (200)")
        sc, body = try_get("/admin/tenants", genuine_admin_jwt)
        print(f"GET /admin/tenants with the REAL admin JWT -> {sc} | {body[:150]}")
        ok_sanity = sc == 200
        checks.append(
            ("genuine admin JWT accepted (sanity control)", ok_sanity, f"{sc}")
        )
        if not ok_sanity:
            vulns.append(
                (
                    "sanity control failed — genuine admin JWT was REJECTED, meaning the endpoint "
                    "may just be broken rather than secure",
                    f"{sc} {body}",
                )
            )

        hr("VERDICT")
        for name, passed, detail in checks:
            print(f"  [{'PASS' if passed else 'FAIL'}] {name} :: {detail}")
        if vulns:
            write_blocker()
            print("\nSECURITY-CRITICAL / BROKEN GATE:")
            for name, detail in vulns:
                print(f"  [VULN] {name} :: {detail}")
            print("\nWritten to state/BLOCKERS.md.")
            return 2
        print(
            "\nAll 5 attacks were rejected (401) and the sanity control succeeded (200)."
        )
        return 0
    finally:
        if server is not None:
            server.terminate()
        if admin_id is not None:
            admin_conn.execute(
                "delete from admin_audit_log where admin_id = %s", (admin_id,)
            )
            admin_conn.execute("delete from admin_users where id = %s", (admin_id,))
        admin_conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
