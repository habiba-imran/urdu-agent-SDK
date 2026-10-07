# Evidence — M8 volatile in-memory state (Habiba services)

**Date:** 2026-10-07

| Structure | Location | Lost on restart? | DB / durable backup? |
|---|---|---|---|
| Mint IP + tenant rate buckets | `control_plane/app.py` `_hits` OrderedDict | Yes | No — limits reset (burst window after cold start) |
| Machine rate buckets | `machine_auth._hits` | Yes | No |
| Webhook signature / event-id LRU | `telephony_webhooks._seen_*` | Yes | Partial — matched events in `telephony_call_events` (M4-F02 gap) |
| Webhook IP rate hits | `telephony_webhooks._webhook_hits` | Yes | No |
| Tenant secret cache | `secrets_db._cache` TTL 60s | Yes | Re-read from DB |
| Portal DB pool | `db_pool` size 4 | Yes (reconnect) | N/A — connections |
| CP mint DB singleton | `mint_db._cached` | Yes | N/A |
| Login throttle | `login_guard` (if process-local) | Yes | Check `login_attempts` table for durable side |

**Cold start:** First requests pay TLS + pool warm; `/healthz`, `/healthz/deep`, `/healthz/warm` (CP) and portal `/healthz` exist. Render plan / sleep idle behavior: UNKNOWN (no dashboard access).
