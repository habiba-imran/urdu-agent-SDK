"""P1-T03 — RLS tenant isolation. Tenant A's JWT must never see tenant B's rows.

Connects to the dev DB (allowed through the offline guard because Supabase dev is
free), seeds two tenants + an agent each as the table owner, then reads back as the
Supabase `authenticated` role carrying tenant A's JWT claims. The cross-tenant read
MUST return zero rows — that is the whole point of Phase 1.
"""

import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

try:
    import psycopg
except ImportError:  # pragma: no cover
    pytest.skip("psycopg not installed", allow_module_level=True)

from dbconn import conn_kwargs  # noqa: E402  (after the psycopg availability guard)


def _kw():
    try:
        return conn_kwargs()
    except SystemExit:
        pytest.skip("SUPABASE_DB_URL not configured in .env.local")


def test_cross_tenant_read_returns_zero_rows():
    kw = _kw()
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    admin = psycopg.connect(**kw, connect_timeout=30, autocommit=True)
    try:
        admin.execute(
            "insert into tenants (id, name, hmac_secret_hash) "
            "values (%s, 'tenant-A', 'x'), (%s, 'tenant-B', 'x')",
            (a, b),
        )
        admin.execute(
            "insert into agents (tenant_id, name, prompt, voice_id) "
            "values (%s, 'agent-A', 'p', 'v_meklc281'), (%s, 'agent-B', 'p', 'v_meklc281')",
            (a, b),
        )

        # Read as the authenticated role carrying tenant A's JWT claims. RLS applies
        # because authenticated is not the table owner.
        with psycopg.connect(**kw, connect_timeout=30) as reader:
            cur = reader.cursor()
            cur.execute("set local role authenticated")
            cur.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (json.dumps({"tenant_id": a}),),
            )
            own_agents = cur.execute("select count(*) from agents").fetchone()[0]
            leaked_agents = cur.execute(
                "select count(*) from agents where tenant_id = %s", (b,)
            ).fetchone()[0]
            own_tenants = cur.execute("select count(*) from tenants").fetchone()[0]

        assert leaked_agents == 0, (
            f"RLS LEAK: tenant A saw {leaked_agents} of tenant B's agents"
        )
        assert own_agents == 1, f"tenant A should see its own 1 agent, saw {own_agents}"
        assert own_tenants == 1, (
            f"tenant A should see only its own tenants row, saw {own_tenants}"
        )
    finally:
        admin.execute("delete from agents where tenant_id in (%s, %s)", (a, b))
        admin.execute("delete from tenants where id in (%s, %s)", (a, b))
        admin.close()
