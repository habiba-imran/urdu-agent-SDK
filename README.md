# Urdu Voice-Agent-as-a-Service (VaaS) Platform
## Enterprise Production Infrastructure & Browser SDK

[![CI Pipeline](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/actions/workflows/ci.yml/badge.svg)](https://github.com/Finova-Solutions/urdu-voice-agent-SDK/actions/workflows/ci.yml)
[![npm version](https://img.shields.io/npm/v/@awaazlabs-uva/voice.svg)](https://www.npmjs.com/package/@awaazlabs-uva/voice)

An enterprise-grade, multi-tenant Voice-Agent-as-a-Service (VaaS) platform built specifically for low-latency Urdu voice interaction. Powered by LiveKit WebRTC, Gladia STT, Gemini LLM, and Uplift TTS.

---

## 🏛️ System Architecture

The platform follows an **SDK-First, Explicit Dispatch** multi-tenant architecture:

```text
[ Browser Client ] ──(@awaazlabs-uva/voice SDK)──> [ Host Platform Backend ]
                                                 │ (HMAC Signature)
                                                 ▼
[ LiveKit WebRTC ] <──(Session JWT)─── [ Control Plane Minter ]
       │                                         │ (Explicit Dispatch)
       ▼                                         ▼
[ LiveKit Voice Worker ] <───────────────────────┘
  (Gladia + Gemini + Uplift)
```

| Component | Directory | Description |
|---|---|---|
| **Control Plane** | `control_plane/` | FastAPI server for HMAC validation, quota enforcement, and LiveKit session token minting. |
| **Voice Worker** | `worker/` | LiveKit agent process running Silero VAD → Gladia STT → Gemini LLM → Uplift TTS. |
| **Client SDK** | `sdk/` | `@awaazlabs-uva/voice` npm package — zero-secret WebRTC browser client wrapper. |
| **Server SDK** | `sdk-server/` | `@awaazlabs-uva/agents` npm package — server-side agent management, holds the tenant HMAC secret. |
| **Telephony SDK** | `telephony/` | `@awaazlabs-uva/telephony` npm package — backend-only Telnyx connection, numbers, routing, and PSTN calls. |
| **Demo App** | `demo-app/` | Reference Express host backend (signs HMAC session requests) + Vite browser client. |
| **Tenant Dashboard** | `dashboard/` | Next.js self-service portal for managing agents, voices, and credentials. |
| **Super-Admin Portal** | `admin/` | Separate administrative backend for TOTP auth, audit logging, and usage metrics. |

---

## 📚 Documentation Index

- **[Control Plane API Reference](docs/api-reference.md)** — Complete OpenAPI specification for Control Plane endpoints.
- **[Host Backend Integration Spec](docs/HOST_BACKEND_CONTRACT.md)** — HMAC signature formula and backend integration contract.
- **[Client Quickstart Guide](docs/CLIENT_QUICKSTART.md)** — Step-by-step guide for integrating `@awaazlabs-uva/voice` into web applications.
- **[SDK Documentation](sdk/README.md)** — NPM package installation and API reference.
- **[Server SDK Documentation](sdk-server/README.md)** — `@awaazlabs-uva/agents` installation and API reference.

---

## ⚡ Local Quickstart

### Prerequisites
- Python 3.12+
- Node.js 20+
- LiveKit Cloud account (or local LiveKit server)
- PostgreSQL / Supabase instance

### 1. Set Up Environment
```bash
cp .env.example .env.local
# Fill in your LIVEKIT_*, SUPABASE_DB_URL, and provider API keys in .env.local
```

### 2. Build the Database Schema

`scripts/migrate.py` is the forward-only runner: it records what it applies in a
`schema_migrations` table, runs each file in its own transaction, and never drops anything.

```bash
make db-migrate-status   # what is applied, what is pending
make db-migrate          # apply pending migrations
```

For a **brand new, empty** database, add `--allow-initial` once so `0001_schema.sql` runs
(it drops every table before creating them, which is why the runner skips it by default):

```bash
python scripts/migrate.py --allow-initial
```

For an **existing** database that was built by hand, record the current files as applied
before using the runner normally:

```bash
python scripts/migrate.py --baseline
```

`make db-reset` still exists for local development only — it **drops and recreates every
table, destroying all rows**. Never point it at a database you care about.

### 3. Start Control Plane (Port 8000)
```bash
uvicorn control_plane.app:app --reload --port 8000
```
Interactive docs: `http://localhost:8000/docs`

### 4. Start Admin Portal (Port 8001)
```bash
uvicorn admin.app:app --reload --port 8001
```

### 5. Start Voice Worker
```bash
python -m worker.main dev
```

### 6. Test with the Demo App
```bash
cd demo-app
npm run build:sdk
npm run install:all
npm run dev:backend    # terminal 1 — host backend on http://localhost:3000
npm run dev:frontend   # terminal 2 — browser client on http://localhost:5173
```
Copy `backend/.env.example` and `frontend/.env.example` to `.env` first — see [demo-app/README.md](demo-app/README.md).

---

## 🧪 Testing & Verification

Run unit tests and verification checks:

```bash
# Python test suite
python -m pytest tests/ -v

# Browser SDK (@awaazlabs-uva/voice): build, type-check, unit tests
cd sdk && npm ci && npm run build && npm run lint && npm test

# Server SDK (@awaazlabs-uva/agents): build, type-check, unit tests
cd sdk-server && npm ci && npm run lint && npm test

# Telephony SDK (@awaazlabs-uva/telephony): build, type-check, contract tests
cd telephony && npm ci && npm run lint && npm test
```

---

## 🔐 Security & Trust Boundaries

1. **Zero Client Secrets**: The browser SDK `@awaazlabs-uva/voice` holds **zero** provider or tenant secrets.
2. **HMAC Signing**: Host backends hold the tenant's raw HMAC secret and sign every mint request with a 60-second replay window.
3. **Tenant Prompt Isolation**: Tenant prompts are treated as untrusted data and placed in a separate `chat_ctx` system message framing, never interpolated into system operating rules.
