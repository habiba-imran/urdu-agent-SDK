#!/usr/bin/env python3
"""Provision a demo tenant + agent for the Gate-3 human-listen (NON-LIVE: dev DB writes only).

Seeds one tenant + one agent (voice v_meklc281, the ported Mahnoor persona) into the dev DB,
generates a random HMAC secret, and prints tenant_id / agent_id / secret + the .env.local line to
add. Touches no paid provider. Each run creates fresh UUIDs.

    python scripts/provision_demo_tenant.py            # dry-run: prints the plan, no DB write
    python scripts/provision_demo_tenant.py --commit   # actually seed the dev DB
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import uuid
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from control_plane.secrets import secret_hash  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402


def _prompt() -> str:
    try:
        import persona

        return (
            getattr(persona, "SYSTEM_PROMPT", "")
            or "You are Mahnoor, a warm receptionist."
        )
    except Exception:
        return "You are Mahnoor, a warm receptionist at TechZone Laptops."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--commit", action="store_true", help="actually write to the dev DB"
    )
    args = ap.parse_args()

    tid, aid = str(uuid.uuid4()), str(uuid.uuid4())
    hmac_secret = secrets.token_urlsafe(32)
    prompt = _prompt()
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
            "values (%s, 'demo-gate3', %s, 5, %s)",
            (tid, secret_hash(hmac_secret), []),
        )
        c.execute(
            "insert into agents (id, tenant_id, name, prompt, voice_id, llm_model) "
            "values (%s, %s, 'Mahnoor demo', %s, 'v_meklc281', 'gemini-2.5-flash')",
            (aid, tid, prompt),
        )
    print(
        "\nSEEDED to dev DB. Delete later with: delete from tenants where id = '%s';"
        % tid
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
