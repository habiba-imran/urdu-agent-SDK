# Wave 2 High — Phase A baseline + contracts (F-H18 / F-H10)

**Date:** 2026-09-18  
**Owner (this artifact):** Habiba  
**Plan:** `docs/WAVE2-HIGH-FH10-FH18-IMPLEMENTATION-PLAN.md`  
**Ehsan handoff (all shared Wave 2 items):** `docs/WAVE2-EHSAN-HANDOFF.md`

**Phase A goal:** Freeze “what is true today” and the cron/contracts Ehsan needs. **No runtime behaviour change.**

| Item | Status |
|---|---|
| A.1 F-H18 close-path snapshot | **Done** (this doc §A.1) |
| A.2 F-H10 provider matrix | **Done** (this doc §A.2) |
| A.3 Ehsan cron contract | **Drafted** — needs Ehsan schedule + sign-off (`WAVE2-EHSAN-HANDOFF.md` §1) |
| Cron already exists in repo? | **No** — searched `.github/workflows`; only unrelated `refresh-voice-previews.yml` cron |
| Habiba Render recording env (FC4 A.1) | **Deferred** — nothing deployed on Render today; confirm at first deploy |

---

## A.1 — F-H18 session close / quota / usage (code snapshot)

### Call graph (clean end only)

```text
AgentSession "close" event
  → _on_session_close (worker/main.py)
  → ctx.shutdown(reason=…)
  → LiveKit runs shutdown callbacks registered in _setup_and_start:
       1. _release_quota_slot → worker.session_close.release_session_quota_slot
          (session row + quota + best-effort transcript/retention/usage)
       2. _record_agent_minutes   ← local usage_guard counter
       3. _persist_session_recording ← FC4 recording finalize
```

**Update 2026-09-18 (High Phase B):** Close/quota/usage logic extracted to `worker/session_close.py`. Order is now: close open session → decrement quota → best-effort transcript / retention / usage. DB/quota failures log **ERROR** (not only warning). Snapshot steps below still describe the *intent*; prefer reading `session_close.py` for exact SQL.

### `_release_quota_slot` / `release_session_quota_slot` — ordered stages

1. Build transcript from `session_obj.history` (failure → empty list + **warning**).  
2. Open sync `psycopg` connection (`connect_timeout=5`, `autocommit=True`).  
3. `UPDATE sessions SET ended_at, duration_sec, end_reason WHERE room_name=? AND ended_at IS NULL RETURNING id`  
4. If row updated **and** `tenant_id`: `UPDATE quota_state SET concurrent_now = greatest(concurrent_now - 1, 0)` (failure → **ERROR**).  
5. Best-effort: attach `transcript`; `apply_retention_on_session_close`; `collect_model_usage` + `record_usage_many` + minutes bump (each failure → **ERROR**, does not reopen session).  
6. If updated but no `tenant_id`: **ERROR** that reconcile_sessions must correct concurrency.  
7. Connect/close failure → **ERROR** `stage=connect` / `stage=close_session`.

### What happens on hard crash / OOM / kill

- Shutdown callbacks **do not run**.  
- `sessions.ended_at` stays null; `quota_state.concurrent_now` stays high; no `usage_events` for that call.  
- `worker/stale_jobs.py` only rejects **orphan dispatches before connect** — it does **not** close mid-call dead sessions.

### Safety nets that already exist (unscheduled)

| Script | What it does | Default |
|---|---|---|
| `scripts/reconcile_sessions.py` | Close open sessions older than `--max-age-minutes` with `end_reason='reconciled_stale'`; set `concurrent_now` to true open count | 30 minutes; `--dry-run` supported |
| `scripts/reconcile_telephony.py` | CLI → `tenant_portal_api.telephony_reconcile.reconcile_telephony_state` (stale orders, stuck calls, quota leaks) | Dry-run unless `--apply` |
| `scripts/simulate_worker_crash.py` | Drill: insert stale open session + run reconcile | Manual / Phase 8 drill |

**Repo schedule search (2026-09-18):** no GitHub Action or Makefile target schedules reconcile or purge. Only cron found: `.github/workflows/refresh-voice-previews.yml`.

---

## A.2 — F-H10 Urdu provider matrix (code snapshot)

