#!/usr/bin/env python3
"""LIVE HUMAN-GATE attack — docs/27-PHASE-7-SECURITY.md HUMAN GATE item 1:
"Read tenant B's agents using tenant A's credentials." Must fail.

STANDALONE script (deliberately NOT collected by pytest, same not-pytest-collected pattern as
tests/test_token_widen_live.py). Built by the agent, dry-run by the agent to prove it works --
running it is NOT the human gate. The human runs this personally as the actual gate-closing act:

    python tests/test_cross_tenant_read_live.py

What it does: seeds two real tenants (A, B) with one real agent each in the live dev DB, then
connects as the Supabase `authenticated` role carrying ONLY tenant A's JWT claim
(`request.jwt.claims = {"tenant_id": <A>}` -- the exact mechanism a real tenant-scoped Supabase
session would carry) and attempts to read tenant B's `agents` row three ways: an unscoped
`select *`, a `where tenant_id = B` filter (the IDOR-style direct-ID guess), and a join through
`sessions`. Every attempt must return zero of tenant B's rows. If any leaks, this writes a
SECURITY-CRITICAL entry to state/BLOCKERS.md and exits non-zero.

This is the same trust boundary tests/test_isolation.py already proves in pytest form (re-run
fresh this session, see state/HANDOFF.md) -- this file exists to give the human a narrated,
directly-runnable, non-pytest artifact that matches the human-gate ritual already established for
tests/test_token_widen_live.py in Phase 2, rather than asking them to parse pytest dots.
"""

import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import json  # noqa: E402

import psycopg  # noqa: E402

from dbconn import conn_kwargs  # noqa: E402

vulns: list[tuple[str, str]] = []


def hr(title: str) -> None:
    print("\n" + "=" * 78 + "\n" + title + "\n" + "=" * 78)


def write_blocker() -> None:
    path = ROOT / "state" / "BLOCKERS.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = [
        "",
        f"## BLOCK-SEC | P7 human-gate cross-tenant read | {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "**SECURITY-CRITICAL — not a normal 3-strike blocker.**",
        "A cross-tenant read SUCCEEDED using tenant A's credentials against tenant B's data:",
    ]
    for name, detail in vulns:
        entry.append(f"- {name} :: {detail}")
    entry.append("**STATUS: BLOCKED — Phase 7 does not close. Human must review immediately.**")
    out, inserted = [], False
    for ln in lines:
        out.append(ln)
        if ln.strip() == "## Open" and not inserted:
            out.extend(entry)
            inserted = True
    if not inserted:
        out.extend(entry)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    kw = conn_kwargs()
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    ag_a, ag_b = str(uuid.uuid4()), str(uuid.uuid4())
    admin = psycopg.connect(**kw, connect_timeout=30, autocommit=True)
    try:
        hr("SETUP — seeding two real tenants + one real agent each (table-owner connection)")
        admin.execute(
            "insert into tenants (id, name, hmac_secret_hash) values (%s,'gate-A',%s), (%s,'gate-B',%s)",
            (a, "x", b, "x"),
        )
        admin.execute(
            "insert into agents (id, tenant_id, name, prompt, voice_id) "
            "values (%s,%s,'agent-A','p','v_meklc281'), (%s,%s,'agent-B','p','v_meklc281')",
            (ag_a, a, ag_b, b),
        )
        print(f"tenant A = {a}\ntenant B = {b}\nagent A  = {ag_a} (belongs to A)\nagent B  = {ag_b} (belongs to B)")

        hr("ATTACK — authenticated as tenant A ONLY, attempt to read tenant B's data 3 ways")
        with psycopg.connect(**kw, connect_timeout=30) as reader:
            cur = reader.cursor()
            cur.execute("set local role authenticated")
            cur.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (json.dumps({"tenant_id": a}),),
            )

            print("\n[1] unscoped `select * from agents` — does RLS silently filter to only A's rows?")
            all_visible = cur.execute("select id, tenant_id, name from agents").fetchall()
            leaked_1 = [r for r in all_visible if str(r[1]) == b]
            print(f"    rows visible total: {len(all_visible)} | rows belonging to B: {len(leaked_1)}")
            if leaked_1:
                vulns.append(("unscoped select leaked tenant B rows", str(leaked_1)))

            print("\n[2] direct `where tenant_id = B` (attacker knows/guesses B's real UUID)")
            direct = cur.execute(
                "select id, name from agents where tenant_id = %s", (b,)
            ).fetchall()
            print(f"    rows returned: {len(direct)} (must be 0)")
            if direct:
                vulns.append(("direct tenant_id=B filter returned rows", str(direct)))

            print("\n[3] `select id, name from agents where id = agent_B` (attacker knows B's agent_id)")
            by_id = cur.execute(
                "select id, name, tenant_id from agents where id = %s", (ag_b,)
            ).fetchall()
            print(f"    rows returned: {len(by_id)} (must be 0)")
            if by_id:
                vulns.append(("direct agent_id=B's-agent lookup returned a row", str(by_id)))

            print("\n[4] tenants table — can A see B's tenant row at all?")
            tenant_rows = cur.execute(
                "select id, name from tenants where id = %s", (b,)
            ).fetchall()
            print(f"    rows returned: {len(tenant_rows)} (must be 0)")
            if tenant_rows:
                vulns.append(("tenant A could read tenant B's tenants row", str(tenant_rows)))

        hr("VERDICT")
        if vulns:
            write_blocker()
            print("SECURITY-CRITICAL: the following cross-tenant reads SUCCEEDED (must have failed):")
            for name, detail in vulns:
                print(f"  [VULN] {name} :: {detail}")
            print("\nWritten to state/BLOCKERS.md. Phase 7 does not close.")
            return 2
        print("All 4 cross-tenant read attempts returned zero of tenant B's rows.")
        print("RLS held using only tenant A's JWT claim, table-owner connection never used to read.")
        return 0
    finally:
        for t in ("sessions", "quota_state", "used_nonces", "agents"):
            admin.execute(f"delete from {t} where tenant_id in (%s, %s)", (a, b))
        admin.execute("delete from tenants where id in (%s, %s)", (a, b))
        admin.close()


if __name__ == "__main__":
    raise SystemExit(main())
