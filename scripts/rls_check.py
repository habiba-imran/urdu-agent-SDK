#!/usr/bin/env python3
"""GATE 1: every table has RLS. No exceptions (audit gap: schema had no verifier)."""
import os, sys
try: import psycopg
except ImportError: print("SKIP: psycopg not installed (pre-Phase-1)"); sys.exit(0)
DSN = os.getenv("SUPABASE_DB_URL")
if not DSN: print("SKIP: SUPABASE_DB_URL unset"); sys.exit(0)
Q = """select tablename, rowsecurity from pg_tables
       where schemaname='public' order by tablename"""
with psycopg.connect(DSN) as c:
    rows = c.execute(Q).fetchall()
bad = [t for t, rls in rows if not rls]
for t, rls in rows: print(f"  {'OK ' if rls else 'RLS OFF'}  {t}")
if bad:
    print(f"\nGATE FAIL: RLS disabled on {bad}", file=sys.stderr)
    print("Every table. No exceptions. docs/33-GUIDE-SUPABASE.md §4", file=sys.stderr)
    sys.exit(1)
print(f"\nRLS OK on all {len(rows)} tables")
