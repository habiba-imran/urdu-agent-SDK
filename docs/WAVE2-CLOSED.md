# Wave 2 — CLOSED

**Closed:** 2026-09-27  
**Branch tip at close:** `staging` (Habiba residual + portal recording toggle/re-sign)

Wave 2 shared exits and Habiba ops are **done**. Remaining product work is **explicitly out of Wave 2**.

---

## Deferred (not Wave 2 blockers)

| Item | Owner | Note |
|---|---|---|
| Dashboard login / signup / first-run UX | Habiba | Leave for a later pass |
| **F-M25** Render worker Web Service + `/healthz` | Habiba | Worker stays **local**; see `WAVE2-HABIBA-RENDER-DEPLOY.md` when paid |
| `PURGE_APPLY=true` | Habiba ops | Purge cron stays **dry-run** until a deliberate retention week review |
| Real Finova calendar (replace `host-tools`) | Prod | Stub proven for F-C7 |
| Legal / §6 inventory / kill-switch polish | Product | Outside code DoD |

---

## Closed in Wave 2

- Ehsan gates F-C4/C5/C6/C7, F-H1/H18, F-M1/M7/M8 (+ related) merged on `staging`
- Migrations **0028–0033** applied; encryption finalize; Telnyx `all`; hosted fail-fast env
- Reconcile + purge Actions scheduled (dry-run); `RECONCILE_APPLY` may be flipped when dry-run logs look clean
- Host-tools idempotency stub + proof
- Live injection: Gemini green; Groq secrecy harden shipped
- Portal: `agents.recording_enabled` create/PATCH + dashboard Advanced Settings toggle; session reads re-sign from `recording_storage_path`

Evidence: `WAVE2-HABIBA-HOST-FOLLOWUPS.md`, `WAVE2-PHASE-F-CLOSEOUT.md`, `WAVE2-EHSAN-HANDOFF.md`.
