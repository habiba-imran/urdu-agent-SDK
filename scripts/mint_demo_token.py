#!/usr/bin/env python3
"""Mint a LiveKit join token for the Gate-3 demo (NON-LIVE: local JWT + free dev DB writes).

Given a demo tenant_id/agent_id/secret (from provision_demo_tenant.py --commit), mints a real scoped
token via control_plane.mint.mint_session and prints token + wsUrl + roomName. Join that room with the
token in a LiveKit client (Agents Playground / browser) for the human-listen. No paid provider touched
(the mint signs a JWT locally and writes a session/quota/nonce row to the free dev DB).

    python scripts/mint_demo_token.py --tenant <id> --agent <id> --secret <secret>
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import psycopg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from control_plane.mint import expected_signature, mint_session  # noqa: E402
from control_plane.secrets import DictSecretProvider  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--secret", required=True)
    ap.add_argument("--origin", default=None)
    args = ap.parse_args()

    env = dotenv_values(ROOT / ".env.local")
    ts, nonce = str(int(time.time())), str(uuid.uuid4())
    sig = expected_signature(args.secret, args.tenant, ts, nonce, args.agent)
    with psycopg.connect(**conn_kwargs()) as conn:
        res = mint_session(
            conn=conn,
            secrets=DictSecretProvider({args.tenant: args.secret}),
            livekit_key=env.get("LIVEKIT_API_KEY", ""),
            livekit_secret=env.get("LIVEKIT_API_SECRET", ""),
            livekit_url=env.get("LIVEKIT_URL", ""),
            tenant_id=args.tenant,
            ts=ts,
            nonce=nonce,
            agent_id=args.agent,
            signature=sig,
            origin=args.origin,
        )
    join_url = (
        "https://meet.livekit.io/custom"
        f"?liveKitUrl={quote(res['wsUrl'], safe='')}"
        f"&token={quote(res['token'], safe='')}"
    )
    print("roomName:", res["roomName"])
    print("wsUrl   :", res["wsUrl"])
    print("token   :", res["token"])
    print("join_url:", join_url)
    print("\nJoin the room above with this token in a LiveKit client")
    print(
        "  (Agents Playground: https://agents-playground.livekit.io -> wsUrl + token)."
    )
    print(
        "Start the worker first: python -m worker.main dev  — it is dispatched to the room and"
    )
    print("reads {tenant_id, agent_id} from your participant token metadata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
