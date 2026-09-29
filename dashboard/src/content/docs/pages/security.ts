export const meta = {
  slug: 'security',
  title: 'Security',
  eyebrow: 'Reference',
  description: 'Keys, trust boundary, and rotation habits.',
};

export const markdown = `
## Rules that do not bend

1. **HMAC secret** never ships to browsers, mobile apps, or public repos.  
2. **Publishable key** may live in the frontend; it is not a substitute for HMAC.  
3. **LiveKit tokens** are short-lived; mint only through your backend.  
4. Prefer revealing secrets in **[API Keys](/credentials)** over pasting into tickets.

## Trust boundary

See [How integration works](/docs/how-integration-works). Short version: browsers talk to you; you talk to AwaazLabs with a signature.

## Rotation

- Rotate HMAC if it was logged, committed, or shared.  
- Update backend env first, then invalidate old secret in the console if your plan supports dual-key cutover.  
- After rotation, run a Quickstart connect and confirm [Sessions](/sessions).

## Origins

Restrict who can call your \`/api/voice/session\` (auth cookie, CORS allowlist, or both). A publishable key alone is identification, not proof the caller is your app.

## Going live

Use the [Going live](/docs/going-live) checklist before production traffic.
`;
