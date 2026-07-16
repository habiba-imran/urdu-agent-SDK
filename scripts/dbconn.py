"""Shared dev-database connection parameters, parsed from SUPABASE_DB_URL.

Returns discrete keyword params (host/user/password/...) rather than a URL, so a
special character such as '@' in the password needs no percent-encoding and can
never be mis-parsed by libpq. DEV only — the value comes from .env.local, which
holds the dev project's connection string (H1/H6). Never prod.
"""

from __future__ import annotations

import sys
import urllib.parse as up
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent


def conn_kwargs() -> dict:
    """Parse SUPABASE_DB_URL from .env.local into psycopg/libpq keyword params."""
    raw = dotenv_values(ROOT / ".env.local").get("SUPABASE_DB_URL")
    if not raw:
        sys.exit("SUPABASE_DB_URL not set in .env.local (human tasks H1/H6).")
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
