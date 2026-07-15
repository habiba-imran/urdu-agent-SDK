# 10-SPEC.md — what we are building

## Product
An SDK. It embeds in a **third-party platform we do not control**. That platform's users
(tenants) create Urdu voice agents by supplying exactly two things:
1. a **prompt**
2. a **voiceId** (Uplift voice, chosen from a picker with artwork + audio preview)

Multiple tenants. Multiple agents each. Concurrent calls. We run the infrastructure.
A **super-admin portal** gives US full visibility: every tenant, agent, session, minute.

## Who is who
| Actor | Trusts us with | We trust them with |
|---|---|---|
| **Us** | — | — |
| **Host platform** | their users' experience | **NOTHING.** Publishable key only. |
| **Tenant** (their user) | a prompt + voice choice | nothing; prompt is untrusted data |
| **End user** | their voice | nothing |

## Success = all of these
- [ ] Tenant creates an agent from (prompt, voiceId). No code.
- [ ] Voice picker: every Uplift voice, artwork, instant preview, **zero live TTS**.
- [ ] End user talks to it in Urdu over WebRTC. It answers in the chosen voice.
- [ ] Tenant A can never read tenant B. Provable.
- [ ] Host platform never holds a provider key. Provable (`make bundle-check`).
- [ ] Admin portal reconciles every number against `usage_events`.
- [ ] Per-tenant quotas enforced in the token mint.

## OUT OF SCOPE — do not build, do not add deps for
- ❌ **Telephony / SIP / PSTN / Pakistan DIDs.** Separate project. Not now.
  (Context: Telnyx PK numbers ~$43/mo vs ~$1 US; PTA telemarketing rules carry up to
   3yr prison / PKR 10M. It's a legal+carrier problem, not an engineering one.)
- ❌ Self-hosted LiveKit. Revisit ~250k min/mo.
- ❌ Uplift Realtime Assistants API. Their beta IS our product; building on it = zero margin control.
- ❌ Custom voice cloning, multi-language beyond ur+en, mobile native SDKs.

## Known ceilings (published, verified)
| Limit | Value | Binds at |
|---|---|---|
| Uplift Growth ($300/200h) | ~28,570 conv-min/mo @42% talk | 🔴 **hardest ceiling. No published price above it.** |
| LiveKit Ship | 20 concurrent | production |
| LiveKit Build | 5 concurrent, 1,000 min | **development** |
| Uplift concurrency | ⚠️ **UNKNOWN — H9 blocks Phase 8** | could invalidate everything |

## Unit economics (for context; do not optimise for this yet)
Marginal ≈ **$0.0044/min** inside plan allowances; **$0.025–0.032/min** all-in at volume.
Target sell price $0.10–0.15/min with a monthly minimum.
⚠️ **Cost cliff:** crossing Uplift Pro (3,571 conv-min) triples $/min from $0.032 → $0.102
until ~15,000 min. Never sell flat-rate PAYG with no floor.
