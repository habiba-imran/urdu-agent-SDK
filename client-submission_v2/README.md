<<<<<<< HEAD
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
=======
# AwaazLabs-UVA-Voice SDK — Client Submission Package

> Delivered by **Finova Solutions** · Confidential
> Recipient: [Client Name]

---

## Package Contents

```
client-submission/
│
├── sdk/                          ← Install these packages into your application
│   ├── README.md                 ← SDK architecture overview
│   ├── @awaazlabs-uva/voice/               ← @awaazlabs-uva/voice  (browser SDK, zero secrets)
│   │   ├── dist/                 ← Compiled JS + type declarations (ready to use)
│   │   ├── src/                  ← TypeScript source (reference)
│   │   ├── awaazlabs-uva-voice-1.0.0.tgz
│   │   └── package.json
│   └── @awaazlabs-uva/agents/              ← @awaazlabs-uva/agents (server SDK, holds your HMAC secret)
│       ├── dist/                 ← Compiled JS + type declarations (ready to use)
│       ├── src/                  ← TypeScript source (reference)
│       ├── awaazlabs-uva-agents-0.1.0.tgz
│       └── package.json
│
└── docs/
    ├── INTEGRATION_GUIDE.md      ← Complete setup & integration documentation
    ├── ai-integration-guide.md   ← Copy-paste prompt for AI coding assistants
    └── credentials-template.md   ← Credential placeholders (filled by Finova)
```

---

## Where to Start

| I want to… | Go to… |
|---|---|
| Understand the SDK architecture | [`sdk/README.md`](sdk/README.md) |
| Follow the full step-by-step integration guide | [`docs/INTEGRATION_GUIDE.md`](docs/INTEGRATION_GUIDE.md) |
| Let my AI assistant write the integration code | [`docs/ai-integration-guide.md`](docs/ai-integration-guide.md) |
| See what credentials I need and how they connect to code | [`docs/credentials-template.md`](docs/credentials-template.md) |

---

## Quick Install Reference

### Browser SDK — install into your **frontend** project

```bash
npm install ./sdk/@awaazlabs-uva/voice/awaazlabs-uva-voice-1.0.0.tgz livekit-client@^2.0.0
```

### Server SDK — install into your **backend** project only

```bash
npm install ./sdk/@awaazlabs-uva/agents/awaazlabs-uva-agents-0.1.0.tgz
```

> ⚠️ **Never install `@awaazlabs-uva/agents` in a frontend project.** It holds your tenant secret.

---

## Security Notice

**Do not share this package publicly.** It contains structural documentation of a private API.
Your Finova-issued credentials, when added to your `.env` files, must be treated as secrets:

- Never commit `.env` files to version control
- Never include `UVA_HMAC_SECRET` in any frontend bundle
- Refer to the Security Checklist in `docs/INTEGRATION_GUIDE.md` before deploying to production

---

*Questions? Contact your Finova Solutions account manager.*
>>>>>>> origin/ukasha
