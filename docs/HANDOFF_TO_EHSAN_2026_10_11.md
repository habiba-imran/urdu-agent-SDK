# Habiba to Ehsan: handoff implementation response

Date: 2026-10-11. Operating decisions updated 2026-10-12. Based on `FINDINGS_EHSAN.md` and `HANDOFF_TO_HABIBA.md` received locally.
Base commit: `7a3c38229e8784b776977216af448d89227d543c` (`main`).
This handoff describes source changes prepared for GitHub delivery, not a deployed or published release.

## Git synchronization

At the start of implementation, fetched `origin` and `org`. Both remotes'
`main` and `staging` pointed to the base commit. No newer Ehsan commit was available to pull. `git pull --ff-only origin main`
reported **Already up to date**. Ehsan's remote branches (`ehsan`, `ehsan-wave2`,
`ehsan-wave2-gate1`) are older ancestors of this checkout. The received findings and
handoff files remain intact; the pre-existing humanization investigation edit is preserved.

## Implemented in this tree

| Finding | Change | Verification boundary |
|---|---|---|
| M1-F02 | Authenticate the complete received object, not Pydantic's projected/defaulted object. Explicit nulls and unknown signed fields no longer cause misleading 401 responses. | Mounted portal routes with the actual verifier and fake tenant/nonce database. |
| M1-F01 | Add explicit `raw-body-v1` signing to portal, agents SDK and telephony SDK. Hash exactly the transmitted UTF-8 bytes. Agents SDK now sends the canonical string it signed. | Actual compiled JavaScript SDK requests containing exponent-form floats, Urdu and Unicode, accepted by mounted portal routes. Legacy cross-language edge cases remain until opt-in. |
| M12-F01(a) | Legitimate portal clients in the three reported test files send `X-UVA-Portal: 1`; missing-header CSRF protection remains enforced. Auth/member DB fixtures catch missing-configuration `SystemExit` and report an availability skip. | Actual mounted login CSRF allow/reject test and direct fixture setup tests. Real DB assertions require an isolated migrated database. |
| M6-F05 | Negation/correction and ambiguity take precedence over affirmative phrases. ASCII/curly apostrophe contractions and `dont` invalidate a pending proposal instead of confirming it. | Ten actual appointment-tool refusal cases dispatch zero HTTP writes; existing confirmation/correction/outcome tests retained. |
| M10-F01 | Remove credential-absence blanket suppression of Python failures. Keep explicit paid-network/missing-provider-key skips. | Subprocess canary without credentials reports `assert 1 == 2` as failed, exit 1; a paid socket remains blocked and skipped. This small Ehsan-owned overlap was necessary to trust verification. |
| Test isolation | Webhook endpoint unit test replaces durable persistence with a test-local stub; checks persistence happens once before in-memory duplicate rejection. | Original test reached the configured database and returned an existing-event duplicate. The corrected test does not connect to that database. Durable inbox coverage remains in the separate correlation tests. |

### Machine signing contract and rollout

- No header, or `X-Signature-Version: canonical-json-v1`: hash the full received
  object with the existing Python canonicalizer. Older clients keep this default.
- `X-Signature-Version: raw-body-v1`: SHA256 of the exact body bytes. Empty requests
  retain the `{}` hash contract. Unknown versions fail with 401.
- Tenant status, fixed per-route action, constant-time signature comparison,
  timestamp window, nonce replay protection and rate limits remain in place.
- Agent create/update/list, provider capabilities, session lookup and the shared
  telephony machine-route helper use the received authentication payload.
- Business schema behavior is preserved: signing unknown/null fields does not
  make those fields supported or change how they mutate records.
- This does **not** change `/v1/session` control-plane mint authentication.

Deploy the portal first. Then build/package the updated SDK sources and configure
both backend clients with:

```ts
signatureVersion: 'raw-body-v1'
```

No npm publication or package-version bump was performed. Published `0.1.0`
packages do not gain this option automatically. Roll back the client option to
`canonical-json-v1` before rolling the portal back. Legacy float/key-order edge
cases are still open for clients that stay on legacy mode.

