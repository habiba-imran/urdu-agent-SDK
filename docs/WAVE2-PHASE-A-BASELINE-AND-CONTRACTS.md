# Wave 2 Phase A — Baseline snapshot + Ehsan contracts

**Phase:** A only (no runtime behaviour change)  
**Owner (this doc):** Habiba  
**Shared:** Ehsan signs A.3 migration + A.4 mint field; Habiba/ops confirm Render env (A.1 manual)  
**Parent plan:** `docs/WAVE2-P0-FC4-FC7-IMPLEMENTATION-PLAN.md`  
**Code freeze for this phase:** do not change worker/control_plane behaviour; this file freezes facts and contracts.

**Status**

| Item | Status |
|---|---|
| A.1 Code snapshot (recording path) | Done in this doc |
| A.1 Manual — Render/staging `UVA_SESSION_RECORD_AUDIO` | **Blocked — needs human** (see §5) |
| A.2 Code snapshot (tools path) | Done in this doc |
| A.2 Manual live double-book check | Optional; not required to exit A |
| A.3 Schema contract draft | Done — **needs Ehsan sign-off** (§5) |
| A.4 Mint metadata contract draft | Done — **needs Ehsan sign-off** (§5) |

---

## A.1 — Recording path (code reality)

### Call graph

```text
worker/main.py entrypoint
  → session_obj.start(..., record= audio dict | False)     # ~1193–1209
  → (LiveKit RecorderIO writes session_directory/audio.ogg when record audio on)
  → session close → ctx.shutdown (any close reason, including errors)
  → shutdown callbacks (registration order):
       _release_quota_slot        # writes sessions.transcript (+ end fields, quota)
       _record_agent_minutes      # usage_guard minutes (not recording)
       _persist_session_recording
            → worker.session_recording.finalize_and_persist_session_recording
                 → close recorder_io if recording
                 → find audio.ogg
                 → upload_session_audio → Supabase Storage
                 → persist_recording_urls → sessions + telephony_calls
```

### Record gate (start)

| Fact | Location |
|---|---|
| Env key | `UVA_SESSION_RECORD_AUDIO` |
| Code default if unset | `"0"` (off) |
| Truthy values | `1`, `true`, `yes`, `on` (case-insensitive) |
| When on | `record={"audio": True, "traces": False, "logs": False, "transcript": False}` |
| When off | `record=False` |
| Per-agent flag | **None** — `AgentConfig` has no `recording_enabled` |
| Consent / disclosure | **None** before start or upload |

Sources: `worker/main.py` (env + `session.start`); `.env.example` line documenting `UVA_SESSION_RECORD_AUDIO=0`; local `.env.local` currently has `0` (not a secret).

### LiveKit `enable_recording`

| Fact | Evidence |
|---|---|
| Arrives on LiveKit job | Staging log `docs/logs.txt` lines 29–30: job request/assignment JSON includes `"enable_recording": false` |
| Python API | `JobContext.job` → `livekit.protocol.agent.Job`; field `enable_recording` exists on the protobuf |
| UVA worker/control_plane | **No code reads this field** (grep clean). Phase B must honour `ctx.job.enable_recording` (never start/persist when false). |

Also present on Job protobuf: `enable_redaction` — **out of Phase A/B scope** unless product asks; do not invent behaviour.

### Upload + DB persist

| Item | Value |
|---|---|
| Module | `worker/session_recording.py` |
| Bucket | `session-recordings` (private) |
| Object path | `{tenant_id}/{room_name}.ogg` (`/` in room → `_`) |
| Signed URL TTL | 7 days (`SIGNED_URL_TTL_SECONDS`) |
| DB writes | `sessions.recording_url`, `sessions.recording_storage_path`; same two on `telephony_calls` (+ `updated_at`) keyed by `room_name` |
| Bucket ensure | `_ensure_bucket` every upload (F-L15) |
| Failed prior-object remove | bare `except: pass` (F-M1 on this path) |

### Transcript (independent of recording flag)

| Item | Value |
|---|---|
| When | Shutdown `_release_quota_slot` in `worker/main.py` |
| What | JSONB list of `{role, text, at}` for user/assistant turns |
| SQL | `update sessions set … transcript = %s where room_name = %s and ended_at is null` |
| Gate | Attempted on session shutdown (not only “happy” hangs); not tied to `UVA_SESSION_RECORD_AUDIO` |

### Migrations already applied (recording / transcript / retention)

| Migration | Adds |
|---|---|
| `0011_session_transcript.sql` | `sessions.transcript jsonb` |
| `0027_session_call_recordings.sql` | `recording_url`, `recording_storage_path` on `sessions` and `telephony_calls` |
| `0014_telephony_data_governance_audit.sql` | Retention/deletion columns on **`telephony_calls`** (and telephony infra). **Not** on `sessions` or `escalations`. |

`0027` comment already says prefer re-signing from `recording_storage_path`; worker still writes a 7-day signed URL today.

### A.1 still open (human)

