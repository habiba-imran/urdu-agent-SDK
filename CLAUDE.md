# AwaazLabs-UVA-Voice SDK

Multi-tenant SDK embedded in a THIRD-PARTY platform. Their users create Urdu voice
agents from (prompt + voiceId). We own the SDK. We do not own the host platform.

## FIRST ACTION, EVERY SESSION
Read `state/PROGRESS.md`. Then read `docs/00-INDEX.md` and load ONLY the guide it
routes you to. Do not read all docs. Do not guess which guide applies.

## Stack — do not substitute without an ADR in docs/40-ADR.md
LiveKit Agents (Python 3.12) | Uplift TTS | Gladia STT (dev) | Google Gemini (BYO key)
Supabase Postgres + RLS | LiveKit Cloud Build (free) | Node 20 for SDK/admin

## Non-negotiables
1. ONE multi-tenant agent worker. NEVER one deployment per tenant.
2. Client bundle is PUBLIC. Assume every byte is stolen. Nothing secret ships in it.
3. Provider keys server-side ONLY.
4. Host platform's SERVER -> our server (HMAC) -> we mint LiveKit JWT, TTL <=120s,
   scoped to one room + one identity.
5. Quotas enforced in the TOKEN MINT. Never in the client.
6. RLS on every table. No exceptions. Gate-verified.
7. TELEPHONY IS OUT OF SCOPE. No SIP code. No SIP deps.
8. DEV IS FREE-TIER ONLY. Never call a paid API. Fixtures first: docs/30-GUIDE-FREE-TIER.md

## The loop — every task, no exceptions
READ state/PROGRESS.md -> ROUTE via docs/00-INDEX.md -> PLAN -> IMPLEMENT
-> `make gate` -> reviewer subagent -> RECORD in PROGRESS.md -> COMMIT

## Verify, don't assume
Unsure of an API signature? Context7, or read the installed source. NEVER guess.
Cannot verify it? Write it in state/BLOCKERS.md. Do not invent it.

## 3-strike rule
Same failure 3x -> STOP. Write state/BLOCKERS.md. Ask the human. Do not thrash.

## Commands
make gate | make test | make lint | make db-sync | make usage
