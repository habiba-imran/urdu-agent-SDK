"""Machine-to-machine auth for tenant-initiated agent management (existing tenants only).

Separate from both control-plane mint auth and tenant-portal JWT auth:
- control-plane auth (control_plane/mint.py) proves a host backend can mint a room token
- tenant-portal JWT auth (tenant_portal_api/auth.py) proves a HUMAN, logged into the dashboard,
  may manage one tenant's agents for the lifetime of an 8h session
- machine auth (this module) proves a CLIENT'S OWN BACKEND, calling programmatically with the
  tenant's HMAC secret, may perform ONE specific agent-management action, once

Reuses the tenant's existing `hmac_secret` (control_plane.secrets.SecretProvider) rather than
inventing a second credential — that would touch tenant provisioning, out of scope here. To avoid
letting a captured signature for one purpose be replayed against another, the signed message binds
an `action` string (fixed per-route server-side, never client-supplied) and a hash of the exact
request payload, so a management signature can never be replayed against `/v1/session` (or a
different agent-management call) even though both derive from the same secret.

Nonce single-use reuses the existing `used_nonces` table (control_plane/mint.py's own mechanism) —
nonces just need to be single-use per tenant, not per-endpoint, since the action+payload binding
already prevents cross-purpose replay.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import time
from collections import defaultdict

import psycopg

from control_plane.mint import REPLAY_WINDOW_SEC
from control_plane.secrets import SecretProvider

MACHINE_RATE_LIMIT_PER_MIN = 30


class MachineAuthError(Exception):
    """A machine-auth request that must be rejected. `status` is the HTTP code to return."""

    def __init__(self, status: int, reason: str):
        super().__init__(f"{status}: {reason}")
        self.status = status
        self.reason = reason


def payload_hash(body: dict) -> str:
    """Canonical-JSON + sha256 of a request body. Must match byte-for-byte on the signing side
    (docs/MACHINE_AGENT_API_CONTRACT.md) so both sides derive the identical hash.

    ensure_ascii=False is deliberate: agent prompts are Urdu-script text (this product's whole
    point). Python's json.dumps defaults to \\uXXXX-escaping non-ASCII, which JS's JSON.stringify
    never does — leaving that default on would silently desync this hash from the SDK's for any
    non-ASCII prompt. Both sides must encode the canonical string as UTF-8 before hashing.
    """
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def expected_signature(
    secret: str, tenant_id: str, ts: str, nonce: str, action: str, body_hash: str
) -> str:
    msg = f"{tenant_id}.{ts}.{nonce}.{action}.{body_hash}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


_hits: dict[str, list[float]] = defaultdict(list)


def _rate_limited(tenant_id: str) -> bool:
    now = time.time()
    window = _hits[tenant_id]
    window[:] = [t for t in window if now - t < 60]
    if len(window) >= MACHINE_RATE_LIMIT_PER_MIN:
        return True
    window.append(now)
    return False


def verify_machine_request(
    conn: psycopg.Connection,
    secrets: SecretProvider,
    *,
    tenant_id: str,
    ts: str,
    nonce: str,
    action: str,
    body: dict,
    signature: str,
    now: int | None = None,
) -> None:
    """Run every machine-auth gate. Raises MachineAuthError on any failure.

    Does not commit — runs on the caller's connection, alongside the caller's own subsequent
    queries.create_agent/update_agent/list_agents call, so a single conn.commit() (or the
    connection context manager's implicit commit) makes the nonce-burn and the agent mutation
    atomic together, matching this file's existing route style.
    """
    if _rate_limited(tenant_id):
        raise MachineAuthError(429, "rate limited")

    row = conn.execute(
        "select status from tenants where id = %s",
        (tenant_id,),
    ).fetchone()
    # 401 (not 403) on unknown tenant, so the endpoint does not confirm which tenants exist
    if row is None:
        raise MachineAuthError(401, "unknown tenant")
    (status,) = row

    secret = secrets.get(tenant_id)
    if not secret:
        raise MachineAuthError(401, "no secret provisioned for tenant")

    expected = expected_signature(
        secret, tenant_id, ts, nonce, action, payload_hash(body)
    )
    if not hmac.compare_digest(expected, signature or ""):
        raise MachineAuthError(401, "bad signature")

    now = (
        now if now is not None else int(datetime.datetime.now(datetime.UTC).timestamp())
    )
    try:
        skew = abs(now - int(ts))
    except (TypeError, ValueError) as e:
        raise MachineAuthError(401, "bad timestamp") from e
    if skew > REPLAY_WINDOW_SEC:
        raise MachineAuthError(401, "timestamp outside replay window")

    try:
        conn.execute(
            "insert into used_nonces (tenant_id, nonce) values (%s, %s)",
            (tenant_id, nonce),
        )
    except psycopg.errors.UniqueViolation as e:
        raise MachineAuthError(401, "nonce replay") from e

    if status != "active":
        raise MachineAuthError(403, "tenant not active")