Confirm on **Render staging and production worker** services whether `UVA_SESSION_RECORD_AUDIO` is set, and to what. Local repo cannot see Render. See §5.

---

## A.2 — Client write-tools path (code reality)

### Worker dispatch

```text
LLM calls function_tool
  → book_appointment | reschedule_appointment | cancel_appointment
  → _post_client_tool(path, payload)
       base = agents.tools_base_url (or UVA_TOOLS_BASE_URL)
       headers = { x-tool-gateway-secret } if secret set
       body = { tenant_id, agent_id, **payload }
       POST {base}{path}
```

Sources: `worker/tools.py`.

### Write payloads (worker → host)

| Tool function | HTTP path | Body fields from tool args | Always merged |
|---|---|---|---|
| `book_appointment` | `/api/tools/book_slot` | `customer_name`, `customer_phone`, `slot_start_time`; optional `service_name` | `tenant_id`, `agent_id` |
| `reschedule_appointment` | `/api/tools/reschedule_appointment` | `customer_phone`, `new_slot_start_time`; optional `existing_date`, `service_name` | `tenant_id`, `agent_id` |
| `cancel_appointment` | `/api/tools/cancel_appointment` | `customer_phone`; optional `existing_date`, `reason` | `tenant_id`, `agent_id` |

Not sent today: confirmation id, idempotency key, verified caller phone.

### `AgentUserdata` today

**Update 2026-09-18 (Phase E landed):** `verified_caller_phone`, write-gate state (pending write / budget / idempotency), and related fields **are** on the worker path now (`worker/tools.py` `AgentUserdata`, `worker/write_tool_gate.py`). The bullets below are the **Phase A snapshot** at draft time — do not treat them as current code.

`tenant_id`, `agent_id`, `room_name`, `ended_by_agent`, `latency_tracker`, `tools_base_url`, `tools_auth_secret`, `opening_active`.

*(Phase A snapshot)* No `verified_caller_phone`, pending write, or write-call budget.

### Host implementations in this workspace

| Location | Tool gateway? | Idempotency on write tools? |
|---|---|---|
| `client-integration-test/backend` | **No** `/api/tools/*` routes | N/A for tools. Telephony `purchase` / `outbound` accept `idempotencyKey` (unrelated). |
| `client-deliverables-final/host-backend-starter` | Voice session only | No tools |
| `self-serve-demo-UI/backend/src/routes/tools.ts` | **Yes** — mounted at `/api/tools` | **No** idempotency field on book/reschedule/cancel. Auth via `x-tool-gateway-secret`. Resolves business via `agent_id` → `uva_agent_id`. Accepts snake_case and camelCase body fields. |

Phase E must add worker idempotency keys **and** teach at least one host (self-serve and/or integration-test) to honour them. Do not pretend integration-test already has tool routes.

### Identity / mint metadata available to worker today

| Source | Keys used | Notes |
|---|---|---|
| CP dispatch metadata | `tenant_id`, `agent_id`, optional `greeting` | `control_plane/app.py` `_dispatch_agent` |
| JWT token metadata | `tenant_id`, `agent_id` | mint + refresh |
| `parse_dispatch_metadata` | same + optional `direction`, `greeting` | **Update 2026-09-18:** also passes `verified_caller_phone` when present (`worker/latency.py`). Phase A draft said it did not. |
| Telephony job meta | `e164_number` / `from_number` = **platform trunk / from DID**, not remote ANI. Outbound dispatch also carries `to_number` (remote party) in telephony service | Never use trunk/`from_number` as verified caller (plan D10). **Phase E wired:** SIP `sip.phoneNumber` + `telephony_calls` remote party via `worker/caller_identity.py` |
| SIP extract | trunk phone, trunk id, call ids | **Update 2026-09-18:** ANI also resolved via `caller_identity.resolve_verified_caller_phone` (not only trunk extract) |

`verified_caller_phone`: **worker reads it** (mint / SIP ANI / telephony remote). **Still open for Ehsan:** host mint must **send** the field (A.4). Host tool routes may still lack idempotency accept/dedupe.

---

## A.3 — Schema contract (hand to Ehsan)

**Habiba proposes; Ehsan owns the migration file under `supabase/migrations/`.**  
Do not apply until Ehsan signs this section.

Suggested next migration name (Ehsan chooses final filename). Avoid another dual-`0014_` collision — the repo already has both:
- `0014_telephony_data_governance_audit.sql`
- `0014_telephony_idempotency_webhook_tenant_scope.sql`  

Prefer: `0028_session_recording_consent_retention.sql` (or a timestamped name).

### Add to `agents`

```sql
alter table agents
  add column if not exists recording_enabled boolean not null default false,
  add column if not exists recording_consent_mode text not null default 'disclosure';

-- constrain modes (Ehsan: use CHECK or enum-equivalent)
-- allowed: 'off' | 'disclosure' | 'verbal'
```

### Add to `sessions`

