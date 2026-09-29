export const meta = {
  slug: 'going-live',
  title: 'Going live',
  eyebrow: 'Integrate',
  description: 'Pre-launch checklist before real users call.',
};

export const markdown = `
## Pre-launch checklist

### Keys and env

- [ ] Production \`UVA_HMAC_SECRET\` only in backend env / secret store — never in the frontend  
- [ ] Publishable key in the client is the **prod** key (not a leftover test value)  
- [ ] Rotated any keys that were pasted into chat, tickets, or screenshots — [API Keys](/credentials)  
- [ ] \`UVA_CONTROL_PLANE_URL\` points at production  

### Origins and host

- [ ] Allowed origins / CORS on your session endpoint match production domains  
- [ ] Session endpoint is HTTPS and reachable from the browser  
- [ ] Mic works on production HTTPS (not only localhost)  

### Product surfaces

- [ ] Agent prompt and voice verified (inspect on [Agents](/agents); edit via agents SDK)  
- [ ] Browser path: [Frontend setup](/docs/frontend-setup) smoke test  
- [ ] Phone path (if used): number assigned via telephony SDK; confirm on [Agents](/agents); inbound test  


### Observability

- [ ] You can find a test call on [Sessions](/sessions) and read status / transcript  
- [ ] Error logging on your \`/api/voice/session\` captures mint failures  

### Optional webhooks

- [ ] If you receive session or telephony webhooks, the URL is reachable and signature / auth is verified  

### Real-device pass

- [ ] One call from a real phone (telephony) or a clean browser profile (WebRTC)  
- [ ] End reason looks expected in Sessions  

## After go-live

Keep [What to expect](/docs/what-to-expect) handy for lifecycle questions, and [Errors and troubleshooting](/docs/errors-and-troubleshooting) for mint / mic / connect failures.
`;
