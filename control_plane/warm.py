"""Control-plane warm probe — keeps DB + LiveKit API hot (UVA-9)."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import psycopg
from livekit import api
from livekit.protocol.room import ListRoomsRequest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from scripts.dbconn import conn_kwargs
except ImportError:
    from dbconn import conn_kwargs  # type: ignore # noqa: E402


async def run_warm_probe(
    *,
    lk_url: str,
    lk_key: str,
    lk_secret: str,
    agent_name: str,
) -> dict[str, Any]:
    """Exercise DB + LiveKit API so idle Render instances stay warm."""
    started = time.monotonic()
    health: dict[str, Any] = {
        "status": "warm",
        "service": "uva-control-plane",
        "agentName": agent_name,
        "checks": {},
    }

    try:
        with psycopg.connect(**conn_kwargs(), connect_timeout=3) as conn:
            conn.execute("SELECT 1").fetchone()
        health["checks"]["database"] = "ok"
    except Exception as exc:
        health["checks"]["database"] = f"failed: {exc}"
        health["status"] = "unhealthy"

    if not lk_url or not lk_key or not lk_secret:
        health["checks"]["livekit_api"] = "missing_credentials"
        health["status"] = "unhealthy"
    else:
        try:
            async with api.LiveKitAPI(
                url=lk_url,
                api_key=lk_key,
                api_secret=lk_secret,
            ) as lkapi:
                await lkapi.room.list_rooms(ListRoomsRequest())
            health["checks"]["livekit_api"] = "ok"
        except Exception as exc:
            health["checks"]["livekit_api"] = f"failed: {exc}"
            health["status"] = "unhealthy"

    health["elapsedMs"] = int(round((time.monotonic() - started) * 1000))
    return health
