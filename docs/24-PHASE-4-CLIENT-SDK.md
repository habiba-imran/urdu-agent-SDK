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

## GATE 4
```
[ ] npm run build
[ ] grep -rE '(API_KEY|SECRET|SERVICE_ROLE|Bearer )' dist/  -> ZERO
[ ] works from an origin that is not ours
[ ] bundle size recorded in ADR
[ ] no provider SDK in the dep tree (npm ls | grep -iE 'uplift|gladia|supabase' -> zero)
```
**HUMAN GATE:** you personally grep `dist/`.
