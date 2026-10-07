# Handoff to Ehsan — Habiba → runtime / SDK / dashboard

**Filled by:** Habiba during Waves A–E  
**Consumed by:** Ehsan when he starts (after `HABIBA_BACKEND_FINAL`)  
**Rule:** Habiba never waits on these items. Ehsan owns verification and fixes in his trees.

---

## Status

| Field | Value |
|---|---|
| Habiba final gate signed | YES — 2026-10-07 (`HABIBA_BACKEND_FINAL`) |
| Open Critical on Habiba side | 0 |
| Open High (accepted) | M5-F02 (expiry 2026-12-31) |
| Branch / commit Habiba froze against | working tree — audit-context + portal/CP remediations |

---

## Contracts Ehsan must not break (Section 5)

| # | Contract | Habiba note (fill) | Ehsan action |
|---|---|---|---|
| 1 | HMAC mint + machine shapes / `used_nonces` | Server expects: ________ | Verify client signers match; add starter tests if missing |
| 2 | `worker.providers` public interface | Portal imports: ________ | Do not rename without telling Habiba |
| 3 | `sanitize_transcript_turns` | Used at: ________ | Do not rename/signature-change silently |
| 4 | `is_hosted` / `decrypt_tool_secret` / `is_mock_provider_mode` | Habiba may change server; note if changed: ________ | Re-verify worker SSRF + decrypt + telephony mock |
| 5 | Quota lifecycle | Mint/rollback server behavior: ________ | Prove worker release on crash/sleep |
| 6 | Tools URL/secret | Save-time rules: ________ | Match request-time SSRF |
| 7 | Recordings | Portal signed URLs: ________ | Worker write path |
| 8 | Dashboard read-only | Server: `POST /portal/agents` → **403** unless `PORTAL_ALLOW_AGENT_CREATE=1`. Edits still allowed. | Remove/hide create in dashboard UI; use machine HMAC for creates |

---

## M1 — Client signers (Ehsan)

**Habiba verified on server:**

- Mint message: HMAC over `tenant_id.ts.nonce.agent_id` (see `mint.expected_signature`); compare via `hmac.compare_digest`; replay 60s + `used_nonces` unique  
- Machine message + body hash: `tenant_id.ts.nonce.action.body_hash` with SHA-256 of canonical JSON (`machine_auth`)  
- Headers: `X-Tenant-Id`, `X-Timestamp`, `X-Nonce`, `X-Signature` (mint + machine)  

**Ehsan must verify:**

- [ ] `sdk-server` signing matches machine  
- [ ] `telephony` signing matches machine  
- [ ] host-backend-starter + CIT backend signing match mint  
- [ ] Empty-body GET hashing  

**Habiba findings that need client follow-up:** _(IDs)_ none yet (server Mediums M1-F01/F02 are Habiba)

---

## M2 — Worker release / SDK refresh (Ehsan)

**Habiba server facts:**

- No CP session-end route: confirmed Y (quota release is worker/reconcile)  
- Rollback on dispatch fail: Y — `_watch_dispatch` → `_rollback_dispatched_session`  
- Refresh cap / JWT `refresh_count`: MAX_REFRESHES=720; gates re-checked each refresh  
- `reconcile_sessions.py`: closes stale sessions; sets `concurrent_now` to true open count  

**Ehsan must verify:**

- [ ] `worker/session_close.py` always releases `concurrent_now`  
- [ ] `stale_jobs.py` / drain / crash scripts  
- [ ] SDK refresh / listener limits  

**Habiba findings needing worker/SDK follow-up:** M2-F01 (capacity planning / global pool)

---

## M4 — Telephony SDK (Ehsan)

**Habiba server facts:**

- Webhook verify / mock hosted: Ed25519; hosted refuses non-`real` at startup; verify also fail-closed when hosted+mock+no key (M4-F01 fixed)  
- Destination enforcement: `assert_outbound_destination_allowed` on `create_outbound_call`  
- Idempotency DB: `telephony_call_events` when call matched; unmatched gap M4-F02  


