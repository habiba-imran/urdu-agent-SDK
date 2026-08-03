# AwaazLabs UVA Client Handover

This folder contains the client-facing SDK handover for integrating browser voice sessions, backend agent management, and backend telephony management.

## Folder structure

```text
client-submission_v2/
  README.md
  docs/
    INTEGRATION_GUIDE.md
    credentials-template.md
    ai-integration-guide.md
  sdk/
    README.md
    @awaazlabs-uva/
      voice/
        awaazlabs-uva-voice-1.0.0.tgz
      agents/
        awaazlabs-uva-agents-0.1.0.tgz
      telephony/
        awaazlabs-uva-telephony-0.1.0.tgz
```

## Packages

| Package | Runtime | Purpose |
| --- | --- | --- |
| `@awaazlabs-uva/voice` | Browser only | Starts LiveKit/WebRTC voice sessions from your frontend. It uses a publishable key and never receives backend secrets. |
| `@awaazlabs-uva/agents` | Backend only | Creates, lists, and updates voice agents through signed machine API calls. |
| `@awaazlabs-uva/telephony` | Backend only | Connects Telnyx, syncs numbers, assigns numbers to agents, configures routing, checks readiness, and starts outbound calls through signed machine API calls. |

## Recommended integration order

1. Install the backend packages in your server application: `@awaazlabs-uva/agents` and `@awaazlabs-uva/telephony`.
2. Store `UVA_TENANT_ID`, `UVA_HMAC_SECRET`, and the API base URLs only in backend environment variables.
3. Use `@awaazlabs-uva/agents` to create or select the agent IDs your application will expose to the browser.
4. Add backend session endpoints that issue short-lived voice session payloads for `@awaazlabs-uva/voice`.
5. Install `@awaazlabs-uva/voice` in the frontend and connect using only `publishableKey`, `sessionEndpoint`, and `agentId`.
6. Use `@awaazlabs-uva/telephony` from the backend to connect Telnyx, sync/import numbers, assign a number to an agent, configure SIP/routing resources, and check outbound readiness.
7. Enable inbound and outbound phone workflows only after provider credentials, phone number ownership, routing, and readiness checks are complete.

## Install from the handover tarballs

Run these commands from your application package, adjusting the relative path to this handover folder:

```bash
npm install ./client-submission_v2/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz
npm install ./client-submission_v2/sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz
npm install ./client-submission_v2/sdk/@awaazlabs-uva/telephony/awaazlabs-uva-telephony-0.1.0.tgz
```

The voice package has a runtime dependency on `livekit-client`; npm installs it automatically when installing the tarball.

## Start here

Read `docs/INTEGRATION_GUIDE.md` for the full implementation flow. Use `docs/credentials-template.md` to prepare backend and frontend environment variables before writing application code.

If you are integrating telephony, also read `docs/TELNYX_SETUP_AND_PLATFORM_CONSTRAINTS.md` before building purchase, number-assignment, inbound, or outbound call flows. That note explains the tenant-scoped uniqueness rules, idempotency expectations, backend-only Telnyx key handling, and outbound-readiness constraints that affect production behavior.
