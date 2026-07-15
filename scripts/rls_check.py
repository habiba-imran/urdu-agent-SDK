#!/usr/bin/env python3
"""GATE 1: every public table has RLS enabled. No exceptions (schema had no verifier).

Skips cleanly when the dev DB is not configured yet (pre-Phase-1); once
SUPABASE_DB_URL is present it connects and fails if any table lacks RLS or if the
schema is missing entirely.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import psycopg
except ImportError:
    print("SKIP: psycopg not installed (pre-Phase-1)")
    sys.exit(0)

from dbconn import conn_kwargs  # noqa: E402  (kept after the psycopg availability guard)

try:
    kw = conn_kwargs()
except SystemExit:
    print("SKIP: SUPABASE_DB_URL unset (pre-Phase-1)")
    sys.exit(0)

Q = """select tablename, rowsecurity from pg_tables
       where schemaname = 'public' order by tablename"""
with psycopg.connect(**kw, connect_timeout=30) as c:
    rows = c.execute(Q).fetchall()

for t, rls in rows:
    print(f"  {'OK     ' if rls else 'RLS OFF'}  {t}")

if not rows:
    print(
        "\nGATE FAIL: no public tables found — has `make db-reset` been run?",
        file=sys.stderr,
    )
    sys.exit(1)

bad = [t for t, rls in rows if not rls]
if bad:
    print(f"\nGATE FAIL: RLS disabled on {bad}", file=sys.stderr)
    print("Every table. No exceptions. docs/33-GUIDE-SUPABASE.md §4", file=sys.stderr)
    sys.exit(1)

print(f"\nRLS OK on all {len(rows)} tables")
