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

## Phrase-replacement convention (P3, ADR-006)
Uplift's TTS engine handles mixed-script input natively (confirmed from their own docs example:
"Meezan Bank اعتماد کا ضامن"). To get correct pronunciation, the system follows a TWO-LAYER
approach:

**Layer 1 — Persona convention (the common case):** words of genuine English origin — brand
names (TechZone, MacBook, Dell, Lenovo), technical terms (laptop, WiFi, warranty, battery health),
product names (MacBook Air M2, ThinkPad, XPS), and units (256GB, 8GB RAM) — are written in
LATIN script inline within otherwise-normal Urdu sentences. Everything else stays proper Urdu
script and grammar. Do NOT transliterate English-origin words into Urdu script.

Correct: «TechZone میں MacBook Air M2 256GB 315000 روپے کا ہے»
Wrong:   «ٹیک زون میں میک بک ایئر ایم ٹو 256GB 315000 روپے کا ہے»

The measured mispronunciation came from the old persona transliterating brand names into
Urdu script (D42), which the engine reads differently.

**Layer 2 — Phrase replacement config (the safety net):** committed at .uplift_phrase_config.
Covers residual cases: (a) Latin words the engine may still mispronounce even when written
correctly (e.g., "MacBook" → "میک بک" phonetically), (b) common LLM misspellings,
(c) multi-word terms ("battery health"). The configId is wired into every TTS call path
(worker/factories.py for live sessions, scripts/record_fixture.py for fixture recording).
Creating/updating the config is a REST CRUD operation (POST /v1/synthesis/phrase-replacement-config)
that does NOT consume TTS budget — no audio is generated.

Full rationale and the complete phrase list in docs/40-ADR.md ADR-006.
