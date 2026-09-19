# Wave 2 Phase F — Closeout evidence (F-C4 / F-C7)

**Status handoff (new chats):** [`WAVE2-FC4-FC7-STATUS-HANDOFF.md`](./WAVE2-FC4-FC7-STATUS-HANDOFF.md)

**Date:** 2026-09-18  
**Owner:** Habiba (worker proof). Shared exits remain with Ehsan / client / ops.

## F.1 Injection proof

| Artifact | Status |
|---|---|
| `tests/test_injection_write_gate.py` | **Code** — deterministic harness; hostile first-turn / same-turn / cancel-without-identity cannot POST. Whitelisted in `pytest.ini`. |
| `tests/test_injection_live.py` | **Adapted** — attaches `FIXED_TOOLS` + `CLIENT_TOOLS`; executes any write tool-calls against mocked HTTP; fails if unconfirmed write POST escapes. **Not** in pytest whitelist (money). |
| `pytest.ini` | `live` marker + `addopts = -m "not live"` (F-H1 coordination; Ehsan can collect `*_live.py` later under this marker). |

### Unit harness result (2026-09-18)

```text
pytest tests/test_injection_write_gate.py tests/test_write_tool_gate.py
→ 23 passed
```

### Live Gemini run

Run manually (needs `GOOGLE_API_KEY` in `.env.local`):

```bash
python tests/test_injection_live.py
```

Uses `GEMINI_LLM_MODEL` or default `gemini-3.6-flash` (same as worker).

Paste exit code + VERDICT section below when run:

```text
Attempted earlier 2026-09-18: free-tier Gemini 503/429 (quota 5 RPM) — not a gate failure.
Later same day: live run completed — all attacks rejected; no unconfirmed write POST.
(Re-run prefers Groq when GROQ_API_KEY is set: `python tests/test_injection_live.py`
 or force Gemini with `INJECTION_LIVE_LLM=gemini`.)
```

## F.2 Catalog status (honest — not full Critical ✅)

Updated in `docs/UVA-PRIORITY-LIST.md`:

| ID | Habiba worker | Full Critical ✅? | Why not |
|---|---|---|---|
| F-C4 | Phases B–D done | **No** | A.3 sign-off/migration, purge cron, Render env confirm, portal re-sign UI |
| F-C7 | Phase E done + F.1 harness | **No** | A.4 mint `verified_caller_phone`, client host idempotency accept, live/staging manual proof |

### Ehsan / client follow-ups

1. A.3 schema migration sign-off + apply (`sessions` / `escalations` retention + consent cols; `agents.recording_enabled`).
2. A.4 mint/dispatch `verified_caller_phone`.
3. Schedule `scripts/purge_expired_session_media.py` (or accept interim manual runbook).
4. Portal re-sign + agent recording toggle UI (can lag).
5. Client: accept/dedupe `idempotency_key` / `Idempotency-Key` on `/api/tools/*` writes.

## F.3 Regression (code)

```text
pytest tests/test_write_tool_gate.py tests/test_recording_policy.py \
  tests/test_recording_disclosure.py tests/test_session_retention_purge.py \
  tests/test_session_opening.py tests/test_injection_write_gate.py
→ 58 passed (2026-09-18)
```

Covers: recording opt-in policy, disclosure non-interruptible plan, retention/purge unit paths, session opening, write gate + injection harness.

### Manual staging (human)

- [ ] One EN browser call (recording off path still snappy; disclosure if recording on).
- [ ] One tools booking: propose → caller says yes → confirm → one calendar row.
- [ ] Paste live injection VERDICT above.

## Exit F (plan DoD)

Phase F **Habiba proof artifacts** are in place. Wave 2 Criticals are **not** fully closed per plan Exit F until shared DoD items above are green — that is intentional, not a Habiba skip.
