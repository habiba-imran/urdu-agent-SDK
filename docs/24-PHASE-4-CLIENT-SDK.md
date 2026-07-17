# PHASE 4 — CLIENT SDK
**Goal:** ships into someone else's app. Assume it is fully decompiled on day one.
**Gate:** `make bundle-check`

## API
```ts
const uva = new UrduVoiceAgent({ publishableKey, sessionEndpoint }); // host's OWN server
await uva.connect({ agentId });  // host server does the HMAC; we never see their secret
uva.on('transcript'|'speaking'|'error'|'ended', cb);
await uva.disconnect();
```

## Rules
🔴 **Zero secrets.** No API key, no HMAC secret, no LiveKit secret. The publishable key identifies, never authorises.
🔴 The SDK **never** calls Uplift/Gladia/Gemini/Supabase directly. Only: host's session endpoint → LiveKit.
🔴 `sessionEndpoint` is the HOST's server. Their server holds their HMAC secret. Ours never leaves us.

## Tasks
P4-T01 transport wrapper (livekit-client) · P4-T02 session lifecycle · P4-T03 typed events
P4-T04 error taxonomy (quota_exceeded, agent_not_found, session_failed — **never leak internals**)
P4-T05 build + bundle scan

## GATE 4 — machine-checkable lines closed 2026-07-17; HUMAN GATE still open, not skipped

```
[x] npm run build
```
`make bundle-check` → `tsc` compiles clean, **EXIT=0**. `src/index.ts` implements the real
transport/session wiring (P4-T01/T02), not the earlier stub — `connect()` POSTs
`options.sessionEndpoint`, connects via `livekit-client`'s `Room`, and enables the caller's
microphone (`localParticipant.setMicrophoneEnabled(true)` — a voice agent that can't hear the
caller isn't a working session, so this was added beyond the literal API sketch in this doc, on
that reasoning, not guessed).

```
[x] grep -rE '(API_KEY|SECRET|SERVICE_ROLE|Bearer )' dist/  -> ZERO
```
Run literally, 2026-07-17: **zero matches** (`grep` exit code 1 = no match). Full command +
output pasted to the human alongside this gate.

```
[~] works from an origin that is not ours   — verified by code inspection, not a live cross-origin run
```
The SDK makes no same-origin assumption anywhere: `sessionEndpoint` and the LiveKit `wsUrl` are
both fully-qualified URLs supplied at runtime (session response), the `fetch()` call sends no
cookies/credentials, and nothing reads `window.location`. CORS for `sessionEndpoint` is entirely
the HOST's own server's responsibility (outside this SDK's control by design). Not exercised as an
actual two-origin live test — that would need a real host server running, out of scope for this
pass. Flagged as inspected, not empirically run, same honesty standard as GATE 3's soniox line.

```
[x] bundle size recorded in ADR
```
`dist/index.js` (our own code only — `livekit-client` stays an external import, resolved by the
host app's own bundler, same as most npm libraries): **5765 bytes raw / 2162 bytes gzipped**.
`dist/index.d.ts`: 1485 bytes. Full record: `docs/40-ADR.md` ADR-015.

```
[x] no provider SDK in the dep tree (npm ls | grep -iE 'uplift|gladia|supabase' -> zero)
```
`npm ls` → only `livekit-client@2.20.1` and `typescript@5.9.3` (dev). Provider-name grep: zero
matches (exit code 1).

**HUMAN GATE — NOT satisfied by any of the above, per this doc's own line: "you personally grep
`dist/`."** The automated grep above is real, literal, and passed — but it does not substitute for
the human doing this themselves. Flagged clearly, not silently treated as done because the machine
check passed.
