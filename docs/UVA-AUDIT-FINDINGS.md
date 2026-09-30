# UVA Audit — Phase 0–4 Findings

**Date:** 2026-09-30  
**Scope:** Core UVA platform only (`self-serve-demo-UI/` **excluded**)  
**Client delivery model:** **Read-only dashboard as the client product + integration guide.**  
Clients receive the Next.js `dashboard/` to observe agents/sessions/usage/telephony status and to follow in-console docs for integrating voice into **their** systems (host backend + public npm SDKs). Agent/telephony **writes are intentionally not in the dashboard** — they belong on the client’s backend (or AwaazLabs provisioning). npm packages are consumed from the public registry by the client’s engineers, not shipped as a separate “handoff zip” unless you choose to.  
**Bar:** Final / enterprise — strict  
**Status:** Findings document. **Wave 0–5 remediations landed in code** (guide honesty; RBAC; HMAC SPA harden; write-tool/SSRF/machine rate; CI unit+dashboard build; portal deploy required; README tone; legal links/sub-processors; db-reset gate; refresh fail-closed hosted; admin headers hosted fail; tools secret required; webhook insert abort; reconcile apply+usage estimate; CLIENT_* redirects). Counsel-approved ToS/Privacy/DPA text still must be published via `NEXT_PUBLIC_LEGAL_*` URLs.

Related canvases (IDE):

- Phase 0 Criticals re-check  
- Phase 1 Security spine  
- Phase 2 Product surfaces  
- Phase 3 Telephony & providers  
- Phase 4 Ops / data / compliance  

Prior report referenced: `docs/AwaazLabs UVA Audit.md` (commit `94e7000`)

---

## How to use this file

1. For **dashboard-as-final-guide** delivery, prioritize findings that break trust, credentials safety, or **in-dashboard integration docs accuracy**.  
2. Read-only Agents/Telephony is **by design** — do not treat missing write UI as a product defect (**P3-C1 reframed**).  
3. Repo-root `CLIENT_*` guides that still point at deleted trees remain important insofar as engineers find them; prefer fixing **in-dashboard `/docs`** first (that is what clients see).  
4. Phase 0 Criticals that are **Fixed** should not be re-opened unless a regression appears.  
5. P1-C1 (+ dashboard owner UI) and live membership re-check are closed in Wave 1 — still do not over-claim broader enterprise IAM.  
6. “Guide ready” means: credentials + contract + going-live + error docs in the console are complete, accurate, and do not contradict the read-only model.

---

## Overall verdict (after Phase 0–4)

| Claim | Verdict |
|---|---|
| Multi-user / enterprise GA | **NOT GO** |
| **Read-only dashboard as final integration guide** | **NOT GO yet** — secret/XSS surface, Test Studio `dev-mint`, guide gaps, RBAC, **no legal pack (P4-C1)**, CI coverage hole (P4-H1) |
| Controlled single-owner pilot using dashboard + their host backend | Conditional — close guide/security blockers; read-only console is OK |
| Honest “enterprise-grade” marketing | **NOT GO** — README claims vs RBAC/SSO/DPA/observability gaps (**P4-C1**, **P4-H4**) |
| Client builds host backend using public npm SDKs | **In scope for the guide** (documented path); not a second “product zip” |
| npm SDK contract (versions / errors / READMEs) | **Mitigated** — pins `voice@1.1.0` / `agents@0.1.0` / `telephony@0.1.0` in `/docs` + package READMEs; dead `demo-app` / tarball install removed; `voiceId` required in createAgent examples; error codes aligned (`provider_limit`, `outbound_destination_disabled`); `tests/test_sdk_docs_contract.py`; telephony `prepublishOnly` |
| Prior Criticals (F-C1…F-C7) as originally written | None fully open; 4 Fixed, 3 Partial |

### Blocks “dashboard ready as final guide” (fix first)

| ID | Why it blocks | Status (this branch) |
|---|---|---|
| **P1-H6** + **P2-H5** | Guide/credentials flow still puts permanent HMAC in the SPA threat model | **Mitigated** — standing reveal 410; console rotate 410 (default); HttpOnly cookie (+ memory Bearer); credentials UI has no HMAC delivery; admin/out-of-band only |

| **P2-H1** | Test Studio uses `/dev-mint` — teaches the wrong integration path vs host-backend HMAC | **Mitigated** — Test Studio → `/portal/test-studio/session`; docs warn not client path |
| **P1-C1** + **P2-H4** | Members can act as owners via API; guide claims roles that are not enforced | **Mitigated** — live membership + owner gates; Security docs role table |
| **P1-H2** | Empty tenant `allowed_origins` — going-live Origin gate is optional in practice | **Mitigated** — hosted mint fails closed; credentials empty-origins banner |
| **P1-H1** | Open Auth signup can bootstrap random tenants into the console | **Mitigated** — hosted bootstrap off; invite/claim only |
| **P3-G1** *(was P3-C1 / P3-M5)* | Guide quality: docs must be a complete, accurate host-integration path; see reframed P3-C1 | **Mitigated** — `/docs` SoT: provisioned-vs-build, sticky providers, RO Agents/Telephony, rotate (not reveal), origins/errors/Test Studio vs host; legal-and-trust in nav |
| **P3-H1** | Urdu single-provider — only if you claim always-on Urdu in the guide | Product honesty |
| **P4-C1** | No ToS / Privacy / DPA — blocks honest commercial “final” guide | Still open |
| **P4-H1** | CI without DB secret only runs `test_phase0.py` | Still open |
| **P4-H2** | Prod tenant-portal deploy hook optional — dashboard API can lag | Still open |
| **P4-H3** | Dashboard (client deliverable) has no CI build/typecheck | Still open |

Residual for **P1-H6**: none for console delivery — browser reveal/rotate both default **off** (`PORTAL_ALLOW_BROWSER_SECRET_*=1` break-glass only). Prefer admin rotate / out-of-band provision. In-memory Bearer + CSP `'unsafe-inline'` remain general XSS hygiene (not HMAC exfil via credentials APIs).

Read-only Agents/Telephony UI is **accepted**. Soften later: **P2-M1**, **P2-M2**, **P2-M6**, scheduling **P1-H5**.

### Deferred / internal

Repo `CLIENT_*` path redirects (**P2-C1** — Wave 5 tombstoned to `client-deliverables-final/` + dashboard `/docs`). Host-starter CORS/phone (**P2-H2/H3**) remain internal backlog if you ship the starter as a linked download; **in-dashboard `/docs` is the client-facing source of truth** for this model.

---

## Phase 0 — Prior Criticals re-check

Re-verified the seven Critical findings from `AwaazLabs UVA Audit.md` against current HEAD.

