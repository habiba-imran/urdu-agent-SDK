# Preserved inbound route verification — 20 October 2026

**Result: not ready for an end-to-end PASS.** Carrier and LiveKit configuration
checks passed, but an isolated real-provider audio check of the preserved agent
failed on an ordinary LLM question. No PSTN call was placed, so actual telephone
answering, negotiated codec, caller-heard latency, two-way PSTN media and hangup
are still unverified.

The user's choice to keep the existing tenant's route was honored. No Telnyx
number binding, inbound trunk, dispatch rule, tenant assignment, agent prompt,
provider selection or model configuration was changed during these checks.

## Live read-only configuration checks

For `+13144621603`, the preserved phone record is
`c649a6c1-0303-4aff-b086-0fc05960d9ea`, tenant
`13dda2bb-e391-494a-8391-3cd7f9371b20`, agent
`f46e964e-a300-4e89-bbcf-582dc510d391`.

- Telnyx number: active, attached to `3018585419106223381`, matching the preserved
  tenant's SIP connection record.
- Carrier connection: active, TCP, target `4tb4gjjfj8d.sip.livekit.cloud:5060`,
  matching the worker's configured `LIVEKIT_SIP_URI`. Advertised inbound codec
  configuration includes G722/G711U/G711A/G729; no negotiated codec is claimed.
- LiveKit: exactly one matching inbound trunk (`ST_NeABDifhEMKu`), with dispatch
  rule `SDR_A5zzqBXmYW9z` bound to it and no caller-number restriction.
- Dispatch room prefix and agent metadata match the preserved phone, tenant and
  agent; worker name is `uva-staging-agent`.
- Tenant active, phone record enabled and routing ready. Quota snapshot: 0/20
  concurrent and about 12.88/10,000 monthly minutes used.
- The agent configuration loaded under its tenant's RLS context. It uses English,
  Deepgram Nova-3, Gemini, Cartesia, agent-first opening and a static greeting.
  Tools are configured; business tools were not exercised.
- No inbound call records were found for this preserved phone record. This is not
  proof that no carrier calls ever occurred or that accounting is correct.

## Worker reliability fix

The first health request returned HTTP 503 because a cached database socket had
been closed remotely while idle. The next request reconnected and returned 200.

`worker/db_pool.py` now checks cached connections before lending them after at
least 30 seconds idle. An operational/interface failure during that check discards
the socket and opens a new connection before borrower code runs. Hot reuse avoids
an extra health round trip. Borrower SQL and business writes are never replayed.
This follows the pre-check principle described in the
[Psycopg connection quality documentation](https://www.psycopg.org/psycopg3/docs/advanced/pool.html#connection-quality).

After confirming no active LiveKit rooms, the local worker was restarted with this
fix, retaining its dispatch name and baseline flags. It registered as
`AW_zrqBwXHd75HV`. Subsequent health checks returned **200 healthy**: LiveKit
credentials configured, VAD loaded, database connected. That health endpoint alone
does not verify an active worker connection; registration and the audio probe
provide additional evidence.

## Isolated real-provider audio check

An isolated native WebRTC room copied the preserved rule's exact agent-dispatch
metadata. A synthetic microphone published continuous 16 kHz mono PCM, with silence
between single-sentence clips. The probe received non-silent audio and transcripts
from the local worker. The carrier/SIP leg and actual phone route were not invoked.

| Observation | Result |
| --- | --- |
| Isolated room creation and agent dispatch | 1.880 s |
| Native client room join | 7.242 s |
| Workflow to first active received greeting PCM | 11.712 s |
| Identity question: clip end to reply PCM | 1.221 s |
| Arithmetic question requiring LLM generation | Failed |
| Closing reply after provider failure | Not verified; the agent session had shut down |

The greeting and truthful AI identity response arrived. The identity response is
a baseline deterministic policy path, so it does not establish LLM success.

For “What is two plus two?”, logs show an LLM request starting at 21:03:59.962
Karachi time and `bounded_provider_failure stage=LLM` at 21:04:05.969. The useful
progress deadline is six seconds. It raised `TimeoutError`, published
`PROVIDER_UNAVAILABLE`, and shut down the agent session. No arithmetic reply audio
was received. The probe client remained connected to its room after the agent
session stopped; actual PSTN hangup behavior is not established by this test.

The saved configuration requests `gemini-2.5-flash`. The existing adapter maps it
to `gemini-3.6-flash`; live diagnostics report that effective model, minimal thinking,
180 output tokens and a 30-second provider HTTP timeout. The six-second useful
progress bound is separate from that HTTP timeout. A read-only Google model
metadata request returned HTTP 200 in 1.625 seconds and listed `generateContent`
support. No HTTP authentication/quota error was captured for the failed streaming
request; model availability alone does not prove successful generation.

The original probe continued waiting after the terminal failure and sent a closing
clip into a room with no responding agent. Its two 35-second missing-reply windows
are not LLM latency measurements. The reusable probe now stops on a terminal
provider-failure event instead of continuing additional test turns.

## Checks and evidence

73 focused Python tests passed, covering idle connection recovery, startup,
session opening, caller identity, inbound persistence/runtime and write safety.
Scoped Ruff and Python compilation passed. The fail-fast diagnostic probe change
was syntax/lint checked; the failed paid-provider run was not repeated after that
diagnostic-only change. Existing warning: Starlette httpx deprecation.
CRLF-aware diff checks passed. Required graph refresh was attempted but the
installed launcher failed with `uv trampoline failed to canonicalize script path`.

Ignored local evidence:

- `tmp/inbound-verification-20261020.json`: live read-only configuration snapshot.
- `tmp/preserved-inbound-audio-20261020.json`: isolated audio timings, transcripts,
  terminal provider failure and runtime provider snapshot.
- `tmp/inbound-worker-20261020.log`: serving worker registration and failure trace.

Received audio was not saved. Real provider test usage was preserved. No caller
listening score, native Urdu/mixed-language result, PSTN audio result or capacity
guarantee is inferred from these checks.

To complete acceptance, resolve the preserved agent's Gemini useful-output timeout,
repeat the audio check, then verify an actual incoming phone call with greeting,
an ordinary question/reply, interruption and clean hangup. The current demo tenant
remains separate from this preserved route.
