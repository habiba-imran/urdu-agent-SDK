# @uva/client — Urdu Voice Agent client SDK (Phase 4 SCAFFOLD)

⚠️ **Scaffold only.** Only the public TYPE surface + exact event/error names (per
`docs/24-PHASE-4-CLIENT-SDK.md`) are defined in `src/index.ts`. Every method throws
"not implemented — Phase 4". The real transport/session wiring (livekit-client) is Phase-4 work and
must NOT be built until Phase 3's Gate-3 confirms the session/token contract.

Design invariants (docs/24):
- **Zero secrets in the bundle.** `publishableKey` identifies, never authorises.
- The SDK talks only to the HOST platform's own `sessionEndpoint` (their server holds their HMAC
  secret and calls our mint), then to LiveKit. Never directly to Uplift/Gladia/Gemini/Supabase.
- Gate (`make bundle-check`): `dist/` must contain no `API_KEY|SECRET|SERVICE_ROLE|Bearer`, and no
  provider SDK in the dep tree.

TODO at Phase 4 (not done):
- Verify + pin `livekit-client` version (Phase 7 wants exact pins; `^2.0.0` here is a scaffold guess).
- `npm install`, implement P4-T01..T05, then `make bundle-check`.