| ID | Title | Status | Evidence (current) | Residual |
|---|---|---|---|---|
| **F-C1** | Hardcoded telephony JWT fallback (`mock_jwt_secret_for_tests`) | **Fixed** | Shared `tenant_portal_api/jwt_secret.py::portal_jwt_secret()`; telephony + portal use it; hosted fails without `TENANT_PORTAL_JWT_SECRET`; documented in `.env.example` | Ops must set env on every hosted portal |
| **F-C2** | Unauthenticated `POST /v1/session/dev-mint` | **Fixed** | Off by default when hosted (`CP_ENABLE_DEV_MINT`); 404 when disabled; `publishableKey` required and must match agent owner; quota auto-reset opt-in only (`CP_DEV_MINT_RESET_QUOTA`) | Confirm Render does not set `CP_ENABLE_DEV_MINT=1` |
| **F-C3** | Credentialed wildcard CORS | **Fixed** | `control_plane/runtime_env.py::resolve_allowed_origins` — hosted empty `CP_ALLOWED_ORIGINS` → startup fail; credentials never with `*` | Confirm prod `CP_ALLOWED_ORIGINS` is set |
| **F-C4** | Unconditional recording / no consent / no retention | **Partial** | Agent `recording_enabled` default false; `may_start_recorder` / `may_persist_recording`; disclosure; `retention_until` + purge workflow; migration `0028` | Stay-on-line consent (not explicit verbal yes); recorder may start before consent; legal review still needed |
| **F-C5** | Dashboard Next.js CRITICAL/HIGH CVEs | **Fixed** | `next@15.5.26`; `npm audit --omit=dev` → 0; CSP + security headers in `dashboard/next.config.js` | Keep patched; audit lockfile in CI |
| **F-C6** | Plaintext signing secret + browser reveal | **Mitigated (console)** | `hmac_secret_enc`; masked list; standing reveal + console rotate both 410 by default; HttpOnly cookie + in-memory Bearer | Admin rotate may still return secret once to operators; break-glass env for local only → **P1-H6** closed for SPA |
| **F-C7** | Ungoverned LLM write tools | **Partial** | `worker/write_tool_gate.py` propose → user-turn → confirm; cancel/reschedule need verified phone; schema/idempotency/budget | Any user turn unlocks confirm; `book` without verified phone skips ownership → **P1-H5** |

### Phase 0 → Phase 1 residual mapping

| Phase 0 | Folded into |
|---|---|
| F-C6 residual | **P1-H6** |
| F-C7 residual | **P1-H5** |
| F-H8 SSRF residual (from prior audit) | **P1-H4** |
| F-H4-class (machine path still broken) | **P1-H3** |

---

## Phase 1 — Security spine findings

**Modules audited:**

- M20 Security controls  
- M01 Control plane  
- M11 User access & tenancy  
- M05 Super-admin  
- M22 AI / prompt-injection surface  
- M03 Worker tools & webhooks  

**Counts:** 1 Critical · 6 High · 7 Medium · 1 Low

---

### Critical

#### P1-C1 — Owner/member roles are cosmetic on almost every portal route

| | |
|---|---|
| **Severity** | Critical |
| **Module** | M11 User access |
| **Where** | `tenant_portal_api/app.py` — `/portal/*` uses `_require_tenant` only. `require_owner_on_tenant` is used inside `invite_member_to_tenant` only (`membership.py`). |
| **Why** | An invited **member** JWT can reveal/rotate the HMAC signing secret, change `allowed_origins`, create/patch agents (including tools webhook URL/secret), and drive telephony. Multi-user tenancy is unsafe. Role claim exists but is not enforced on mutating routes. |
| **Suggested fix direction** | Enforce role on every mutating route. Owner-only: credentials reveal/rotate, origins, tools webhook secret, telephony connect/purchase/outbound, agent archive/delete. Add tests: member → 403 on owner routes. |
| **Status (this branch)** | **Mitigated** — live membership re-check + `_require_owner` / `require_owner_tenant_id` on credentials mutate, agents mutate, invites, telephony mutations (`tests/test_portal_rbac_wave1.py`). **P2-H4** residual: UI role still cached in `sessionStorage` (cosmetic only; API enforces). |

---

### High

#### P1-H1 — Any Supabase Auth user without membership auto-creates a tenant as owner

| | |
|---|---|
| **Severity** | High |
| **Module** | M11 User access |
| **Where** | `membership.resolve_or_bootstrap_membership` → `bootstrap_owner_for_auth_user`; `POST /portal/auth/supabase` |
| **Why** | If Supabase signup is open (or an attacker can create Auth users), they self-provision a live tenant with signing credentials — open platform onboarding with no admin gate. |
| **Suggested fix direction** | Disable auto-bootstrap in hosted prod, or require invite/claim only. Gate first tenant creation behind admin provision or allowlist. |

#### P1-H2 — Empty `allowed_origins` disables the mint Origin gate

| | |
|---|---|
| **Severity** | High |
| **Module** | M01 Control plane |
| **Where** | `control_plane/mint.py` (~168–170): `if allowed_origins and origin not in allowed_origins`. Also documented in `PUT /portal/credentials/allowed-origins` response note. |
| **Why** | If `allowed_origins` is `[]`, any browser Origin may mint (HMAC still required). Tenants that never set origins run without the documented browser origin control. |
| **Suggested fix direction** | Hosted: require non-empty allowlist before mint succeeds (or fail closed). Dashboard should block “go live” until origins are set. |

#### P1-H3 — Machine-auth rate limit still fills on unauthenticated `tenant_id`

| | |
|---|---|
| **Severity** | High |
| **Module** | M01 / portal machine API |
| **Where** | `tenant_portal_api/machine_auth.py` — `_rate_limited` appends a hit **before** HMAC verify; keyed on caller-supplied `tenant_id`. |
| **Why** | Control plane fixed this class (prior F-H4). Machine path did not. Knowing a tenant UUID lets an attacker burn that tenant’s machine API budget with junk requests. |
| **Suggested fix direction** | Split check vs record like `control_plane/app.py`: check bucket pre-auth; record only after signature OK. Add per-IP pre-auth damper. Bound `_hits` keys. |

#### P1-H4 — SSRF defense is save-time only; worker does not pin resolved IPs

| | |
|---|---|
| **Severity** | High |
| **Module** | M03 Tools / webhooks |
| **Where** | `tenant_portal_api/tools_webhook.py` (documents DNS-rebinding residual); `worker/tools.py::_post_client_tool` — httpx POST with no re-resolve/pin. |
| **Why** | A hostname public at save time can rebind to link-local/metadata at call time. Worker still POSTs `x-tool-gateway-secret` toward that target from the platform network. |
| **Suggested fix direction** | At request time: resolve, reject internal ranges, connect to pinned address (or egress proxy allowlist). Prefer deny `http` entirely even in staging. |

#### P1-H5 — Write-tool confirmation is not a real caller “yes”

