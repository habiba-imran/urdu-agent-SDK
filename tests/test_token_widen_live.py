#!/usr/bin/env python3
"""LIVE adversarial test — Phase 2 human gate: a minted token must NOT be wideable.

STANDALONE script (deliberately NOT collected by pytest — it makes REAL calls to a locally-run
control-plane endpoint and to LiveKit Cloud). Reusable for regression in later phases.

    python tests/test_token_widen_live.py

Each attack prints the RAW verdict from LiveKit Cloud's own `/rtc/validate` endpoint — the token
gate every real client hits before connecting; a 401 there is LiveKit ITSELF refusing the token,
not our app code — or the raw HTTP the running endpoint returned. If any attack that must fail
instead succeeds, this writes a SECURITY-CRITICAL entry to state/BLOCKERS.md and exits non-zero.

Why /rtc/validate and not a full WebRTC connect: livekit.rtc's Room.connect() hangs in this headless
environment (WebRTC negotiation never completes). /rtc/validate is LiveKit's authoritative token
check — the exact signature/expiry/grant validation the WS `/rtc` handshake performs — so a 401 from
it means the connection would be refused by LiveKit.
"""

import datetime  # noqa: F401  (kept for readers extending TTL math)
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import jwt as pyjwt
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import psycopg  # noqa: E402

from control_plane.mint import expected_signature  # noqa: E402
from control_plane.secrets import secret_hash  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402

CFG = dotenv_values(ROOT / ".env.local")
LK_SECRET = CFG.get("LIVEKIT_API_SECRET", "")
LK_HTTPS = (
    CFG.get("LIVEKIT_URL", "")
    .replace("wss://", "https://")
    .replace("ws://", "http://")
    .rstrip("/")
)
PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"
ORIGIN = "https://widen-test.example"
SECRET = "widen-test-secret-" + uuid.uuid4().hex
WRONG_SECRET = "attacker-does-not-have-the-api-secret"

# (name, detail) of attacks that SUCCEEDED when they must have failed
vulns: list[tuple[str, str]] = []


def hr(title: str) -> None:
    print("\n" + "=" * 78 + "\n" + title + "\n" + "=" * 78)


def validate(token: str, room: str | None = None) -> tuple[int, str]:
    """Ask LiveKit Cloud itself whether this token is acceptable (optionally for a requested room)."""
    params = {"access_token": token}
    if room is not None:
        params["room"] = room
    r = httpx.get(f"{LK_HTTPS}/rtc/validate", params=params, timeout=20)
    return r.status_code, r.text.strip()


def _read_claims(token: str) -> dict:
    return pyjwt.decode(
        token, LK_SECRET, algorithms=["HS256"], options={"verify_exp": False}
    )


def _forge(base_token: str, **changes) -> str:
    """Tamper claims and re-sign with a secret the attacker does NOT have."""
    c = _read_claims(base_token)
    if "room" in changes:
        c["video"]["room"] = changes["room"]
    if "exp" in changes:
        c["exp"] = changes["exp"]
    return pyjwt.encode(c, WRONG_SECRET, algorithm="HS256")


