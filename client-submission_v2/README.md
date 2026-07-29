# AwaazLabs-UVA-Voice SDK - Client Submission Package

Delivered by Finova Solutions. Confidential client onboarding package.

## Package Contents

```text
client-submission_v2/
  README.md
  .gitignore
  docs/
    INTEGRATION_GUIDE.md
    ai-integration-guide.md
    credentials-template.md
  sdk/
    README.md
    @awaazlabs-uva/
      voice/
        awaazlabs-uva-voice-1.0.0.tgz
        package.json
        README.md
        dist/
        src/
      agents/
        awaazlabs-uva-agents-0.1.0.tgz
        package.json
        README.md
        dist/
        src/
```

This handoff intentionally does not include a test frontend or sample backend. The client should
integrate the SDK packages into their own application and follow the docs in `docs/`.

## Where To Start

| Goal | File |
|---|---|
| Give a coding agent one complete prompt | `docs/ai-integration-guide.md` |
| Read the full engineering integration guide | `docs/INTEGRATION_GUIDE.md` |
| Understand required credentials and where they belong | `docs/credentials-template.md` |
| Understand the package split | `sdk/README.md` |

## Install Summary

Frontend project:

```bash
npm install /path/to/client-submission_v2/sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz livekit-client@^2.0.0
```

Backend project:

```bash
npm install /path/to/client-submission_v2/sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz
```

Never install `@awaazlabs-uva/agents` in a browser or frontend package. It is a backend-only SDK
that uses the tenant HMAC secret.

## Runtime Boundary

- Browser: uses `@awaazlabs-uva/voice`, holds only `VITE_UVA_PUBLISHABLE_KEY`, and calls the
  client's own backend session routes.
- Backend: uses `@awaazlabs-uva/agents`, holds `UVA_TENANT_ID`, `UVA_HMAC_SECRET`,
  `UVA_PORTAL_API_URL`, and the backend-only session upstream configuration.
- AwaazLabs-UVA services: are reached only by the backend or by LiveKit after the backend has
  minted a short-lived session token.

## Security Notice

Do not publish this package. Do not commit filled `.env` files. Do not place `UVA_HMAC_SECRET`,
`UVA_TENANT_ID`, portal URLs, or backend-only upstream URLs in a frontend bundle.

Before client deployment, complete the security checklist in `docs/INTEGRATION_GUIDE.md`.
