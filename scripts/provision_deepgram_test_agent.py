#!/usr/bin/env python3
"""Provision a throwaway English/Deepgram test agent for Phase 6a's live smoke test
(docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md, ADR-036). NON-LIVE: dev DB writes only.

agent_language='en', stt_provider='deepgram' (the provider under test), llm_provider='gemini'
(already enabled for en, Phase 5), tts_provider='uplift' with an EXISTING enabled Urdu voice
(v_meklc281) — there is no enabled TTS provider for en yet (Phase 6c-f), so this hybrid config is
deliberate: the point of this test is verifying Deepgram's English STT actually works live, not
full English audio quality. A tenant could never create this exact combination through the real
API (resolve_agent_provider_fields would reject tts_provider='uplift' for agent_language='en') —
this script writes directly to the DB, bypassing that validation on purpose, the same way
provision_demo_tenant.py already does for the existing Gate-3 pattern.

    python scripts/provision_deepgram_test_agent.py            # dry-run: prints the plan
    python scripts/provision_deepgram_test_agent.py --commit   # actually seed the dev DB
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
    "You are a friendly assistant for a phone-based test call. Respond briefly and naturally in "
    "English to whatever the caller says, in one or two short sentences."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--commit", action="store_true", help="actually write to the dev DB"
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
            "values (%s, 'deepgram-en-test', %s, 2, %s)",
            (tid, secret_hash(hmac_secret), []),
        )
        c.execute(
            """
            insert into agents (
                id, tenant_id, name, prompt, voice_id, llm_model,
                agent_language, stt_provider, stt_model, stt_options,
                llm_provider, llm_options, tts_provider, tts_voice_id, tts_options
            ) values (
                %s, %s, 'Deepgram EN Test', %s, 'v_meklc281', 'gemini-2.5-flash',
                'en', 'deepgram', 'nova-3', %s,
                'gemini', %s, 'uplift', 'v_meklc281', %s
            )
            """,
            (aid, tid, _PROMPT, Jsonb({}), Jsonb({}), Jsonb({})),
        )
    print(
        "\nSEEDED to dev DB (agent_language=en, stt_provider=deepgram). "
        f"Delete later with: delete from tenants where id = '{tid}';"
    )
    print(
        "\nNext: python scripts/mint_demo_token.py --tenant <tenant_id> --agent <agent_id> "
        "--secret <hmac secret>"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
