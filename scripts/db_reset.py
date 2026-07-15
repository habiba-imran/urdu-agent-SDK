#!/usr/bin/env python3
"""Rebuild the dev database from zero by applying supabase/migrations/ in order.

Phase 1 gate: `make db-reset` must rebuild the whole schema from nothing, because
Supabase free projects pause after 7 days idle and return empty
(docs/33-GUIDE-SUPABASE.md §3). The migrations are idempotent (0001 drops before
it creates), so this is safe to re-run.

Each file is applied with psql under --single-transaction + ON_ERROR_STOP, so a
bad migration rolls back rather than leaving a half-built schema. Connection comes
from SUPABASE_DB_URL via discrete PG* env vars (password passed literally, so an
'@' in it needs no encoding). DEV only — never prod.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dbconn import conn_kwargs

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "supabase" / "migrations"


def main() -> int:
    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        sys.exit(f"db-reset: no migrations found in {MIGRATIONS}")

    kw = conn_kwargs()
    env = os.environ.copy()
    env.update(
        PGHOST=kw["host"],
        PGPORT=str(kw["port"]),
        PGUSER=kw["user"],
        PGPASSWORD=kw["password"],
        PGDATABASE=kw["dbname"],
        PGSSLMODE=kw["sslmode"],
    )

    for f in files:
        result = subprocess.run(
            [
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "--single-transaction",
                "-q",
                "-f",
                str(f),
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            sys.stderr.write(result.stdout + result.stderr)
            sys.exit(f"db-reset: FAILED on {f.name}")
        print(f"  applied {f.name}")

    print(f"db-reset: rebuilt from zero ({len(files)} migrations).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
