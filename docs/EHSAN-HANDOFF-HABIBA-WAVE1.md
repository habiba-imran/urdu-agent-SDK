# Ehsan handoff — Habiba Wave 1 (final)

**From:** Habiba  
**Source of truth:** `docs/AwaazLabs UVA Audit.md` · `docs/UVA-PRIORITY-LIST.md`  
**Branch with Habiba Wave 1 code:** `habiba` @ `47c72d0` (pushed to `origin/habiba`)  
**Not merged to `main` / `staging` yet** — treat this as “ready on Habiba’s branch,” not “shipped to production.”

Freeze rules (do not violate):

| Habiba owns (Wave 1) | Ehsan owns (do not ask Habiba) |
|---|---|
| `sdk/src/**` | `sdk/package.json`, `sdk/README.md`, `sdk-server/` |
| `worker/tools.py`, `worker/prompt_compact.py` | `pytest.ini` (whitelist **one filename at a time**) |
| Temporary smoke host `demo-app/` (local only) | `control_plane/`, `.github/`, root `README.md`, `examples/` |
| — | Portal / migrations / telephony (Wave 2 for F-M2 write-time cap) |

Habiba will **not** edit `pytest.ini`, `sdk/package.json`, or `sdk/README.md` in Wave 1.

---

## Habiba Wave 1 status (honest)

### Closed on `habiba` (code present; see caveats below)

| ID | What Habiba shipped | Evidence on branch |
|---|---|---|
| **F-H12** | Refresh retries with exponential backoff until token expiry; terminal `token_refresh_failed` | `sdk/src/index.ts` `refreshToken()` |
| **F-M14** | `AbortController` timeout on session / refresh / voices fetch; code `timeout`; `fetchTimeoutMs` option | `sdk/src/internal/http.ts`, wired in `index.ts` |
| **F-M16** | Extra codes: `rate_limit`, `worker_not_ready`, `provider_limit`, `timeout`, `token_refresh_failed`; 429 body heuristics | `sdk/src/internal/errors.ts` |
| **F-L7** | Skip `document.body.appendChild` when `document` / `body` missing | `attachRemoteAudio` in `sdk/src/index.ts` |
| **F-L8** | `emit()` wraps each listener in `try/catch` | `sdk/src/index.ts` |
| **F-H9** | `end_conversation_summary` / `escalate_to_human` DB I/O via `asyncio.to_thread` | `worker/tools.py` |
| **F-M2 (worker only)** | Groq persona compact at session build (`compact_prompt_for_groq`); soft chars default **3000** | `worker/prompt_compact.py` + `build_agent` in `worker/main.py`. Habiba’s latest commit mainly **proved assembly wiring with tests**; compact itself predates that commit on this branch line. |

Local automated checks Habiba ran (not CI):

```bash
# Python (must pass explicit paths — see whitelist gap below)
python -m pytest tests/test_tools_lifecycle_db.py tests/test_prompt_compact.py \
  tests/test_worker.py::test_build_agent_compacts_prompt_when_llm_provider_is_groq \
  tests/test_worker.py::test_build_agent_skips_compact_when_llm_provider_is_not_groq -q

# SDK (vitest present as files; package.json has NO "test" script yet)
cd sdk && npx vitest run
```

### Still open on Habiba (Wave 1 delivery items — not `F-*`)

These are **explicitly still Habiba’s job**. Do not take them unless ownership changes.

| Item | Why still open |
|---|---|
| **Humanization + LLM TTFT** | Priority-list ticket: Cartesia emotion/token tax, Gemini vs Groq first-token, **no chat-history sliding window**, Groq **429 → multi-second dead air**. Partial Cartesia/Rime spoken-output code exists from earlier work; the Wave 1 ticket as defined is **not closed**. |
| **Worker cold start / time-to-first-greeting** | **Shipped on Habiba branch** — in-process greeting PCM cache (`worker/greeting_cache.py`), skip 5s prewarm on cache hit, interruptible WebRTC greeting (`UVA_GREETING_INTERRUPTIBLE=0` escape), config TTL 8s→30s. Remaining first-audio floor is mostly **CP dispatch** (Ehsan below), not worker greeting path. |

### Not Habiba Wave 1 (do not treat as Habiba leftovers)

- All Criticals except ownership notes: F-C1–C3, C5–C6 → Ehsan; F-C4 / F-C7 → Habiba **Wave 2**
- F-H1 full whitelist removal → Ehsan Wave 2 (Wave 1 = **add filenames only**)
- F-M2 **portal write-time 422 + schema** → Ehsan Wave 2 (`tenant_portal_api/` frozen in Wave 1)
- Control-plane dispatch handshake, Groq/Cartesia account liveness → Ehsan Wave 1 roster
  - **Explicit Habiba follow-up for Ehsan (not in Habiba worker PR):** replace `_run_dispatch_background` (`control_plane/app.py` ~419–445) `asyncio.run` + per-call `LiveKitAPI` with an **app-lifespan singleton client** + async background task. Optionally await / start dispatch before mint response flush once the singleton exists. This is the highest remaining infra lever for mint→job assignment latency after the worker greeting-cache path.
- F-H10, F-M15 honesty API, F-M24, F-M25, F-L6, F-L10, F-L15, etc. → Wave 2+

---

## What Ehsan must do so Habiba’s Wave 1 is real in CI / npm

### 1. Pytest whitelist (F-H1 Wave 1 exception)

