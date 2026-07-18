"""Shared database connection parameters, parsed from SUPABASE_DB_URL.

Returns discrete keyword params (host/user/password/...) rather than a URL, so a
special character such as '@' in the password needs no percent-encoding and can
never be mis-parsed by libpq.

P9 FIX (2026-07-18): previously read ONLY from a physical .env.local file via
dotenv_values() — correct for local dev (H1/H6), but silently broken in any
deployed environment (container/host) where secrets arrive as real process env
vars and no .env.local file exists — dotenv_values() on a missing file returns
{}, so this would have returned SUPABASE_DB_URL=None with no error until a much
later, more confusing failure. Fixed to check os.environ FIRST, matching the
pattern already established in control_plane/secrets.py::EnvSecretProvider and
admin/app.py::_ensure_admin_jwt_secret — .env.local stays the fallback so every
existing local-dev workflow is unchanged.
"""

from __future__ import annotations

import os
import sys
import urllib.parse as up
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent


def conn_kwargs() -> dict:
    """Parse SUPABASE_DB_URL — checks the real process environment first (prod), falls back to
    .env.local (dev) — into psycopg/libpq keyword params."""
    raw = os.environ.get("SUPABASE_DB_URL") or dotenv_values(ROOT / ".env.local").get(
        "SUPABASE_DB_URL"
    )
    if not raw:
        sys.exit(
            "SUPABASE_DB_URL not set (checked os.environ, then .env.local — human tasks H1/H6)."
        )
    p = up.urlparse(raw)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": p.username or "postgres",
        # unquote so this works whether the URL's password is percent-encoded (%40)
        # or has a literal '@'; the value passed to libpq must be the real password.
        "password": up.unquote(p.password or ""),
        "dbname": (p.path or "/postgres").lstrip("/") or "postgres",
        "sslmode": "require",
    }