Source of truth: `worker/providers/capabilities.py` (`CAPABILITIES`).

### `ur` (exactly one per layer)

| Layer | Provider | State | Notes |
|---|---|---|---|
| STT | `gladia` | enabled | Adapter: `worker/providers/stt/gladia.py` |
| LLM | `gemini` | enabled | Models advertised include `gemini-3.6-flash`; remap in `worker/providers/llm/gemini.py` |
| TTS | `uplift` | enabled | Adapter: `worker/providers/tts/uplift.py` |

**Structural rule (capabilities.py ~88–91):** Groq is **absent** from `ur` LLM — “do not allow Groq for Urdu.”

### `en` (for contrast — already redundant)

| Layer | Providers |
|---|---|
| STT | gladia, deepgram |
| LLM | gemini, groq |
| TTS | elevenlabs, fish_audio (testing), cartesia, rime |

### Registry behaviour

`worker/providers/registry.py`: unknown provider → `UnsupportedProviderError`. Comment: **no silent provider fallback** (ADR-036).

### Retries (evidence, not assumptions)

| Adapter / gate | Retry setting in this repo |
|---|---|
| **Session connect (all langs)** | `worker/provider_retries.py` — default `UVA_PROVIDER_MAX_RETRY=2` (Phase D). Was hard-coded `0` in Wave 1. |
| Groq LLM constructor | `max_retries=0` in `worker/providers/llm/groq.py` (~79) — separate from session options |
| Uplift TTS **fixture** mode | `APIConnectOptions(max_retry=0)` (~93) — keep fail-fast offline |
| Uplift TTS **live/record** | `upliftai.TTS(...)` with **no** explicit max_retry in wrapper — **session** `tts_conn_options` applies |
| Gemini | Timeout/thinking knobs; no Habiba `max_retries` on constructor — **session** `llm_conn_options` applies |

Adapters that **exist** but are **not** listed under `ur`: Deepgram STT, Soniox STT, Cartesia/ElevenLabs/Rime/Fish TTS, Groq LLM. Enabling any as Urdu #2 requires **product + quality** sign-off in Phase D — not Phase A.

---

## A.3 — Cron / ops contract (summary)

Full checklist, commands, and sign-off boxes for Ehsan: **`docs/WAVE2-EHSAN-HANDOFF.md`**.

Minimum for F-H18 shared exit:

```bash
# every 5–15 minutes recommended
python scripts/reconcile_sessions.py --max-age-minutes 30
python scripts/reconcile_telephony.py --apply   # only after a dry-run looks sane
```

Habiba will add a Habiba-owned runbook in High Phase C; scripts already exist.

---

## §5 — Human actions required (stop here for behaviour change)

Phase A **docs** are done. Phase A **exit** (“contracts agreed”) needs:

### 1) You (Habiba) — cron ownership question

**What this means:** When a worker crashes, open sessions and stuck concurrency are only fixed if something regularly runs `scripts/reconcile_sessions.py` and `scripts/reconcile_telephony.py`. Those scripts exist in git; **nothing in this repo turns them on on a timer**.

Ask whoever will run ops (often Ehsan): will they schedule those two scripts (and the recording purge) when infra is up — or is there already a timer somewhere outside git?

**Render recording env:** Deferred — Habiba confirmed nothing is on Render today. Check `UVA_SESSION_RECORD_AUDIO` at first deploy.

### 2) Ehsan — tomorrow (use `WAVE2-EHSAN-HANDOFF.md`)

- Schedule reconcile + purge (or accept interim).  
- A.3 migration + A.4 mint field for FC4/FC7.  
- Sign the boxes in that handoff.

**Do not start High Phase B coding until A.3 cron ownership is acknowledged** (can be “Ehsan owns schedule; Habiba ships worker harden + runbook”).

---

## Verify A (this phase)

- [x] [Code] Close path line snapshot matches `worker/main.py` (~1143–1312).  
- [x] [Code] Urdu matrix matches `capabilities.py`.  
- [x] [Code] No reconcile/purge schedule in `.github/workflows`.  
- [ ] [Manual] Habiba/ops: any external cron?  
- [ ] [Ehsan] Sign `WAVE2-EHSAN-HANDOFF.md` sections.