**Ehsan must verify:**

- [ ] 28 SDK ops cannot bypass server spend controls  
- [ ] SDK timeouts/retries  

---

## M6 — Request-time SSRF / host-tools (Ehsan)

**Habiba save-time (`tools_webhook.py`):**

- Rules: hosted → https only; no credentials/query/fragment; block private/loopback/link-local/metadata hostnames; best-effort DNS reject of internal A/AAAA  
- Gaps vs worker guard: save-time cannot defeat DNS rebinding; `worker/ssrf_guard.py` re-resolves + pins public IP at request time  

**Ehsan must verify:**

- [ ] `ssrf_guard.py` when `is_hosted` is false (local worker)  
- [ ] host-tools demo vs production use  
- [ ] write-tool confirmation / injection  

---

## M7 — Worker laptop / logs (Ehsan)

**Habiba server facts:**

- Recording URLs / retention: signed URL TTL 1h via Storage REST; purge script + GH Action (dry-run unless `PURGE_APPLY=true`) — M7-F02  
- Sentry scrub: `control_plane/sentry_scrub.before_send` on CP init (M7-F01 fixed)  

**Ehsan must verify:**

- [ ] Laptop disk / `.env.local` / service role scope  
- [ ] Transcript/prompt dump destinations  

---

## M8 — SDK / demo timeouts (Ehsan)

**Habiba server cold-start notes:**

- CP: `/healthz`, `/healthz/deep`, `/healthz/warm`; mint_db singleton reconnect on wake  
- Portal: `/healthz`; db_pool size 4 warmed in background  
- Admin: `/healthz`; per-request connect_timeout 10  

**Ehsan must verify:**

- [ ] Voice 15s vs wake time  
- [ ] Agents/telephony no timeout  
- [ ] Starter/demo AbortController  

---

## M11 — UI / visibility (Ehsan)

**Product decision (from Habiba gate log):** Interim — dashboard must not **create** agents; edits/reveal/telephony/studio undecided (still allowed server-side).

**Habiba enforcement result:**

- Portal create blocked: **Y** (403 unless `PORTAL_ALLOW_AGENT_CREATE=1`)  
- RLS browser write blocked: **Y** for agents (SELECT-only)  
- Other actions: PATCH/DELETE agents, telephony, Test Studio still allowed until product freezes  

**Ehsan must verify:**

- [ ] No create-agent UI path  
- [ ] Agent list visibility / staleness / archive  
- [ ] Dashboard hygiene (XSS, NEXT_PUBLIC)  

---

## Env / ops Ehsan should know

| Item | Habiba note |
|---|---|
| Required hosted env vars (CP/portal/admin) | `UVA_ENV=production` (Docker), `SUPABASE_DB_URL`, LiveKit keys (CP), `TELNYX_PUBLIC_KEY` + `TELEPHONY_CREDENTIAL_ENCRYPTION_KEY` (portal telephony), JWT secrets |
| `TELEPHONY_PROVIDER_MODE` must be | `real` when hosted (startup refuse otherwise) |
| Nonce purge schedule confirmed? | UNKNOWN (script min age 5m; cron not verified) |
| Migrations Habiba applied | None this wave (audit/remediation only) |
| Ops follow-ups | Set GH `PURGE_APPLY` if retention must delete; confirm `TENANT_SECRET_ENCRYPTION_KEY` on hosted |

---

## Open questions still for humans (Section 8)

| Q | Status |
|---|---|
| Q1 Render topology | |
| Q2 Peak concurrent calls | |
| Q3 Worker machine | |
| Q4 Nonce purge scheduled | |
| Q5 M11 full scope | |
| Q6 Mock mode anywhere | |
| Q7 Repo private | |
| Q8 client-deliverables shipped | |
| Q9 self-serve-demo etc. | |
