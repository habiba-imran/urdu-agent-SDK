"""Supabase Auth Admin helpers (service role — portal server only).

Never import this from the dashboard. Used for Phase 2 invites.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .auth import TenantAuthError


def _supabase_url() -> str:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    if not url:
        raise TenantAuthError(503, "SUPABASE_URL is not configured on the tenant portal")
    return url


def _service_role_key() -> str:
    key = (os.environ.get("SUPABASE_SERVICE_ROLE") or "").strip()
    if not key:
        raise TenantAuthError(
            503,
            "SUPABASE_SERVICE_ROLE is not configured on the tenant portal",
        )
    return key


def _admin_headers() -> dict[str, str]:
    key = _service_role_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def find_auth_user_id_by_email(email: str) -> str | None:
    """Return auth.users.id for an email if it already exists, else None."""
    normalized = email.strip().lower()
    url = f"{_supabase_url()}/auth/v1/admin/users"
    try:
        with httpx.Client(timeout=20.0) as client:
            # Paginate a few pages — tenant orgs are small; avoid full dump.
            for page in range(1, 6):
                resp = client.get(
                    url,
                    headers=_admin_headers(),
                    params={"page": page, "per_page": 200},
                )
                if resp.status_code >= 400:
                    raise TenantAuthError(
                        502, f"supabase admin list users failed ({resp.status_code})"
                    )
                payload = resp.json()
                users = payload.get("users") if isinstance(payload, dict) else payload
                if not users:
                    break
                for user in users:
                    if not isinstance(user, dict):
                        continue
                    if (user.get("email") or "").strip().lower() == normalized:
                        uid = user.get("id")
                        return str(uid) if uid else None
                if len(users) < 200:
                    break
    except TenantAuthError:
        raise
    except Exception as exc:
        raise TenantAuthError(502, f"supabase admin list users error: {exc}") from exc
    return None


def _invite_redirect_to() -> str:
    """Dashboard /invite page — must be listed in Supabase Auth Redirect URLs."""
    redirect_to = (
        os.environ.get("DASHBOARD_INVITE_REDIRECT_URL")
        or os.environ.get("NEXT_PUBLIC_DASHBOARD_URL")
        or "http://localhost:3000"
    ).strip().rstrip("/")
    if not redirect_to.endswith("/invite"):
        redirect_to = f"{redirect_to}/invite"
    return redirect_to


def _send_auth_email_with_redirect(email: str, *, path: str) -> None:
    """POST GoTrue email endpoint. ``redirect_to`` must be a query param (not JSON body)."""
    url = f"{_supabase_url()}{path}"
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            url,
            headers=_admin_headers(),
            params={"redirect_to": _invite_redirect_to()},
            json={"email": email},
        )
        if resp.status_code in (200, 201):
            return
        raise TenantAuthError(
            502,
            f"supabase {path} failed ({resp.status_code}): {resp.text[:240]}",
        )


def invite_auth_user_by_email(email: str) -> dict[str, Any]:
    """Invite a user via Supabase Auth (sends invite email when SMTP is configured).

    Returns the Auth user object (must include ``id``).
    If the email already exists, resends a recovery email with the same /invite redirect
    so the invitee can still set a password (invite API will not re-mail existing users).
    """
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise TenantAuthError(422, "invalid email")

    existing = find_auth_user_id_by_email(normalized)
    if existing:
        # Invite API will not re-mail an existing Auth user — send recovery → /invite
        # so they can set a password on the same accept page.
        _send_auth_email_with_redirect(normalized, path="/auth/v1/recover")
        return {"id": existing, "email": normalized, "existing": True}

    # GoTrue reads redirect_to from the *query string*, not the JSON body.
    # Body-only values are ignored → email falls back to Site URL (often / → /login).
    url = f"{_supabase_url()}/auth/v1/invite"
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                url,
                headers=_admin_headers(),
                params={"redirect_to": _invite_redirect_to()},
                json={"email": normalized},
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                if isinstance(data, dict):
                    uid = data.get("id") or (data.get("user") or {}).get("id")
                    if uid:
                        return {
                            "id": str(uid),
                            "email": normalized,
                            "existing": False,
                            "raw": data,
                        }
                raise TenantAuthError(502, "supabase invite returned no user id")

            if resp.status_code in (422, 400) and "already" in (resp.text or "").lower():
                again = find_auth_user_id_by_email(normalized)
                if again:
                    _send_auth_email_with_redirect(normalized, path="/auth/v1/recover")
                    return {"id": again, "email": normalized, "existing": True}

            raise TenantAuthError(
                502,
                f"supabase invite failed ({resp.status_code}): {resp.text[:240]}",
            )
    except TenantAuthError:
        raise
    except Exception as exc:
        raise TenantAuthError(502, f"supabase invite error: {exc}") from exc