```sql
alter table sessions
  add column if not exists recording_consent_status text,
  add column if not exists recording_consent_at timestamptz,
  add column if not exists retention_until timestamptz,
  add column if not exists deletion_requested_at timestamptz,
  add column if not exists deleted_at timestamptz,
  add column if not exists redacted_at timestamptz;

-- recording_consent_status intended values:
--   'not_applicable' | 'pending' | 'granted' | 'declined'
```

### Do **not** re-add on `telephony_calls`

Already from `0014_telephony_data_governance_audit.sql`:  
`retention_until`, `deletion_requested_at`, `deleted_at`, `offboarded_at`, `redacted_at`, `redaction_reason`, plus export/access audit columns.

Purge (Phase D) must **use** these and clear `recording_url` / `recording_storage_path` when purging.

### Add to `escalations`

```sql
alter table escalations
  add column if not exists retention_until timestamptz,
  add column if not exists deletion_requested_at timestamptz,
  add column if not exists deleted_at timestamptz,
  add column if not exists redacted_at timestamptz;
```

(`escalations` today: `id`, `tenant_id`, `session_id`, `reason`, `contact_info`, `requested_at`, `status` — from `0008_tools.sql`.)

### Optional v1 (defer unless Ehsan wants it now)

```text
session_recording_events (session_id, event, at, detail jsonb)
```

Not required to start Phase B if worker can write consent fields on `sessions` alone.

### Sign-off box (Ehsan)

- [ ] Column list accepted  
- [ ] Migration filename reserved  
- [ ] Will not duplicate `telephony_calls` retention columns  
- [ ] Portal/UI toggle for `recording_enabled` can lag (default false is enough for worker)

**Signed:** _____________ **Date:** _____________

---

## A.4 — Mint / dispatch metadata contract (hand to Ehsan)

### Today

Dispatch metadata JSON:

```json
{ "tenant_id": "<uuid>", "agent_id": "<uuid>", "greeting": "<optional>" }
```

Token metadata: `{ "tenant_id", "agent_id" }` only.

### Proposed addition (browser / host-verified identity)

```json
{
  "tenant_id": "<uuid>",
  "agent_id": "<uuid>",
  "greeting": "<optional>",
  "verified_caller_phone": "+923001234567"
}
```

| Rule | Detail |
|---|---|
| Optional on mint | Yes — omit when host has no verified phone |
| Required for browser cancel/reschedule after F-C7 | Yes — worker fail-closes without it |
| Format | E.164 preferred (`+` + country + national). Worker will normalize; hosts should still send E.164 when possible |
| Where to put it | (1) LiveKit **agent dispatch** metadata (worker early path) **and** (2) participant JWT metadata if the worker also reads participant meta — Ehsan must forward the same key on both paths the worker already uses |
| Worker follow-up | **Done (Phase E, 2026-09-18).** Remaining: Ehsan forwards mint field (sign-off below). |

### Sign-off box (Ehsan)

- [ ] Host mint/session API may accept optional `verified_caller_phone`  
- [ ] CP forwards it into dispatch metadata (and token/participant meta as agreed)  
- [ ] Unknown/extra metadata keys are not stripped in a way that drops this field  

**Signed:** _____________ **Date:** _____________

---

## §5 — Human actions required (stop here)

Phase A **code/docs draft** is done. Phase A **exit** (“contracts agreed”) is **not** complete until the items below are answered. **Do not start Phase B coding until A.3 is signed** (Phase B can feature-flag default `recording_enabled=false` without the column, but consent/retention columns need A.3 before Phase C/D).

### 1) You — Render env (A.1 manual)

**Answered 2026-09-18 (Habiba):** Nothing is deployed on Render right now. Staging/prod worker env check is **deferred until first deploy** — **Habiba owns Render**, not Ehsan.

**Remember later:** full checklist in `docs/WAVE2-HABIBA-HOST-FOLLOWUPS.md` §3. When you ask for a Render deployment guide, that section must be included.

At deploy time:

1. Set `UVA_SESSION_RECORD_AUDIO=0` (or omit) on staging/prod.  
2. Paste actual values into this §5.  
3. Do not expect this env to force recording on Render — agent opt-in required.

### 2) You + Ehsan — sign A.3 and A.4

Send Ehsan this file (or the A.3 / A.4 sections). Get the checkboxes signed (or a written “approved as written” in chat/PR). Paste confirmation here; I will mark status Done.

Optional A.2 live booking double-call test: only if you already have tools gateway + calendar wired; not a Phase A blocker.

---

## Phase A exit checklist

- [x] A.1 code snapshot written  
- [x] A.1 Render values — **N/A for now** (no Render deploy; confirm at first deploy)  
- [x] A.2 code snapshot written (incl. real host = self-serve tools router; integration-test has no tool routes)  
- [x] A.3 contract drafted  
- [ ] A.3 Ehsan sign-off  
- [x] A.4 contract drafted  
- [ ] A.4 Ehsan sign-off  

When all boxes are checked → Phase A complete → start Phase B only.
