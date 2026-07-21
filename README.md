# Urdu Voice-Agent-as-a-Service (VaaS) Platform
## Enterprise Production Infrastructure & Browser SDK

[![CI Pipeline](https://github.com/habiba-imran/urdu-agent-SDK/actions/workflows/ci.yml/badge.svg)](https://github.com/habiba-imran/urdu-agent-SDK/actions/workflows/ci.yml)
[![npm version](https://img.shields.io/npm/v/@uva/voice.svg)](https://www.npmjs.com/package/@uva/voice)

An enterprise-grade, multi-tenant Voice-Agent-as-a-Service (VaaS) platform built specifically for low-latency Urdu voice interaction. Powered by LiveKit WebRTC, Gladia STT, Gemini LLM, and Uplift TTS.

---

## 🏛️ System Architecture

The platform follows an **SDK-First, Explicit Dispatch** multi-tenant architecture:

```text
[ Browser Client ] ──(@uva/voice SDK)──> [ Host Platform Backend ]
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
| **Client SDK** | `sdk/` | `@uva/voice` npm package — zero-secret WebRTC browser client wrapper. |
| **Host Backend Starter** | `examples/host-backend-node/` | Reference Node.js/Express server that signs HMAC requests to the Control Plane. |
| **Tenant Dashboard** | `dashboard/` | Next.js self-service portal for managing agents, voices, and credentials. |
| **Super-Admin Portal** | `admin/` | Separate administrative backend for TOTP auth, audit logging, and usage metrics. |

---

## 📚 Documentation Index

- **[Control Plane API Reference](docs/api-reference.md)** — Complete OpenAPI specification for Control Plane endpoints.
- **[Host Backend Integration Spec](docs/HOST_BACKEND_CONTRACT.md)** — HMAC signature formula and backend integration contract.
- **[Client Quickstart Guide](docs/CLIENT_QUICKSTART.md)** — Step-by-step guide for integrating `@uva/voice` into web applications.
- **[SDK Documentation](sdk/README.md)** — NPM package installation and API reference.
- **[VaaS Master Plan V2](VAAS_GODTIER_MASTER_PLAN_V2.md)** — Architectural master plan and repository blueprint.
- **[Dual-Track Collaboration Guide](VAAS_COLLABORATION_GUIDE.md)** — Developer workflow and GitHub branching timeline.

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

### 2. Run Database Migrations
```bash
python scripts/reconcile_sessions.py --dry-run
```

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

### 6. Test with Example Web Client
```bash
cd examples/basic-web-client
npm install
npm run dev
```

---

## 🧪 Testing & Verification

Run unit tests and verification checks:

```bash
# Python test suite
python -m pytest tests/ -v

# SDK package build & lint
cd sdk && npm run build && npm run lint

# Host backend starter test runner
cd examples/host-backend-node && npm test
```

---

## 🔐 Security & Trust Boundaries

1. **Zero Client Secrets**: The browser SDK `@uva/voice` holds **zero** provider or tenant secrets.
2. **HMAC Signing**: Host backends hold the tenant's raw HMAC secret and sign every mint request with a 60-second replay window.
3. **Tenant Prompt Isolation**: Tenant prompts are treated as untrusted data and placed in a separate `chat_ctx` system message framing, never interpolated into system operating rules.
