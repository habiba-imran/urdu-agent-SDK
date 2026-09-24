#!/usr/bin/env python3
"""Forward-only migration runner (F-H11).

Before this, the only automation was scripts/db_reset.py — a DEV-ONLY script whose first
migration opens with `drop table if exists usage_events, quota_state, sessions, agents,
voices, tenants cascade`. Production schema changes were hand-applied with no record of what
had run, and one `make db-reset` against a production connection string would destroy every
tenant, agent, session and usage row.

This runner:
  * records what it applies in a `schema_migrations` table (filename, checksum, when);
  * applies only files that have not been applied, in filename order;
  * wraps each file in its own transaction — a failing migration rolls back, and the ones
    before it stay applied;
  * refuses to run a file whose contents changed after it was applied (checksum mismatch),
    because that means the database and the repo disagree about what the schema is;
  * never drops anything and never touches data.

First use against an existing database (staging/production already built by hand):

    python scripts/migrate.py --baseline      # record every current file as applied
    python scripts/migrate.py --status        # confirm: nothing pending

Then, normally:

    python scripts/migrate.py --status        # what would run
    python scripts/migrate.py                 # apply pending files

0001_schema.sql is destructive by design (db_reset rebuilds dev from zero with it), so it is
never applied by this runner unless it is already recorded as applied or --allow-initial is
passed explicitly on an empty database.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from dbconn import conn_kwargs
except ImportError:  # pragma: no cover - import shim, same pattern as sibling scripts
    from scripts.dbconn import conn_kwargs  # type: ignore # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
# 0001 drops every table before recreating it. It is the dev rebuild path, not a migration
# to replay against a database that holds data.
DESTRUCTIVE_INITIAL = "0001_schema.sql"

CREATE_TABLE = """
create table if not exists schema_migrations (
  filename    text primary key,
  checksum    text not null,
  applied_at  timestamptz not null default now(),
  applied_by  text
)
"""


def checksum(path: Path) -> str:
    # Normalise line endings so a Windows checkout and a Linux CI agree.
    body = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(body).hexdigest()


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)


def applied_map(conn: psycopg.Connection) -> dict[str, str]:
    conn.execute(CREATE_TABLE)
    rows = conn.execute("select filename, checksum from schema_migrations").fetchall()
    return {r[0]: r[1] for r in rows}


def plan(conn: psycopg.Connection, *, allow_initial: bool) -> tuple[list[Path], list[str]]:
    """Return (pending files, checksum-mismatch warnings)."""
    applied = applied_map(conn)
    pending: list[Path] = []
    drift: list[str] = []
    for path in migration_files():
        recorded = applied.get(path.name)
        if recorded is None:
            if path.name == DESTRUCTIVE_INITIAL and not allow_initial:
                continue
            pending.append(path)
        elif recorded != checksum(path):
            drift.append(path.name)
    return pending, drift


def duplicate_prefixes() -> dict[str, list[str]]:
    """F-M27: the repo already has two different 0014_ migrations, plus a second naming
    scheme (timestamped 20260801185628_...). Ordering happens to resolve alphabetically
    today; a third contributor reusing a number is how that stops being true."""
    seen: dict[str, list[str]] = {}
    for path in migration_files():
        prefix = path.name.split("_", 1)[0]
        seen.setdefault(prefix, []).append(path.name)
    return {k: v for k, v in seen.items() if len(v) > 1}


def cmd_status(conn: psycopg.Connection, *, allow_initial: bool) -> int:
    for prefix, names in duplicate_prefixes().items():
        print(f"[migrate] WARNING: version {prefix} is used by {len(names)} files: " + ", ".join(names))
    pending, drift = plan(conn, allow_initial=allow_initial)
    applied = applied_map(conn)
    print(f"[migrate] {len(applied)} applied, {len(pending)} pending")
    for path in pending:
        print(f"  pending: {path.name}")
    for name in drift:
        print(f"  CHANGED SINCE APPLIED: {name}")
    if drift:
        print(
            "[migrate] a recorded migration's contents changed - the database and the repo "
            "disagree about the schema. Resolve by adding a NEW migration, not by editing "
            "an applied one."
        )
        return 1
    return 0


def cmd_baseline(conn: psycopg.Connection) -> int:
    """Record every current file as applied, without running any of it."""
    applied = applied_map(conn)
    recorded = 0
    for path in migration_files():
        if path.name in applied:
            continue
        conn.execute(
            "insert into schema_migrations (filename, checksum, applied_by) "
            "values (%s, %s, %s) on conflict (filename) do nothing",
            (path.name, checksum(path), "baseline"),
        )
        recorded += 1
    conn.commit()
    print(f"[migrate] baseline recorded {recorded} file(s) as already applied")
    print("[migrate] nothing was executed against the database")
    return 0


def cmd_apply(conn: psycopg.Connection, *, allow_initial: bool, dry_run: bool) -> int:
    pending, drift = plan(conn, allow_initial=allow_initial)
    if drift:
        for name in drift:
            print(f"[migrate] REFUSING: {name} changed after it was applied")
        return 1
    if not pending:
        print("[migrate] nothing to apply")
        return 0

    for path in pending:
        if dry_run:
            print(f"[migrate] would apply {path.name}")
            continue
        sql = path.read_text(encoding="utf-8")
        print(f"[migrate] applying {path.name} ...", flush=True)
        try:
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "insert into schema_migrations (filename, checksum, applied_by) "
                    "values (%s, %s, %s)",
                    (path.name, checksum(path), "migrate.py"),
                )
        except Exception as exc:
            print(f"[migrate] FAILED on {path.name}: {exc}")
            print("[migrate] that file was rolled back; earlier files remain applied")
            return 1
        print(f"[migrate] applied {path.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="Show applied and pending")
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Record all current files as applied without executing them (existing databases)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List what would be applied")
    parser.add_argument(
        "--allow-initial",
        action="store_true",
        help=f"Also apply {DESTRUCTIVE_INITIAL}, which DROPS every table (empty databases only)",
    )
    args = parser.parse_args(argv)

    with psycopg.connect(**conn_kwargs(), connect_timeout=15) as conn:
        conn.autocommit = False
        if args.status:
            rc = cmd_status(conn, allow_initial=args.allow_initial)
            conn.commit()
            return rc
        if args.baseline:
            return cmd_baseline(conn)
        rc = cmd_apply(conn, allow_initial=args.allow_initial, dry_run=args.dry_run)
        conn.commit()
        return rc


if __name__ == "__main__":
    raise SystemExit(main())
