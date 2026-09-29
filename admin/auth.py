"""Admin auth — a completely separate domain from the tenant/LiveKit token mint (control_plane/).

GATE 6 line 2: "admin JWT cannot be used as a tenant JWT (and vice versa)". The tenant-facing
token is a LiveKit `AccessToken` (control_plane/mint.py): signed with `LIVEKIT_API_SECRET`,
`iss=<LIVEKIT_API_KEY>`, a `video` grants block, no `aud` claim (verified live against the
installed `livekit-api` SDK — see the shape check this module's tests assert against).

The admin JWT is deliberately different on both axes, not just one:
  - CRYPTOGRAPHIC: signed with `ADMIN_JWT_SECRET`, a value that is never LIVEKIT_API_SECRET and
    is read from its own env var. A LiveKit token verified against ADMIN_JWT_SECRET fails
    signature verification (different key); an admin token verified against LIVEKIT_API_SECRET
    fails the same way.
  - STRUCTURAL: `aud="admin-portal"`, no `video` grants block, `sub=<admin_users.id>`. Even if
    someone tried to reuse a decoded-without-verification token shape, this app's verifier
    rejects any token missing `aud=="admin-portal"` or carrying a `video` key.

DB access uses the same trusted owner connection as mint.py/worker/config.py (SUPABASE_DB_URL,
RLS bypass — ADR-005, and now explicitly re-affirmed as correct for admin by
docs/26-PHASE-6-ADMIN.md: "Admin bypasses RLS by design"). admin_users/admin_audit_log carry no
RLS policy for authenticated/anon (0007_admin.sql) — only this trusted path ever touches them.
"""

from __future__ import annotations

import datetime
import logging
import uuid

import jwt as pyjwt
import psycopg

from .security import hash_password, totp_counter_for, verify_password

ADMIN_JWT_AUDIENCE = "admin-portal"
ADMIN_JWT_ISSUER = "uva-admin"
ADMIN_JWT_TTL_SEC = (
    8 * 3600
)  # a work session, not a 120s room-join grant — different threat model


