# AwaazLabs UVA SDK — Integration Package (Wave 1)

Everything you need to integrate browser voice, agents, and phone (PSTN) — **this folder + your tenant secrets**. Deployed service URLs are filled in later when AwaazLabs brings the environment online.

## What you receive

| Item | When |
|------|------|
| This docs + `host-backend-starter/` folder | Now |
| Tenant secrets (`tenantId`, HMAC secret, publishable key) | Now (secure message) |
| Service URLs (control plane, portal API) | Later, when services are deployed |
| Your own Telnyx API key | You bring this for phone |

No separate “adapter package” is required. Session signing lives in **`host-backend-starter/`** inside this folder.

---

## Install (npm — public packages)

| Package | Version | Where it runs |
|---------|---------|----------------|
| `@awaazlabs-uva/voice` | **1.1.0** | Your frontend (browser) |
| `@awaazlabs-uva/agents` | **0.1.0** | Your backend only |
| `@awaazlabs-uva/telephony` | **0.1.0** | Your backend only |

```bash
npm install @awaazlabs-uva/voice@1.1.0
npm install @awaazlabs-uva/agents@0.1.0
npm install @awaazlabs-uva/telephony@0.1.0
```

- https://www.npmjs.com/package/@awaazlabs-uva/voice  
- https://www.npmjs.com/package/@awaazlabs-uva/agents  
- https://www.npmjs.com/package/@awaazlabs-uva/telephony  

---

## What’s in this package

| Path | Contents |
|------|----------|
| `01-INTEGRATION_GUIDE.md` | End-to-end: agents → host backend → browser → telephony |
| `02-HOST_BACKEND_CONTRACT.md` | Browser ↔ host session contract + signing details |
| `03-ERROR_HANDLING.md` | Error codes |
| `04-TELEPHONY_AND_PROVIDER_KEYS.md` | Telnyx (not Twilio) |
| `05-CREDENTIALS_TEMPLATE.md` | Env templates |
| `06-SECURITY_RULES.md` | Browser vs backend secrets |
| **`host-backend-starter/`** | **Runnable Node host backend** (session mint + refresh + HMAC) |

Start with **`01-INTEGRATION_GUIDE.md`**, then run **`host-backend-starter/`**.

---

## Architecture

```text
Browser (@awaazlabs-uva/voice)
  → your host backend  (use host-backend-starter/ or port its code)
    → AwaazLabs control plane  (URL filled when deployed)
      → LiveKit + hosted voice worker
```

Phone flows use `@awaazlabs-uva/telephony` on your backend with your Telnyx API key.

---

## Recommended build order

1. Install npm packages (pinned versions above).  
2. Put tenant secrets into `host-backend-starter/.env` (and your app backends).  
3. Create an agent with `@awaazlabs-uva/agents` once the portal URL is available — or use a provided `agentId`.  
4. Run `host-backend-starter` once `UVA_CONTROL_PLANE_URL` is available.  
5. Wire `@awaazlabs-uva/voice` to **your** session/refresh URLs.  
6. Confirm browser connect: agent audio + transcripts.  
7. (Phone) Connect Telnyx → sync/assign number → readiness → test call.  

---

## Success checklist

- [ ] Packages installed from npm  
- [ ] Tenant secrets in backend `.env` (never in the browser)  
- [ ] `host-backend-starter` (or equivalent) running with control-plane URL  
- [ ] Frontend has publishable key + your session/refresh URLs + agent id  
- [ ] `POST /api/voice/session` returns `{ token, wsUrl, roomName }`  
- [ ] Connect succeeds: agent audio + transcripts  
- [ ] (Phone) Telnyx connected, number assigned, readiness OK, test call works  

---

## Support

Include: HTTP status from your host backend, the SDK `error.code`, and whether failure is browser connect, agents API, or telephony. Do not send HMAC secrets or Telnyx API keys.
