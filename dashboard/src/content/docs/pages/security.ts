export const meta = {
  slug: 'security',
  title: 'Security',
  eyebrow: 'Reference',
  description: 'Keys, trust boundary, and rotation habits.',
};

export const markdown = `
## Rules that do not bend

1. **HMAC secret** stays on your **host backend** — never ship it in a browser app bundle or public repo.
2. **Publishable key** may live in the frontend; it is not a substitute for HMAC.
3. **LiveKit tokens** are short-lived; mint only through your backend.
4. Obtain the HMAC through secure operator delivery, or an explicit permitted owner reveal on [API Keys](/credentials), and put it in your secret manager. **Console rotation is disabled** — ask AwaazLabs to rotate via admin if the secret was exposed.

## Trust boundary

See [How integration works](/docs/how-integration-works). Short version: browsers talk to you; you talk to AwaazLabs with a signature.

The console [API Keys](/credentials) page loads **masked metadata**. An owner can request an explicit audited reveal when deployment policy permits it; hosted reveal defaults off. If disabled, ask an operator for secure delivery. Members cannot reveal it. Do not paste the secret into tickets, chat, or frontend env.

## Rotation

- Console rotate is **off** (API \`410\`).
- If the HMAC was logged, committed, or shared, ask an AwaazLabs operator to rotate via **admin**.
- Update every host backend secret store with the new value immediately — there is no grace period.
- After rotation, run a Quickstart connect and confirm [Sessions](/sessions).

## Roles (owner vs member)

| Capability | Owner | Member |
|------------|-------|--------|
| View agents, sessions, usage, docs | Yes | Yes |
| Explicit audited HMAC reveal | Only if deployment policy permits; hosted default off | No |
| Rotate HMAC in console | No (disabled) | No |
| Set \`allowed_origins\` / invite members | Yes | No (API 403) |
| Create / update agents | \`@awaazlabs-uva/agents\` on **your backend** (not this console) | Same |
| Telephony connect / purchase / outbound | \`@awaazlabs-uva/telephony\` on **your backend** (console read-only) | Same |
| Test Studio smoke call | Yes | Yes (portal server-side HMAC; secret never needed in the browser SDK) |

The dashboard UI hides owner-only credential/invite controls for members; the portal API also enforces owner on those routes. Do not treat the JWT \`role\` claim alone as authoritative — membership is re-checked live.

Agents and telephony are **not** mutated through portal UI paths. Treat [Agents](/agents) as inspection only.

## Origins

You need **two** allowlists in production:

1. **Your host** CORS / auth on \`/api/voice/session\` (who may call your mint).
2. **UVA tenant \`allowed_origins\`** in [API Keys](/credentials) — the control plane rejects browser mint when this list is empty on hosted deployments. Include every production frontend origin (and the dashboard origin if you use Test Studio).

A publishable key alone is identification, not proof the caller is your app.

## Going live

Use the [Going live](/docs/going-live) checklist before production traffic.

## Test Studio

Dashboard Test Studio mints through the **tenant portal** with HMAC on the server (same contract as a host backend). It is an operator smoke test — not the path your customers' apps should copy. Production clients mint only from **their** backend.
`;