`pytest.ini` `python_files` currently **excludes** Habiba’s new/needed files. Add **only** these names (do not restore full discovery):

| Filename | Why |
|---|---|
| `test_tools_lifecycle_db.py` | F-H9 — Habiba added; **not** collected by CI today |
| `test_prompt_compact.py` | F-M2 compact unit tests — on disk since earlier; **still excluded** |

Already whitelisted (no action): `test_worker.py` — includes Habiba’s F-M2 **assembly wiring** tests:

- `test_build_agent_compacts_prompt_when_llm_provider_is_groq`
- `test_build_agent_skips_compact_when_llm_provider_is_not_groq`

Until you whitelist the two files above, `make gate` / CI **do not** prove F-H9 or prompt-compact behaviour.

### 2. Browser SDK package wiring (`sdk/package.json` — you own)

Habiba shipped:

- `sdk/src/index.ts` + `sdk/src/internal/{http,errors}.ts`
- `sdk/src/*.test.ts`, `sdk/vitest.config.ts`

You still need for a trustworthy release path:

| Action | Notes |
|---|---|
| Add `vitest` (devDependency) + `"test": "vitest run"` | Habiba verified with `npx vitest run` (20 tests). `npm test` does **not** exist today. |
| Keep Habiba’s `sdk/src` changes when you touch package.json | File freeze: Habiba = `sdk/src/`; you = package metadata / scripts |

### 3. Document new error codes (`sdk/README.md` — you own)

**Gap (honest):** published README still documents **only three** codes and says all `429` → `quota_exceeded`. Code on `habiba` already exports more.

Update README to match code:

| Code | Meaning |
|---|---|
| `quota_exceeded` | Plan concurrent / monthly cap (also **opaque** 429 with no distinguishable body — backward compatible) |
| `agent_not_found` | HTTP 404 |
| `session_failed` | Generic connect / session failure |
| `rate_limit` | Platform rate limit signal in body |
| `worker_not_ready` | Worker not ready signal in body |
| `provider_limit` | Upstream provider limit signal in body |
| `timeout` | Client AbortController timeout (F-M14) |
| `token_refresh_failed` | Refresh exhausted / auth rejected (F-H12) |

Also document optional constructor field `fetchTimeoutMs` (default 15000).

Dead example links in this README remain **your** F-H2 Wave 1 work — do not mix into Habiba’s behaviour PR narrative if you split PRs; just don’t regress `sdk/src`.

### 4. F-M16 needs control-plane / host body signals (your surface)

SDK mapping alone is not enough if every 429 body is empty/opaque — those still become `quota_exceeded` by design.

If hosts should distinguish rate limit vs quota vs provider limit, **session mint / error responses** must include distinguishable text or codes that match Habiba’s heuristics (see `mapSessionHttpError` in `sdk/src/internal/errors.ts`). That is control-plane / host-contract work on **your** side of the freeze, not another Habiba `sdk/src` pass.

### 5. F-M2 portal half (Wave 2 — not now)

Audit permanent fix for F-M2:

- Server-side character cap at write time → clear **422** (`tenant_portal_api/app.py` prompt field)
- Schema / product UX as you decide in Wave 2

Do **not** expect Habiba to touch portal in Wave 1.

### 6. Release / metadata (your Wave 1 roster)

F-M21, F-L14, F-M23, §2 #26 (`sdk-server` test script) — stay on your list. Do not conflict with Habiba `sdk/src`.

### 7. Demo app

`demo-app/` is Habiba’s local browser smoke host for SDK findings. It is **not** the published examples path and not your npm release surface unless you later choose to document it.

---

## Caveats Habiba is not claiming

1. **Not on `main`.** Closing a finding “on `habiba`” ≠ closed in production.  
2. **F-H9 live audio stall** is fixed in structure (`to_thread`); Habiba did **not** attach a signed live escalate/hang-up audio proof to this handoff. Unit tests mock DB.  
3. **Humanization + LLM TTFT** remain Habiba Wave 1 open work. **Worker cold start** greeting-cache path is implemented on Habiba’s branch; **CP `_run_dispatch_background` singleton** remains **your** Wave 1 delivery item (see above).  
4. **README / `npm test` / pytest whitelist** are blockers for *integrator-visible* and *CI-visible* completeness — they are **your** Wave 1 follow-through, not Habiba code gaps inside `sdk/src` / `worker/tools.py`.

---

## ACK checklist (reply to Habiba)

- [ ] `test_tools_lifecycle_db.py` added to `pytest.ini` `python_files`
- [ ] `test_prompt_compact.py` added to `pytest.ini` `python_files`
- [x] `test_greeting_cache.py` + `test_session_opening.py` added to `pytest.ini` `python_files` (worker cold-start unit tests)
- [ ] `sdk/package.json`: vitest + `"test": "vitest run"`
- [ ] `sdk/README.md`: full error-code table + `fetchTimeoutMs` (and F-H2 dead links as your PR)
- [ ] (Optional / Wave 1+) CP/host 429 bodies distinguishable for F-M16
- [ ] F-M2 portal 422 scheduled for Wave 2 (not Habiba)
- [ ] Confirmed: Habiba still owns humanization; worker cold-start greeting path done; **you** still own CP dispatch singleton
- [ ] Replace `_run_dispatch_background` `asyncio.run` + per-call `LiveKitAPI` with app-lifespan singleton (Wave 1)