| | |
|---|---|
| **Severity** | High |
| **Module** | M22 / M03 |
| **Where** | `worker/write_tool_gate.py` — any `user_turn_count` advance unlocks confirm; `book_appointment` skips ownership when `verified_caller_phone` is absent. |
| **Why** | Injection/noise after propose can satisfy the barrier. Browser sessions without host-verified phone can book with an attacker-chosen `customer_phone`. |
| **Suggested fix direction** | Require explicit confirm (spoken/DTMF or host-side confirm API). Require `verified_caller_phone` for book too (or bind to host session identity). |

#### P1-H6 — Signing secret still reachable from the browser (XSS chain remains)

| | |
|---|---|
| **Severity** | High |
| **Module** | M20 / M11 |
| **Where** | Was: `POST /portal/credentials/rotate-secret` returned `{ hmac_secret }` to SPA. **Now:** console rotate/reveal both 410 by default; credentials page has no rotate/copy-HMAC UI. Session: HttpOnly cookie + in-memory Bearer. CSP still allows `'unsafe-inline'` scripts. |
| **Why** | Age gate + encryption-at-rest help, but XSS in a window where the SPA held raw HMAC could exfiltrate a **permanent** signing key. |
| **Suggested fix direction** | Never return raw HMAC to the browser — out-of-band provision only; hosted rotate → 410; delete dead SPA rotate client. |
| **Status (this branch)** | **Mitigated** — console never returns HMAC (reveal + rotate → 410 by default). Admin / out-of-band provision only. Break-glass: `PORTAL_ALLOW_BROWSER_SECRET_REVEAL` / `PORTAL_ALLOW_BROWSER_SECRET_ROTATE`. |

---

### Medium

#### P1-M1 — Session refresh fails open when DB checks error

| | |
|---|---|
| **Module** | M01 |
| **Where** | `control_plane/app.py::_enforce_refresh_gates` — exception → allow refresh |
| **Why** | During a DB outage, suspended tenants / closed sessions / minute caps cannot stop in-flight calls via refresh. Documented availability tradeoff. |
| **Suggested fix direction** | Fail closed after N consecutive check failures, or short circuit-breaker + hard alert. |
| **Wave 5** | **Fixed** — hosted → HTTP 503; local/dev still fails open. |

#### P1-M2 — Admin image may ship without security headers

| | |
|---|---|
| **Module** | M05 |
| **Where** | `admin/app.py` — `ImportError` around `SecurityHeadersMiddleware` logs warning and continues |
| **Why** | Thin admin Docker tree may omit `control_plane`, so no CSP/HSTS/XFO on admin API. |
| **Suggested fix direction** | Vendor `security_headers` into admin image or inline middleware; fail startup if headers cannot load when hosted. |
| **Wave 5** | **Fixed** — hosted ImportError raises; Dockerfile already vendors `security_headers.py`. |

#### P1-M3 — TOTP replay & account disable fail open if migrations missing

| | |
|---|---|
| **Module** | M05 |
| **Where** | `admin/auth.py` — `UndefinedColumn` handlers for `last_totp_counter` / `disabled_at` |
| **Why** | Pre-0031/0032 DBs silently lose replay protection and disablement. |
| **Suggested fix direction** | Hosted startup: assert columns exist or refuse to serve `/admin/login`. |

#### P1-M4 — Tools webhook may be called with no gateway secret

| | |
|---|---|
| **Module** | M03 |
| **Where** | `worker/tools.py::_tool_gateway_headers` returns `{}` when secret unset |
| **Why** | Agent can set `tools_base_url` without `tools_auth_secret`; worker still POSTs tenant/agent IDs with no shared secret. |
| **Suggested fix direction** | Reject `tools_base_url` without secret at portal save; worker refuse to call if secret missing when hosted. |
| **Wave 5** | **Fixed** — portal `assert_tools_webhook_pair`; worker refuses POST without secret. |

#### P1-M5 — Persona framing only — lifecycle & RAG tools remain injection-reachable

| | |
|---|---|
| **Module** | M22 |
| **Where** | `worker/main.py` `_PERSONA_FRAME`; tools `end_conversation_summary` / `escalate_to_human` / RAG |
| **Why** | Successful injection can hang up (DoS), spam escalations, or cause tool-gateway side effects. Write tools are gated; these are not. Matches honest ceiling in `31-GUIDE-SECURITY.md`. |
| **Suggested fix direction** | Rate-limit escalate; confirm before end; egress allowlist; never put secrets in tool responses. |

#### P1-M6 — `verified_caller_phone` is host-asserted

| | |
|---|---|
| **Module** | M22 / mint |
| **Where** | Control plane `SessionBody` + mint metadata; `write_tool_gate` ownership |
| **Why** | Compromised/buggy host can assert any phone and unlock cancel/reschedule ownership. PSTN ANI is stronger. |
| **Suggested fix direction** | Document trust boundary; for browser, bind OTP/host verification proof into mint HMAC payload. |

#### P1-M7 — Login throttle fails open if `login_attempts` missing/errors

| | |
|---|---|
| **Module** | M20 |
| **Where** | `control_plane/login_guard.py::assert_not_throttled` |
| **Why** | Brute-force protection evaporates if migration 0031 not applied or DB errors. |
| **Suggested fix direction** | Hosted: require `login_attempts` at startup; on check error apply coarse IP deny rather than full open. |

---

### Low

#### P1-L1 — Machine rate-limit map is unbounded in-process

| | |
|---|---|
| **Module** | M01 machine auth |
| **Where** | `machine_auth.py` `_hits` defaultdict |
| **Why** | Distinct `tenant_id` flood grows memory (F-H5 class). Control plane bounded this; machine path did not. |
| **Suggested fix direction** | Cap keys like control plane `_MAX_TRACKED_KEYS`. |

---

## What still holds (do not regress)

| Control | Evidence |
|---|---|
| Mint gate order | HMAC → skew → nonce → active → ownership → origin → quota → JWT (`control_plane/mint.py`) |
| Hosted CORS | `CP_ALLOWED_ORIGINS` required; no credentialed `*` |
| Dev-mint | Hosted off by default; `publishableKey` must match owner |
| Portal JWT secret | Shared `portal_jwt_secret()`; hosted fail-fast (F-C1 closed) |
| Admin auth domain | Separate `aud`/secret from LiveKit; TOTP + replay when migrated |
| Login audit/throttle | `login_guard` wired for portal + admin when 0031 applied |
| Write-tool gate scaffolding | Propose/confirm/idempotency/budget exist (incomplete — P1-H5) |
| Webhook URL validator (save-time) | Blocks private/link-local/`http`-on-hosted at save (incomplete — P1-H4) |
| Dashboard dependency hygiene (snapshot) | `next@15.5.26`, npm audit clean at Phase 0 check |
| Security headers (CP / portal / dashboard) | Middleware + Next `headers()` present |

