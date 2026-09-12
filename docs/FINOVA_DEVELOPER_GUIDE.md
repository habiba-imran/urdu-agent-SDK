# Finova Solutions — AwaazLabs-UVA SDK Developer Guide

Welcome to the internal engineering guide for **Finova Solutions' AwaazLabs-UVA SDK Platform**.

This document explains the codebase architecture, folder structure, component responsibilities, and end-to-end logical flow for Finova developers and maintainers.

---

## 1. High-Level Architecture (B2B2C Model)

Finova Solutions operates a **multi-tenant B2B2C platform**:
- **Finova Solutions (Us):** Platform owner hosting cloud infrastructure, voice engines (STT/LLM/TTS), token minting, and database.
- **Finova Client (Tenant):** Businesses (e.g. `finova-client`) using our SDKs to offer AI Urdu voice agents to their customers.
- **End-User (Caller):** People visiting the client's web/mobile apps to talk to an Urdu voice agent over WebRTC.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Finova Client Platform                             │
│                                                                             │
│   ┌───────────────────────────┐     ┌───────────────────────────────────┐   │
│   │ Client Frontend (Browser) │     │     Client Backend (Node.js)      │   │
│   │  - Uses @awaazlabs-uva/voice (SDK)  │     │  - Uses @awaazlabs-uva/agents (SDK)         │   │
│   │  - Zero secrets           │     │  - Holds tenant_secret            │   │
│   └─────────────┬─────────────┘     └───────┬──────────────┬────────────┘   │
└─────────────────┼───────────────────────────┼──────────────┼────────────────┘
                  │ Connect WebRTC            │ Create Agent │ Mint Token
                  ▼                           ▼              ▼
       ┌─────────────────────┐       ┌───────────────────────────────────┐
       │ LiveKit WebRTC Cloud│       │    Finova Control Plane &         │
       └──────────┬──────────┘       │      Tenant Portal API            │
                  │ Audio Stream     └──────────────┬────────────────────┘
                  ▼                                 │ Reads DB
       ┌─────────────────────┐                      │
       │    Finova Worker    │◄─────────────────────┘
       │ (Gladia/Gemini/     │  Loads prompt & voice_id
       │  Uplift AI)         │  via room metadata agent_id
       └─────────────────────┘
