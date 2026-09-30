# Legal & trust pack (P4-C1)

Commercial delivery of a voice platform that processes caller audio and transcripts needs tenant-facing **Terms of Service**, **Privacy Policy**, and a **DPA** path.

This repository does **not** ship final counsel-approved contracts. Operators must:

1. Publish ToS / Privacy / DPA on your legal site (or counsel-approved pages).
2. Set dashboard env URLs so the console links to those documents:
   - `NEXT_PUBLIC_LEGAL_TERMS_URL`
   - `NEXT_PUBLIC_LEGAL_PRIVACY_URL`
   - `NEXT_PUBLIC_LEGAL_DPA_URL`
3. Until those URLs are set, the dashboard Legal page lists **sub-processors** and asks tenants to contact you for the current pack.

## Sub-processors (typical)

| Vendor | Role |
|--------|------|
| LiveKit | Real-time media / WebRTC rooms |
| STT provider(s) configured per agent (e.g. Gladia, Deepgram) | Speech-to-text |
| LLM provider(s) configured per agent (e.g. Gemini, Groq) | Dialogue |
| TTS provider(s) configured per agent (e.g. Uplift, Cartesia, ElevenLabs) | Text-to-speech |
| Telnyx (when telephony enabled) | PSTN / SIP |
| Supabase | Auth + Postgres data plane |

Retention, recording consent, and purge schedules must be stated in your Privacy Policy (see also session media purge workflows in this repo).