---

## Phase 2 — Product surfaces findings

**Modules audited:**

- M10 Tenant dashboard  
- M06 Browser SDK (`@awaazlabs-uva/voice`)  
- M07 Server / Agents SDK (`@awaazlabs-uva/agents`)  
- M12 Client integration (host-tools, client-deliverables-final, client-integration-test)  
- M13 Client / product handoff (repo docs + in-dashboard `/docs`)  

**Counts:** 1 Critical · 5 High · 7 Medium · 1 Low  

### Phase 2 verdict

| Claim | Verdict |
|---|---|
| **Dashboard-only client delivery** | **NOT GO yet** — treat as **read-only guide** readiness (see top “Blocks final guide”); not “add write UI” |
| Repo CLIENT_* / host-starter handoff pack | **Out of delivery scope** — P2-C1 / P2-H2 / P2-H3 remain internal backlog |
| Browser/server npm SDK as client deliverable | **Out of delivery scope** for this model |

**Must close for dashboard delivery:**

- **P1-C1**, **P1-H6**, **P2-H1**, **P2-H4**, **P2-H5**  
- **P1-H2**, **P1-H1** (if signup open)  
- Prefer also **P2-M1**, **P2-M2**, **P2-M6** before calling the console “final”

**Deferred for this delivery model:** P2-C1, P2-H2, P2-H3, P2-M3, P2-M5, P2-M7, P2-L1

Each finding below is tagged: `delivery: blocks dashboard` | `delivery: deferred` | `delivery: platform (behind dashboard)`.

---

### Critical

#### P2-C1 — Official client handoff / quickstart docs point at deleted paths

| | |
|---|---|
| **Severity** | Critical *(internal docs)* |
| **delivery** | **deferred** — not part of dashboard-only client package |
| **Module** | M13 Handoff / M12 Integration |
| **Where** | `docs/CLIENT_HANDOFF_GUIDE.md` → `examples/host-backend/`, `examples/web-client/`; `docs/CLIENT_QUICKSTART.md` → `demo-app/`; `docs/CLIENT_ONBOARDING_EMAIL_TEMPLATE.md` same deleted paths. **Neither `examples/` nor `demo-app/` exist.** Real pack: `client-deliverables-final/` (+ `host-backend-starter`). In-dashboard docs correctly cite `host-backend-starter`. |
| **Why** | A new client following the repo handoff guide cannot complete integration. Dual truth (broken repo docs vs fixed dashboard docs) guarantees support failures and wrong architecture attempts. |
| **Suggested fix direction** | Rewrite/redirect all `CLIENT_*` guides to `client-deliverables-final/`. Kill or stub deleted path references. Align onboarding email template. Add a CI check that linked paths exist. |
| **Wave 5** | **Fixed** — CLIENT_* tombstoned to dashboard `/docs` + `client-deliverables-final/`. |

---

### High

#### P2-H1 — Test Studio connects browser → control plane `dev-mint` (skips host backend)

| | |
|---|---|
| **Severity** | High |
| **delivery** | **blocks dashboard** |
| **Module** | M10 Dashboard |
| **Where** | Was: Test Studio → CP `dev-mint`. **Now:** `/portal/test-studio/session` HMAC-signs to `/v1/session` (`tenant_portal_api/test_studio.py`). CP `dev-mint` remains env-gated, unused by dashboard. |
| **Why** | Teaches / exercises a path that is **not** the production host-backend contract. Requires `CP_ENABLE_DEV_MINT` on hosted CP (or fails). If enabled in prod, dashboard is a privileged soft-mint client from any logged-in tenant browser. |
| **Suggested fix direction** | Test Studio must mint via a dashboard-owned BFF that HMAC-signs like a real host (or a dedicated test mint with tenant JWT + audit). Never call `dev-mint` from production dashboard builds. |
| **Status (this branch)** | **Mitigated** — portal test-studio path; docs label operator smoke vs host mint. |

#### P2-H2 — Host starter CORS reflects any Origin when allowlist is empty

| | |
|---|---|
| **Severity** | High |
| **delivery** | **deferred** — starter not client-delivered |
| **Module** | M12 Client integration |
| **Where** | `client-deliverables-final/host-backend-starter/src/createApp.js` — `if (config.allowedOrigins.length === 0 \|\| config.allowedOrigins.includes(origin))` |
| **Why** | Setting `HOST_ALLOWED_ORIGINS=` (empty) opens CORS to every browser Origin. Default is localhost (safe), but empty is a silent production footgun. |
| **Suggested fix direction** | Fail startup if allowlist empty in non-dev; never treat empty as allow-all. Mirror UVA mint’s hosted fail-closed posture. |

#### P2-H3 — Host starter / NestJS sample omit `verified_caller_phone`

| | |
|---|---|
| **Severity** | High |
| **delivery** | **deferred** for starter pack; **platform** if dashboard agents use scheduling tools without host phone (see P1-H5) |
| **Module** | M12 / M13 / ties to P1-H5 |
| **Where** | `host-backend-starter` session body only `{ agent_id }`; dashboard `backend-setup.ts` NestJS sample same. No `verified_caller_phone` anywhere under deliverables. |
| **Why** | Browser integrations using the official starter cannot satisfy cancel/reschedule ownership; `book` may proceed without verified phone (P1-H5). Clients will ship incomplete security for write tools. |
| **Suggested fix direction** | Extend contract + starter: accept host-verified phone (or session identity) and forward to control plane mint body. Document as required when scheduling tools are enabled. |

#### P2-H4 — Dashboard does not hide owner-only surfaces for members

| | |
|---|---|
| **Severity** | High |
| **delivery** | **blocks dashboard** (with P1-C1) |
| **Module** | M10 (product face of P1-C1) |
| **Where** | `getPortalRole()` used on `/members` invite UI only. `/credentials`, `/agents`, `/telephony` have no role gating. |
| **Why** | Even before API enforcement (P1-C1), the console UX invites members to reveal secrets and mutate telephony. Fixes must be API **and** UI. |
| **Suggested fix direction** | Gate nav + pages by role; disable Reveal/Rotate/telephony connect for members; match API 403s. |

#### P2-H5 — In-dashboard Security docs encourage browser HMAC reveal

| | |
|---|---|
| **Severity** | High |
| **delivery** | **blocks dashboard** (with P1-H6) |
| **Module** | M13 / M10 |
| **Where** | `dashboard/src/content/docs/pages/security.ts` — “Prefer revealing secrets in **API Keys** over pasting into tickets.” |
| **Why** | Normalizes shipping the permanent signing secret into the XSS/localStorage threat model (P1-H6). Wrong guidance for a final security bar. |
| **Suggested fix direction** | Docs: copy secret once at provision via secure channel / download after step-up; never store/display long-lived in SPA. Align with P1-H6 fix. |

