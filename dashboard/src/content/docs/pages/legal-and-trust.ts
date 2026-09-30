export const meta = {
  slug: 'legal-and-trust',
  title: 'Legal and trust',
  eyebrow: 'Reference',
  description: 'Terms, privacy, DPA path, and sub-processors for guide delivery.',
};

export const markdown = `
## Why this page exists

The console helps you integrate voice agents that may process **caller audio and transcripts**. Commercial use needs tenant-facing Terms, Privacy, and a DPA path — not marketing claims alone.

## Where to find documents

Operators can set public URLs via dashboard env:

- \`NEXT_PUBLIC_LEGAL_TERMS_URL\`
- \`NEXT_PUBLIC_LEGAL_PRIVACY_URL\`
- \`NEXT_PUBLIC_LEGAL_DPA_URL\`

When those are configured, the console surfaces them on **[Legal](/legal)**. If they are empty, ask your AwaazLabs contact for the current pack before go-live.

Repo operator note: \`docs/legal/README.md\` (platform team).

## Sub-processors (typical)

| Vendor | Role |
|--------|------|
| LiveKit | WebRTC / rooms |
| STT / LLM / TTS providers you configure | Speech and dialogue — see [Providers](/docs/providers) |
| Telnyx | PSTN when telephony is enabled |
| Supabase | Auth + Postgres |

State retention and recording consent in **your** Privacy Policy. Platform purge tooling exists; legal wording must match your deployment.

## Related

- [Security](/docs/security)
- [Going live](/docs/going-live)
- [Providers](/docs/providers)
`;
