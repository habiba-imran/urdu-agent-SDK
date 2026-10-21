# Latency audit and improvement plan — 2026-10-21

Author: Ehsan (M3 worker capacity / provider failure).
Branch `ehsan` at the merge of `origin/main` `a37b635`.

Scope: where the time actually goes between a caller finishing a sentence and hearing the
reply, measured against the live provider keys in `.env.local` rather than inferred from the
code. Complements `client-integration-test/INBOUND_LLM_FAILURE_2026-10-20.md`, which measured
the same stack from inside a disposable worker and reached a compatible conclusion.

## How these numbers were taken

Direct HTTPS calls to each vendor from the development laptop, streaming, timing the first
byte or first content token. Node's `fetch` with connection reuse, three or more runs per
case. No PSTN call was placed, no agent row or phone route was touched, and no worker was
started. These are **provider-side** numbers: they bound what the pipeline can achieve and
they do not include LiveKit SIP, jitter buffering, or playout — see L-05.

The scratch scripts live in the session scratchpad, not in the repo.

## Measured results

### LLM time to first usable token

| Provider | Model | Cold | Warm (connection reused) |
| --- | --- | ---: | ---: |
| Groq | `openai/gpt-oss-20b` | 552 ms | **235 / 345 / 351 ms** |
| Gemini | `gemini-3.6-flash` | — | **HTTP 503 after 13,395 ms** |

Groq was measured at production settings: `reasoning_effort=low`,
`max_completion_tokens=96`, `temperature=0.35`, an ~800-character system prompt and a real
question ("What time do you open on Saturday?"). Time is to first **content** token, not to
the first SSE frame — `gpt-oss-20b` emits 6-8 `delta.reasoning` chunks first, and those do not
produce audio.

Gemini is still shedding load with the same message Habiba recorded yesterday. Note the cost
of the failure itself: **13.4 seconds to return a 503.**

### TTS time to first audio byte

| Provider | Format | Cold | Warm | Ratio |
| --- | --- | ---: | ---: | ---: |
| Cartesia `sonic-2` | raw PCM 16 kHz | — | **312 / 322 / 376 ms** | — |
| UpliftAI `v_meklc281` | `PCM_22050_16` | **1,009-1,534 ms** | **343 / 359 / 367 ms** | **~3-4x** |

TTFB does not scale with text length — 8 characters cost 1,534 ms and 215 characters cost
423 ms on a warm connection — so the large numbers are connection establishment, not
synthesis. Warm, UpliftAI and Cartesia are within ~30 ms of each other.

### Vendor TLS + HTTP round trip, no inference

| | groq | google | cartesia | upliftai | deepgram | gladia | livekit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| first | 670 | 413 | 866 | 1,144 | 2,072 | 1,880 | 767 |
| median | 367 | 410 | 232 | 666 | 904 | 835 | 660 |
| best | 303 | 166 | 143 | 216 | 302 | 460 | 229 |

Establishing a connection costs 150-2,000 ms depending on vendor and luck. **That is the same
order of magnitude as the entire inference budget**, which is why warm-up dominates this audit.

## Findings

### L-01 — the Urdu TTS path has no warm-up at all

**Severity: High.** `prewarm_tts` (`worker/latency.py:264`) duck-types a `prewarm` attribute
on the TTS object. Only two providers in the whole tree define one:

```
worker/providers/llm/groq.py
worker/providers/tts/cartesia.py
```

`worker/providers/tts/uplift.py` returns a bare `upliftai.TTS(...)` (line 143) with no
`prewarm`, so the warm-up task finds nothing, returns immediately, and logs success. The first
Urdu utterance of every call therefore pays cold-connection cost.

Measured gap: **1,009-1,534 ms cold against 343-367 ms warm — roughly 650 ms to 1.2 s of
avoidable dead air on the first reply**, on the product's primary language. English (Cartesia)
is already warmed, so the better-instrumented path is the one that needed it less.

### L-02 — Uplift does not re-warm after a barge-in

**Severity: High. Confidence: medium — see the confound.** `wire_interruption_tts_prewarm`
(`worker/latency.py:376`) looks for `prewarm_after_interruption` on the session TTS. Cartesia
implements it, with a comment that names the mechanism exactly:

> Pinned plugin 1.6.5 removes cancelled sockets from its pool.

Uplift implements neither hook. So on the Urdu path every barge-in plausibly discards the warm
connection and the next reply pays L-01's cost again — on a voice agent, where interruption is
normal rather than exceptional.

Measured, aborting each stream mid-playout to simulate barge-in:

