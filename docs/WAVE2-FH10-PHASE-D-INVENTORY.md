# F-H10 Phase D — Urdu redundancy inventory + retries

**Date:** 2026-09-18  
**Owner:** Habiba  
**Plan:** `docs/WAVE2-HIGH-FH10-FH18-IMPLEMENTATION-PLAN.md` Phase D  
**Source of truth for selectability:** `worker/providers/capabilities.py`

## D.1 Inventory (evidence only — no fake providers)

### What `ur` can select today

| Layer | Primary | Adapters in repo | Listed under `ur` in capabilities? |
|---|---|---|---|
| STT | `gladia` | `worker/providers/stt/gladia.py` (+ `deepgram.py`, `soniox.py` exist) | **Only gladia** |
| LLM | `gemini` | `worker/providers/llm/gemini.py` (+ `groq.py` exists) | **Only gemini** — Groq structurally absent for `ur` |
| TTS | `uplift` | `worker/providers/tts/uplift.py` (+ cartesia/elevenlabs/fish/rime for `en`) | **Only uplift** |

### Candidate #2 status (Habiba recommendation until product signs)

| Layer | Candidate in **this** repo? | Urdu-safe? | Habiba stance for Phase E |
|---|---|---|---|
| STT | Deepgram / Soniox adapters exist | **UNVERIFIED** for Urdu quality (no listening sign-off in this Wave 2 track) | **Do not enable** for `ur` until product listens and says yes |
| LLM | Groq adapter exists | Forbidden for `ur` today (capabilities comment + matrix) | **Do not enable** without explicit product yes |
| TTS | EN TTS adapters exist | EN-oriented in capabilities; no Urdu voice mapping proven here | **Do not enable** without product + voice mapping |

**Explicit residual:** Until product signs a concrete #2, F-H10 Phase E must **not** invent a fallback chain. Retries (D.2) are the Habiba-owned mitigation for transient 429/503.

### Product sign-off box (required before Phase E)

**Decision (Habiba chat, 2026-09-18):** Product chose **A — No #2 yet.**

- [x] **No #2 yet** — keep `ur` single-provider; Phase E **skipped** (residual only)  
- [ ] Approve STT #2: _____________ (must already have an adapter in this repo)  
- [ ] Approve LLM #2: _____________ (Groq for `ur` needs an explicit yes — today forbidden)  
- [ ] Approve TTS #2: _____________ + voice IDs / mapping notes _____________  

**Signed:** Habiba (product reply “A”) **Date:** 2026-09-18

**Consequence:** No cross-provider fallback resolver, no capabilities change for `ur`, no Ehsan schema for fallback columns. Habiba mitigation remains Phase D bounded retries (`UVA_PROVIDER_MAX_RETRY`). Re-open Phase E only with a new named #2 approval.

---

## D.2 Bounded retries (implemented)

**Where retries were forced off:** `worker/main.py` → `build_session_connect_options()` used `APIConnectOptions(max_retry=0)` for LLM, TTS, and STT (Wave 1 “no dead air”). That is the real gate for Uplift + Gemini on live calls — not the fixture-mode Uplift `max_retry=0` (fixtures stay fail-fast).

**Now:** `worker/provider_retries.py` reads env and builds session connect options:

| Env | Default | Cap |
|---|---|---|
| `UVA_PROVIDER_MAX_RETRY` | `2` | 0–5 |
| `UVA_PROVIDER_RETRY_INTERVAL` | `2.0` (seconds) | 0.1–30 |
| `UVA_PROVIDER_CONNECT_TIMEOUT` | `30.0` (seconds) | 1–120 |

Set `UVA_PROVIDER_MAX_RETRY=0` to restore Wave 1 fail-fast.

**Fixture Uplift:** still uses `max_retry=0` inside fixture mode only (no network).

**Gemini constructor:** no `max_retries` kwarg; session `llm_conn_options` is the retry path.

**Groq (EN):** still passes `max_retries=0` to the OpenAI-compatible client (separate from LiveKit session retries). Unchanged this phase.

## D.3 Observability

On session connect-option build, worker logs:

```text
provider_retries max_retry=… retry_interval=… timeout=… (env …)
```

LiveKit performs the actual connect retries; we do not swallow failures at this layer.

## Tests

- `tests/test_provider_retries.py` — env parsing + connect options applied  
- Existing `tests/test_humanization_gap_fixes_e2e.py` updated for Phase D defaults

## Ehsan

No migration this phase. If Phase E later needs agent/platform fallback columns, Habiba will draft a contract into `docs/WAVE2-EHSAN-HANDOFF.md` — do not invent columns now.
