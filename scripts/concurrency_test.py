"""P3-T08 concurrency test driver (LIVE — pre-approved, docs/23-PHASE-3-WORKER.md /
30-GUIDE-FREE-TIER.md §4). Run ONLY against an already-running worker (`python -m worker.main dev`).

A prior session found a headless `livekit.rtc` (Python) client HANGS on this Windows environment
(state/HANDOFF.md, Session 5) — the suggested driver is a real browser, not a headless Python RTC
script. This uses Playwright + real Chromium + the actual `livekit-client` JS SDK (installed at
sdk/node_modules, already a Phase-4 dependency) to make 6 real WebRTC room connections, no media
tracks published (LiveKit Build's concurrency cap is enforced at the participant/session level,
not at track-publish time — verified: connecting is sufficient to exercise it).

Mints 6 fresh tokens (6 distinct rooms — each mint issues a fresh uuid4 room) for the
already-provisioned demo tenant/agent, serves this repo over a local HTTP server so the browser can
load the real livekit-client bundle, opens 6 pages roughly simultaneously, and reports the REAL
observed status/error per page — does not assume which one fails or what the error looks like.

Run: python scripts/concurrency_test.py
"""

from __future__ import annotations

import functools
import http.server
import json
import secrets as secrets_mod
import sys
import threading
import time
import uuid
from pathlib import Path

import psycopg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from control_plane.mint import expected_signature, mint_session  # noqa: E402
from control_plane.secrets import DictSecretProvider, secret_hash  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402

N_CONCURRENT = 6  # LiveKit Build free-tier cap is 5; the 6th must fail cleanly.
HTTP_PORT = 8934
POLL_TIMEOUT_S = 25
POLL_INTERVAL_S = 0.5
HOLD_OPEN_S = 15  # let worker.main's entrypoint fully complete before disconnecting; see below.


def provision_fresh_tenant(conn) -> tuple[str, str, str]:
    """Fresh tenant per run, own DB write, max_concurrent set well above N_CONCURRENT.

    Deliberately NOT the shared demo-gate3 tenant used earlier tonight: every mint increments
    quota_state.concurrent_now, nothing in tonight's ad-hoc testing ever decremented it back (the
    real session-end quota decrement isn't wired yet — same gap as the usage_events follow-up), so
    that tenant's own count is already stale/elevated and would trip OUR control-plane's 429
    before ever reaching LiveKit's actual concurrency cap, which is what P3-T08 needs to observe.
    max_concurrent=20 here so our own cap is not the confound; LiveKit Build's real 5-concurrent
    limit is the only one being exercised.
    """
    tid, aid = str(uuid.uuid4()), str(uuid.uuid4())
    secret = secrets_mod.token_urlsafe(32)
    conn.execute(
        "insert into tenants (id, name, hmac_secret_hash, max_concurrent, allowed_origins) "
        "values (%s, 'p3t08-concurrency', %s, 20, %s)",
        (tid, secret_hash(secret), []),
    )
    conn.execute(
        "insert into agents (id, tenant_id, name, prompt, voice_id, llm_model) "
        "values (%s, %s, 'p3t08 probe', 'You are a test probe.', 'v_meklc281', 'gemini-2.5-flash')",
        (aid, tid),
    )
    return tid, aid, secret


def mint_tokens(n: int, tenant_id: str, agent_id: str, secret: str) -> list[dict]:
    env = dotenv_values(ROOT / ".env.local")
    provider = DictSecretProvider({tenant_id: secret})
    results = []
    with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
        for _ in range(n):
            ts, nonce = str(int(time.time())), str(uuid.uuid4())
            sig = expected_signature(secret, tenant_id, ts, nonce, agent_id)
            res = mint_session(
                conn=conn,
                secrets=provider,
                livekit_key=env.get("LIVEKIT_API_KEY", ""),
                livekit_secret=env.get("LIVEKIT_API_SECRET", ""),
                livekit_url=env.get("LIVEKIT_URL", ""),
                tenant_id=tenant_id,
                ts=ts,
                nonce=nonce,
                agent_id=agent_id,
                signature=sig,
                origin=None,
            )
            results.append(res)
    return results