```
cold:                              1,441 ms
TTFB, full drain (reuse):   1,125 → 343 → 359 → 367 ms
TTFB, mid-stream abort:       386 → 382 → 1,001 → 2,420 ms
TTFB, drain again after:    2,663 → 1,218 → 2,931 ms
```

**Confound:** these twelve requests were issued back to back, so vendor-side rate limiting
could explain part of the rising tail. The steady 343/359/367 ms under full drain is tight and
repeatable; the post-abort degradation is suggestive but not isolated. Confirm with spaced
requests before treating the magnitude as established. The architectural gap — no hook where
Cartesia has one — is not in doubt.

### L-03 — the fastest LLM is the one denied TTFT hiding

**Severity: High.** `worker/humanization/turn.py:192-197`:

```python
if llm == "groq":
    preemptive = {"enabled": False, "preemptive_tts": False, ...}
```

Groq is preemptive-off on **every** channel, while telephony explicitly re-enables preemptive
generation for non-Groq providers to "hide Gemini TTFT". The stated reason is free-tier TPM:
cancelled turns burn tokens.

So the provider measured at **235-351 ms** gets no TTFT hiding, and the provider currently
returning 503 after 13 s does. That is a billing decision wearing the costume of a latency
decision, and it is the wrong way round for the user experience. It is defensible on a free
tier and indefensible on a paid one.

### L-04 — Gemini is unusable right now, and the retry configuration makes it worse

**Severity: High, operational.** Already filed as OB-F11/OB-F12; restated here with a number.
Gemini takes 13.4 s to return 503. `worker/provider_retries.py:17-19` defaults
`max_retry=0` and `timeout=5.0` while `.env.example` ships `1` and `30`, and the supplied env
sets neither — so there are zero LLM connect retries. Against `PROGRESS_TIMEOUT = 6.0`
(`provider_retries.py:141`), a Gemini turn consumes the entire conversational budget and
produces nothing, which is exactly the 6,062 ms failure Habiba timed.

### L-05 — nothing measures what the caller hears

**Severity: Medium, and it blocks verifying every other item.** The instrumentation is good:
`sttMs`, `turnMs`, `llmMs`, `ttsMs`, `ttsTtfbMs`, `toolMs`, `e2eMs` per turn, with rolling p50
(`worker/latency.py:672-706`). It is also explicitly labelled for what it is:

```python
"latencyKind": "server_diagnostic_proxy",
"acousticVerified": False,
```

Every number in the system — mine included — stops at the provider boundary. Nothing measures
EOU to first audio **in the caller's ear**, which adds LiveKit SIP bridging, Telnyx transit,
jitter buffer and playout. Habiba reached the same conclusion from the other direction
("Caller-heard PSTN/browser playback latency and subjective humanization remain unverified").
Until that exists, improvements are argued rather than demonstrated.

### L-06 — reasoning tokens share the 96-token reply budget

**Severity: Medium.** `GROQ_MAX_COMPLETION_TOKENS` defaults to 96 (`groq.py:42`) and
`gpt-oss-20b` spends 6-8 chunks on `delta.reasoning` before its first content token. All three
production-setting runs produced complete bilingual replies, so 96 is working — but reasoning
is charged against the same cap, so the margin before mid-sentence truncation is thin and
varies per turn.

`reasoning_format: "hidden"` suppressed reasoning chunks entirely (0 vs 6-8) but did not
reliably improve time to first content in my runs (112 ms and 695 ms across two attempts —
too noisy to call). Worth a controlled comparison, not worth assuming.

### L-07 — a `reasoning_effort` value Groq rejects, currently unreachable

**Severity: Low.** `groq.py:115-116` sets `reasoning_effort="none"` for `qwen/` models. Groq
rejects that outright:

```
HTTP 400 `reasoning_effort` must be one of `low`, `medium`, or `high`
```

Today this is dead code: every `qwen/` ID is in `_DEAD_GROQ_MODELS` (`groq.py:49-51`, with the llama and kimi IDs) and
`resolve_groq_model` remaps it to the default before the branch is reached. But a future qwen
ID placed in `GROQ_LLM_MODEL` would reach it and **400 every single LLM call**. Verified by
sending `none` directly.

### L-08 — the connect budget and the progress budget are not aligned

**Severity: Medium.** Connect timeout defaults to 5.0 s; the useful-progress watchdog is 6.0 s.
A provider that connects in 4.9 s has 1.1 s left to produce a token or the turn is killed. The
two numbers were chosen independently and `.env.example`'s 30 s connect timeout is larger than
the entire progress budget, so an operator following the example gets a connect timeout that
can never fire before the watchdog does.

