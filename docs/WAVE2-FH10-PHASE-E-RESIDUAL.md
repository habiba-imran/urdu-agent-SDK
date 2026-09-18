# F-H10 Phase E — residual close (no #2)

**Date:** 2026-09-18  
**Product decision:** **A — No #2 yet** (Habiba chat)  
**Plan:** `docs/WAVE2-HIGH-FH10-FH18-IMPLEMENTATION-PLAN.md` Phase E  
**Inventory:** `docs/WAVE2-FH10-PHASE-D-INVENTORY.md`

## What was not built (intentionally)

| Item | Status |
|---|---|
| Platform fallback chain config for `ur` | **Not built** |
| Session-build resolver (primary → secondary) | **Not built** |
| Mid-call hot-swap | **Not built** (was stretch anyway) |
| `capabilities.py` expansion for `ur` | **Unchanged** — still gladia / gemini / uplift only |
| Ehsan DB columns for fallback JSON | **Not requested** — do not invent |

## What remains as mitigation

- Phase D bounded LiveKit retries: `UVA_PROVIDER_MAX_RETRY` (default 2) via `worker/provider_retries.py`
- Registry still raises on unknown providers (ADR-036 — no silent swap)

## Residual risk (honest)

If Gladia, Gemini, or Uplift is down after retries exhaust, that Urdu layer fails. There is **no** second provider.

## Re-open Phase E when

Product names a concrete #2 that already has an adapter in this repo (and Urdu-safe sign-off for STT/TTS; explicit yes for Groq-on-`ur`). Then Habiba implements E.1–E.2 and drafts any Ehsan schema contract first.
