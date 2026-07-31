# AwaazLabs-UVA-Voice SDK — Package Overview

> Delivered by **Finova Solutions** · Confidential Client Package

---

## What's in This Folder

This folder contains the two npm packages that power your AwaazLabs-UVA integration.

```
sdk/
├── @awaazlabs-uva/voice/          →  Browser SDK  (@awaazlabs-uva/voice)
│   ├── dist/            →  Compiled JS + TypeScript declaration files
│   ├── src/             →  TypeScript source (reference only)
│   ├── awaazlabs-uva-voice-1.0.0.tgz
│   ├── package.json
│   └── README.md
│
└── @awaazlabs-uva/agents/         →  Server-side Agent Management SDK  (@awaazlabs-uva/agents)
    ├── dist/            →  Compiled JS + TypeScript declaration files
    ├── src/             →  TypeScript source (reference only)
    ├── awaazlabs-uva-agents-0.1.0.tgz
    ├── package.json
    └── README.md
```

---

## The Two Packages at a Glance

### `@awaazlabs-uva/voice` — Browser SDK

| Property | Value |
|---|---|
| **Environment** | Browser only (React, Vue, vanilla JS, etc.) |
| **Purpose** | Opens a real-time WebRTC Urdu voice session with an AI agent |
| **Secrets held** | **None** — fully safe to ship in a public bundle |
| **Key dependency** | `livekit-client ^2.0.0` |

The browser SDK never talks to AwaazLabs-UVA upstream services with credentials. It calls
**your own backend's** session endpoint, which holds your secrets and mints the
LiveKit token on your behalf.

### `@awaazlabs-uva/agents` — Server-Side Agent Management SDK

| Property | Value |
|---|---|
| **Environment** | Node.js backend **only** |
| **Purpose** | Create, list, and update Urdu AI agents via the Tenant Portal API |
| **Secrets held** | `tenantSecret` (HMAC-SHA256 signing key) — **NEVER import in browser code** |
| **Key dependency** | Node.js built-ins (`crypto`) only |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      YOUR APPLICATION                       │
│                                                             │
│  ┌──────────────────────┐     ┌────────────────────────┐   │
│  │   Browser / Frontend │     │  Node.js Backend        │   │
│  │                      │     │                         │   │
│  │  @awaazlabs-uva/voice          │────▶│  Your /api/voice/session│   │
│  │  (zero secrets)      │     │  endpoint               │   │
│  │                      │     │                         │   │
│  │                      │     │  @awaazlabs-uva/agents            │   │
│  │                      │     │  (holds tenantSecret)   │   │
│  └──────────────────────┘     └────────────┬───────────┘   │
└───────────────────────────────────────────|────────────────┘
                                            │
                              ┌─────────────▼──────────────┐
                              │  AwaazLabs-UVA Services     │
                              │  (session issuance and      │
                              │   agent orchestration)      │
                              └────────────────────────────┘
```

**Security rule:** `tenantSecret` and `hmacSecret` never cross the browser boundary.
Your backend holds them; your browser only ever holds the `publishableKey`.

---

## Quick Reference: Which Package Do I Use Where?

| Task | Package | Environment |
|---|---|---|
| Start a voice call in the browser | `@awaazlabs-uva/voice` | Browser |
| Display live transcription | `@awaazlabs-uva/voice` | Browser |
| Create a new AI agent | `@awaazlabs-uva/agents` | Backend |
| List existing agents | `@awaazlabs-uva/agents` | Backend |
| Update agent prompt / voice | `@awaazlabs-uva/agents` | Backend |
| Sign session token requests | Your backend + HMAC secret | Backend |

---

## Version Compatibility

| SDK Package | Node.js | Browser Targets |
|---|---|---|
| `@awaazlabs-uva/voice` | N/A | ES2020+, all modern browsers |
| `@awaazlabs-uva/agents` | ≥ 18.0.0 | Not applicable |

---

> For full setup instructions, see the `docs/` folder.
> For the AI integration prompt, see `../docs/ai-integration-guide.md`.
> For credentials, see `../docs/credentials-template.md`.