---

### Medium

#### P2-M1 — Dashboard route gating is client-side only

| | |
|---|---|
| **Module** | M10 |
| **delivery** | soft block — prefer before final dashboard |
| **Where** | `AppShell.tsx` — `ensurePortalSession` / redirect |
| **Why** | Unauthenticated users briefly hit shells; real enforcement is API. Acceptable if API is strict; still not defense-in-depth for a final console. |
| **Suggested fix direction** | Middleware cookie session or BFF; keep API as source of truth. |

#### P2-M2 — Claim flow requires pasting raw HMAC in the browser

| | |
|---|---|
| **Module** | M10 / M11 |
| **delivery** | soft block — prefer before final dashboard |
| **Where** | `/claim` + `claimExistingTenant` posts `tenant_secret` from the browser |
| **Why** | Needed for legacy claim, but puts permanent secret in browser memory/network from an SPA. |
| **Suggested fix direction** | One-time claim codes issued by admin/portal email; invalidate after use. |

#### P2-M3 — Server SDK `fetch` has no timeout

| | |
|---|---|
| **Module** | M07 |
| **delivery** | deferred |
| **Where** | `sdk-server/src/index.ts::request` — bare `fetch` |
| **Why** | Hung portal can stall host backends indefinitely. Browser SDK already fixed timeouts (F-M14). |
| **Suggested fix direction** | AbortController timeout option (default 15s), same as voice SDK. |

#### P2-M4 — Going-live checklist omits UVA tenant `allowed_origins`

| | |
|---|---|
| **Module** | M13 |
| **Where** | `dashboard/.../going-live.ts` — host CORS only; no “set tenant allowed_origins in API Keys” |
| **Why** | Amplifies P1-H2: clients can go live with empty UVA origin allowlist. |
| **Suggested fix direction** | Checklist item: non-empty tenant origins matching production frontends; block go-live badge until set. |

#### P2-M5 — Internal turn latency metrics exposed to browser end users

| | |
|---|---|
| **Module** | M06 |
| **Where** | `sdk/src/index.ts` emits `turn_latency` / `metrics_updated` from worker data packets |
| **Why** | Prior F-L6: leaks internal stage timings to any page embedding the SDK. |
| **Suggested fix direction** | Gate behind explicit `enableDebugMetrics: true`, or strip stage names in production builds. |

#### P2-M6 — Dashboard CSP still allows `'unsafe-inline'` scripts

| | |
|---|---|
| **Module** | M10 / M20 |
| **delivery** | soft block — prefer before final dashboard |
| **Where** | `dashboard/next.config.js` `script-src … 'unsafe-inline'` |
| **Why** | Weakens XSS mitigation for localStorage JWT + secret reveal (P1-H6). |
| **Suggested fix direction** | Nonce/hash-based CSP for production; remove unsafe-inline. |

#### P2-M7 — Two host starters (`host-tools` vs `client-deliverables-final`) risk drift

| | |
|---|---|
| **Module** | M12 |
| **Where** | `host-tools/` and `client-deliverables-final/host-backend-starter/` |
| **Why** | Clients may copy either; fixes applied to one may not land in the other. |
| **Suggested fix direction** | Single canonical starter; other becomes thin wrapper or deleted with redirect in docs. |

---

### Low

#### P2-L1 — `/integration` is a redirect stub

| | |
|---|---|
| **Module** | M13 |
| **Where** | `dashboard/src/app/integration/page.tsx` → `/docs/overview` |
| **Why** | Fine if docs are correct; bookmarks to “Integration” skip a dedicated checklist page. |
| **Suggested fix direction** | Optional dedicated handoff checklist page linking deliverables + going-live. |

---

### Phase 2 — what still holds (do not regress)

| Control | Evidence |
|---|---|
| Browser SDK fetch timeout | `sdk/src/internal/http.ts` + `fetchTimeoutMs` |
| Browser SDK refresh retry / terminal teardown | `refreshTokenLoop` + tests in `index.test.ts` |
| Browser SDK SSR `document` guard | `typeof document !== 'undefined' && document.body` |
| Host starter publishableKey check | `createApp.js` rejects mismatched key |
| Host starter rewrites refreshUrl to host | `resolveRefreshUrl` |
| Deliverables security rules | `06-SECURITY_RULES.md` — HMAC never in browser |
| In-dashboard docs cite real starter | `host-backend-starter` in quickstart/backend-setup |
| Docs markdown renderer | Custom parser (not raw `dangerouslySetInnerHTML` HTML dump) |
| client-integration-test | Exercises public npm packs against host starter pattern |

---

## Phase 3 — Telephony, providers, voices, quota

**Modules audited:**

- M09 Telephony platform (`tenant_portal_api/telephony_*`, Telnyx, LiveKit SIP, webhooks)  
- M08 Telephony SDK (`telephony/` — platform lens; not client-delivered)  
- M14 Providers (`worker/providers/`)  
- M15 Humanization (`worker/humanization/`)  
- M16 Voices / catalogue  
- M19 Quota & metering  

**Counts:** 1 Critical · 4 High · 5 Medium · 1 Low  

### Phase 3 verdict (read-only dashboard = integration guide)

| Claim | Verdict |
|---|---|
| Read-only Agents/Telephony console | **Accepted by design** (not a missing feature) |
| Dashboard ready as **final integration guide** | **NOT GO yet** — see guide checklist under reframed **P3-C1** |
| Urdu provider resilience | **NOT GO** for “always-on Urdu” claims (**P3-H1**) |
| Telephony platform security vs prior Criticals | Improved; residuals P3-H2… remain platform work |

**Must close for “guide ready”:** security/credentials blockers (P1-H6, P2-H1, P2-H5, P1-C1) **and** guide completeness items in reframed P3-C1.  

---

### Critical → reframed

#### P3-C1 — Read-only dashboard must be a complete, accurate integration guide (not a write console)

