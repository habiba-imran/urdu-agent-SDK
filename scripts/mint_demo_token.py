#!/usr/bin/env python3
"""Mint a LiveKit join token for the Gate-3 demo (NON-LIVE: local JWT + free dev DB writes).

Given a demo tenant_id/agent_id/secret (from provision_demo_tenant.py --commit), mints a real scoped
token via control_plane.mint.mint_session and prints token + wsUrl + roomName. Join that room with the
token in a LiveKit client (Agents Playground / browser) for the human-listen. No paid provider touched
(the mint signs a JWT locally and writes a session/quota/nonce row to the free dev DB).

    python scripts/mint_demo_token.py --tenant <id> --agent <id> --secret <secret>

FIX (Phase 6a live smoke test, ADR-036): this script used to call mint_session() alone and stop
there. This repo's architecture is explicit-dispatch (its own README) — the actual
`agent_dispatch.create_dispatch(...)` call only lived in control_plane/app.py's real /v1/session
HTTP route (`_dispatch_agent`/`_with_dispatch`), which this standalone script never went through.
So minting via this script created a room + token + session row, but never told LiveKit to
dispatch our worker to it — the worker (even running and connected) would never receive a job for
that room. Discovered live: "nothing updates in the worker terminal at all, the agent doesn't
reply" — not a Deepgram problem, this script was silently incomplete for actually exercising a
live session. Fixed by adding the same explicit-dispatch call app.py already makes correctly.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import psycopg
from dotenv import dotenv_values
from livekit import api

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from control_plane.mint import expected_signature, mint_session  # noqa: E402
from control_plane.secrets import DictSecretProvider  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402


async def _dispatch_agent(
    *, url: str, key: str, secret: str, agent_name: str, room: str
) -> None:
    """Mirrors control_plane/app.py::_dispatch_agent exactly — the real, explicit dispatch call
    this repo's architecture requires. Without this, a minted room/token has no worker job
    attached to it at all, regardless of whether a worker process is running."""
    async with api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lkapi:
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=agent_name, room=room)
        )


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

    agent_name = env.get("LIVEKIT_AGENT_NAME", "uva-dev-agent")
    asyncio.run(
        _dispatch_agent(
            url=env.get("LIVEKIT_URL", ""),
            key=env.get("LIVEKIT_API_KEY", ""),
            secret=env.get("LIVEKIT_API_SECRET", ""),
            agent_name=agent_name,
            room=res["roomName"],
        )
    )
    print(f"dispatched agent '{agent_name}' to room {res['roomName']}")

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
