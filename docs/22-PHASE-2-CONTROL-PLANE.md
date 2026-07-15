# PHASE 2 — CONTROL PLANE (the token mint)
**Goal:** the whole security model. If this is right, a stolen client bundle is worthless.
**Read first:** 31-GUIDE-SECURITY.md
**Gate:** `pytest tests/test_mint.py -q`

## The only endpoint that matters
```
POST /v1/session
Headers: X-Tenant-Id, X-Timestamp, X-Nonce, X-Signature
Body:    {agent_id}
Sig:     HMAC-SHA256(tenant_secret, f"{tenant_id}.{ts}.{nonce}.{agent_id}")

1. verify HMAC              -> 401
2. |now-ts| <= 60s          -> 401  (replay window)
3. nonce unused             -> 401  (replay)
4. tenant active            -> 403
5. agent belongs to tenant  -> 403  🔴 IDOR guard
6. concurrent < max         -> 429
7. minutes < max            -> 429
8. mint JWT: room=uuid4, identity=uuid4, TTL=120s,
   grants={roomJoin, room:<that one>, canPublish, canSubscribe}
   metadata={tenant_id, agent_id}
9. create session row, increment quota_state
-> {token, wsUrl, roomName}
```

## Non-negotiable
- TTL **≤120s**. Not 1h. The token is for joining, not for the call's duration.
- **Never** `roomCreate`, `roomAdmin`, `roomList`. `roomJoin` on ONE named room only.
- Quota checked at **step 6-7 — BEFORE the token exists.** Never client-side.
- Origin allowlist per tenant.
- Rate limit per tenant per minute.

## Tasks
P2-T01 HMAC verify + replay window · P2-T02 nonce store · P2-T03 quota check
P2-T04 JWT mint (scoped) · P2-T05 session row + quota increment · P2-T06 origin allowlist + rate limit

## GATE 2 — `tests/test_mint.py` must prove ALL of these fail
```
[ ] replayed nonce            -> 401
[ ] ts 61s old                -> 401
[ ] wrong signature           -> 401
[ ] agent_id of another tenant-> 403   (IDOR)
[ ] suspended tenant          -> 403
[ ] over concurrent cap       -> 429
[ ] over monthly minutes      -> 429
[ ] wrong Origin              -> 403
[ ] 🔴 minted token CANNOT join a different room  <- the whole ballgame
[ ] 🔴 minted token expires at 120s
```
**HUMAN GATE:** try to widen a token yourself. Must fail.