| | |
|---|---|
| **Severity** | Critical *(as guide quality — not “add write UI”)* |
| **delivery** | **blocks “final guide” claim** |
| **Module** | M10 / M13 |
| **Design intent (confirmed)** | Dashboard stays read-only for agent/telephony mutation. Clients integrate into **their** systems using in-console docs + credentials + public npm SDKs (`voice` in browser via their host; `agents` / `telephony` on their backend). |
| **Where (current gap)** | Agents empty states / copy correctly say “use SDKs,” but: (1) Test Studio still demos `dev-mint` (**P2-H1**) — wrong pattern for the guide; (2) Security docs encourage SPA HMAC reveal (**P2-H5**); (3) Going-live omits tenant `allowed_origins` (**P2-M4**); (4) Repo `CLIENT_*` paths are stale if anyone leaves the console (**P2-C1**); (5) Guide must clearly state what AwaazLabs provisions vs what the client builds. |
| **Why** | Under this model the dashboard’s job is **trustworthy onboarding + observability**. If the guide teaches the wrong mint path or unsafe secret handling, “final” is false even when read-only is correct. |
| **Suggested fix direction** | Treat `/docs` + Credentials + Going live as the product. Fix wrong paths (Test Studio → host-shaped mint or clearly label “platform internal only”). Document: provisioned agent IDs, publishable key, HMAC → **backend only**, session contract, refresh, origins, telephony via backend SDK. Optionally embed or link a downloadable host-backend starter from Credentials. Do **not** add agent write UI unless product intent changes. |
| **Status (this branch)** | **Mitigated as P3-G1** — `dashboard/src/content/docs/`: overview provisioned-vs-build; how-integration / security rotate (not standing reveal); going-live origins + roles; errors origins/outbound/Test Studio vs host; providers sticky + RO; telephony backend-only; legal-and-trust wired in nav/index. Residual: counsel legal pack (**P4-C1**), Urdu single-provider honesty (**P3-H1**). |

---

### High

#### P3-H1 — Urdu has zero provider redundancy per layer

| | |
|---|---|
| **Severity** | High |
| **delivery** | **blocks dashboard** for Urdu reliability claims (product language) |
| **Module** | M14 Providers |
| **Where** | `worker/providers/capabilities.py` — `ur`: Gladia-only STT, Gemini-only LLM, Uplift-only TTS. Registry still raises rather than substituting (`registry.py`). Bounded retries exist (`provider_retries.py`) but **no alternate provider**. |
| **Why** | Any single Urdu vendor outage/rate-limit takes 100% of Urdu traffic down. English has multiple STT/LLM/TTS options; Urdu does not. Prior F-H10 largely unfixed on redundancy. |
| **Suggested fix direction** | Add ≥1 alternate per layer for `ur` + explicit logged failover policy (even degraded). |

#### P3-H2 — Webhook durable-write path can still lose event rows while applying side effects

| | |
|---|---|
| **Severity** | High |
| **delivery** | platform (behind dashboard sessions/calls) |
| **Module** | M09 Telephony |
| **Where** | `telephony_webhooks.py::_persist_telnyx_webhook_event` — on insert exception, logs and **continues with side effects**; outer endpoint now returns 500 if the whole persist call throws (F-H6 partial fix). In-memory `_seen_webhook_event_ids` still checked **before** durable write. |
| **Why** | Multi-worker / insert-failure races can still desync call status vs quota release. In-memory dedupe is not shared across processes. |
| **Suggested fix direction** | Durable insert in same transaction as side effects; on failure abort side effects + 500. Prefer DB unique constraint as sole dedupe; shrink/remove process-local set. |
| **Wave 5** | **Fixed** — insert failure re-raises (no side effects); endpoint 500 → Telnyx retry. In-memory dedupe residual remains. |

#### P3-H3 — Portal telephony mutating APIs remain member-accessible (P1-C1)

| | |
|---|---|
| **Severity** | High |
| **delivery** | **blocks dashboard** if any telephony write UI is added; **platform** today via API |
| **Module** | M09 / M11 |
| **Where** | All `/portal/telephony/*` use `get_current_tenant_id` JWT only — no owner role check. `telephonyApi.ts` still exposes connect/purchase/outbound helpers even though UI is read-only. |
| **Why** | Any member JWT (or XSS-stolen token) can still call purchase/outbound/rotate Telnyx via API. Dashboard read-only UX does not remove the API surface. |
| **Suggested fix direction** | Owner-only on all telephony mutations (same as P1-C1). |
| **Wave 1** | **Fixed** — `require_owner_tenant_id` on telephony mutations. |

#### P3-H4 — Usage / minutes metering still depends on clean worker shutdown

| | |
|---|---|
| **Severity** | High |
| **delivery** | platform / billing honesty |
| **Module** | M19 Quota |
| **Where** | `worker/usage.py` + `main.py` shutdown callbacks (`_release_quota_slot`, usage emit). Prior F-H18 class. |
| **Why** | Crash/kill loses usage_events and can leak concurrent slots until reconcile. Dashboard usage UI then under-reports. |
| **Suggested fix direction** | Periodic heartbeat usage flush; reconcile job already exists — ensure it is mandatory in prod + alert on leak. |
| **Wave 5** | **Partial Fixed** — scheduled reconcile **applies by default**; writes capped `agent_sec` for stale sessions lacking usage. Mid-call heartbeat flush still optional backlog. |

---

### Medium

#### P3-M1 — Mock telephony auth switches still live in production modules

| | |
|---|---|
| **Module** | M09 |
| **delivery** | platform |
| **Where** | `telephony_routes.py` — `TELEPHONY_ALLOW_MOCK_*`; `assert_mock_switches_disabled()` only when hosted |
| **Why** | Mis-set `UVA_ENV` / hosted detection could re-open mock auth. Safer than before, still a footgun. |
| **Suggested fix direction** | Compile-out mock paths outside tests; refuse process start if switches set unless `pytest`. |

#### P3-M2 — Webhook signature verification bypasses in mock provider mode

| | |
|---|---|
| **Module** | M09 |
| **Where** | `verify_telnyx_webhook_signature` returns True when mock mode and no public key |
| **Why** | Expected for tests; disastrous if `TELEPHONY_PROVIDER_MODE=mock` in a shared env. |
| **Suggested fix direction** | Assert mock mode off when hosted (already partially done for auth switches — extend to provider mode). |

#### P3-M3 — Uplift fixture/path still hard-codes `max_retry=0` in places

| | |
|---|---|
| **Module** | M14 |
| **Where** | `worker/providers/tts/uplift.py` fixture TTS `APIConnectOptions(max_retry=0)`; session path uses `provider_retries` separately |
| **Why** | Easy to confuse “fixture” with live path; live Urdu TTS resilience still thin (see P3-H1). |
| **Suggested fix direction** | Keep fixture isolated; document that live path uses shared retry settings only. |

#### P3-M4 — Humanization is provider-specific and telephony-remap aware — residual complexity risk

| | |
|---|---|
| **Module** | M15 |
| **delivery** | platform quality |
| **Where** | `worker/humanization/*` — spoken/turn profiles per TTS/LLM; `resolve_effective_providers` after telephony remaps |
| **Why** | Correct design, but remap mismatches (PSTN forced providers vs DB agent config) can produce wrong spoken rules. Needs regression suite discipline. |
| **Suggested fix direction** | Keep telephony-channel golden tests per provider; fail loud when remap leaves unsupported combo. |

#### P3-M5 — In-dashboard docs teach SDK-based telephony (aligned with guide model; keep accurate)

