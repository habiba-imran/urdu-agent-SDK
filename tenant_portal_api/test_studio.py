"""Dashboard Test Studio mint — host-shaped HMAC path (Wave 0 / P2-H1).

The browser never sees the tenant HMAC secret. The portal JWT authenticates the
operator; the portal signs ``POST {control_plane}/v1/session`` the same way a
real host backend does. This replaces Test Studio → ``/v1/session/dev-mint``.
"""

from __future__ import annotations

import logging
import os
import secrets as pysecrets
import time
from typing import Any

import httpx
from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, Field

from control_plane.login_guard import record_attempt
from control_plane.mint import expected_signature

from . import queries
from .jwt_secret import portal_jwt_secret
from .portal_access import http_require_portal

logger = logging.getLogger("tenant_portal_api.test_studio")


def _control_plane_base() -> str:
    raw = (
        os.environ.get("UVA_CONTROL_PLANE_URL")
        or os.environ.get("CONTROL_PLANE_URL")
        or ""
    ).strip().rstrip("/")
    if not raw:
        raise HTTPException(
            status_code=503,
            detail=(
                "UVA_CONTROL_PLANE_URL is not configured on the tenant portal — "
                "Test Studio cannot mint sessions"
            ),
        )
    return raw


class TestStudioSessionBody(BaseModel):
    publishableKey: str = Field(min_length=1)
    agentId: str = Field(min_length=1)


class TestStudioRefreshBody(BaseModel):
    token: str | None = None


def _normalize_cp_failure(status: int, payload: Any) -> tuple[int, dict]:
    detail = ""
    if isinstance(payload, dict):
        detail = str(
            payload.get("detail") or payload.get("error") or payload.get("code") or ""
        )
    lower = detail.lower()
    if status == 429:
        return 429, {"error": detail or "quota_exceeded"}
    if status == 404 or "agent" in lower or "not found" in lower:
        return 404, {"error": "agent_not_found"}
    if status in (401, 403):
        return status, {"error": detail or "session_failed"}
    return 502, {"error": "session_failed", "detail": detail or None}


def _session_payload(payload: dict, refresh_url: str) -> dict:
    return {
        "token": payload["token"],
        "wsUrl": payload.get("wsUrl") or payload.get("ws_url"),
        "roomName": payload.get("roomName") or payload.get("room_name"),
        "refreshUrl": refresh_url,
        "expiresIn": payload.get("expiresIn") or payload.get("expires_in") or 120,
    }


def register_test_studio_routes(app, *, conn_factory) -> None:
    """Attach routes using the portal app's DB connection factory (avoids import cycles)."""

    def _require_tenant(authorization: str | None, request: Request) -> dict:
        from .session_cookie import portal_token_from_request

        token = portal_token_from_request(request, authorization)
        with conn_factory() as conn:
            if token:
                return http_require_portal(
                    conn, token=token, jwt_secret=portal_jwt_secret()
                )
            return http_require_portal(
                conn, authorization=authorization, jwt_secret=portal_jwt_secret()
            )

    @app.post("/portal/test-studio/session")
    def test_studio_mint_session(
        body: TestStudioSessionBody,
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        claims = _require_tenant(authorization, request)
        tenant_id = str(claims["sub"])
        publishable = body.publishableKey.strip()
        agent_id = body.agentId.strip()

        if publishable != tenant_id:
            raise HTTPException(
                status_code=403,
                detail="publishableKey does not match this tenant",
            )

        cp_base = _control_plane_base()
        origin = request.headers.get("origin")

        with conn_factory() as conn:
            try:
                secret = queries.get_raw_secret(conn, tenant_id)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e

            owned = conn.execute(
                "select 1 from agents where id = %s and tenant_id = %s",
                (agent_id, tenant_id),
            ).fetchone()
            if owned is None:
                raise HTTPException(status_code=404, detail="agent not found")

            ts = str(int(time.time()))
            nonce = pysecrets.token_hex(8)
            signature = expected_signature(secret, tenant_id, ts, nonce, agent_id)

            headers = {
                "Content-Type": "application/json",
                "X-Tenant-Id": tenant_id,
                "X-Timestamp": ts,
                "X-Nonce": nonce,
                "X-Signature": signature,
            }
            if origin:
                headers["Origin"] = origin

            try:
                with httpx.Client(timeout=20.0) as client:
                    upstream = client.post(
                        f"{cp_base}/v1/session",
                        headers=headers,
                        json={"agent_id": agent_id},
                    )
                    try:
                        payload = upstream.json()
                    except Exception:
                        payload = {"raw": upstream.text}
            except httpx.HTTPError as exc:
                logger.warning("test-studio mint CP unreachable: %s", exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"control plane unreachable at {cp_base}",
                ) from exc

            record_attempt(
                conn,
                realm="portal-test-studio-mint",
                identity=tenant_id,
                client_ip=request.client.host if request.client else None,
                successful=upstream.is_success,
                reason=f"agent={agent_id} status={upstream.status_code}",
            )
            conn.commit()

        if not upstream.is_success:
            status, err_body = _normalize_cp_failure(upstream.status_code, payload)
            raise HTTPException(status_code=status, detail=err_body)

        if not isinstance(payload, dict) or not payload.get("token"):
            raise HTTPException(status_code=502, detail="session_failed")

        refresh_url = (
            str(request.base_url).rstrip("/") + "/portal/test-studio/session/refresh"
        )
        return _session_payload(payload, refresh_url)

    @app.post("/portal/test-studio/session/refresh")
    def test_studio_refresh_session(
        request: Request,
        body: TestStudioRefreshBody | None = None,
        authorization: str | None = Header(default=None),
    ):
        cp_base = _control_plane_base()
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization[len("Bearer ") :].strip()
        if not token and body and body.token:
            token = body.token.strip()
        if not token:
            raise HTTPException(status_code=401, detail="missing bearer token")

        headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
        try:
            with httpx.Client(timeout=20.0) as client:
                upstream = client.post(
                    f"{cp_base}/v1/session/refresh", headers=headers
                )
                try:
                    payload = upstream.json()
                except Exception:
                    payload = {}
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"control plane unreachable at {cp_base}",
            ) from exc

        if not upstream.is_success:
            detail = (
                payload.get("detail")
                if isinstance(payload, dict)
                else "refresh failed"
            )
            raise HTTPException(status_code=upstream.status_code, detail=detail)

        if not isinstance(payload, dict) or not payload.get("token"):
            raise HTTPException(status_code=502, detail="refresh failed")

        refresh_url = (
            str(request.base_url).rstrip("/") + "/portal/test-studio/session/refresh"
        )
        return _session_payload(payload, refresh_url)
