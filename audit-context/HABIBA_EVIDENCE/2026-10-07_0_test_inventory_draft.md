# Habiba Python test inventory (draft) — Wave A / Phase 0

**Date:** 2026-10-07

## Control plane / mint / sessions

- `tests/test_mint.py`
- `tests/test_mint_db.py`
- `tests/test_control_plane_dispatch.py`
- `tests/test_session_close.py`
- `tests/test_session_opening.py`
- `tests/test_session_recording.py`
- `tests/test_session_retention_purge.py`
- `tests/test_reconcile_sessions.py`
- `tests/test_wave2_tenant_secret_encryption.py`

## Portal / machine / auth

- `tests/test_machine_agent_api.py`
- `tests/test_phase4_portal_api.py`
- `tests/test_portal_*.py` (db pool, rbac, supabase auth, members, credentials)
- `tests/test_wave2_portal_hardening.py`
- `tests/test_wave2_gate1.py` (mock switch refuse)
- `tests/test_tools_webhook.py`

## Telephony

- `tests/test_telephony_*.py` (client, routes, outbound destinations, reconcile, schema, RLS, LiveKit SIP, etc.)

## Admin

- `tests/test_admin.py`
- `tests/test_admin_boundary_live.py`

## Gaps noted in Wave A

- No dedicated test asserting machine create enforces `MAX_AGENTS_PER_TENANT` (M5-F01) — add in Wave B.
- Portal create-forbid (M11-F01) needs test once 403 enforced.
