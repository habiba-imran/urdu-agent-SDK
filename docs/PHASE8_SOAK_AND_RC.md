# Phase 8 Soak And Release Candidate

Phase 8 Habiba track turns the dashboard/SDK/frontend work into repeatable validation and a
release-candidate bundle. This doc is the operator-facing runbook.

## Scope

Habiba-owned Phase 8 scenarios:

- multiple tenant agents
- concurrent dashboard usage
- long-running browser session
- release candidate assembly

This doc does not replace Hamza's load/failure drills. It complements them from the client/product
surface outward.

## Preconditions

Before running this soak pass:

1. `tenant_portal_api` runs locally or in staging.
2. `dashboard/` runs locally or in staging.
3. `@uva/voice` has a built `dist/` directory.
4. `examples/host-backend-node/` is installable.
5. At least one active tenant exists with a valid HMAC secret.

## Scenario 1: Multiple Tenant Agents

Goal: prove the dashboard/backend handles more than one agent row for a tenant without leaking or
colliding.

Steps:

1. Log into the tenant portal API with one tenant's `tenant_id` + tenant secret.
2. Create at least 2 agents with distinct:
   - `name`
   - `prompt`
   - `voice_id`
3. Call `GET /portal/agents`.
4. Verify only that tenant's agents are returned.
5. Update one agent with `PATCH /portal/agents/{agent_id}`.
6. Re-fetch `GET /portal/agents` and verify the other agent is unchanged.

Pass criteria:

- both agents appear
- update persists
- no cross-tenant rows appear

## Scenario 2: Concurrent Dashboard Usage

Goal: prove the dashboard pages remain stable when opened in multiple tabs/windows.

Suggested local run:

1. Start `tenant_portal_api` on `http://127.0.0.1:8002`.
2. Start `dashboard` on `http://localhost:3000`.
3. Open 3 browser tabs:
   - `/`
   - `/agents`
   - `/sessions`
4. Refresh all 3 tabs several times while the backend stays running.
5. Keep DevTools open for console/runtime errors.

Pass criteria:

- no blank page / red error overlay
- no client-side crash
- navigation remains responsive

## Scenario 3: Long-Running Browser Session

Goal: prove the browser-side voice surface can stay connected long enough for token refresh to
matter.

Suggested run:

1. Keep the worker running on a stable host (local worker is acceptable for this soak pass).
2. Start the host-backend starter and basic web client.
3. Connect once and leave the session open beyond the initial token lifetime.
4. Confirm:
   - `/v1/session/refresh` occurs
   - the browser does not disconnect unexpectedly
   - transcript / speaking state still update

Pass criteria:

- refresh succeeds
- no forced reconnect loop
- no unreconciled quota drift afterward

## Release Candidate Assembly

Use the assembly script to snapshot the current SDK/dashboard/starter state:

```bash
python scripts/assemble_phase8_release_candidate.py
```

Optional env overrides:

- `PHASE8_DASHBOARD_STAGING_URL`
- `PHASE8_HOST_BACKEND_TAG`
- `PHASE8_NOTES`

Output:

- `state/phase8_release_candidate.json`

The file should capture:

- SDK version candidate
- SDK tarball presence
- dashboard route inventory
- dashboard staging URL (if provided)
- host-backend starter tag/commit hint
- git commit at the time of assembly

## Human Follow-Up

Human-only inputs still required before a true external release:

1. real dashboard staging URL
2. chosen host-backend starter tag/release ref
3. final signoff that the long-running browser session was observed, not merely assumed