| | |
|---|---|
| **Module** | M13 / M10 |
| **delivery** | **guide quality** — teaching backend SDKs is **correct** for this model; severity is accuracy/completeness, not “wrong architecture” |
| **Where** | `content/docs/pages/overview.ts`, `sdk-reference.ts`, Agents empty states |
| **Why** | Clients must leave the dashboard to wire their host — docs must be complete (install, env, signing, refresh, origins, telephony) and must not contradict Test Studio / security pages. |
| **Suggested fix direction** | Fold into reframed **P3-C1** guide checklist; cross-link Credentials → Backend setup → Frontend setup → Going live. |
| **Status** | **Mitigated** with **P3-G1** — telephony + backend-setup + overview tables insist on backend SDKs; console RO reinforced. |

---

### Low

#### P3-L1 — `/telephony` route is a redirect stub

| | |
|---|---|
| **Module** | M10 |
| **Where** | `dashboard/src/app/telephony/page.tsx` → `/agents` |
| **Why** | Fine if Agents is the home; confusing if clients expect a telephony console. |
| **Suggested fix direction** | Keep redirect; document in guide that phone inventory lives under Agents (read-only). |

---

### Phase 3 — what still holds (do not regress)

| Control | Evidence |
|---|---|
| Shared portal JWT for telephony | `portal_jwt_secret()` (F-C1 closed) |
| Outbound quota includes monthly minutes | `telephony_queries.reserve_call_quota` (F-H17 class addressed) |
| Unknown/suspended tenant refused quota | same |
| Webhook persist failure → HTTP 500 retry | `telnyx_webhook_endpoint` (F-H6 partial) |
| Telnyx creds AES-GCM v2 | `telephony_credentials.py` (F-M7 class improved) |
| Hosted mock-auth assert | `assert_mock_switches_disabled` |
| No silent provider substitution | `UnsupportedProviderError` in registry |
| Bounded provider connect retries | `worker/provider_retries.py` |
| English multi-provider matrix | `capabilities.py` `en` |
| Telephony reconcile helpers | `telephony_reconcile.py` |

---

## Suggested fix order (for later — not started here)

### Dashboard-as-final-guide (product intent)

0. **P3-C1 (reframed)** — make `/docs` + Credentials + Going live a complete host-integration guide; keep Agents/Telephony **read-only**  
1. **P2-H1** — stop teaching `dev-mint` as the client path (or quarantine as internal-only)  
2. **P2-H5** + **P1-H6** — guide must not normalize long-lived HMAC in the browser  
3. **P2-M4** — going-live must require tenant `allowed_origins`  
4. **P1-C1** + **P2-H4** — enforce roles if the console has multiple humans  

### Security spine (Phase 1) — still required behind the guide

5. **P1-H2**, **P1-H3**, **P1-H4**, **P1-H5**, **P1-H1**, mediums as capacity allows  

### Telephony / providers (Phase 3 platform)

6. **P3-H1** — Urdu redundancy (if claimed)  
7. **P3-H2**, **P3-H3**, **P3-H4** — webhook / API role / usage durability  
8. Mediums P3-M1…M4 as capacity allows  

### Repo hygiene (secondary to in-dashboard guide)

9. **P2-C1** — fix or delete stale `CLIENT_*` paths so they don’t contradict the console  
10. Host-starter footguns (**P2-H2/H3**) if you link a starter from Credentials  

### Ops / compliance (Phase 4)

11. **P4-C1** — publish ToS / Privacy / DPA (or stop commercial “final” claims)  
12. **P4-H1** — CI must run real unit suite without depending on live DB secret alone  
13. **P4-H3** — dashboard `lint`/`build` in CI  
14. **P4-H2** — require tenant-portal deploy hook in prod pipeline  
15. **P4-H4** — tone down README “enterprise-grade” until evidence matches  
16. Mediums P4-M1…M5 as capacity allows  

---

## Phase 4 — CI/CD, tests, data ops, observability, compliance

**Modules audited:**

- M23 CI/CD & deploy (`.github/workflows/`, `docker/`)  
- M24 Test harness (`tests/`, `pytest.ini`)  
- M18 Data layer / migrations (`supabase/`, `scripts/migrate.py`)  
- M17 Recording retention / purge (workflows + worker helpers — residual from F-C4)  
- M21 Dependency / CVE hygiene (CI audits)  
- M25 Observability  
- M27 Scripts / dangerous ops  
- M28 Compliance / legal / trust pack  

**Counts:** 1 Critical · 4 High · 5 Medium · 1 Low  

### Phase 4 verdict

| Claim | Verdict |
|---|---|
| CI/CD ready for final guide ship | **NOT GO** — DB-less CI is a stub; dashboard not built in CI; portal deploy optional |
| Legal/trust pack for commercial guide | **NOT GO** (**P4-C1**) |
| Migration / docker hygiene vs prior audit | **Improved** — `migrate.py` + `schema_migrations`; `.dockerignore` present; deploy waits on CI |
| Test discovery (F-H1) | **Largely fixed** — `python_files = test_*.py`; small explicit `collect_ignore` |

---

### Critical

#### P4-C1 — No public ToS / Privacy Policy / DPA in the repository

| | |
|---|---|
| **Severity** | Critical *(commercial / trust)* |
| **delivery** | **blocks “final guide” for paying customers** |
| **Module** | M28 Compliance |
| **Where** | Absent from repo and dashboard; prior audit matrix #36; README still says “Enterprise Production Infrastructure” / “enterprise-grade”. |
| **Why** | Dashboard guide helps clients process caller audio/transcripts via your platform. Without tenant-facing terms and a DPA path, “final” commercial delivery is dishonest — especially with recording/transcript features (F-C4 residual). |
| **Suggested fix direction** | Publish ToS + Privacy + DPA (or link hosted legal URLs from dashboard login/docs). Soften README claims until done. List sub-processors (LiveKit, STT/LLM/TTS, Telnyx, Supabase). |

---

### High

#### P4-H1 — CI falls back to a single unit file when DB secret is missing

| | |
|---|---|
| **Severity** | High |
| **delivery** | platform — gates what reaches the guide’s backend |
| **Module** | M23 / M24 |
| **Where** | `.github/workflows/ci.yml` pytest job: if `SUPABASE_DB_URL` unset → only `tests/test_phase0.py`. |
| **Why** | Local discovery was fixed (F-H1), but CI without the secret does **not** run portal/telephony/provider/humanization suites. PRs can look green while almost none of the product tests ran. |
| **Suggested fix direction** | Split unit vs integration jobs. Unit job always runs full non-DB suite (sqlite/mocks). Integration job requires DB secret and is required for `main`. Never equate `test_phase0.py` with “CI passed.” |

#### P4-H2 — Production tenant-portal deploy is optional warning, not fail

