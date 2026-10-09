# Client and dashboard testing finalization — 2026-10-09

The independent client and dashboard are aligned with current P0 source. The previous final verdict remains `P0_IMPLEMENTATION_READY_ACTIVATION_BLOCKED`. This work prepares testing; it does not provide live activation evidence.

## Client setup

- Copy the entire `client-integration-test/` folder, including `packages/`, to use it independently. It imports installed packages and calls public platform endpoints through its own backend; no imports from worker, dashboard, database or SDK source.
- Browser SDK: included, **unpublished** `1.1.1-humanization.0` test snapshot built from current SDK source. Published registry `1.1.0` remains the baseline and lacks the new readiness handshake. Agents/telephony use their published `0.1.0` packages. GitHub publication does not update npm.
- Lockfiles, archive SHA-256/integrity and source-hash manifest identify the build. `npm run verify` checks installed versions, local package resolution, archive identity and readiness support.
- README no longer relies on deleted `client-deliverables-final/`. `TESTING.md` covers six language/channel lanes and interaction evidence; `PLATFORM_TESTING.md` documents existing operator-owned candidate switches and rollback.
- Client and Test Studio distinguish room connection from browser playback readiness. Client diagnostics deduplicate turns and preserve outcome/correlation/component identity; latency labels are proxies, not caller-acoustic FUAW. Closed sessions clear thinking/speaking state.
- Existing client backend/frontend env files contain all required fields, checked without printing values. Presence does not prove service availability or credential validity. Actual env files, worker flags, provider models and service configuration were preserved.

## Dashboard

- Added `/docs/humanization-testing` to documentation navigation and static generation. Updated lifecycle, frontend setup, quickstart, SDK reference, providers, what-to-expect, going-live, overview and security instructions.
- The API Keys page now uses the **existing** audited owner-only reveal endpoint through an explicit control. Revealed HMAC stays in page-local tenant-scoped state, outside the SWR metadata cache; hiding it removes it from generated env snippets. Hosted reveal remains disabled by default and shows the existing API error; secure operator delivery is documented. No backend permission was relaxed.
- Test Studio reports readiness and links to the testing checklist. It uses current repository SDK source through the dashboard's existing local package/build setup; it is an operator path, not the independent client's host integration.

## Verification

| Check | Result |
| --- | --- |
| Clean copy of only client folder: npm ci, host tests, TypeScript, Vite build, package/hash checks | PASS; 7 synthetic host-contract tests, no skipped or failed |
| Original client final build | PASS |
| Dashboard typecheck and final production build | PASS; 32 generated pages |
| Served docs | HTTP 200 and content checks PASS: testing, events, providers, security |
| Served credentials/Test Studio | HTTP 200; expected unauthenticated session-check shell only |
| Intended offline Python CI manifest | 638 passed, 1 existing offline SSRF skip, 0 failed; five existing warnings |
| Browser SDK | 33 passed; lint/typecheck/build PASS |
| Server SDK | 12 passed; lint/typecheck/build PASS |
| Telephony SDK | Existing phase8 smoke/phase9 contract PASS; build/typecheck PASS |
| npm audits | Client and SDK report zero findings after compatible source-map-js patch update; SDK lock metadata also aligned with its existing 1.1.0 package version |
| Static checks | Packer Ruff/Python compile PASS; CRLF-aware staged diff check PASS |
| Publication preparation | User explicitly requested git add . for all current work/deletions; staged private-env/configured-secret-value checks PASS |
| Graph refresh | Attempted; existing uv trampoline canonicalization failure |

The existing client large-bundle warning remains. Automated tests/builds and HTTP shells are not proof of authenticated reveal behavior, browser mic/autoplay, actual hearing, provider calls, native Urdu/mixed listening, telephony, deployed persistence or migrations. No live call, purchase, provisioning, migration, npm release tag, policy activation or production canary was started. Caller-acoustic FUAW remains unavailable. Current candidate policies stay off unless an operator explicitly enables them on an isolated test worker.

## Start testing

From `client-integration-test/`: run `npm run install:all`, then `npm run verify`. Start `npm run dev:backend` and `npm run dev:frontend` in two terminals; open `http://localhost:5174`. The platform services and dedicated test tenant/agent must already be available. Follow `TESTING.md` and the isolated worker instructions in `PLATFORM_TESTING.md`. The committed additive 0039 telephony provider-ID migration is not automatically applied by a GitHub push; deployment/schema readiness remains a platform responsibility.

## Publication scope

The user explicitly authorized **all** current repository changes and deletions, including completed humanization, prior API/telephony fixes and these client/dashboard updates. The fetched origin/org main/staging tips are ancestors of local main, so ordinary fast-forward pushes preserve history. No organization-only exclusion was requested; the independent client is included on all four requested branches. Verify all remote tips against the resulting commit after push.
