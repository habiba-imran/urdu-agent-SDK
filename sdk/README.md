# @uva/client — Urdu Voice Agent client SDK

Implemented 2026-07-17, after Phase-3 Gate-3 confirmed the session/token contract
(`{token, wsUrl, roomName}` from `control_plane.mint.mint_session`). `src/index.ts` is real, not a
stub — `connect()`/`on()`/`disconnect()` all work against a live LiveKit room.

Design invariants (docs/24-PHASE-4-CLIENT-SDK.md):
- **Zero secrets in the bundle.** `publishableKey` identifies, never authorises. Confirmed:
  `grep -rE '(API_KEY|SECRET|SERVICE_ROLE|Bearer )' dist/` → zero matches.
- The SDK talks only to the HOST platform's own `sessionEndpoint` (their server holds their HMAC
  secret and calls our mint), then to LiveKit via `livekit-client`. Never directly to
  Uplift/Gladia/Gemini/Supabase. Confirmed: `npm ls` → only `livekit-client` + `typescript` (dev),
  no provider SDK in the dep tree.
- `sessionEndpoint` contract: this SDK POSTs `{publishableKey, agentId}` and expects
  `{token, wsUrl, roomName}` on success (the host's server is expected to relay our control plane's
  `POST /v1/session` response verbatim); non-2xx maps to the public `UvaErrorCode` taxonomy
  (`429` → `quota_exceeded`, `404` → `agent_not_found`, anything else → `session_failed`) — raw
  server/network error text is never attached to the thrown `UvaError`.

Build: `npm run build` (`tsc`, unbundled ESM — `livekit-client` stays an external import, resolved
by the HOST app's own bundler when they `npm install @uva/client`, same as most npm libraries).
`dist/index.js` is ~4.8KB raw / ~1.8KB gzipped for our own code; `livekit-client` itself is a much
larger transitive dependency the host's bundler pulls in separately — see `docs/40-ADR.md` for the
full Gate-4 record.