## Source-backed answers

**M4 number purchases:** the real-database purchase path uses
`TelephonyService._tenant_telnyx_client(conn, tenant_id)`, which loads that tenant's
active connection and decrypts its stored `encrypted_api_key_ref`. There is no
platform-key fallback in this path; the no-DB path is explicitly mock-only.
See `tenant_portal_api/telephony_service.py` (`_tenant_telnyx_client`, `purchase_number`).
This supports your reading of the code. Account ownership still depends on which
Telnyx credential an operator connects; no live bill/account was inspected and no
number was purchased. A number cap was not added.

**M3-F03 model validation:** the portal already checks models against
`allowed_llm_models`, including deliberate legacy aliases, in
`tenant_portal_api/provider_validation.py`. The old SDK default is separate from
accepting arbitrary models. No default model/provider migration was made here;
please retain ownership of your SDK-default finding and coordinate any alias policy.

**M6-F03 recording:** your proposed reuse of `runtime_env.is_hosted()` is still your
implementation item. `worker/recording_policy.py` is unchanged in this patch.
Recommended policy is documented below; final CTO/legal agreement remains pending.
Do not treat this recommendation as a deployed change or live consent evidence.

## Validation

- Final focused Python regression: **400 passed, 0 failed, 0 skipped**;
  includes **43 new handoff cases**. One existing Starlette deprecation warning.
- Agents SDK: **15 tests passed**, build and TypeScript typecheck passed.
- Telephony SDK: phase8 smoke, phase9 frozen-route contract and new wire-body
  compatibility checks passed; build and TypeScript typecheck passed.
- Scoped Ruff and `git diff --check` passed.
- Required `graphify update .` attempted; blocked by the existing
  `uv trampoline failed to canonicalize script path` environment error.

