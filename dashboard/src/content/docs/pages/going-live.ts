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
- [ ] Hosted console access is **invite- or claim-only** (no open self-serve tenant bootstrap)
- [ ] Rotated any keys that were pasted into chat, tickets, or screenshots — ask AwaazLabs to rotate via **admin** (console rotate is disabled) ([Security](/docs/security))
- [ ] \`UVA_CONTROL_PLANE_URL\` points at production

### Origins (both required)

- [ ] **UVA tenant \`allowed_origins\`** set in [API Keys](/credentials) to your production frontend origin(s) — hosted mint fails closed if this list is empty
- [ ] Allowed origins / CORS on **your** session endpoint match those same production domains
- [ ] Session endpoint is HTTPS and reachable from the browser
- [ ] Mic works on production HTTPS (not only localhost)

### Product surfaces

- [ ] Agent prompt, language, and providers verified (inspect on [Agents](/agents); edit via [agents SDK](/docs/backend-setup); matrix on [Providers](/docs/providers))
- [ ] Browser path: [Frontend setup](/docs/frontend-setup) smoke test against **your** host mint (not Test Studio alone)
- [ ] Phone path (if used): number assigned via telephony SDK; confirm on [Agents](/agents); inbound test
- [ ] Owner vs member roles understood — credential / invite mutations are owner-only ([Security](/docs/security))

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

## Candidate humanization activation

P0 implementation tests passing does not clear the audible activation gate. Keep candidates off until the intended provider/language/channel lanes have real readiness, acoustic, interaction and native-listening evidence. Test through your independent host as well as Test Studio. Review [Humanization testing](/docs/humanization-testing); this repository update does not start a production canary.
`;
