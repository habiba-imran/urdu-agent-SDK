#!/usr/bin/env python3
"""Provision a throwaway English/Cartesia test agent for Phase 6c's live smoke test
(docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036). NON-LIVE: dev DB writes only.

agent_language='en', stt_provider='deepgram' + llm_provider='gemini' (both already `enabled`,
proven in Phases 5/6a — reused so this test also incidentally re-exercises them), tts_provider=
'cartesia' with the seeded voice (migration 0018) — the provider under test. Unlike the Deepgram/
Groq hybrid tests, this one's TTS output IS real English audio through the actual vendor under
test, not a stand-in — the point of this test.

    python scripts/provision_cartesia_test_agent.py            # dry-run: prints the plan
    python scripts/provision_cartesia_test_agent.py --commit   # actually seed the dev DB
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from control_plane.secrets import secret_hash  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402

_PROMPT = (
    "You are a friendly receptionist on a phone test call. Stay warm and helpful. Keep replies to "
    "one or two short spoken sentences — the platform TTS rules handle pacing, pauses, and natural "
    "speech patterns."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--commit", action="store_true", help="actually write to the dev DB"
    )
    ap.add_argument(
        "--expressive",
        action="store_true",
        help="set tts_options.expressive=true for LiveKit expressive-mode A/B",
    )
    args = ap.parse_args()

    tid, aid = str(uuid.uuid4()), str(uuid.uuid4())
    hmac_secret = secrets.token_urlsafe(32)
    print(f"tenant_id : {tid}")
    print(f"agent_id  : {aid}")
    print(f"hmac secret: {hmac_secret}")
    print("\nAdd to .env.local (the control plane reads this):")
    print(f"  CP_TENANT_SECRETS={json.dumps({tid: hmac_secret})}")

    if not args.commit:
        print("\nDRY RUN — pass --commit to seed the dev DB. Nothing written.")
        return 0

    with psycopg.connect(**conn_kwargs(), autocommit=True) as c:
        c.execute(
            "insert into tenants (id, name, hmac_secret_hash, max_concurrent, allowed_origins) "
            "values (%s, 'cartesia-en-test', %s, 2, %s)",
            (tid, secret_hash(hmac_secret), []),
        )
        c.execute(
            """
            insert into agents (
                id, tenant_id, name, prompt, voice_id, llm_model,
                agent_language, stt_provider, stt_model, stt_options,
                llm_provider, llm_options, tts_provider, tts_voice_id, tts_options
            ) values (
                %s, %s, 'Cartesia EN Test', %s, 'cartesia-sonic-default', 'gemini-2.5-flash',
                'en', 'deepgram', 'nova-3', %s,
                'gemini', %s, 'cartesia', 'cartesia-sonic-default', %s
            )
            """,
            (aid, tid, _PROMPT, Jsonb({}), Jsonb({}), Jsonb({"expressive": True} if args.expressive else {})),
        )
    print(
        "\nSEEDED to dev DB (agent_language=en, tts_provider=cartesia"
        + (", expressive=true" if args.expressive else "")
        + "). "
        f"Delete later with: delete from tenants where id = '{tid}';"
    )
    print(
        "\nNext: python scripts/mint_demo_token.py --tenant <tenant_id> --agent <agent_id> "
        "--secret <hmac secret>"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
