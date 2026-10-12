# Backend SDK staging integration

Date: 2026-10-12, Asia/Karachi. This is a source/integration report, not a hosted
deployment completion claim.

## Inventory and source commits

| Application | Actual SDK consumption | Updated source commit | Deployment |
| --- | --- | --- | --- |
| `client-integration-test/backend` in `Finova-Solutions/urdu-voice-agent-SDK` | Agents factory in `src/createApp.js`; Telephony factory in `src/telephonyRoutes.js` | `34e404d34c02ba9e50becc668fe83065c4634b21` | No hosted Node staging target identified; not deployed |
| `backend` in `habiba-imran/self-serve-demo-UI` | Agents singleton/factory in `src/uva/agentsClient.ts`; Telephony singleton in `src/telephony/client.ts` | `5aef37ac1e3b32f6ec529f428fb0681439291c83` | No hosted Node staging target identified; not deployed |

Both commits are uploaded on `codex/backend-sdk-raw-body-staging` in their
respective repositories. Main and staging branches were not updated. The
self-serve repository was inspected and changed in an isolated checkout under
ignored `tmp/backend-integrators/self-serve-demo-UI`, preserving the existing
separate working copy. Its standalone production-audit Telephony constructor
was aligned with raw mode too; the production audit was not run.

The tracked local package/source inventory contains one consumer application.
An authenticated GitHub SDK-reference search scoped to the two repository
owners associated with this checkout identified the second application above.
`host-tools` is a Node gateway but does not consume either SDK. Root package
metadata supplies the Supabase CLI. `sdk-server` and `telephony` are SDK source
packages and compatibility tests, not integrator applications. Dashboard,
browser/frontend packages and the Python LiveKit worker are excluded.
Archived documentation/examples and vendored SDK definitions are not additional
running backend applications. Customer-owned applications in repositories not
supplied or accessible cannot be inventoried from this checkout; those need
repository access, staging service identity and the integrator's test environment.

## Implementation

- Both real Node backends pin published npm Agents and Telephony `0.1.1`.
- Relevant backend lockfiles contain registry artifact URLs and integrity hashes.
  The self-serve backend no longer obtains these two SDKs from a local tarball/link.
- Every applicable application constructor explicitly sets
  `signatureVersion: 'raw-body-v1'`; SDK compatibility-test defaults are preserved.
- Installed-package guards and SDK distribution documentation are updated.
- Regression tests exercise the actual application factories with Unicode,
  exponent-form floats and explicit null, checking the version header and HMAC
  against the actual transmitted bytes.
- Each backend has a repeatable staging verification runner that refuses any
  machine API URL other than the confirmed staging portal.
- `/uva-signing-test/` is now ignored. Its contents and `.env.local` were not
  staged or committed; no environment file or credential was copied into source.

## Verification results

### Independent integration backend

Clean lockfile installation passed. Backend tests: 8 passed, 0 failed, 0 skipped.
Frontend TypeScript and production build passed; Vite reported its existing
large-chunk advisory. Installed package/hash checks passed for the retained
Voice snapshot and both published backend SDKs. The frontend dependency was not
changed by this task. The initial sandbox-only Vite build could not traverse an
ancestor directory; the same build passed outside that sandbox restriction.

Using the existing ignored staging environment, the actual local backend routes
returned 200 for `/api/provider-capabilities`, `/api/agents` and
`/api/telephony/calls`. Its actual Telephony factory's managed-number POST also
passed. Installed Agents and Telephony versions were checked as `0.1.1`.
The checks were repeated after clean installation and the source commit.

Repeat from `client-integration-test/backend`:

```powershell
npm ci
npm test
npm run verify:staging
node ../scripts/check-packages.mjs
```

### Self-serve backend

All five supporting local engine/scraper dependency builds passed. Backend
TypeScript with and without emit passed. Focused SDK/configuration/error tests:
7 passed, 0 failed. Actual Agents singleton list/capabilities and Telephony
singleton managed-number POST passed against the confirmed staging portal,
with installed versions checked as `0.1.1`.

The full backend suite after building dependencies returned 140 passed,
11 failed, 0 skipped. Failures are database-backed SMS tests in
`enqueueFollowup`, `hardening`, `reengagement`, `reviews` and `webhooks`:
the fresh checkout has no configured Supabase service-role test environment,
and requests fail with `TypeError: fetch failed`. These SMS files were not
changed. The full application test gate remains red; no deployment is approved
by these SDK-only successes. Use an isolated migrated test database or proper
test doubles to complete this gate, not production/customer data.

See that repository's `backend/SDK_STAGING_ROLLOUT.md` and
`backend/src/scripts/verify-sdk-staging.ts` for repeat commands and limitations.
The live check imported the actual application client modules; it did not start
or verify the entire self-serve authenticated route stack.

## Staging deployment status and remaining access

Confirmed target: `https://uva-tenant-portal-staging.onrender.com`.
The supplied control plane is
`https://uva-control-plane-staging-dsyy.onrender.com`. The user also confirms a
UVA admin staging service. These three services run Python platform entrypoints;
none is the Node backend application changed here. The portal's actual deployed
source SHA is unavailable without deployment metadata; do not infer it from a
successful signing probe or repository HEAD.

Repository workflows deploy only the Python platform services. No Node backend
Render hook/blueprint or GitHub deployment record was identified. Existing local
integration configuration identifies `http://localhost:3100` as its host URL.
No authenticated deployment browser, Render CLI or configured Render credential
was available. A Render connection was offered but remains unconfirmed.

Successful hosted Node staging deployments: **none**. Deployed Node commits:
**none**. Source branches are prepared and uploaded; that is not deployment.
Do not redeploy the Python services simply to publish these Node package changes.

To continue, identify an existing Node staging service and its hosting account,
repository/branch, root/build/start settings and URL, then provide deployment
access through the appropriate connection. If the backends are intentionally
local/internal, record that arrangement instead of provisioning a new public
service. The integration harness has unauthenticated management routes; public
hosting needs its separate access-control review or restricted ingress.

Before production: finish the self-serve full test gate, verify applicable
authenticated application/write paths using isolated staging fixtures, deploy
the intended Node staging service, and repeat the checks through its hosted URL.
Record the deployed commit, deployment identifier and timestamp from the hosting
provider. Production rollout requires separate authorization.

## Rollback procedure

1. If only the backend application needs rollback, use its previous deployment
   artifact and verify read-only Agents/Telephony calls.
2. Before any rollback to a portal without raw-body support, set **both** backend
   constructors to `signatureVersion: 'canonical-json-v1'` and redeploy the
   backends first. Keep SDK `0.1.1`, which supports legacy mode.
3. Verify those backends, then roll the portal back if required. Legacy numeric
   and Unicode canonicalization limitations remain in that mode.
4. Preserve tenant identity/credentials. No history rewrite, force push or
   credential rotation is part of this procedure.

No production deployment, provider purchase, real call, credential rotation,
Git history rewrite or worker-hosting change was performed. The worker remains
local. `graphify update .` was attempted in both repositories and failed with
`uv trampoline failed to canonicalize script path`; graph refresh is unverified.
