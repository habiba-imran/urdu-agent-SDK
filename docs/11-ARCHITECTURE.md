# 11-ARCHITECTURE.md

## The whole system

```
Tenant's end user (browser, on HOST PLATFORM's site)
   │  1. clicks "talk"
   ▼
HOST PLATFORM's SERVER ──2. HMAC-signed POST /v1/session──► OUR CONTROL PLANE
   │                          {tenant_id, agent_id, ts, nonce, sig}      │
   │                                                                      │ 3. verify HMAC
   │                                                                      │ 4. check quota (Supabase)
   │                                                                      │ 5. mint LiveKit JWT
   │  ◄────────6. {token, wsUrl, roomName} TTL<=120s ─────────────────────┘
   ▼
7. our SDK in browser connects to LiveKit Cloud with that token
   ▼
LiveKit Cloud room ◄──8. job dispatch──► OUR ONE AGENT WORKER
                                            │ 9. read room metadata {tenant_id, agent_id}
                                            │ 10. load prompt+voiceId from Supabase
                                            │ 11. Gladia STT -> Gemini -> Uplift TTS
                                            │ 12. write usage_events
```

## Why ONE worker
LiveKit Scale allows **4 agent deployments**. One-per-tenant caps you at 4 tenants. Dead on arrival.
One worker + per-session config from `room.metadata` = **unlimited tenants**, zero marginal infra.
**Creating an agent is a database INSERT. It costs nothing and touches no infrastructure.**

## Trust boundaries — memorise this
```
UNTRUSTED: host platform's browser | tenant's prompt text | end user audio | anything from the DB
TRUSTED:   our control plane | our agent worker | our .env
```
The tenant's prompt is **data**, never instruction. It never concatenates into a system prompt,
never reaches a tool, never influences a tool call. See 31-GUIDE-SECURITY.md §4.

## The token mint is the whole security model
It is the only place where: identity is established, quota is enforced, scope is bound.
If it's correct, an attacker with the full client bundle gets nothing.
If it's wrong, nothing else matters.

## Component map
| Component | Lang | Dir | Phase |
|---|---|---|---|
| Control plane (mint, quotas, HMAC) | Py 3.12 FastAPI | `control/` | 2 |
| Agent worker | Py 3.12 livekit-agents | `worker/` | 3 |
| Client SDK | TS, Node 20 | `sdk/` | 4 |
| Admin portal | TS/React | `admin/` | 6 |
| DB | Supabase Postgres | `supabase/` | 1 |

## Ported from the old Pipecat repo — this is real IP, do not rewrite
`persona.py` · `tools.py` · `db.py` · **`tests/` CER harness (most valuable)** · `DECISIONS.md` → `40-ADR.md`
**Scrapped:** `bot.py` pipeline wiring · `services/uplift_tts.py` (the LiveKit plugin replaces
300 lines of hand-rolled Socket.IO — that's the whole reason we chose LiveKit) · `processors.py` · `static/`
