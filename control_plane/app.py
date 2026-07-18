"""FastAPI control-plane endpoint: POST /v1/session — the only endpoint that matters.

Reads the host-platform's HMAC-signed headers, runs the mint (all gates in mint.py), and returns
{token, wsUrl, roomName} or the appropriate 4xx. Adds a per-tenant-per-minute rate limit (P2-T06);
the origin allowlist is enforced inside the mint from the tenant's `allowed_origins`.

The endpoint is a sync `def` so FastAPI runs it in a threadpool — the mint uses sync psycopg, so
this keeps blocking DB work off the event loop without an async driver.
"""

from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from dbconn import conn_kwargs  # noqa: E402

from .mint import MintError, mint_session  # noqa: E402
from .secrets import EnvSecretProvider  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from admin.audit import record_mint_rejection  # noqa: E402

# P9 FIX (2026-07-18): previously read LIVEKIT_* ONLY from a physical .env.local file --
# correct for local dev, silently empty in any deployed environment with no such file
# (dotenv_values() on a missing file returns {}, no error). Checks os.environ first now,
# matching control_plane/secrets.py::EnvSecretProvider's already-established pattern.
_ENV = dotenv_values(Path(__file__).resolve().parent.parent / ".env.local")
_LK_URL = os.environ.get("LIVEKIT_URL") or _ENV.get("LIVEKIT_URL", "")
_LK_KEY = os.environ.get("LIVEKIT_API_KEY") or _ENV.get("LIVEKIT_API_KEY", "")
_LK_SECRET = os.environ.get("LIVEKIT_API_SECRET") or _ENV.get("LIVEKIT_API_SECRET", "")
RATE_LIMIT_PER_MIN = 120

app = FastAPI(title="UVA control plane")
_secrets = EnvSecretProvider()
_hits: dict[str, list[float]] = defaultdict(list)


class SessionBody(BaseModel):
    agent_id: str


def _rate_limited(tenant_id: str) -> bool:
    now = time.time()
    window = _hits[tenant_id]
    window[:] = [t for t in window if now - t < 60]
    if len(window) >= RATE_LIMIT_PER_MIN:
        return True
    window.append(now)
    return False


@app.post("/v1/session")
def create_session(
    body: SessionBody,
    request: Request,
    x_tenant_id: str = Header(...),
    x_timestamp: str = Header(...),
    x_nonce: str = Header(...),
    x_signature: str = Header(...),
):
    if _rate_limited(x_tenant_id):
        record_mint_rejection(x_tenant_id, 429, "rate limited")
        return JSONResponse({"error": "rate limited"}, status_code=429)
    try:
        with psycopg.connect(**conn_kwargs(), connect_timeout=10) as conn:
            return mint_session(
                conn=conn,
                secrets=_secrets,
                livekit_key=_LK_KEY,
                livekit_secret=_LK_SECRET,
                livekit_url=_LK_URL,
                tenant_id=x_tenant_id,
                ts=x_timestamp,
                nonce=x_nonce,
                agent_id=body.agent_id,
                signature=x_signature,
                origin=request.headers.get("origin"),
            )
    except MintError as e:
        record_mint_rejection(x_tenant_id, e.status, e.reason)
        return JSONResponse({"error": e.reason}, status_code=e.status)
