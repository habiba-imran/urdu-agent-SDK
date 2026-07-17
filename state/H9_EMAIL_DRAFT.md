# H9 email draft — staged for the human to send, NOT sent by the agent

Per `docs/41-HUMAN-TASKS.md` H9: "EMAIL UPLIFT TODAY. Blocks Phase 8." This has never been sent
(confirmed: no reply, no draft, no record of it going out anywhere in this project's history —
see the raw search in this session's earlier message). This is not agent-doable work — sending
email isn't something this session can or should do — so it's staged here, ready to send with
only the bracketed placeholders filled in.

Two near-identical drafts below: one to Uplift (questions 1-4 as written in H9), one to Gladia
(question 1+2 only, per H9's own note: "Same question 1+2 to Gladia").

---

## Draft 1 — to Uplift

**To:** [Uplift support/sales contact email — not held anywhere in this repo, human must supply]
**Subject:** Pre-launch capacity questions — concurrency, rate limits, and Enterprise pricing

Hi Uplift team,

We're building a production voice-agent product on top of your TTS API (currently evaluating on
your free tier — account email: [your Uplift account email]) and are close to a production
capacity decision. Before we commit to a paid tier, we need to understand a few specifics that
aren't covered in your published docs:

1. **Concurrency limit** — what is the maximum number of simultaneous TTS streams allowed per
   account, at each paid tier (Pro and Enterprise)?
2. **Rate limiting** — what specifically triggers a 429 from your API? Is it requests/second,
   concurrent streams, characters/minute, or something else? What's the actual limit?
3. **Pro-tier minute cap behavior** — your published Pro tier appears to include 1,500 minutes.
   What happens at minute 1,501 in a billing period — a hard stop (calls fail), a 429 (rate
   limited but recoverable), or an automatic upgrade/overage charge?
4. **Enterprise pricing above Growth** — we don't see a published rate for usage above your
   Growth tier's 200 hours/month. What is the Enterprise rate structure above that threshold?

Answer #1 in particular could materially change our capacity planning, so we'd appreciate
specifics rather than general tier descriptions if possible. Happy to hop on a call if that's
easier than email.

Thanks,
[Your name]
[Your company/product name]
[Your account email / account ID]

---

## Draft 2 — to Gladia

**To:** [Gladia support/sales contact email — not held anywhere in this repo, human must supply]
**Subject:** Pre-launch capacity questions — concurrency and rate limits

Hi Gladia team,

We're building a production voice-agent product using your STT API (currently on your free tier
for development — account email: [your Gladia account email]) and are finalizing production
capacity planning. Two questions your published docs don't answer for us:

1. **Concurrency limit** — what is the maximum number of simultaneous transcription streams
   allowed per account, at your paid tiers?
2. **Rate limiting** — what specifically triggers a 429 from your API, and what's the actual
   limit (requests/second, concurrent streams, or something else)?

Happy to hop on a call if that's easier than email.

Thanks,
[Your name]
[Your company/product name]
[Your account email / account ID]

---

## What's still needed from the human before sending
- The actual support/sales contact email for each vendor (not in this repo — check their sites'
  contact/support pages, or the account dashboard).
- Your name, product/company name, and account email/ID to fill the placeholders.
- A decision on whether to also ask Uplift's informational H9 #5 (character-artwork licensing) —
  per ADR-017 this is no longer blocking (owned artwork used instead), so it's omitted from this
  draft; H9's own note says it's still fine to ask informationally if useful, not required.

## After sending
Record the reply (or a summary of it) in `docs/40-ADR.md` as a new ADR once received — H9's own
line says "Answer #1 can invalidate the capacity model," so P8-T02's capacity math must be
revisited once a real number exists, not left on the placeholder/estimate this session used.
