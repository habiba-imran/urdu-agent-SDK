"""Login throttling and failed-attempt audit, shared by the admin and tenant portals (F-H14).

Neither login endpoint was rate-limited, throttled or locked out, and only successful admin
actions were recorded — so a password-guessing run against the portal that can rotate any
tenant's secret left no trace at all.

State is in the database (0031), not in process memory: the in-process limiter of F-H5 resets
on deploy and is per worker, which is fine for absorbing floods and useless as a lockout.

Every failure is recorded with a reason, never with the credential that was tried.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("auth.login_guard")

# A human retyping a password gets plenty of room; a script does not. Counted per identity
# and, separately, per client IP so one attacker cannot lock out an entire realm by guessing
# against many accounts.
MAX_FAILURES_PER_IDENTITY = 8
MAX_FAILURES_PER_IP = 30
WINDOW_MINUTES = 15


class LoginThrottled(Exception):
    def __init__(self, retry_after_seconds: int):
        super().__init__("too many failed login attempts")
        self.retry_after_seconds = retry_after_seconds
        self.status = 429


def _table_exists(conn: Any) -> bool:
    try:
        return (
            conn.execute(
                "select 1 from information_schema.tables where table_name = 'login_attempts'"
            ).fetchone()
            is not None
        )
    except Exception:
        return False


def record_attempt(
    conn: Any,
    *,
    realm: str,
    identity: str,
    client_ip: str | None,
    successful: bool,
    reason: str | None = None,
) -> None:
    """Append one attempt. Never raises: an auth decision must not depend on the audit write
    succeeding, but a failure to record is logged rather than swallowed (F-M1)."""
    if not _table_exists(conn):
        return
    try:
        conn.execute(
            "insert into login_attempts (realm, identity, client_ip, successful, reason) "
            "values (%s, %s, %s, %s, %s)",
            (realm, (identity or "").strip().lower()[:320], client_ip, successful, reason),
        )
    except Exception:
        logger.warning(
            "could not record %s login attempt for %s", realm, identity, exc_info=True
        )


def assert_not_throttled(
    conn: Any, *, realm: str, identity: str, client_ip: str | None
) -> None:
    """Raise LoginThrottled when this identity or IP has failed too often recently.

    Fails OPEN on a database error: locking everyone out because the audit table is
    unreachable would be a worse outage than the brute-force window it protects.
    """
    if not _table_exists(conn):
        return
    ident = (identity or "").strip().lower()
    try:
        row = conn.execute(
            "select count(*) from login_attempts "
            "where realm = %s and identity = %s and not successful "
            "  and at > now() - (%s || ' minutes')::interval",
            (realm, ident, WINDOW_MINUTES),
        ).fetchone()
        identity_failures = int(row[0]) if row else 0

        ip_failures = 0
        if client_ip:
            row = conn.execute(
                "select count(*) from login_attempts "
                "where realm = %s and client_ip = %s and not successful "
                "  and at > now() - (%s || ' minutes')::interval",
                (realm, client_ip, WINDOW_MINUTES),
            ).fetchone()
            ip_failures = int(row[0]) if row else 0
    except Exception:
        logger.warning("login throttle check failed for %s - allowing", realm, exc_info=True)
        return

    if identity_failures >= MAX_FAILURES_PER_IDENTITY or ip_failures >= MAX_FAILURES_PER_IP:
        logger.warning(
            "login throttled realm=%s identity=%s ip=%s identity_failures=%d ip_failures=%d",
            realm,
            ident,
            client_ip,
            identity_failures,
            ip_failures,
        )
        raise LoginThrottled(WINDOW_MINUTES * 60)