def write_blocker() -> None:
    path = ROOT / "state" / "BLOCKERS.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = [
        "",
        f"## BLOCK-SEC | P2 token-widen live gate | {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "**SECURITY-CRITICAL — not a normal 3-strike blocker.**",
        "A live token-widen attack SUCCEEDED against LiveKit / the endpoint when it must have failed:",
    ]
    for name, detail in vulns:
        entry.append(f"- {name} :: {detail}")
    entry.append(
        "**STATUS: BLOCKED — Phase 3 does not start. Human must review immediately.**"
    )
    # insert under the "## Open" heading if present, else append
    out, inserted = [], False
    for ln in lines:
        out.append(ln)
        if ln.strip() == "## Open" and not inserted:
            out.extend(entry)
            inserted = True
    if not inserted:
        out.extend(entry)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    kw = conn_kwargs()
    tid, aid = str(uuid.uuid4()), str(uuid.uuid4())
    admin = psycopg.connect(**kw, autocommit=True)
    server = None
    try:
        admin.execute(
            "insert into tenants (id, name, hmac_secret_hash, allowed_origins) values (%s,'widen-test',%s,%s)",
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
        print(f"live endpoint ready: {ready} at {BASE}")

        # CHECK 1 — real token from the live endpoint
        hr("CHECK 1 — POST /v1/session (valid HMAC) -> real LiveKit token")
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
            BASE + "/v1/session", json={"agent_id": aid}, headers=headers, timeout=20
        )
        print("HTTP", r.status_code, "|", r.text)
        token = r.json()["token"]
        room = r.json()["roomName"]

        # CHECK 2 — decode + print raw claims
        hr("CHECK 2 — decoded token claims (raw)")
        claims = _read_claims(token)
        print(json.dumps(claims, indent=2, default=str))
        v = claims.get("video", {})
        for g in ("roomAdmin", "roomCreate", "roomList"):
            print(f"  grant {g}: {v.get(g)!r}  (must be absent/None)")
        if v.get("roomAdmin") or v.get("roomCreate") or v.get("roomList"):
            vulns.append(("token carries an admin/create/list grant", f"video={v}"))

        # CHECK 3 — token is cryptographically bound to its room
        hr(
            "CHECK 3 — LiveKit /rtc/validate: unmodified token vs token re-pointed at a DIFFERENT room"
        )
        sc_ok, body_ok = validate(token)
        print(f"unmodified token (room={room}): LiveKit -> {sc_ok} | {body_ok}")
        other_room = "attacker-room-" + str(uuid.uuid4())
        forged_room = _forge(token, room=other_room)
        sc3, body3 = validate(forged_room)
        print(
            f"token re-pointed to room={other_room} (re-signed w/ WRONG secret): LiveKit -> {sc3} | {body3}"
        )
        if sc3 == 200:
            vulns.append(
                (
                    "LiveKit accepted a token pointed at a different room",
                    f"{sc3} {body3}",
                )
            )
        # 3b (informational) — /rtc/validate takes a ?room= param but IGNORES it (validates the token
        # only): a valid token + a DIFFERENT requested room still returns 200. Room binding is enforced
        # at CONNECT time (LiveKit seats you in the token's embedded room), which the forged-room 401
        # above already protects. Recorded so a future LiveKit change enforcing room here shows up.
        sc_rm, body_rm = validate(token, room="requested-" + str(uuid.uuid4()))
        print(
            f"unmodified token + ?room=DIFFERENT: LiveKit -> {sc_rm} | {body_rm}  "
            "(validate IGNORES the room param; binding is enforced at connect — see forged-room 401 above)"
        )

        # CHECK 4 — tamper room + extend exp, re-signed with wrong secret
        hr(
            "CHECK 4 — tampered token (room changed + exp +1h), re-signed with WRONG secret"
        )
        forged = _forge(
            token,
            room="attacker-room-" + str(uuid.uuid4()),
            exp=int(time.time()) + 3600,
        )
        sc4, body4 = validate(forged)
        print(f"tampered+extended token: LiveKit -> {sc4} | {body4}")
        if sc4 == 200:
            vulns.append(
                ("LiveKit accepted a tampered+extended token", f"{sc4} {body4}")
            )

        # CHECK 6 — replay the SAME nonce against the LIVE endpoint (do this before the 120s wait)
        hr("CHECK 6 — replay same nonce to LIVE /v1/session (second time)")
        r6 = httpx.post(
            BASE + "/v1/session", json={"agent_id": aid}, headers=headers, timeout=20
        )
        print("HTTP", r6.status_code, "|", r6.text)
        if r6.status_code != 401:
            vulns.append(
                (
                    "live endpoint did not reject a replayed nonce with 401",
                    f"{r6.status_code} {r6.text}",
                )
            )

        # CHECK 5 — wait until the token is well PAST LiveKit's expiry leeway, then validate.
        # LiveKit /rtc/validate honours a ~60s JWT clock-skew leeway (measured: exp-45s -> 200,
        # exp-60s -> 401), so we wait to exp + 90s to test a *genuinely* rejected token. A tighter
        # margin would sit inside the leeway and read as a false "expired token accepted".
        hr(
            "CHECK 5 — wait for the token to pass expiry + LiveKit's ~60s leeway, then /rtc/validate"
        )
        margin = 90
        wait = max(0, claims["exp"] - int(time.time()) + margin)
        print(
            f"waiting {wait}s (exp={claims['exp']} + {margin}s past LiveKit's ~60s leeway) ..."
        )
        time.sleep(wait)
        sc5, body5 = validate(token)
        print(
            f"token {int(time.time()) - claims['exp']}s past exp: LiveKit -> {sc5} | {body5}"
        )
        if sc5 == 200:
            vulns.append(
                (
                    "LiveKit accepted a token well past expiry (beyond leeway)",
                    f"{sc5} {body5}",
                )
            )

        hr("VERDICT")
        if vulns:
            write_blocker()
            print(
                "SECURITY-CRITICAL: the following widen attacks SUCCEEDED (must have failed):"
            )
            for name, detail in vulns:
                print(f"  [VULN] {name} :: {detail}")
            print("\nWritten to state/BLOCKERS.md. Phase 3 must NOT start.")
            return 2
        print(
            "All six checks behaved: every widen/replay/expiry attack was rejected by"
        )
        print(
            "LiveKit Cloud or the live endpoint. (Human still confirms before Phase 3.)"
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
