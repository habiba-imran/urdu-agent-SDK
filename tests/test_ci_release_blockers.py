"""Offline database and secret-scan release gates."""
from pathlib import Path
import pytest
from scripts import dbconn


def test_explicit_empty_db_url_never_loads_developer_database(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "")
    def forbidden(*args, **kwargs):
        raise AssertionError("Explicitly offline tests must not read developer DB credentials")
    monkeypatch.setattr(dbconn, "dotenv_values", forbidden)
    with pytest.raises(SystemExit, match="SUPABASE_DB_URL not set"):
        dbconn.conn_kwargs()


def test_absent_db_url_retains_local_development_fallback(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("CI_UNIT_FORCE_OFFLINE", raising=False)
    monkeypatch.setattr(dbconn, "dotenv_values", lambda path: {"SUPABASE_DB_URL": "postgresql://dev:fixture@localhost:5433/devdb"})
    settings = dbconn.conn_kwargs()
    assert settings["host"] == "localhost"
    assert settings["port"] == 5433
    assert settings["dbname"] == "devdb"


def test_process_db_url_keeps_priority(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://ci:fixture@localhost:5434/cidb")
    monkeypatch.setattr(dbconn, "dotenv_values", lambda path: pytest.fail("Process configuration must take priority"))
    assert dbconn.conn_kwargs()["port"] == 5434


def test_offline_network_guard_never_allows_configured_remote_db(monkeypatch):
    from tests import conftest
    monkeypatch.setenv("CI_UNIT_FORCE_OFFLINE", "1")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fixture:fixture@remote-db.example:5432/db")
    assert conftest._extra_allowed_hosts() == set()


def test_secret_scan_uses_default_rules_and_redacts_full_history():
    import tomllib
    import yaml
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / ".gitleaks.toml").read_text())
    assert config["extend"]["useDefault"] is True
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["security-scan"]["steps"]
    command = next(step["run"] for step in steps if step.get("name") == "Scan for committed secrets (gitleaks)")
    assert "--redact" in command
    assert '--log-opts="--all"' in command
    assert ':ro"' in command
    assert "gitleaks-action" not in command


def test_offline_mode_without_db_env_never_uses_dotenv(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.setenv("CI_UNIT_FORCE_OFFLINE", "1")
    monkeypatch.setattr(dbconn, "dotenv_values", lambda path: pytest.fail("Offline mode must not restore the local DB"))
    with pytest.raises(SystemExit):
        dbconn.conn_kwargs()
