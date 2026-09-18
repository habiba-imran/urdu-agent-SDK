# 03 — Error Handling

## Browser voice (`@awaazlabs-uva/voice`)

Errors are emitted on the `error` event as `AwaazLabsUvaVoiceError` with a stable `code`:

```ts
voice.on('error', (error) => {
  switch (error.code) {
    case 'rate_limit':
      // back off and retry
      break;
    case 'quota_exceeded':
      // plan concurrency or monthly minutes
      break;
    case 'audio_blocked':
      // use the audio_blocked event + startAudio() from a click
      break;
    default:
      console.error(error.code, error.message);
  }
});
```

| Code | Meaning | What to do |
|------|---------|------------|
| `quota_exceeded` | Tenant plan cap (concurrency / monthly minutes), or opaque `429` | Show plan/limit UI; do not hammer connect |
| `rate_limit` | Platform rate limit | Exponential backoff, then retry |
| `provider_limit` | Upstream LLM/TTS/STT provider limit | Retry later; distinct from your plan quota |
| `worker_not_ready` | Voice worker not ready | Retry shortly |
| `agent_not_found` | Bad `agentId` / wrong tenant / deleted agent | Fix agent id |
| `timeout` | Host backend slower than `fetchTimeoutMs` (default 15s) | Check your session route / upstream |
| `token_refresh_failed` | Refresh rejected or retries exhausted | Reconnect session |
| `session_failed` | Other session mint/connect failure | Check host backend + upstream config |

The SDK does not expose raw infra stack traces as part of the public contract.

### Browser autoplay

If `audio_blocked` fires with `true`, show a user gesture button and call `voice.startAudio()`.

---

## Agents (`@awaazlabs-uva/agents`)

Failures throw `AwaazLabsUvaAgentsError` with `status`, `message`, and sometimes a stable `code` (mainly HTTP 422 validation):

| `code` (when present) | Meaning |
|-----------------------|---------|
| `unsupported_provider_for_language` | Provider not valid for that language |
| `provider_not_enabled` | Provider not enabled for tenant |
| `unsupported_model_for_provider` | Bad model for provider |
| `unsupported_voice_for_provider` | Bad voice id |
| `invalid_greeting` | Greeting validation failed |
| `invalid_first_speaker` | `firstSpeaker` invalid |

Auth / suspended tenant / missing agent / rate limits may leave `code` undefined — use `status` + `message`.

---

## Telephony (`@awaazlabs-uva/telephony`)

Failures throw `AwaazLabsUvaTelephonyError` with `status`, `code`, `message`.

Handle connect/sync/purchase/outbound failures by:

1. Logging `status` + `code` + `message` (never the Telnyx API key)  
2. Surfacing `getOutboundReadiness().reasons` when outbound is blocked  
3. Using idempotency keys for purchase/outbound — do not invent a new key after an ambiguous timeout without checking call/order status  

---

## Common mistakes → symptoms

| Symptom | Likely cause |
|---------|--------------|
| Immediate `session_failed` | Host misconfigured; bad upstream; wrong HMAC |
| `agent_not_found` | Wrong agent id or tenant |
| `timeout` | Host hung or upstream slow |
| No agent audio | Autoplay blocked — handle `audio_blocked` |
| 401/403 from agents/telephony | Wrong HMAC / tenant id / clock skew |
| Telnyx connect fails | Invalid Telnyx key, unpaid account, or permissions |
| Outbound not ready | SIP/routing/trunk/number assignment incomplete |
