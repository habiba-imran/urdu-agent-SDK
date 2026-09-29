"""Tenant membership + first-user bootstrap (Phase 1) + invites (Phase 2).

Link: auth.users.id → tenant_members.auth_user_id → tenant_id → tenants.

First login with a valid Supabase user and no membership row creates a new
tenant (credentials on ``tenants``) and an ``owner`` membership.

Invites create an Auth user (service role) and a ``member`` row for the
**inviter's existing tenant** — never a new tenant. Because the membership
row exists before the invitee logs in, Phase 1 bootstrap will not create
Tenant B.
"""

from __future__ import annotations

import hmac
import secrets
import uuid

import psycopg

from control_plane.secret_crypto import encrypt_tenant_secret
from control_plane.secrets import secret_hash

from .auth import TenantAuthError, issue_portal_session
from .supabase_admin import invite_auth_user_by_email


def get_membership_by_auth_user(
    conn: psycopg.Connection, auth_user_id: str
) -> dict | None:
    row = conn.execute(
        """
        select m.tenant_id, m.auth_user_id, m.email, m.role, t.name, t.status,
               coalesce(m.status, 'active')
          from tenant_members m
          join tenants t on t.id = m.tenant_id
         where m.auth_user_id = %s
         limit 1
        """,
        (auth_user_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "tenant_id": str(row[0]),
        "auth_user_id": str(row[1]),
        "email": row[2],
        "role": row[3],
        "tenant_name": row[4],
        "tenant_status": row[5],
        "status": row[6],
    }


def require_membership_on_tenant(
    conn: psycopg.Connection, *, auth_user_id: str, tenant_id: str
) -> dict:
    membership = get_membership_by_auth_user(conn, auth_user_id)
    if membership is None or membership["tenant_id"] != str(tenant_id):
        raise TenantAuthError(403, "not a member of this tenant")
    return membership


def require_owner_on_tenant(
    conn: psycopg.Connection, *, auth_user_id: str, tenant_id: str
) -> dict:
    membership = require_membership_on_tenant(
        conn, auth_user_id=auth_user_id, tenant_id=tenant_id
    )
    if membership["role"] != "owner":
        raise TenantAuthError(403, "owner role required")
    return membership


def list_members(conn: psycopg.Connection, tenant_id: str) -> list[dict]:
    rows = conn.execute(
        """
        select auth_user_id, email, role, coalesce(status, 'active'), created_at
          from tenant_members
         where tenant_id = %s
         order by
           case role when 'owner' then 0 else 1 end,
           created_at asc
        """,
        (tenant_id,),
    ).fetchall()
    return [
        {
            "auth_user_id": str(r[0]),
            "email": r[1],
            "role": r[2],
            "status": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]


def mark_member_active(conn: psycopg.Connection, auth_user_id: str) -> None:
    has_status = conn.execute(
        """
        select 1 from information_schema.columns
         where table_schema = 'public'
           and table_name = 'tenant_members'
           and column_name = 'status'
        """
    ).fetchone()
    if not has_status:
        return
    conn.execute(
        """
        update tenant_members
           set status = 'active'
         where auth_user_id = %s
           and coalesce(status, 'active') <> 'active'
        """,
        (auth_user_id,),
    )

def invite_member_to_tenant(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    inviter_auth_user_id: str,
    email: str,
) -> dict:
    """Owner-only: create/link Supabase Auth user + member row on THIS tenant."""
    require_owner_on_tenant(
        conn, auth_user_id=inviter_auth_user_id, tenant_id=tenant_id
    )
    normalized = (email or "").strip().lower()
    if not normalized or "@" not in normalized:
        raise TenantAuthError(422, "invalid email")

    existing_row = conn.execute(
        """
        select auth_user_id, role, coalesce(status, 'active')
          from tenant_members
         where tenant_id = %s and lower(coalesce(email, '')) = %s
         limit 1
        """,
        (tenant_id, normalized),
    ).fetchone()
    if existing_row:
        status = str(existing_row[2] or "active")
        if status == "invited":
            # Resend email with /invite redirect (earlier invites often hit Site URL → /login).
            auth_user = invite_auth_user_by_email(normalized)
            return {
                "auth_user_id": str(existing_row[0]),
                "email": normalized,
                "role": str(existing_row[1] or "member"),
                "status": "invited",
                "tenant_id": str(tenant_id),
                "existing_auth_user": True,
                "resent": True,
            }
        raise TenantAuthError(409, "user is already a member of this tenant")

    auth_user = invite_auth_user_by_email(normalized)
    auth_user_id = str(auth_user["id"])

    other = get_membership_by_auth_user(conn, auth_user_id)
    if other is not None:
        if other["tenant_id"] == str(tenant_id):
            raise TenantAuthError(409, "user is already a member of this tenant")
        raise TenantAuthError(409, "user already belongs to another tenant")

    try:
        conn.execute(
            """
            insert into tenant_members (tenant_id, auth_user_id, email, role, status)
            values (%s, %s, %s, 'member', 'invited')
            """,
            (tenant_id, auth_user_id, normalized),
        )
    except psycopg.errors.UndefinedColumn:
        conn.execute(
            """
            insert into tenant_members (tenant_id, auth_user_id, email, role)
            values (%s, %s, %s, 'member')
            """,
            (tenant_id, auth_user_id, normalized),
        )
    except psycopg.errors.UniqueViolation as exc:
        raise TenantAuthError(409, "user already belongs to another tenant") from exc

    return {
        "auth_user_id": auth_user_id,
        "email": normalized,
        "role": "member",
        "status": "invited",
        "tenant_id": str(tenant_id),
        "existing_auth_user": bool(auth_user.get("existing")),
    }


def _tenant_display_name(email: str | None) -> str:
    if email and "@" in email:
        local = email.split("@", 1)[0].strip()
        if local:
            return f"{local}'s workspace"
    return "Workspace"


def bootstrap_owner_for_auth_user(
    conn: psycopg.Connection,
    *,
    auth_user_id: str,
    email: str | None,
) -> dict:
    """Create tenants row + owner membership. Caller must hold a transaction."""
    existing = get_membership_by_auth_user(conn, auth_user_id)
    if existing is not None:
        return existing

    tenant_id = str(uuid.uuid4())
    raw_secret = secrets.token_urlsafe(32)
    hashed = secret_hash(raw_secret)
    enc = encrypt_tenant_secret(raw_secret)
    name = _tenant_display_name(email)

    try:
        conn.execute(
            """
            insert into tenants (
                id, name, hmac_secret, hmac_secret_enc, hmac_secret_hash,
                status, max_concurrent, max_minutes_month, allowed_origins
            )
            values (
                %s, %s, %s, %s, %s,
                'active', 20, 10000,
                array['http://localhost:3000', 'http://127.0.0.1:3000']
            )
            """,
            (
                tenant_id,
                name,
                None if enc else raw_secret,
                enc,
                hashed,
            ),
        )
        conn.execute(
            """
            insert into quota_state (tenant_id, concurrent_now, minutes_this_month)
            values (%s, 0, 0)
            on conflict (tenant_id) do nothing
            """,
            (tenant_id,),
        )
        try:
            conn.execute(
                """
                insert into tenant_members (tenant_id, auth_user_id, email, role, status)
                values (%s, %s, %s, 'owner', 'active')
                """,
                (tenant_id, auth_user_id, email),
            )
        except psycopg.errors.UndefinedColumn:
            conn.execute(
                """
                insert into tenant_members (tenant_id, auth_user_id, email, role)
                values (%s, %s, %s, 'owner')
                """,
                (tenant_id, auth_user_id, email),
            )
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raced = get_membership_by_auth_user(conn, auth_user_id)
        if raced is None:
            raise TenantAuthError(409, "membership race — retry login") from None
        return raced

    return {
        "tenant_id": tenant_id,
        "auth_user_id": auth_user_id,
        "email": email,
        "role": "owner",
        "tenant_name": name,
        "tenant_status": "active",
        "status": "active",
    }


def resolve_or_bootstrap_membership(
    conn: psycopg.Connection,
    *,
    auth_user_id: str,
    email: str | None,
) -> dict:
    membership = get_membership_by_auth_user(conn, auth_user_id)
    if membership is None:
        membership = bootstrap_owner_for_auth_user(
            conn, auth_user_id=auth_user_id, email=email
        )
    else:
        mark_member_active(conn, auth_user_id)
        membership["status"] = "active"
    if membership["tenant_status"] != "active":
        raise TenantAuthError(403, "tenant suspended")
    return membership


def exchange_supabase_user_for_portal_session(
    conn: psycopg.Connection,
    *,
    auth_user_id: str,
    email: str | None,
    jwt_secret: str,
) -> dict:
    membership = resolve_or_bootstrap_membership(
        conn, auth_user_id=auth_user_id, email=email
    )
    session = issue_portal_session(
        conn,
        tenant_id=membership["tenant_id"],
        jwt_secret=jwt_secret,
        auth_user_id=auth_user_id,
        role=membership["role"],
    )
    session["role"] = membership["role"]
    session["email"] = membership.get("email") or email
    return session


def _verify_tenant_hmac(
    conn: psycopg.Connection, *, tenant_id: str, tenant_secret: str
) -> tuple[str, str]:
    """Return (tenant_id, status) if HMAC matches; raise TenantAuthError otherwise."""
    row = conn.execute(
        """
        select id, status, hmac_secret_hash
          from tenants
         where id = %s
        """,
        (tenant_id,),
    ).fetchone()
    if row is None:
        raise TenantAuthError(401, "invalid credentials")
    tid, status, stored_hash = row
    if status != "active":
        raise TenantAuthError(403, "tenant suspended")
    provided_hash = secret_hash(tenant_secret)
    if not stored_hash or not hmac.compare_digest(provided_hash, stored_hash):
        raise TenantAuthError(401, "invalid credentials")
    return str(tid), str(status)


def _tenant_agent_count(conn: psycopg.Connection, tenant_id: str) -> int:
    try:
        row = conn.execute(
            "select count(*) from agents where tenant_id = %s",
            (tenant_id,),
        ).fetchone()
    except psycopg.errors.UndefinedTable:
        return 0
    return int(row[0] if row else 0)


def _detach_empty_membership(
    conn: psycopg.Connection, *, auth_user_id: str, membership: dict
) -> None:
    """Drop a mistaken Phase-1 bootstrap membership if that tenant has no agents."""
    if _tenant_agent_count(conn, membership["tenant_id"]) > 0:
        raise TenantAuthError(
            409,
            "your email is already linked to a different tenant that has agents — "
            "ask an owner to invite you, or use that workspace",
        )
    conn.execute(
        "delete from tenant_members where auth_user_id = %s",
        (auth_user_id,),
    )


def claim_existing_tenant_for_auth_user(
    conn: psycopg.Connection,
    *,
    auth_user_id: str,
    email: str | None,
    tenant_id: str,
    tenant_secret: str,
    jwt_secret: str,
) -> dict:
    """Link a Supabase Auth user to a pre-email tenant by proving the HMAC secret.

    Legacy tenants (provisioned with tenant id + secret only) have no ``tenant_members``
    row. After the owner creates an email/password Auth user, they claim the old tenant
    here instead of keeping a brand-new empty bootstrap workspace.
    """
    tid, _status = _verify_tenant_hmac(
        conn, tenant_id=tenant_id.strip(), tenant_secret=tenant_secret
    )

    existing = get_membership_by_auth_user(conn, auth_user_id)
    if existing is not None:
        if existing["tenant_id"] == tid:
            mark_member_active(conn, auth_user_id)
            session = issue_portal_session(
                conn,
                tenant_id=tid,
                jwt_secret=jwt_secret,
                auth_user_id=auth_user_id,
                role=existing["role"],
            )
            session["role"] = existing["role"]
            session["email"] = existing.get("email") or email
            session["claimed"] = False
            return session
        _detach_empty_membership(conn, auth_user_id=auth_user_id, membership=existing)

    owner = conn.execute(
        """
        select auth_user_id from tenant_members
         where tenant_id = %s and role = 'owner'
         limit 1
        """,
        (tid,),
    ).fetchone()
    if owner is not None and str(owner[0]) != str(auth_user_id):
        raise TenantAuthError(
            409,
            "this tenant already has an owner — ask them to invite your email instead",
        )

    already = conn.execute(
        """
        select auth_user_id, role from tenant_members
         where tenant_id = %s and auth_user_id = %s
         limit 1
        """,
        (tid, auth_user_id),
    ).fetchone()
    if already is None:
        try:
            conn.execute(
                """
                insert into tenant_members (tenant_id, auth_user_id, email, role, status)
                values (%s, %s, %s, 'owner', 'active')
                """,
                (tid, auth_user_id, email),
            )
        except psycopg.errors.UndefinedColumn:
            conn.execute(
                """
                insert into tenant_members (tenant_id, auth_user_id, email, role)
                values (%s, %s, %s, 'owner')
                """,
                (tid, auth_user_id, email),
            )
        except psycopg.errors.UniqueViolation as exc:
            raise TenantAuthError(
                409, "email is already linked to another tenant"
            ) from exc

    session = issue_portal_session(
        conn,
        tenant_id=tid,
        jwt_secret=jwt_secret,
        auth_user_id=auth_user_id,
        role="owner",
    )
    session["role"] = "owner"
    session["email"] = email
    session["claimed"] = True
    return session
