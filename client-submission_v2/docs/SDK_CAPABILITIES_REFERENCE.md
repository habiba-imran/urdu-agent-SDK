# SDK Capabilities Reference

This document lists the client-facing capabilities exposed by the SDK packages included in `client-submission_v2/sdk`.

Use it as the quickest "what do we actually get?" reference during implementation planning.

## 1. Package Boundaries

| Package | Runtime | Main responsibility |
| --- | --- | --- |
| `@awaazlabs-uva/voice` | Browser only | Starts and manages LiveKit/WebRTC browser voice sessions. |
| `@awaazlabs-uva/agents` | Backend only | Creates, lists, updates agents, reads provider capabilities, and exposes helper methods for number assignment. |
| `@awaazlabs-uva/telephony` | Backend only | Manages Telnyx connection, number inventory, assignment, SIP/routing, outbound readiness, and outbound calls. |

## 2. `@awaazlabs-uva/voice`

### Constructor

```ts
new AwaazLabsUvaVoice({
  publishableKey,
  sessionEndpoint,
  refreshEndpoint?,
})
```

### Browser session methods

```ts
voice.connect({ agentId, voiceId? })
voice.disconnect()
voice.startAudio()
voice.on(eventName, callback)
voice.off(eventName, callback)
```

### Static helper

```ts
AwaazLabsUvaVoice.listVoices(endpointUrl)
```

### Events

- `connected`
- `disconnected`
- `ended`
- `error`
- `transcript`
- `speaking`
- `agent_speaking`
- `metrics_updated`
- `audio_blocked`

### Important note

The frontend voice SDK depends on your backend session endpoint for the actual session payload. `agentId` is required. `voiceId` should be treated as an optional compatibility field in the browser API, but your backend session flow remains the source of truth for which agent/session configuration is used.

## 3. `@awaazlabs-uva/agents`

### Constructor

```ts
new AwaazLabsUvaAgentsClient({
  baseUrl,
  tenantId,
  tenantSecret,
  extraHeaders?,
})
```

### Agent methods

```ts
client.createAgent({
  name,
  prompt,
  voiceId,
  llmModel?,
  agentLanguage?,
  sttProvider?,
  sttModel?,
  sttOptions?,
  llmProvider?,
  llmOptions?,
  ttsProvider?,
  ttsVoiceId?,
  ttsOptions?,
  greeting?,
  firstSpeaker?,
})

client.listAgents()

client.updateAgent(agentId, {
  name?,
  prompt?,
  voiceId?,
  llmModel?,
  agentLanguage?,
  sttProvider?,
  sttModel?,
  sttOptions?,
  llmProvider?,
  llmOptions?,
  ttsProvider?,
  ttsVoiceId?,
  ttsOptions?,
  greeting?,
  firstSpeaker?,
})
```

### Provider discovery

```ts
client.getProviderCapabilities()
```

This returns the currently enabled provider/language/model/voice combinations and should be used to build provider pickers instead of hardcoding options.

### Greeting and first speaker

These live on the agent record. The browser voice SDK does not take them on `connect()`.

- `greeting` — exact opening line when the agent speaks first. Omit for a generated greeting. On update, `greeting: ''` clears it.
- `firstSpeaker` — `'agent'` (default, greets immediately) or `'user'` (wait for the caller).

### English TTS (Cartesia / Rime)

Set `agentLanguage: 'en'` and `ttsProvider: 'cartesia' | 'rime'`, with `ttsVoiceId` from `getProviderCapabilities()`. Humanized spoken output is applied by the hosted worker. Do not put SSML or `spell()` in `prompt` or `greeting`. Switching providers is an `updateAgent` of `ttsProvider` + `ttsVoiceId`.

### Number-assignment helper methods

These methods are exposed by the agents package for convenience, even though they target telephony-managed numbers:

```ts
client.listManagedNumbers({ assignedAgentId? })
client.assignAgentToNumber(numberId, agentId)
client.unassignAgentFromNumber(numberId)
```

