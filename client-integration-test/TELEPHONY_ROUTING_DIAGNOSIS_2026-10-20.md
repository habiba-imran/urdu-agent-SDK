# Telephony routing diagnosis — 20 October 2026

The selected phone number is assigned to the demo agent, but its routing is not
ready. The assignment persisted despite the browser's 20-second timeout. A direct
retry through the published Telephony SDK returned HTTP 502 after 20.469 seconds:
`livekit_sip_dispatch_rule_failed`. The subsequent read confirmed assignment saved,
routing `not_configured`, and outbound readiness false. No outbound call was placed.

## Verified conflict

Read-only database inspection found two active records for `+13144621603`:

| Record | Tenant | Agent | Routing | Disabled |
| --- | --- | --- | --- | --- |
| `c649a6c1-0303-4aff-b086-0fc05960d9ea` | `13dda2bb-e391-494a-8391-3cd7f9371b20` | `f46e964e-a300-4e89-bbcf-582dc510d391` | ready | no |
| `71d52b33-faa7-4f58-a371-3098d71fc57a` | `21590a56-2cf6-4943-b0b0-1c1ae69ed4fc` | `c507b48c-0e85-4cc8-9f31-f80252482f3e` | not_configured | no |

LiveKit inventory confirmed:

- The number is on inbound trunk `ST_NeABDifhEMKu`, named for the older record.
- Dispatch rule `SDR_A5zzqBXmYW9z` is bound to that trunk. Its room-agent metadata
  names the older tenant, phone record, and agent, with worker `uva-staging-agent`.
- The adapter reuses a trunk by phone number, then finds dispatch rules by the
  current phone-record ID. The older rule has a different name. Creating a new
  rule for this same trunk is consistent with the observed provider setup failure;
  the precise upstream provider detail was not captured, so the overlap's role in
  that 502 remains an inference. The active ownership conflict is directly verified.

[LiveKit documents](https://docs.livekit.io/telephony/accepting-calls/dispatch-rule/)
that dispatch rules determine inbound rooms and can configure agent dispatch.
Replacing the existing rule would change the older tenant's inbound agent route.
The user chose to preserve the existing tenant's route. Neither tenant record was
disabled or transferred, and no existing dispatch rule was modified or deleted.

## Fixes made

- Local host SDK requests have a bounded 120-second timeout. Browser reads allow
  45 seconds and mutations 180 seconds, with a visible provisioning message.
- A timeout explains that server completion is unknown and tells the user to
  refresh before retrying. It does not trigger an automatic call retry.
- Assignment refreshes persisted state after failure. The host returns
  `assignmentSaved` and `routingStatus`, preserving failure HTTP status.
- Removed the redundant explicit routing call after assignment: the current
  platform assignment operation already configures Telnyx/LiveKit routing.
  Already-ready assignments do not provision again. A non-ready SDK result fails
  closed instead of appearing successful.
- Importing an already-managed number returns its existing record, and its import
  button stays disabled even after loading states finish.
- The UI displays routing per number and blocks outbound unless the selected
  number is ready and assigned to the selected agent, tenant readiness is true,
  and the destination is valid E.164.
- Platform adapter source now detects another named dispatch rule on the same
  trunk and returns `409 call_state_conflict` before attempting create/update/delete.
  It does not silently take over another route. **This platform source guard is
  tested locally and has not been deployed to the tenant API.**

The local backend was restarted with its fixes. Vite serves the updated UI at
http://localhost:5174/. Refresh the page to load its current number state.

## Verification and pending work

Passed: 20 backend tests, 15 DOM tests, TypeScript, production frontend build,
published SDK package checks, and 60 focused telephony Python regressions. The
tests cover failure/partial assignment, no duplicate provisioning/import, timeout
recovery, call gating, and preserving another number's dispatch rule.

The restarted host returned HTTP 200 and `alreadyManaged: true` for the existing
number's import request without reinserting it. The served frontend module includes
the new routing hint, provisioning timeout, and timeout recovery text. Scoped Ruff,
Python compilation, and CRLF-aware diff checks passed. Graph refresh was attempted;
the installed launcher failed with `uv trampoline failed to canonicalize script path`.

Live evidence came from deployed SDK reads/retry, LiveKit inventory, and one
read-only query limited to this phone number. It does not prove a successful PSTN
call. The current number remains unrouted in the demo tenant.

The user chose **keep the existing tenant's route**. The other listed number,
`+14755587853`, also has a pre-existing LiveKit rule (`SDR_Hv4CxMQbwEdL`) whose
metadata identifies tenant `bd576401-25dd-43e6-8bc5-6469c49bab71`; that rule was
also left unchanged. This observation does not establish whether its old platform
record is still active. No alternate route was adopted or transferred.

To proceed without replacing routes, use an unused owned number for the current
demo tenant, or configure the demo with the matching credentials and agent of the
tenant owning the desired existing route. Enter credentials in the local environment
files, not chat. Do not just mark the demo record ready while LiveKit still
dispatches another tenant.

Deploying the adapter guard and deciding cross-tenant number ownership are separate
from installing this local demo update.

## Follow-up: panel-wide loading freeze

The global pending-request counter disabled every input/button, including recovery
controls, while a slow provisioning request waited up to three minutes. Its feedback
was below the visible controls. The panel now tracks requests separately, shows
operation/progress/error information above the controls, and allows independent
reads and number browsing during provisioning. Conflicting writes stay guarded.

Browser reads now expire after 20 seconds, including stalled response bodies;
ignored-abort and late-response cases cannot leave the UI locked or overwrite its
recovered state. Concurrent refreshes share reads. Upstream reads use 10 seconds,
status checks run concurrently, and provisioning SDK steps share one 120-second
operation budget, with a 150-second browser deadline.

Verification passed 24 backend and 20 DOM tests, TypeScript, build, and published
SDK checks. New cases cover never-returning requests, stalled response bodies,
late replies, duplicate refreshes, concurrent status checks, and shared deadlines.
After restarting the local backend, live list/status reads returned HTTP 200 in
about five seconds and Vite served the updated progress/deadline implementation.
No browser automation surface was available; browser visual acceptance was not
performed. The graph refresh was attempted and hit the existing launcher failure.

These changes fix panel loading behavior. They do not transfer either existing
phone route or make the current tenant's unrouted number call-ready.

## Follow-up: disabled outbound action

The selected demo record has its agent assignment saved, but still reports
`routing_status: not_configured`. The outbound action now says `Routing not ready`,
has an accessible explanation, and distinguishes missing assignment from saved
assignment with incomplete routing. Connection status also displays the configured
tenant ID, including when either upstream status read fails. Once routing and
readiness pass, the action returns to `Place outbound call` and becomes available.

The existing route remains unchanged. No matching credentials for its tenant were
found in the inspected local demo profiles. Configuring that tenant's credentials
and existing agent is still required to use this number without moving its route.
All 44 frontend/backend tests and the production build pass after this change.
