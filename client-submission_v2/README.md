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