## 4. `@awaazlabs-uva/telephony`

### Constructor

```ts
new TelephonyClient({
  baseUrl,
  tenantId,
  tenantSecret,
  extraHeaders?,
  fetch?,
  nowSeconds?,
  nonceFactory?,
})
```

### Telnyx connection lifecycle

```ts
client.connectTelnyxAccount({ apiKey, label? })
client.rotateTelnyxAccountKey({ apiKey })
client.reverifyTelnyxAccount()
client.disconnectTelnyxAccount()
client.getConnectionStatus()
```

### Number inventory and discovery

```ts
client.listTelnyxOwnedNumbers({ cursor?, limit?, platformStatus?, providerStatus? })
client.listManagedPhoneNumbers({ cursor?, limit?, platformStatus?, providerStatus? })
client.getManagedPhoneNumber(numberId)
client.importTelnyxNumber({ e164Number, externalCustomerRef? })
client.syncTelnyxOwnedNumbers()
client.getTelnyxNumberDrift()
client.searchAvailableNumbers({
  country,
  areaCode?,
  numberType?,
  features?,
  exactPhoneNumber?,
  limit?,
})
```

### Reservation and purchase

```ts
client.reserveNumber({ e164Number, idempotencyKey })
client.purchaseNumber({ e164Number, externalCustomerRef?, idempotencyKey })
client.getNumberOrderStatus(orderId)
```

Important:

- `purchaseNumber()` is the main acquisition flow for live buying.
- `searchAvailableNumbers()` can return `upfront_cost`, `monthly_cost`, and `currency`.
- `reserveNumber()` is present in the SDK contract, but whether it is part of your production flow depends on your hosted backend behavior and product policy.
- Always use a unique idempotency key for each intended purchase action.

### Number assignment and number state

```ts
client.assignAgentToNumber(numberId, agentId)
client.unassignAgentFromNumber(numberId)
client.disableNumber(numberId)
```

### SIP and outbound profile

```ts
client.upsertTelnyxSipConnection({
  sipFqdn?,
  sipUsername?,
  sipSecret?,
  providerSipConnectionId?,
})
client.verifyTelnyxSipConnection()

client.upsertTelnyxOutboundVoiceProfile({
  providerOutboundVoiceProfileId?,
  telnyxSipConnectionId?,
  allowedDestinations?,
  concurrencyLimit?,
  channelLimit?,
  dailySpendingLimit?,
})
client.verifyTelnyxOutboundVoiceProfile()
```

### Routing and trunk configuration

```ts
client.configureNumberRouting(numberId)
client.configureOutboundTrunk()
client.getOutboundReadiness()
```

### Outbound calling and call records

```ts
client.createOutboundCall({
  agentId,
  fromNumberId,
  toNumber,
  recipient?,
  context?,
  externalCustomerRef?,
  externalWorkflowRef?,
  idempotencyKey,
})

client.getCallStatus(telephonyCallId)
client.listCallRecords({ cursor?, limit?, platformStatus?, providerStatus? })
```

## 5. Recommended End-To-End Telephony Sequence

For a real tenant using Telnyx:

1. Connect Telnyx with `connectTelnyxAccount({ apiKey })`.
2. Sync owned numbers or search/purchase/import the intended number.
3. Create or select the target agent.
4. Assign the number to the agent.
5. Configure SIP and verify it when required by your hosted deployment.
6. Configure outbound voice profile and verify it when required.
7. Configure number routing.
8. Configure the outbound trunk.
9. Call `getOutboundReadiness()` before enabling live outbound calls.
10. Create one outbound call per explicit user-approved action using a unique idempotency key.

## 6. Security Summary

- Never import `@awaazlabs-uva/agents` or `@awaazlabs-uva/telephony` in browser code.
- Never expose `UVA_HMAC_SECRET`, Telnyx API keys, SIP secrets, or provider credentials to the browser.
- Keep purchase, disable, and outbound-call actions approval-gated in your product flow.
- Treat backend logs and analytics as secret-sensitive surfaces.