```

---

## 2. Directory & Module Map ("What Does What")

| Directory / File | Description & Purpose | Logic Explanation |
| :--- | :--- | :--- |
| **`sdk/` (`@awaazlabs-uva/voice`)** | Browser Client SDK | **Browser-only.** Connects end-user browsers to LiveKit WebRTC audio rooms, streams mic input, renders assistant audio output, handles transcript/speaking events. Holds **ZERO secrets**. |
| **`sdk-server/` (`@awaazlabs-uva/agents`)** | Server Agent Management SDK | **Node.js Server-only.** Allows client backends to programmatically create, list, and update agents (`createAgent`, `listAgents`, `updateAgent`) using HMAC signatures signed by `tenant_secret`. |
| **`control_plane/`** | Token Minting Service | FastAPI app (`control_plane/app.py` & `mint.py`) hosting `POST /v1/session`. Validates HMAC signatures, checks origin allowlists, enforces concurrency/minute quotas, and mints short-lived (≤120s) LiveKit WebRTC room tokens. |
| **`tenant_portal_api/`** | Tenant Self-Service API | FastAPI app (`tenant_portal_api/app.py`) hosting `/machine/agents` (for `@awaazlabs-uva/agents` HMAC auth) and `/portal/*` (for tenant human dashboard JWT auth). |
| **`worker/`** | LiveKit Python Voice Worker | Python process (`worker/main.py`) listening for LiveKit rooms. Reads `tenant_id` and `agent_id` from room metadata, loads agent prompt/voice from Postgres, and runs Gladia STT → Gemini LLM → Uplift AI TTS pipeline. |
| **`dashboard/`** | Tenant Portal Web UI | Next.js web application for client administrators to log in manually (`/portal/login`), view agents, monitor minutes, and retrieve API keys. |
| **`admin/`** | Super-Admin Management | Internal CLI & query functions (`admin/queries.py`) for Finova staff to provision new clients (`tenants`), generate HMAC secrets, set quota caps, and view platform metrics. |
| **`supabase/`** | Database Schemas & Migrations | PostgreSQL database definitions ([`SCHEMA.md`](file:///d:/FinovaSolution/ukasha-urdu-sdk/supabase/SCHEMA.md)), RLS policies, and SQL migrations (`migrations/`). |
| **`client_deliverables-urdu-sdk/`** | Client Hand-Off Package | Standalone, self-contained hand-off package provided to clients, containing pre-built SDKs (`packages/`) and a starter test app (`test-app/`). |
| **`scripts/`** | Maintenance & Ops Scripts | Operational scripts like `reconcile_sessions.py` (repairs quota counters) and `dbconn.py` (Postgres connection helper). |
| **`tests/`** | Pytest Test Suite | Automated test suite (`test_machine_agent_api.py`, `test_mint.py`, `test_worker.py`, `test_admin.py`). |
| **`hamza/`** | Archived Legacy Files | Git-ignored directory containing old single-tenant Pipecat demo files and historical planning markdown documents. |

---

## 3. End-to-End System Logic Flow

### Step 1: Client Provisioning (Finova Internal)
1. Finova Admin uses `admin/` functions to provision a new client tenant (`tenants` table).
2. The system generates a unique `tenant_id`, a raw `hmac_secret`, a `publishableKey`, and assigns quota limits (`max_concurrent=20`, `max_minutes_month=10000`).

### Step 2: Programmatic Agent Creation (`@awaazlabs-uva/agents`)
1. Client backend uses `@awaazlabs-uva/agents` (`createAgent`) to create a new agent.
2. The client backend uses the server-only `@awaazlabs-uva/agents` SDK to authenticate the request without exposing raw signing material to browsers, prompts, or public handoff docs.
3. Finova's `tenant_portal_api` (`/machine/agents`) verifies the HMAC signature, checks for nonce replay, and inserts the agent record into PostgreSQL linked to `agents.tenant_id = tenant_id`.

### Step 3: Session Token Minting (`control_plane`)
1. An end-user clicks "Connect" on the client's web app.
2. The browser calls the client backend, which delegates to the backend-only AwaazLabs-UVA session service integration.
3. The AwaazLabs-UVA session service:
   - Verifies backend authentication and replay protections.
   - Verifies single-use nonce via `used_nonces` table.
   - Verifies agent belongs to tenant (IDOR check).
   - Verifies tenant status is active and origin is allowed.
   - Verifies quotas (`quota_state.concurrent_now < tenants.max_concurrent`).
   - Mints a short-lived (120s) LiveKit WebRTC JWT token.
   - Increments `quota_state.concurrent_now = concurrent_now + 1`.

### Step 4: WebRTC Audio Session & Worker Execution
1. Browser uses `@awaazlabs-uva/voice` to connect to LiveKit Cloud using the minted token.
2. LiveKit Cloud dispatches a job request to Finova's `worker/main.py`.
3. Finova Worker:
   - Joins the WebRTC room.
   - Extracts `tenant_id` and `agent_id` from room metadata.
   - Loads the agent's prompt and voice ID from the database.
   - Streams user speech to **Gladia STT** (Urdu).
   - Sends transcripts to **Gemini LLM** (`gemini-2.5-flash`).
   - Synthesizes assistant responses using **Uplift AI TTS** (Urdu Orator voice).
   - Executes platform tools (`escalate_to_human`, `end_conversation_summary`).
4. Upon disconnect, the worker decrements `quota_state.concurrent_now` and records usage minutes.

---

## 4. Security & Multi-Tenant Isolation

1. **Secret Boundary:** `tenant_secret` is a server-side HMAC secret. It is **only** held by `finova-client`'s backend and Finova's Control Plane. It must **NEVER** be shipped to browser code.
2. **Replay Protection:** Every signed request requires a Unix timestamp (skew ≤60s) and a single-use `X-Nonce` stored in `used_nonces`.
3. **Tenant Isolation:** Agents are strictly scoped by `agents.tenant_id`. Database queries enforce tenant ownership (`WHERE id = %s AND tenant_id = %s`), preventing cross-tenant IDOR attacks.
4. **Quota Reconciliation:** If a call disconnects ungracefully, running `python scripts/reconcile_sessions.py` automatically resets `quota_state.concurrent_now` back to true active session counts.

---

## 5. How to Run Finova Services Locally for Dev & Testing

### Finova Platform Terminals:
```bash
# 1. Tenant Portal API (Port 8002)
python -m uvicorn tenant_portal_api.app:app --port 8002

# 2. Control Plane (Port 8000)
python -m uvicorn control_plane.app:app --port 8000

# 3. LiveKit Voice Worker
python -m worker.main dev
```

### Test Suite Execution:
```bash
python -m pytest tests/test_machine_agent_api.py tests/test_mint.py tests/test_worker.py tests/test_admin.py
```