def start_http_server() -> tuple[http.server.HTTPServer, threading.Thread]:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(ROOT)
    )
    server = http.server.HTTPServer(("127.0.0.1", HTTP_PORT), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t


def main() -> int:
    import argparse

    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tone",
        action="store_true",
        help="publish a real synthetic audio track per session (ADR-014 addendum (b) re-test) "
        "instead of joining with zero media",
    )
    args = ap.parse_args()

    with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
        tenant_id, agent_id, secret = provision_fresh_tenant(conn)
    print(f"provisioned fresh tenant={tenant_id} agent={agent_id} (max_concurrent=20)")

    print(f"minting {N_CONCURRENT} fresh tokens...")
    tokens = mint_tokens(N_CONCURRENT, tenant_id, agent_id, secret)
    for i, tok in enumerate(tokens):
        print(f"  [{i}] room={tok['roomName']}")

    server, thread = start_http_server()
    base_url = f"http://127.0.0.1:{HTTP_PORT}/scripts/concurrency_test_client.html"
    print(f"local HTTP server up on :{HTTP_PORT}")

    results = [None] * N_CONCURRENT
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            pages = [browser.new_page() for _ in range(N_CONCURRENT)]

            tone_qs = "&publishTone=1" if args.tone else ""
            mode = "WITH synthetic-tone published media" if args.tone else "no media (zero tracks)"
            print(f"opening {N_CONCURRENT} room connections roughly simultaneously — {mode}...")
            for i, (page, tok) in enumerate(zip(pages, tokens)):
                url = (
                    f"{base_url}?wsUrl={tok['wsUrl']}&token={tok['token']}&label={i}{tone_qs}"
                )
                page.goto(url)

            deadline = time.monotonic() + POLL_TIMEOUT_S
            pending = set(range(N_CONCURRENT))
            while pending and time.monotonic() < deadline:
                for i in list(pending):
                    try:
                        text = pages[i].locator("#status").text_content(timeout=1000)
                    except Exception:
                        continue
                    if text and (text.startswith("connected") or text.startswith("failed") or text.startswith("disconnected")):
                        results[i] = text
                        pending.discard(i)
                if pending:
                    time.sleep(POLL_INTERVAL_S)

            for i in pending:
                results[i] = f"TIMEOUT after {POLL_TIMEOUT_S}s (never reached a terminal state)"

            # HOLD_OPEN_S: closing right after "connected" races worker.main's
            # ctx.wait_for_participant() — a fast disconnect can cancel that await before it
            # resolves (RuntimeError: room disconnected while waiting for participant), so the
            # entrypoint never reaches session.start(). Verified live: holding a connection open
            # ~15s lets the full pipeline (wait_for_participant -> build_session -> session.start
            # -> STT connect -> adaptive interruption init) complete normally. Without this, a
            # concurrency test only proves room-join concurrency, not full-agent-session
            # concurrency, which is the thing the free-tier doc is actually worried about.
            connected_count = sum(1 for r in results if r and r.startswith("connected"))
            if connected_count:
                print(
                    f"\nholding {connected_count} connected session(s) open {HOLD_OPEN_S}s so the "
                    "worker's full entrypoint (wait_for_participant -> session.start -> STT/"
                    "adaptive-interruption init) can actually complete, not just the room join..."
                )
                time.sleep(HOLD_OPEN_S)

            print("\n--- results ---")
            for i, r in enumerate(results):
                print(f"  [{i}] room={tokens[i]['roomName']}: {r}")

            for page in pages:
                try:
                    page.close()
                except Exception:
                    pass
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)

    n_connected = sum(1 for r in results if r and r.startswith("connected"))
    n_failed = sum(1 for r in results if r and r.startswith("failed"))
    print(f"\nsummary: connected={n_connected} failed={n_failed} other={N_CONCURRENT - n_connected - n_failed}")
    print(f"\ncleanup: delete from tenants where id = '{tenant_id}';  -- cascades agents/sessions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