Commands (from repository root unless noted):

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ehsan_handoff.py -q
# sdk-server directory
npm test
npm run lint
# telephony directory
npm test
npm run lint
```

The focused Python suite includes the handoff tests, write/injection gates,
humanization Batch A/B/final P0, prior live regression fixes, conversational behavior,
telephony machine routes/provider wiring and session-close checks. Artifacts are
local/ignored under `tmp/ehsan-handoff/`.

No local PostgreSQL/Docker tooling was available. The new auth tests use fake
connections; no migrated local DB result is claimed. The pre-existing webhook
unit test accidentally reached the configured database on the initial focused
run and observed a pre-existing duplicate; it is now isolated. No paid provider,
carrier purchase, real call, browser audio, deployment or npm release was run.

## Files changed by this task

- Signing: `tenant_portal_api/machine_auth.py`, `tenant_portal_api/app.py`,
  `tenant_portal_api/telephony_routes.py`.
- SDKs: `sdk-server/src/index.ts`, `telephony/src/index.ts`,
  `telephony/src/signing.ts`, `telephony/src/types.ts`, both SDK READMEs and
  `docs/MACHINE_AGENT_API_CONTRACT.md`.
- Write safety: `worker/write_tool_gate.py`, `worker/humanization/understanding.py`.
- Tests: `tests/test_ehsan_handoff.py`, `tests/conftest.py`,
  `tests/ci_unit_manifest.txt`, `tests/test_phase4_portal_api.py`,
  `tests/test_portal_wave2_credentials.py`, `tests/test_portal_supabase_auth.py`,
  `tests/test_portal_members_invite.py`, `tests/test_telephony_real_provider_wiring.py`,
  `sdk-server/test/client.test.mjs`, `telephony/test/phase9-contract.mjs`.
- Response: this document. Received Ehsan documents and the pre-existing dirty
  humanization investigation document were not edited by this task.

## Remaining work owned by Ehsan

Please rebase your work on these source changes instead of duplicating the SDK
wire-body patch, negative-confirmation fix or conftest suppression removal.
The broader M10-F02 CI manifest/database gating work is still open; this patch
only adds its own new regression file to the existing unit manifest. Your SSRF,
worker load/lifecycle, test-client authentication, release/provenance and remaining
findings are not declared closed by this document.

No return files, PostgreSQL setup scripts, reports or other documents are
requested from Ehsan. This is a self-contained handoff of the completed changes,
confirmed operating decisions and remaining work ownership.

Migrated-database verification remains outstanding and requires an isolated test
database. That limitation is recorded here without requesting a setup file or a
report back. Customer tenant data must not be used for fixture seeding/cleanup.

## Confirmed decisions from Habiba (2026-10-12)

Deployment presence below is Habiba's confirmation. Service purpose is verified
from source; actual Render plans and deployed revisions have not been inspected.

### Q1: three staging services on Render

| Service | Source and actual responsibility |
|---|---|
| Tenant portal staging | `tenant_portal_api/app.py`: dashboard backend; Supabase access-token exchange, tenant memberships/invites, agents, sessions, usage, credentials, telephony routes/webhooks and registered Test Studio mint/refresh routes. Dashboard uses `NEXT_PUBLIC_TENANT_PORTAL_API_URL`. |
| UVA admin staging | `admin/app.py`: internal admin authentication, tenant/agent/session listings, usage, quota/concurrency/blocker inspection and credential administration. Internal operations only; not a client deliverable. |
| UVA control plane staging | `control_plane/app.py`: authenticated voice-session mint/refresh, LiveKit agent dispatch and public voice catalogue. Dashboard catalogue uses `NEXT_PUBLIC_CONTROL_PLANE_URL`; Test Studio/backend session creation reaches the control plane. |

Matching entrypoints are the Dockerfiles under `docker/` for tenant portal,
admin and control plane. No root `render.yaml` blueprint exists. The tenant
portal API is separate from the `dashboard/` frontend; the dashboard hosting
location/public URL has not been supplied. Render subscription tiers, sizes,
actual service URLs and deployed SHAs remain unconfirmed. Do not assume free
plans or a confirmed cold-start budget from older documentation.

### Q3: worker stays local until CTO confirmation

The voice worker must run locally for now. Moving it to Render or another host
is deferred until the CTO confirms the hosting decision. `worker/main.py` runs
the media/STT/LLM/TTS pipeline and tools; the hosted control plane coordinates
sessions and dispatches it through LiveKit. Worker and control plane must share
the LiveKit project and matching `LIVEKIT_AGENT_NAME`. This configuration
requirement does not establish which worker is serving an individual call.

`scripts/dev_worker.py` is the existing local watchdog: it launches
`worker.main dev` and restarts the child while the watchdog remains alive.
It cannot provide availability when the machine sleeps, loses connectivity or
powers off. Machine specifications, always-on hours and named restart owner
remain unconfirmed. Recommended interim owner: the local development operator,
with a documented health/restart procedure and CTO escalation for hosting.

**Ehsan deployment follow-up:** `.github/workflows/deploy-staging.yml` still
requires `RENDER_DEPLOY_HOOK_WORKER_STAGING`. Without it, the worker step fails
and subsequent admin/tenant-portal steps do not run. Align staging CI with the
three hosted services plus local worker. Do not create a cloud worker or dummy
hook solely to satisfy CI. Production workflow also assumes a hosted worker,
but production topology is undecided. No workflow was modified by this update.

### Q2: concurrency target is 20 calls

Habiba requests **20 simultaneous calls**. Use 20 as the initial overall
capacity-planning target; whether this is also per tenant and the tenant quota
allocation remain unconfirmed. This is a requirement, not measured capacity.

`control_plane/mint.py` enforces each tenant's stored `max_concurrent` using
`quota_state`; telephony has tenant quota checks too. The optional owner
bootstrap in `tenant_portal_api/membership.py` inserts 20 as a creation-time
per-tenant default. That does not update existing quotas or establish a global
20-call cap or safe worker capacity. Ehsan should validate local admission and
load behavior against the real machine. No load test or quota change was made.

### Q8: client receives dashboard access only, via Supabase invitation

The client-facing deliverable is access to [`dashboard/`](../dashboard/),
following invitation through Supabase. Clients are not being handed the
`client-integration-test/` harness, deleted `client-deliverables-final/` pack,
worker/platform repository or internal admin access. Source/package delivery
of the dashboard was not specified; dashboard access is the confirmed surface.

Current onboarding implementation:

1. Provision/link the client's tenant and initial owner using the supported
   operator/claim process.
2. Additional users within that tenant are invited by an owner from dashboard
   `/members`. `POST /portal/members/invite` sends the Supabase Auth invitation
   and associates the user with the inviter's tenant in `tenant_members`.
3. The user opens `/invite`, sets a password and exchanges their Supabase access
   token through `/portal/auth/supabase` for tenant-scoped portal access.

Evidence: `dashboard/src/app/members/page.tsx`, `dashboard/src/app/invite/page.tsx`,
`dashboard/src/lib/portalAuth.ts`, `tenant_portal_api/membership.py` and
`tenant_portal_api/supabase_admin.py`.

An invitation issued directly through Supabase Auth alone does not establish
the intended application tenant membership. Ensure the appropriate membership
link exists. Do not add independent client organizations as members of a
single shared tenant; those members share that tenant's data. Configure the
invite redirect and Supabase allowlist for the actual dashboard `/invite` URL.
Service-role credentials stay backend-only. No invitation or email/redirect
verification was run in this update.

The dashboard currently includes agents, sessions, usage, credentials, telephony,
Test Studio, members and docs. There are no UI callers for agent create/update/
delete helpers; server endpoints still exist. Dashboard-only delivery does not
itself change server permissions. Preserve existing owner/member checks and
tenant isolation. No dashboard features or access controls were changed here.

Recommendation: retire stale client-pack references and align client-facing
handoff instructions with dashboard access, rather than restoring the pack as
a deliverable. Original deletion intent/internal archival needs remain unknown.
The internal test harness still needs security fixes even though it is not
shipped to clients.

## Remaining items: source-backed answers and recommendations

Unknown operational facts are marked unverified. Recommendations below are
provisional, not CTO/legal approval or configuration changes.

| Item | Answer for Ehsan |
|---|---|
| Render plans | Three staging services confirmed; actual subscription plans, sizes and deployed revisions need operator verification. Dashboard frontend hosting/public URL is also unconfirmed. |
| Q4: nonce purge | `.github/workflows/reconcile.yml` schedules every 15 minutes and calls `scripts/purge_used_nonces.py`. Scheduled runs apply unless `RECONCILE_APPLY=false/0`; default purge age is 60 minutes. Live execution is **unverified**. Check relevant default-branch workflow activation, DB secret, apply mode and recent successful purge logs before declaring it operational. |
| Q7: repo privacy | Dashboard access does not require giving clients repository access. Recommend keeping platform source private pending CTO/product approval and fixing client docs/links accordingly. Actual GitHub visibility was not queried; no visibility change was made. |
| M6-F03: recording | Recommend consistent hosted detection, no hosted env-only force-on, and persistence only with granted consent. Current code distinguishes recorder startup from consent-gated persistence; do not conflate them. Ehsan owns the fix. Local hosting does not imply caller consent. Final legal wording and retention period remain pending. |
| License | No license decision supplied. CTO/authorized owner must select terms; do not invent MIT/Apache/proprietary licensing or imply redistribution permission. |
| Prompt-dump history | Recommend preventing new prompt dumps from being committed and keeping debug artifacts ignored/local. Assess historical content and secret exposure first; any history rewrite needs separate coordination across both remotes/branches and collaborators. No purge/rewrite was performed or authorized here. |
| Local-worker operation | Placement is local pending CTO. Record machine specifications, named operator, availability hours and health/restart procedure before promising continuous service or verified 20-call capacity. |

This update records product decisions and recommendations only. It does not
deploy services, enable the scheduler, invite users, change quotas/recording
policy, restart a worker or change repository visibility. Earlier implementation
test results remain recorded above; this documentation update adds no live-call,
listening or runtime-capacity evidence.
