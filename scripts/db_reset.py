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

🔴 KNOWN GAP, GUARDED BELOW (found P7, 2026-07-17): migration 0005 deliberately
leaves voices.preview_url NULL — it's populated at RUNTIME by
scripts/upload_voice_previews.py, not by any migration. A reset wipes that column
back to NULL even though the CDN files themselves are untouched (Storage is
separate from Postgres). This silently regressed GATE 5's "81/81 preview_url
populated" evidence once already (re-running db_reset.py during Phase 6 to apply
0007_admin.sql wiped it, undetected until Phase 7's ABUSE checklist noticed).
main() checks for this after every reset and prints a loud warning rather than
silently leaving it stale — see _warn_if_previews_stale() below.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dbconn import conn_kwargs

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "supabase" / "migrations"
PREVIEWS_DIR = ROOT / "voice-picker" / "previews"


def _warn_if_previews_stale(kw: dict) -> None:
    """After a reset, check whether locally-recorded preview WAVs exist for voices whose
    preview_url just got wiped back to NULL by the re-seed. Not auto-fixed here (a schema-reset
    script silently making network calls to Storage would be its own surprise) — just impossible
    to miss."""
    local_ids = {p.stem for p in PREVIEWS_DIR.glob("*.wav")}
    if not local_ids:
        return
    import psycopg

    with psycopg.connect(**kw, connect_timeout=15) as conn:
        rows = conn.execute(
            "select id from voices where preview_url is null and id = any(%s)",
            (list(local_ids),),
        ).fetchall()
    stale = {r[0] for r in rows}
    if stale:
        print(
            f"\nWARNING: {len(stale)} voice(s) have a local preview .wav in "
            f"{PREVIEWS_DIR} but voices.preview_url is now NULL (this reset wiped it — "
            "migration 0005 never sets it, only runtime upload does).\n"
            "    Fix: python scripts/upload_voice_previews.py   (Storage-only, uploads "
            "already-recorded files — makes ZERO new Uplift calls)\n"
        )


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
    _warn_if_previews_stale(kw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
