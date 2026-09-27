"""Unit tests for portal recording URL re-sign helpers (no live Supabase)."""

from __future__ import annotations

from tenant_portal_api.recording_urls import enrich_session_recording


def test_enrich_pops_storage_path_and_keeps_legacy_url(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE", raising=False)
    session = {
        "id": "s1",
        "recording_url": "https://example.com/old.ogg",
        "recording_storage_path": "tenant/a/b.ogg",
    }
    out = enrich_session_recording(session)
    assert "recording_storage_path" not in out
    assert out["recording_url"] == "https://example.com/old.ogg"
    assert out["recordingUrl"] == "https://example.com/old.ogg"


def test_enrich_uses_signed_url_when_helper_returns(monkeypatch):
    monkeypatch.setattr(
        "tenant_portal_api.recording_urls.create_signed_recording_url",
        lambda path, **_kw: "https://signed.example/x.ogg" if path else None,
    )
    session = {
        "recording_url": None,
        "recording_storage_path": "t/agent/room.ogg",
    }
    out = enrich_session_recording(session)
    assert out["recording_url"] == "https://signed.example/x.ogg"
    assert out["recordingUrl"] == "https://signed.example/x.ogg"
    assert "recording_storage_path" not in out
