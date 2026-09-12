"""Phase 7 tests — certification, OpenAPI docs route verification, and documentation completeness."""

from __future__ import annotations

import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from control_plane.app import app as cp_app  # noqa: E402


def test_control_plane_openapi_docs_routes():
    """Verify Swagger UI (/docs) and ReDoc (/redoc) routes respond with 200 OK."""
    client = TestClient(cp_app)

    response_docs = client.get("/docs")
    assert response_docs.status_code == 200
    assert "UVA Control Plane" in response_docs.text

    response_redoc = client.get("/redoc")
    assert response_redoc.status_code == 200
    assert "UVA Control Plane" in response_redoc.text


def test_documentation_files_exist():
    """Verify essential client onboarding and architecture docs exist."""
    api_ref = ROOT / "docs" / "api-reference.md"
    contract_spec = ROOT / "docs" / "HOST_BACKEND_CONTRACT.md"
    readme = ROOT / "README.md"

    assert api_ref.exists(), "docs/api-reference.md is missing"
    assert contract_spec.exists(), "docs/HOST_BACKEND_CONTRACT.md is missing"
    assert readme.exists(), "README.md is missing"

    api_content = api_ref.read_text(encoding="utf-8")
    assert "X-Tenant-Id" in api_content
    assert "/v1/session/refresh" in api_content

    readme_content = readme.read_text(encoding="utf-8")
    assert "Control Plane API Reference" in readme_content
    assert "Urdu Voice-Agent-as-a-Service" in readme_content