| | |
|---|---|
| **Severity** | High |
| **delivery** | **blocks dashboard** reliability — portal is the dashboard API |
| **Module** | M23 |
| **Where** | `deploy-prod.yml` — missing `RENDER_DEPLOY_HOOK_TENANT_PORTAL` → warning + `exit 0`. |
| **Why** | Control plane/worker/admin can ship while dashboard’s API stays stale. Clients see a “final” console talking to old portal behavior. |
| **Suggested fix direction** | Fail the job if portal hook unset (same as control plane). Confirm staging same. |

#### P4-H3 — Dashboard has no CI build / typecheck

| | |
|---|---|
| **Severity** | High |
| **delivery** | **blocks dashboard** as client deliverable |
| **Module** | M23 / M10 |
| **Where** | `ci.yml` — SDK packages build/test; dashboard only appears in `npm audit` (continue-on-error). No `next build` / `tsc`. |
| **Why** | The product you deliver to clients is not compile-gated. Broken guide pages or type errors can ship unnoticed. |
| **Suggested fix direction** | Add `dashboard` job: `npm ci` + `npm run lint` (+ `next build` with env stubs). |

#### P4-H4 — README “enterprise-grade” claims outrun the product

| | |
|---|---|
| **Severity** | High *(marketing / trust)* |
| **Module** | M28 / docs |
| **Where** | `README.md` lines 2, 7 — “Enterprise Production Infrastructure”, “enterprise-grade”. |
| **Why** | Audit still finds no SSO, weak RBAC, no DPA, thin observability. Guide clients will quote this. |
| **Suggested fix direction** | Rewrite claims to match reality (“multi-tenant voice platform; dashboard is read-only integration console”) until P1-C1 + P4-C1 close. |

---

### Medium

#### P4-M1 — Dependency audits are non-gating (`continue-on-error`)

| | |
|---|---|
| **Module** | M21 / M23 |
| **Where** | `ci.yml` pip-audit + npm audit |
| **Why** | Deliberate for hotfix velocity; CRITICAL CVEs can warn-only (mitigated today for Next, but process gap). |
| **Suggested fix direction** | Gate on Critical; warn on High; or scheduled mandatory upgrade job. |

#### P4-M2 — Observability is optional Sentry hooks, not an ops product

| | |
|---|---|
| **Module** | M25 |
| **Where** | Optional `Sentry` in control plane; latency events to browser; no OTel/Prometheus/alert pack in repo. |
| **Why** | Fine for pilot; insufficient for “enterprise” ops claims behind a customer-facing guide. |
| **Suggested fix direction** | Minimum: error tracking on portal + worker + dashboard; alert on deploy/webhook/quota reconcile failures. |

#### P4-M3 — `make db-reset` remains a footgun next to real migrate

| | |
|---|---|
| **Module** | M27 / M18 |
| **Where** | `Makefile` `db-reset` → `scripts/db_reset.py` (destructive). Forward migrate exists (`scripts/migrate.py` + `schema_migrations`) — prior F-H11 largely addressed. |
| **Why** | Improved, but reset can still be pointed at a shared DB by mistake. |
| **Suggested fix direction** | Refuse reset unless `ALLOW_DB_RESET=1` and non-hosted; document migrate-only for staging/prod. |
| **Wave 5** | **Fixed** — `ALLOW_DB_RESET=1` required; hosted env refused. |

#### P4-M4 — Recording retention/purge exists but legal consent residual remains

| | |
|---|---|
| **Module** | M17 |
| **Where** | Migration 0028, `purge-session-media.yml`, disclosure/policy modules; stay-on-line consent (F-C4 Partial). |
| **Why** | Tech path improved; commercial guide still needs P4-C1 + consent strength for recorded calls. |
| **Suggested fix direction** | Keep purge scheduled in all envs; document retention defaults in Privacy policy. |

#### P4-M5 — A few harness tests still explicitly ignored

| | |
|---|---|
| **Module** | M24 |
| **Where** | `tests/conftest.py::collect_ignore` — CER/`bench` leftovers (`test_harness`, `test_tts`, `test_phase8_prod`, etc.). |
| **Why** | Much better than the old 50+ silent skip whitelist; dead files still clutter trust in “full suite.” |
| **Suggested fix direction** | Delete or quarantine under `tests/retired/` so count matches runnable suite. |

---

### Low

#### P4-L1 — Docker smoke builds CP/worker/admin but not tenant-portal image

| | |
|---|---|
| **Module** | M23 |
| **Where** | `ci.yml` docker-smoke job |
| **Why** | Portal Dockerfile may break unnoticed until deploy. |
| **Suggested fix direction** | Add `tenant-portal-api.Dockerfile` to smoke (and prefer fail if missing). |

---

### Phase 4 — what still holds (do not regress)

| Control | Evidence |
|---|---|
| Pytest discovery default | `python_files = test_*.py` (F-H1 class fixed) |
| Live tests excluded by marker | `addopts = -m "not live"` |
| Prod deploy waits on CI success | `deploy-prod.yml` `workflow_run` + conclusion gate (F-H3 class fixed) |
| Missing core deploy hooks fail | control plane / worker / admin |
| `.dockerignore` | Present (F-H16 class fixed) |
| Forward migrate runner | `scripts/migrate.py` + `schema_migrations` (F-H11 class fixed) |
| Gitleaks in CI | `security-scan` job |
| SDK packages built/tested in CI | voice / agents / telephony |
| Session media purge workflow | `purge-session-media.yml` |
| Reconcile workflow | `reconcile.yml` |

---

## Out of scope (this document)

- `self-serve-demo-UI/`  
- Turning the dashboard into an agent/telephony **write** console (explicitly **not** the chosen product shape)  
- Live penetration / load / soak / carrier proof  
- Production env value verification (Render / Supabase / Telnyx / GitHub secrets contents) — owner must confirm  
- Further phases beyond 0–4 (none planned in this file unless requested)  

---

## Appendix — module IDs referenced

| ID | Module |
|---|---|
| M01 | Control plane |
| M03 | Worker tools & webhooks |
| M05 | Super-admin service |
| M06 | Browser SDK |
| M07 | Server / Agents SDK |
| M08 | Telephony SDK (npm) |
| M09 | Telephony platform |
| M10 | Tenant dashboard |
| M11 | User access & tenancy |
| M12 | Client integration |
| M13 | Client / product handoff |
| M14 | Providers (STT/LLM/TTS) |
| M15 | Humanization |
| M16 | Voices / catalogue |
| M17 | Recording / retention / purge |
| M18 | Data layer / migrations |
| M19 | Quota & metering |
| M20 | Security controls (cross-cutting) |
| M21 | Dependency / CVE hygiene |
| M22 | AI / prompt-injection surface |
| M23 | CI/CD & deploy |
| M24 | Test harness |
| M25 | Observability |
| M27 | Scripts / ops tooling |
| M28 | Compliance / legal / trust pack |
