# 05 — Credentials Template

Fill this with values from AwaazLabs provisioning + (later) deployed service URLs.  
Do not commit real values to git. Do not put HMAC or Telnyx keys in frontend files.

Replace every `<...>` placeholder.

---

## A. Values from AwaazLabs

| Placeholder | When | Goes in |
|-------------|------|---------|
| `<PUBLISHABLE_KEY>` | Now | Frontend + backend |
| `<TENANT_UUID>` | Now | Backend only |
| `<TENANT_HMAC_SECRET>` | Now | Backend only |
| `<AGENT_UUID>` | After portal is up (or create via agents SDK) | Frontend connect |
| `<SESSION_UPSTREAM_URL>` | When control plane is deployed | Backend only (`UVA_CONTROL_PLANE_URL`) |
| `<TENANT_PORTAL_API_BASE_URL>` | When portal API is deployed | Backend only (`UVA_API_BASE_URL` / telephony) |

Session mint/signing code is included in this package: `host-backend-starter/`.

---

## B. Values from you

| Placeholder | Source |
|-------------|--------|
| `<YOUR_TELNYX_API_V2_KEY>` | Your Telnyx dashboard (telephony only) |
| `<YOUR_BACKEND_PUBLIC_URL>` | Your deployed API host |

---

## Backend `.env` (template)

Use the same values in `host-backend-starter/.env` for browser voice.

```bash
# --- AwaazLabs (now) ---
UVA_TENANT_ID=<TENANT_UUID>
UVA_HMAC_SECRET=<TENANT_HMAC_SECRET>
UVA_PUBLISHABLE_KEY=<PUBLISHABLE_KEY>

# --- AwaazLabs (when deployed) ---
UVA_API_BASE_URL=<TENANT_PORTAL_API_BASE_URL>
UVA_TELEPHONY_API_URL=<TENANT_PORTAL_API_BASE_URL>
UVA_CONTROL_PLANE_URL=<SESSION_UPSTREAM_URL>

# --- You (required for phone) ---
TELNYX_API_KEY=<YOUR_TELNYX_API_V2_KEY>

# --- Optional Telnyx SIP / outbound ---
TELNYX_SIP_FQDN=
TELNYX_SIP_USERNAME=
TELNYX_SIP_SECRET=
TELNYX_OUTBOUND_ALLOWED_DESTINATIONS=US

# --- Your host ---
HOST_ALLOWED_ORIGINS=http://localhost:5173,https://your-app.example.com
HOST_PUBLIC_BASE_URL=https://your-api.example.com
PORT=3000
```

---

## Frontend `.env` (template)

```bash
VITE_UVA_PUBLISHABLE_KEY=<PUBLISHABLE_KEY>
VITE_UVA_SESSION_ENDPOINT=https://your-api.example.com/api/voice/session
VITE_UVA_REFRESH_ENDPOINT=https://your-api.example.com/api/voice/session/refresh
VITE_UVA_AGENT_ID=<AGENT_UUID>
# optional:
# VITE_UVA_FETCH_TIMEOUT_MS=15000
```

Session/refresh URLs must be **your** host backend (e.g. the included starter), never the control-plane URL.

---

## Checklist before first connect

- [ ] Backend has HMAC + tenant id + publishable key  
- [ ] `UVA_CONTROL_PLANE_URL` set and `host-backend-starter` (or equivalent) running  
- [ ] Frontend has publishable key + **your** session/refresh URLs only  
- [ ] Agent id exists (created or provided)  
- [ ] No HMAC / Telnyx key in any frontend file  
- [ ] (Phone) Portal URL + Telnyx key on backend; `connectTelnyxAccount` succeeded  
