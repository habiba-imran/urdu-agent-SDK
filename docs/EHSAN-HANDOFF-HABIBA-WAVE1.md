# Ehsan handoff — Habiba Wave 1 leftovers

**From:** Habiba  
**Branch:** `habiba` (SDK work already pushed; F-H9/F-M2 worker work may still be local until end PR)  
**Do not expand:** Habiba will not edit `pytest.ini`, `sdk/package.json`, `sdk/README.md`, or portal/migrations in Wave 1.

Use this as a checklist for your Wave 1 / follow-up PRs. Items are from the priority list freeze rules + Habiba delivery.

---

## 1. Pytest whitelist (F-H1 exception — one name at a time)

`pytest.ini` `python_files` currently excludes Habiba’s new/needed worker tests.

**Add these filenames only** (do not restore full discovery):

| File | Why |
|---|---|
| `test_tools_lifecycle_db.py` | F-H9 unit tests (mocked DB / `asyncio.to_thread`) — Habiba added |
| `test_prompt_compact.py` | F-M2 worker compact unit tests — already on disk; never whitelisted |

Habiba local verify (until whitelist lands):

```bash
python -m pytest tests/test_tools_lifecycle_db.py tests/test_prompt_compact.py tests/test_worker.py::test_build_agent_compacts_prompt_when_llm_provider_is_groq tests/test_worker.py::test_build_agent_skips_compact_when_llm_provider_is_not_groq -q
```

Note: F-M2 **G2 assembly wiring** tests were added inside `tests/test_worker.py` (already whitelisted). No extra `pytest.ini` row needed for those two.
---

## 2. Browser SDK package follow-ups (from F-H12 / F-M14 / F-M16 / F-L7 / F-L8)

Habiba shipped behaviour + tests under `sdk/src/**` (and `sdk/vitest.config.ts`). Per freeze, **you** own:

| Item | Where | Notes |
|---|---|---|
| Add `vitest` + `"test": "vitest run"` | `sdk/package.json` | Habiba verified with `npx vitest run` / local install; CI/`npm test` needs your script |
| Document new error codes in README | `sdk/README.md` | Codes now include `rate_limit`, `timeout`, `token_refresh_failed`, `worker_not_ready`, `provider_limit` (plus prior three) |
| Release / metadata / publish path | F-M21, F-L14, F-M23 | Your Wave 1 roster — do not conflict with Habiba `sdk/src` |

---

## 3. F-M2 portal half (Ehsan Wave 2 — not Habiba Wave 1)

Audit §9 F-M2 permanent fix (not Habiba’s current worker PR):

- Enforce server-side character cap at write time with clear **422** — `tenant_portal_api/app.py` (~prompt field)
- Schema / product surfacing as you decide in Wave 2
- Habiba Wave 1 only ships **worker** `prompt_compact` + assembly mitigation for Groq

---

## 4. Coordination notes

- Habiba end PR strategy: **one PR** to `staging`/`main` when F-H9 + F-M2 worker phases finish (no mid-work PR).
- Habiba will **not** edit `pytest.ini` — whitelist is your change.
- Demo app (`demo-app/`) is Habiba-local smoke host; not your package publish path unless you choose to document it later.

---

## 5. Quick ACK back to Habiba

When done or scheduled, reply with:

- [ ] `test_tools_lifecycle_db.py` whitelisted  
- [ ] `test_prompt_compact.py` whitelisted  
- [ ] `sdk` vitest + `npm test` scheduled / done  
- [ ] README error codes scheduled / done  
