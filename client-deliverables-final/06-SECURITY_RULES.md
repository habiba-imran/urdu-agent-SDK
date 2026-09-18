# 06 — Security Rules

Non-negotiable for every integration.

## Never in the browser / mobile client

- Tenant **HMAC secret**  
- **Telnyx** API key (or any carrier key)  
- Session upstream / control-plane admin URLs used for signing  
- SIP passwords / provider secrets  
- Raw provider keys (Cartesia, Groq, etc.) unless AwaazLabs explicitly designs a public token for that purpose (v1: no)

## Allowed in the browser

- `publishableKey`  
- Your own session and refresh HTTPS endpoints  
- `agentId`  
- LiveKit join token **after** your backend mints it (short-lived; returned by your API)

## Architecture rule

```text
Browser → YOUR backend → AwaazLabs upstream → LiveKit / worker
```

If the browser calls AwaazLabs upstream directly with a secret, the integration is wrong.

## Operational rules

- Do not commit `.env` files with real secrets  
- Rotate HMAC only in a coordinated window (old signatures stop working)  
- Rotate Telnyx keys via `rotateTelnyxAccountKey` from backend code  
- Do not log secrets, full HMAC signatures, or Telnyx keys  
- Gate number purchase and outbound dial behind your own authorization  

## npm packages are public; credentials are not

Anyone can `npm install` the packages. **Access to your tenant** is controlled by the credentials AwaazLabs issues you and the Telnyx key you own. Treat those like production passwords.
