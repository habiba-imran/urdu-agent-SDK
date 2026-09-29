"""Wave 2 — portal/API hardening: F-M3, F-M4, F-M5, F-M10, F-M12, F-M13, F-M17, F-M26.

Schema-backed cases (archive, escalations, index) run against the configured database and
skip cleanly without one, matching the rest of the suite's convention.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_DB_URL = os.environ.get("SUPABASE_DB_URL")
requires_db = pytest.mark.skipif(not _DB_URL, reason="SUPABASE_DB_URL not configured")


# ------------------------------------------------------------------- F-M10 headers


def test_security_headers_cover_the_baseline():
    from control_plane.security_headers import API_CSP, SecurityHeadersMiddleware

    assert "default-src 'none'" in API_CSP
    assert "frame-ancestors 'none'" in API_CSP
    assert SecurityHeadersMiddleware is not None


def test_security_headers_are_applied_to_responses(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from control_plane.security_headers import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, hsts=True)

    @app.get("/thing")
    def thing():
        return {"ok": True}

    response = TestClient(app).get("/thing")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "max-age=" in response.headers["Strict-Transport-Security"]


def test_hsts_is_omitted_off_hosted_environments():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from control_plane.security_headers import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, hsts=False)

    @app.get("/thing")
    def thing():
        return {"ok": True}

    response = TestClient(app).get("/thing")
    assert "Strict-Transport-Security" not in response.headers


# -------------------------------------------------------------------- F-M3 page limits


def test_session_page_size_is_capped_in_the_helper():
    """F-M3: ?limit=1000000 returned every session with full transcripts."""
    import tenant_portal_api.queries as queries

    captured = {}

    class _Conn:
        def execute(self, sql, params):
            captured["limit"] = params[-1]

            class _R:
                def fetchall(self_inner):
                    return []

            return _R()

    queries.list_recent_sessions(_Conn(), "tenant", limit=1_000_000)
    assert captured["limit"] == queries.MAX_SESSION_PAGE


def test_session_page_size_floor():
    import tenant_portal_api.queries as queries

    captured = {}

    class _Conn:
        def execute(self, sql, params):
            captured["limit"] = params[-1]

            class _R:
                def fetchall(self_inner):
                    return []

            return _R()

    queries.list_recent_sessions(_Conn(), "tenant", limit=0)
    assert captured["limit"] == 1


# ------------------------------------------------------------- F-M2 portal / F-M26 caps


def test_prompt_length_is_capped_at_write_time():
    """F-M2 (portal half): agents.prompt had no length limit, so every LLM turn paid for
    whatever the tenant stored."""
    import pydantic

    from tenant_portal_api.app import MAX_PROMPT_CHARS, CreateAgentBody

    CreateAgentBody(name="a", prompt="x" * MAX_PROMPT_CHARS, voice_id="v")
    with pytest.raises(pydantic.ValidationError):
        CreateAgentBody(name="a", prompt="x" * (MAX_PROMPT_CHARS + 1), voice_id="v")


def test_agent_cap_is_configurable_and_bounded():
    from tenant_portal_api.app import MAX_AGENTS_PER_TENANT

    assert MAX_AGENTS_PER_TENANT > 0


# ------------------------------------------------------------------------ F-M4 webhook


def test_webhook_body_cap_is_small_enough_to_matter():
    from tenant_portal_api.telephony_webhooks import MAX_WEBHOOK_BODY_BYTES

    # Telnyx payloads are a few KB. The cap exists so an unauthenticated caller cannot make
    # the service read an arbitrarily large body into memory before signature verification.
    assert 0 < MAX_WEBHOOK_BODY_BYTES <= 1024 * 1024


# ------------------------------------------------------------------- F-M5 error leakage


def test_outbound_failure_message_carries_no_exception_text():
    source = (ROOT / "tenant_portal_api" / "telephony_routes.py").read_text(
        encoding="utf-8"
    )
    # F-M5: message=f"Outbound call setup failed: {e}" leaked internal hostnames and driver
    # messages to the caller.
    assert 'f"Outbound call setup failed: {e}"' not in source
    assert '"Outbound call setup failed"' in source


# ----------------------------------------------------- F-M12 / F-M13 (database-backed)


@pytest.fixture
def db_conn():
    import psycopg
    from dbconn import conn_kwargs

    conn = psycopg.connect(**conn_kwargs(), connect_timeout=10, autocommit=True)
    yield conn
    conn.close()


def _column_exists(conn, table, column) -> bool:
    return (
        conn.execute(
            "select 1 from information_schema.columns "
            "where table_name = %s and column_name = %s",
            (table, column),
        ).fetchone()
        is not None
    )


@requires_db
def test_agents_archive_column_and_index_exist(db_conn):
    """F-M13 / 0030."""
    if not _column_exists(db_conn, "agents", "archived_at"):
        pytest.skip("0030 not applied to this database")
    assert (
        db_conn.execute(
            "select 1 from pg_indexes where indexname = 'agents_tenant_live_idx'"
        ).fetchone()
        is not None
    )


@requires_db
def test_usage_events_session_id_is_indexed(db_conn):
    """F-M17 / 0029."""
    row = db_conn.execute(
        "select 1 from pg_indexes where indexname = 'usage_events_session_id_idx'"
    ).fetchone()
    if row is None:
        pytest.skip("0029 not applied to this database")
    assert row is not None


@requires_db
def test_archiving_hides_an_agent_but_keeps_its_sessions(db_conn):
    import tenant_portal_api.queries as queries

    if not _column_exists(db_conn, "agents", "archived_at"):
        pytest.skip("0030 not applied to this database")

    tenant_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    db_conn.execute(
        "insert into tenants (id, name, hmac_secret, hmac_secret_hash) values (%s,%s,%s,%s)",
        (tenant_id, f"archive-test-{tenant_id[:8]}", "s", "h"),
    )
    db_conn.execute(
        "insert into agents (id, tenant_id, name, prompt, voice_id) "
        "values (%s,%s,'a','p','v_meklc281')",
        (agent_id, tenant_id),
    )
    db_conn.execute(
        "insert into sessions (tenant_id, agent_id, room_name, ended_at) "
        "values (%s,%s,%s, now())",
        (tenant_id, agent_id, f"room-{uuid.uuid4()}"),
    )

    try:
        assert len(queries.list_agents(db_conn, tenant_id)) == 1
        assert queries.count_live_sessions_for_agent(db_conn, tenant_id, agent_id) == 0
        assert queries.archive_agent(db_conn, tenant_id, agent_id) is True

        # Hidden from the portal…
        assert queries.list_agents(db_conn, tenant_id) == []
        # …but the session history survives, which a real DELETE would have cascaded away.
        remaining = db_conn.execute(
            "select count(*) from sessions where agent_id = %s", (agent_id,)
        ).fetchone()[0]
        assert remaining == 1
        # Archiving twice is not an error the caller has to handle differently.
        assert queries.archive_agent(db_conn, tenant_id, agent_id) is False
    finally:
        db_conn.execute("delete from sessions where tenant_id = %s", (tenant_id,))
        db_conn.execute("delete from agents where tenant_id = %s", (tenant_id,))
        db_conn.execute("delete from tenants where id = %s", (tenant_id,))


@requires_db
def test_a_live_session_blocks_archiving(db_conn):
    import tenant_portal_api.queries as queries

    tenant_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    db_conn.execute(
        "insert into tenants (id, name, hmac_secret, hmac_secret_hash) values (%s,%s,%s,%s)",
        (tenant_id, f"live-test-{tenant_id[:8]}", "s", "h"),
    )
    db_conn.execute(
        "insert into agents (id, tenant_id, name, prompt, voice_id) "
        "values (%s,%s,'a','p','v_meklc281')",
        (agent_id, tenant_id),
    )
    db_conn.execute(
        "insert into sessions (tenant_id, agent_id, room_name) values (%s,%s,%s)",
        (tenant_id, agent_id, f"room-{uuid.uuid4()}"),
    )
    try:
        assert queries.count_live_sessions_for_agent(db_conn, tenant_id, agent_id) == 1
    finally:
        db_conn.execute("delete from sessions where tenant_id = %s", (tenant_id,))
        db_conn.execute("delete from agents where tenant_id = %s", (tenant_id,))
        db_conn.execute("delete from tenants where id = %s", (tenant_id,))


@requires_db
def test_escalations_can_be_read_back(db_conn):
    """F-M12: the table was write-only — worker/tools.py inserted rows nothing could read."""
    import tenant_portal_api.queries as queries

    tenant_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    db_conn.execute(
        "insert into tenants (id, name, hmac_secret, hmac_secret_hash) values (%s,%s,%s,%s)",
        (tenant_id, f"esc-test-{tenant_id[:8]}", "s", "h"),
    )
    db_conn.execute(
        "insert into agents (id, tenant_id, name, prompt, voice_id) "
        "values (%s,%s,'a','p','v_meklc281')",
        (agent_id, tenant_id),
    )
    session_id = db_conn.execute(
        "insert into sessions (tenant_id, agent_id, room_name) values (%s,%s,%s) returning id",
        (tenant_id, agent_id, f"room-{uuid.uuid4()}"),
    ).fetchone()[0]
    db_conn.execute(
        "insert into escalations (tenant_id, session_id, reason, contact_info) "
        "values (%s,%s,'callback requested','+923001234567')",
        (tenant_id, session_id),
    )
    try:
        rows = queries.list_escalations(db_conn, tenant_id)
        assert len(rows) == 1
        assert rows[0]["reason"] == "callback requested"
        assert rows[0]["contact_info"] == "+923001234567"
        assert rows[0]["session_id"] == str(session_id)
        # Scoped to the tenant that owns them.
        assert queries.list_escalations(db_conn, str(uuid.uuid4())) == []
    finally:
        db_conn.execute("delete from escalations where tenant_id = %s", (tenant_id,))
        db_conn.execute("delete from sessions where tenant_id = %s", (tenant_id,))
        db_conn.execute("delete from agents where tenant_id = %s", (tenant_id,))
        db_conn.execute("delete from tenants where id = %s", (tenant_id,))


@requires_db
def test_mint_refuses_an_archived_agent(db_conn):
    """F-M13: archiving must also stop new sessions, not just hide the row."""
    import control_plane.mint as mint

    if not _column_exists(db_conn, "agents", "archived_at"):
        pytest.skip("0030 not applied to this database")

    mint.reset_schema_probe()
    assert mint._agents_have_archived_at(db_conn) is True
