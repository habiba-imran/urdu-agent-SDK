"""The token mint. Verifies a host-platform request and issues a scoped LiveKit JWT.

Every check happens server-side, BEFORE the token exists (docs/22-PHASE-2, 31-GUIDE §5):
HMAC over server->server request, <=60s replay window + single-use nonce, tenant active, agent
owned by tenant (IDOR guard), origin allowlist, quota (concurrent + monthly minutes). Only then is a
JWT minted: room=uuid4, identity=uuid4, TTL<=120s, grant = roomJoin on that ONE room. Never
roomAdmin/roomCreate/roomList. Session row + quota increment commit in the same transaction as the
nonce, so a replay cannot double-mint.

DB access is the postgres owner connection (RLS bypass, ADR-005) — the mint is a trusted service
that must read/write across the tenant boundary before any tenant JWT exists.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import uuid

import psycopg
from livekit import api

from .secrets import SecretProvider

REPLAY_WINDOW_SEC = 60
TTL_SEC = 120


class MintError(Exception):
    """A request that must be rejected. `status` is the HTTP code to return."""

    def __init__(self, status: int, reason: str):
        super().__init__(f"{status}: {reason}")
        self.status = status
        self.reason = reason


def expected_signature(
    secret: str, tenant_id: str, ts: str, nonce: str, agent_id: str
) -> str:
    msg = f"{tenant_id}.{ts}.{nonce}.{agent_id}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def mint_session(
    *,
    conn: psycopg.Connection,
    secrets: SecretProvider,
    livekit_key: str,
    livekit_secret: str,
    livekit_url: str,
    tenant_id: str,
    ts: str,
    nonce: str,
    agent_id: str,
    signature: str,
    origin: str | None = None,
    now: int | None = None,
) -> dict:
    """Run every gate and return {token, wsUrl, roomName}, or raise MintError."""
    now = (
        now if now is not None else int(datetime.datetime.now(datetime.UTC).timestamp())
    )

    with conn.transaction():
        # tenant record (need config + the stored hash; the raw secret comes from the provider)
        row = conn.execute(
            "select status, max_concurrent, max_minutes_month, hmac_secret_hash, allowed_origins "
            "from tenants where id = %s",
            (tenant_id,),
        ).fetchone()
        # 401 (not 403) on unknown tenant, so the endpoint does not confirm which tenants exist
        if row is None:
            raise MintError(401, "unknown tenant")
        status, max_concurrent, max_minutes, stored_hash, allowed_origins = row

        secret = secrets.get(tenant_id)
        if not secret:
            raise MintError(401, "no secret provisioned for tenant")

        # 1. HMAC verify (constant-time)
        expected = expected_signature(secret, tenant_id, ts, nonce, agent_id)
        if not hmac.compare_digest(expected, signature or ""):
            raise MintError(401, "bad signature")

        # 2. replay window
        try:
            skew = abs(now - int(ts))
        except (TypeError, ValueError) as e:
            raise MintError(401, "bad timestamp") from e
        if skew > REPLAY_WINDOW_SEC:
            raise MintError(401, "timestamp outside replay window")

        # 3. nonce single-use — the unique PK is the check
        try:
            conn.execute(
                "insert into used_nonces (tenant_id, nonce) values (%s, %s)",
                (tenant_id, nonce),
            )
        except psycopg.errors.UniqueViolation as e:
            raise MintError(401, "nonce replay") from e

        # 4. tenant active
        if status != "active":
            raise MintError(403, "tenant not active")

        # 5. agent belongs to tenant — the IDOR guard
        owned = conn.execute(
            "select 1 from agents where id = %s and tenant_id = %s",
            (agent_id, tenant_id),
        ).fetchone()
        if owned is None:
            raise MintError(403, "agent does not belong to tenant")

        # 6. origin allowlist (per tenant; empty list = not enforced in dev)
        if allowed_origins and origin not in allowed_origins:
            raise MintError(403, "origin not allowed")

        # 7. quota — checked BEFORE the token exists
        q = conn.execute(
            "select concurrent_now, minutes_this_month from quota_state where tenant_id = %s",
            (tenant_id,),
        ).fetchone()
        concurrent_now, minutes = q if q else (0, 0)
        if concurrent_now >= max_concurrent:
            raise MintError(429, "concurrent cap reached")
        if minutes >= max_minutes:
            raise MintError(429, "monthly minutes cap reached")

        # 8. mint the scoped JWT
        room = str(uuid.uuid4())
        identity = str(uuid.uuid4())
        token = (
            api.AccessToken(livekit_key, livekit_secret)
            .with_identity(identity)
            .with_ttl(datetime.timedelta(seconds=TTL_SEC))
            .with_metadata(json.dumps({"tenant_id": tenant_id, "agent_id": agent_id}))
            .with_grants(
                api.VideoGrants(
                    room_join=True, room=room, can_publish=True, can_subscribe=True
                )
            )
            .to_jwt()
        )

        # 9. session row + quota increment, same transaction as the nonce
        conn.execute(
            "insert into sessions (tenant_id, agent_id, room_name) values (%s, %s, %s)",
            (tenant_id, agent_id, room),
        )
        conn.execute(
            "insert into quota_state (tenant_id, concurrent_now) values (%s, 1) "
            "on conflict (tenant_id) do update set concurrent_now = quota_state.concurrent_now + 1",
            (tenant_id,),
        )

    return {"token": token, "wsUrl": livekit_url, "roomName": room}