class AdminAuthError(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(f"{status}: {reason}")
        self.status = status
        self.reason = reason


def provision_admin(
    conn: psycopg.Connection, *, email: str, password: str, totp_secret: str
) -> str:
    """Create an admin_users row. Returns the new admin_id. MFA is mandatory at creation time."""
    admin_id = str(uuid.uuid4())
    conn.execute(
        "insert into admin_users (id, email, password_hash, totp_secret) values (%s, %s, %s, %s)",
        (admin_id, email, hash_password(password), totp_secret),
    )
    return admin_id


def _consume_totp_counter(conn: psycopg.Connection, admin_id, counter: int) -> bool:
    """Claim this TOTP step for this admin. False when it was already used (a replay).

    The UPDATE is the check: it only matches when the stored counter is lower, so two
    concurrent logins with the same code cannot both win.
    """
    try:
        claimed = conn.execute(
            "update admin_users set last_totp_counter = %s "
            "where id = %s and (last_totp_counter is null or last_totp_counter < %s) "
            "returning id",
            (counter, admin_id, counter),
        ).fetchone()
    except psycopg.errors.UndefinedColumn:
        # 0031 not applied yet: fall back to the pre-fix behaviour rather than locking
        # every admin out, and say so.
        conn.rollback()
        logging.getLogger("admin.auth").warning(
            "admin_users.last_totp_counter missing (migration 0031) - TOTP replay "
            "protection is NOT active"
        )
        return True
    return claimed is not None


def _account_disabled(conn: psycopg.Connection, admin_id) -> bool:
    """True when the account is disabled (§3.5). False when 0032 has not been applied."""
    try:
        row = conn.execute(
            "select disabled_at from admin_users where id = %s", (admin_id,)
        ).fetchone()
    except psycopg.errors.UndefinedColumn:
        conn.rollback()
        logging.getLogger("admin.auth").warning(
            "admin_users.disabled_at missing (migration 0032) - account disablement is "
            "NOT enforced"
        )
        return False
    return bool(row and row[0] is not None)


def login(
    conn: psycopg.Connection,
    *,
    email: str,
    password: str,
    totp_code: str,
    jwt_secret: str,
    now: int | None = None,
) -> dict:
    """Verify BOTH factors (password + current TOTP code). Either failing -> 401, same message
    (do not reveal which factor was wrong — standard auth-endpoint discipline, mirrors mint.py's
    "unknown tenant" vs "bad signature" both being 401)."""
    row = conn.execute(
        "select id, password_hash, totp_secret from admin_users where email = %s",
        (email,),
    ).fetchone()
    if row is None:
        raise AdminAuthError(401, "invalid credentials")
    admin_id, password_hash, totp_secret = row
    # §3.5: a disabled account must not be able to log in. Same 401 as a wrong password, so
    # the endpoint does not confirm which accounts exist or which are suspended.
    if _account_disabled(conn, admin_id):
        raise AdminAuthError(401, "invalid credentials")

    if not verify_password(password, password_hash):
        raise AdminAuthError(401, "invalid credentials")

    # F-H14: a TOTP code must be single-use. The +/-1 step drift window keeps a code
    # arithmetically valid for up to 90 seconds, so without this a captured code can be
    # replayed (RFC 6238 §5.2 requires refusing a previously accepted code).
    counter = totp_counter_for(totp_secret, totp_code)
    if counter is None:
        raise AdminAuthError(401, "invalid credentials")
    if not _consume_totp_counter(conn, admin_id, counter):
        raise AdminAuthError(401, "invalid credentials")

    now_dt = (
        datetime.datetime.fromtimestamp(now, tz=datetime.UTC)
        if now is not None
        else datetime.datetime.now(datetime.UTC)
    )
    claims = {
        "sub": str(admin_id),
        "aud": ADMIN_JWT_AUDIENCE,
        "iss": ADMIN_JWT_ISSUER,
        "email": email,
        "iat": now_dt,
        "exp": now_dt + datetime.timedelta(seconds=ADMIN_JWT_TTL_SEC),
    }
    token = pyjwt.encode(claims, jwt_secret, algorithm="HS256")
    return {"token": token, "admin_id": str(admin_id), "expires_in": ADMIN_JWT_TTL_SEC}


def assert_admin_session_valid(conn: psycopg.Connection, claims: dict) -> None:
    """Refuse a token whose account was disabled or whose sessions were revoked (§3.5).

    Admin tokens live for 8 hours and were previously accepted for that whole window no
    matter what happened to the account; the only kill switch was rotating
    ADMIN_JWT_SECRET, which signs out every admin at once.

    Fails OPEN if the columns are missing (0032 not applied yet) and CLOSED on an actual
    negative answer.
    """
    admin_id = claims.get("sub")
    if not admin_id:
        raise AdminAuthError(401, "invalid admin token")
    try:
        row = conn.execute(
            "select disabled_at, tokens_valid_from from admin_users where id = %s",
            (admin_id,),
        ).fetchone()
    except psycopg.errors.UndefinedColumn:
        conn.rollback()
        logging.getLogger("admin.auth").warning(
            "admin_users.disabled_at/tokens_valid_from missing (migration 0032) - admin "
            "token revocation is NOT active"
        )
        return
    if row is None:
        raise AdminAuthError(401, "admin account no longer exists")
    disabled_at, tokens_valid_from = row
    if disabled_at is not None:
        raise AdminAuthError(401, "admin account is disabled")
    if tokens_valid_from is not None:
        issued_at = claims.get("iat")
        if issued_at is None:
            raise AdminAuthError(401, "admin token cannot be checked against revocation")
        issued_dt = datetime.datetime.fromtimestamp(int(issued_at), tz=datetime.UTC)
        if issued_dt < tokens_valid_from:
            raise AdminAuthError(401, "admin session was revoked")


def verify_admin_jwt(token: str, jwt_secret: str) -> dict:
    """Raises AdminAuthError(401, ...) on any failure: bad signature, wrong/missing audience,
    a `video` grants block present (i.e. someone handed us a LiveKit tenant token), or expiry."""
    try:
        claims = pyjwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience=ADMIN_JWT_AUDIENCE,
            issuer=ADMIN_JWT_ISSUER,
        )
    except pyjwt.PyJWTError as e:
        raise AdminAuthError(401, "invalid admin token") from e
    if "video" in claims:
        raise AdminAuthError(
            401, "invalid admin token"
        )  # a tenant/LiveKit-shaped token
    return claims
