"""Phase 3 contract fixtures for the host backend <-> control plane integration path."""

from __future__ import annotations

import datetime
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from control_plane.mint import MintError, expected_signature  # noqa: E402
from control_plane import app as app_module  # noqa: E402


def test_expected_signature_fixture_matches_documented_format():
    signature = expected_signature(
        "super-secret",
        "tenant-123",
        "1721670000",
        "nonce-456",
        "agent-789",
    )

    assert len(signature) == 64
    assert signature == expected_signature(
        "super-secret",
        "tenant-123",
        "1721670000",
        "nonce-456",
        "agent-789",
    )


def test_session_endpoint_contract_success(monkeypatch):
    client = TestClient(app_module.app)
    seen: dict[str, object] = {}

    def fake_mint_session(**kwargs):
        seen.update(kwargs)
        return {
            "token": "token-123",
            "wsUrl": "wss://example.livekit.cloud",
            "roomName": "room-123",
        }

    def fake_with_dispatch(res, tenant_id, agent_id):
        return {**res, "refreshUrl": "/v1/session/refresh", "expiresIn": 120}

    monkeypatch.setattr(app_module, "mint_session", fake_mint_session)
    monkeypatch.setattr(app_module, "_with_dispatch", fake_with_dispatch)
    monkeypatch.setattr(app_module, "_rate_limited", lambda tenant_id: False)

    ts = str(int(datetime.datetime.now(datetime.UTC).timestamp()))
    nonce = str(uuid.uuid4())
    headers = {
        "X-Tenant-Id": "tenant-123",
        "X-Timestamp": ts,
        "X-Nonce": nonce,
        "X-Signature": "signed-request",
        "Origin": "https://host.example.com",
    }

    response = client.post(
        "/v1/session", json={"agent_id": "agent-123"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json() == {
        "token": "token-123",
        "wsUrl": "wss://example.livekit.cloud",
        "roomName": "room-123",
        "refreshUrl": "/v1/session/refresh",
        "expiresIn": 120,
    }
    assert seen["tenant_id"] == "tenant-123"
    assert seen["agent_id"] == "agent-123"
    assert seen["origin"] == "https://host.example.com"


def test_session_endpoint_contract_error_mapping(monkeypatch):
    client = TestClient(app_module.app)

    def fake_mint_session(**kwargs):
        raise MintError(429, "concurrent cap reached")

    monkeypatch.setattr(app_module, "mint_session", fake_mint_session)
    monkeypatch.setattr(app_module, "_rate_limited", lambda tenant_id: False)

    ts = str(int(datetime.datetime.now(datetime.UTC).timestamp()))
    headers = {
        "X-Tenant-Id": "tenant-123",
        "X-Timestamp": ts,
        "X-Nonce": str(uuid.uuid4()),
        "X-Signature": "signed-request",
    }

    response = client.post(
        "/v1/session", json={"agent_id": "agent-123"}, headers=headers
    )

    assert response.status_code == 429
    assert response.json() == {"error": "concurrent cap reached"}


def test_refresh_endpoint_contract_accepts_bearer(monkeypatch):
    client = TestClient(app_module.app)

    def fake_refresh(token: str):
        assert token == "existing-token"
        return app_module.RefreshResponse(
            token="refreshed-token",
            wsUrl="wss://example.livekit.cloud",
            roomName="room-123",
            refreshUrl="/v1/session/refresh",
            expiresIn=120,
        )

    monkeypatch.setattr(app_module, "_mint_refresh_token", fake_refresh)

    response = client.post(
        "/v1/session/refresh",
        headers={"Authorization": "Bearer existing-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "token": "refreshed-token",
        "wsUrl": "wss://example.livekit.cloud",
        "roomName": "room-123",
        "refreshUrl": "/v1/session/refresh",
        "expiresIn": 120,
    }


def test_refresh_endpoint_contract_accepts_body_token(monkeypatch):
    client = TestClient(app_module.app)

    def fake_refresh(token: str):
        assert token == "body-token"
        return app_module.RefreshResponse(
            token="refreshed-token",
            wsUrl="wss://example.livekit.cloud",
            roomName="room-123",
            refreshUrl="/v1/session/refresh",
            expiresIn=120,
        )

    monkeypatch.setattr(app_module, "_mint_refresh_token", fake_refresh)

    response = client.post("/v1/session/refresh", json={"token": "body-token"})

    assert response.status_code == 200
    assert response.json()["token"] == "refreshed-token"