## Plan

Ordered by measured benefit per unit of risk. Items 1, 2, 6, 7 and 8 are M3 (mine). Item 3 is
a commercial decision. Item 5 is the prerequisite for claiming any of this worked.

### 1. Give UpliftAI the two warm-up hooks — **do this first**

Implement `prewarm` and `prewarm_after_interruption` on the Uplift TTS wrapper, mirroring
`cartesia.py`. The generic plumbing already exists and is duck-typed, so this is additive and
cannot affect the English path.

- Expected: **650 ms to 1.2 s off the first Urdu reply**, and if L-02 holds, a similar saving
  after every barge-in.
- Risk: low. Wrap in try/except and log on failure, as Cartesia does; a failed warm-up must
  never block the greeting.
- Verify: `ttsTtfbMs` on turn 1 against turn 3 of the same call, before and after.

### 2. Set the three provider-retry knobs

```
UVA_PROVIDER_MAX_RETRY=2
UVA_PROVIDER_RETRY_INTERVAL=2.0
UVA_PROVIDER_CONNECT_TIMEOUT=30
```

Zero code change. Then align the code defaults with `.env.example` so the two cannot disagree
again (L-04), and resolve the budget conflict in item 8 at the same time — a 30 s connect
timeout under a 6 s watchdog is incoherent as shipped.

### 3. Make Groq the default for the voice path, and decide the preemptive question

On today's measurements Groq is the only working LLM and it is fast: 235-351 ms warm. Gemini
returns 503 after 13.4 s. Switching the affected agents' `llm_provider` needs no code change.

Separately, decide L-03 deliberately: on a paid Groq tier, enable preemptive generation for
Groq and the LLM effectively disappears from perceived latency. On the free tier, leave it off
and accept ~300 ms. **This is a cost question, not an engineering one — it needs an owner's
answer, not my recommendation.**

### 4. Keep the warm path warm between calls

Both L-01 and the RTT table say the same thing: the first request to any vendor costs
150-2,000 ms more than the rest. `LIVEKIT_NUM_IDLE_PROCESSES=3` keeps processes warm, but
process warmth is not connection warmth — a fresh job gets fresh sockets. Worth measuring
whether provider connections can be pooled per worker process rather than per job. Investigate
before committing; the gain is real but the lifetime questions (idle eviction, credential
rotation per tenant) are not trivial.

### 5. Build the acoustic measurement harness — the only way to know any of this worked

Everything above is a provider-boundary improvement justified by a provider-boundary
measurement. Add a probe that joins a room with a synthetic microphone, plays a known clip,
and timestamps the **first received audio frame** of the reply, so EOU to first-audio-in-ear
is a number. Habiba's native WebRTC probes (14,461 ms and 9,255 ms setup-to-first-PCM) are the
right shape; they need to become a repeatable check rather than a one-off.

Until this exists, report latency work as "provider-boundary measured, caller-heard
unverified" — the language the code already uses, and the honest framing.

### 6. Re-run the L-02 abort experiment with spaced requests

Thirty minutes. It converts L-02 from "suggestive" to a number, and it determines whether item
1's second hook matters per-turn or only once per call. Do it before claiming the win.

### 7. Raise or instrument the Groq token cap

Log when a completion stops on `length` rather than `stop`. If truncation is real, raise
`GROQ_MAX_COMPLETION_TOKENS` to ~160; if not, leave 96 alone. Do not raise it blind — it
trades directly against TPM on the free tier.

### 8. Align the two timeout budgets, and delete the qwen trap

Make the connect timeout provably smaller than `PROGRESS_TIMEOUT`, or make the watchdog aware
of connect time. Fix L-07 by dropping the `qwen/` branch or using `low`.

## What I did not measure

- **STT.** Deepgram and Gladia were RTT-probed only; no streaming-recognition latency, which
  needs real audio and a session. Endpointing is configured at `min_delay` 0.12 s /
  `max_delay` 1.2 s (`worker/latency.py:72`) and that window is a direct latency/false-cut
  trade I have not characterised.
- **Caller-heard latency.** See L-05. This is the gap that matters most.
- **Under load.** All numbers are single-stream on one laptop. The 20-concurrent-call target
  from Q2 is unmeasured, and contention will change every figure here.
- **Tool-call turns.** `toolMs` is instrumented but no tool-invoking turn was timed; a gateway
  round trip sits on top of everything above.
