# AwaazLabs-UVA SDK Packages

This folder contains two private npm package tarballs. Install them from the included `.tgz` files;
they are not public npm registry packages.

```text
sdk/
  @awaazlabs-uva/
    voice/
      awaazlabs-uva-voice-1.0.0.tgz
      dist/
      src/
      package.json
      README.md
    agents/
      awaazlabs-uva-agents-0.1.0.tgz
      dist/
      src/
      package.json
      README.md
```

## Package Split

| Package | Install In | Purpose | Secrets |
|---|---|---|---|
| `@awaazlabs-uva/voice` | Frontend/browser | Opens LiveKit voice sessions and emits transcripts/events | None |
| `@awaazlabs-uva/agents` | Backend only | Creates, lists, and updates agents through the tenant portal API | Uses `UVA_HMAC_SECRET` at runtime |

## Architecture

```text
Browser app
  -> @awaazlabs-uva/voice
  -> client's backend /api/voice/session
  -> backend-only session upstream
  -> LiveKit room
  -> AwaazLabs-UVA worker/agent

Client backend
  -> @awaazlabs-uva/agents
  -> AwaazLabs-UVA tenant portal API
```

The browser never calls private AwaazLabs-UVA infrastructure directly and never receives tenant
secrets. The backend owns all HMAC signing and session-upstream configuration.

## Version Compatibility

| Package | Runtime |
|---|---|
| `@awaazlabs-uva/voice` | Modern browser, ES2020+, `livekit-client@^2.0.0` |
| `@awaazlabs-uva/agents` | Node.js 18+ backend, ESM |

## More Detail

- Full integration guide: `../docs/INTEGRATION_GUIDE.md`
- Coding-agent prompt: `../docs/ai-integration-guide.md`
- Credential template: `../docs/credentials-template.md`
