# Mid-conversation latency: local worker follow-up

The supplied worker log at 23:12 confirms healthy Cartesia client reuse, Nova-3
endpointing at 100 ms, and Claude Haiku with thinking disabled. One complete
turn took 2,360 ms from worker-observed speech stop to its first TTS frame:
500 ms before the LLM request, about 1,360 ms to observable text, and 500 ms
from text to audio (156 ms chunk planning plus 344 ms synthesis). This is a
worker diagnostic, not a measurement of caller-heard playback.

Nova transcript delay reached 2,768 ms on the closing turn. The browser excerpt
also contains a 4,155 ms final-transcript-to-active-speaker proxy on a different
turn whose full worker trace was not supplied. Active-speaker signals are not
an acoustic latency measurement. Do not infer audio gaps from their toggling.

## Local changes

- `.env.local` opts the local English Deepgram worker into Flux with eager EOT
  threshold 0.4 (initially 0.6; see the follow-up below). Prior settings are in the ignored
  `.env.local.before-flux-20261023`. Per-agent explicit STT options still win;
  the selected demo agent had no stored mode/eager override when inspected.
- Flux uses native STT turn detection without an added endpointing pause.
  Claude is limited to one speculative draft per user turn. Groq speculation
  remains disabled. LiveKit still authorizes speech and tool execution after
  turn commitment; this change does not execute business writes early.
- Flux whole-turn finals bypass Nova's 1.8-second incomplete-phone segment
  settling path. Incomplete phone preflight transcripts are suppressed, while
  final transcripts pass unchanged. Nova segment coalescing remains intact.
- Speech-level diagnostic stages retain the generation that produced the first
  audio when a later tool continuation is silent. All generations remain in
  the payload; this reporting correction does not make audio faster.

The pinned Deepgram plugin is retained. No dependency upgrade or unsupported
constructor parameter is required. Eager generation may increase LLM calls.

Reference: https://developers.deepgram.com/docs/flux/voice-agent-eager-eot

## Manual verification after worker restart

No tests or provider calls were run for these changes. Restart the existing
terminal worker, then check that its STT build line names `STTv2 Flux` and
`eager_eot_threshold=0.4`; the turn profile must show `detector=stt`,
`endpointing_min=0.00`, and preemptive generation enabled. Repeat the same
conversation, including phone capture, a pause followed by continued speech,
and a closing turn. Inspect `using preemptive generation` or invalidation logs,
STT delay, first-text/chunk/audio stages and client reuse. Actual improvement,
false turn endings, native speech quality and browser audibility remain
unverified until that run.

## Follow-up: the 23:30 call

The new worker log confirms Flux and a 0.6 eager threshold were active.
Preemptive lead was only 36 ms on both supplied turns: the preflight and final
arrived almost together. This is not evidence that speculative generation
hid a useful part of Claude's 1.19-1.49 second TTFT. The local eager threshold
is now 0.4, matching Deepgram's documented low-latency example, while final
EOT stays at 0.7. Earlier drafts can increase cancellations/cost; incomplete
phone drafts remain filtered and LiveKit owns final authorization.

The phone turn had 1,914 ms provider transcript delay, 1,190 ms LLM TTFT,
265 ms chunk wait, then about 1,184 ms from chunk readiness to first audio.
That last interval includes 553 ms opening a new Cartesia websocket. Its
preceding interrupted reply and delivery-setting changes can leave no idle
matching client. The next turn reused the client and took only about 234 ms
from chunk readiness to first audio.

Delivery now prepares the exact planned client when its speech plan is
created, before LLM output arrives. It opens only a transport and sends no
speech text. Prepared clients remain under the bounded session pool, are
leased exclusively, and close at session end. Text-dependent option changes
still use separate clients; failed/interrupted streams are never recycled.
This overlaps connection setup with LLM work instead of waiting for a text
chunk. It cannot eliminate provider TTFT or guarantee the connection is ready.

For this phone turn, monotonic speech-stop to first frame is 4,250 ms; the
legacy 3,763 ms component-sum proxy omits some pipeline intervals. Neither is
receiver playout. Inspect the raw stage intervals alongside the proxy.

Verification remains static only: no tests, provider requests, or service
restarts were performed. The next manual run should show `delivery transport
prepare` before `first_speakable_chunk_ready`, warm-client acquisition, and
the measured preemptive lead. These changes have no measured live result yet.

Reference: https://developers.deepgram.com/docs/flux/configuration

## Follow-up: the 23:41 call

The caller reports improvement. The supplied worker stages show one turn with
1,485 ms from observed speech stop to first TTS frame: LLM request to useful
text was 1,235 ms, chunk wait 94 ms, and chunk-to-audio 250 ms, overlapping
94 ms of the speech-stop interval through preemptive generation. Another
completed turn's stage fragment shows 1,875 ms stop-to-frame, 1,172 ms to
useful LLM text, 235 ms chunk wait, and 390 ms chunk-to-audio. Browser
active-speaker proxies range from 1,356 ms to 2,569 ms after final transcript;
they are not acoustic measurements or interchangeable with worker intervals.

The adapter's previous comment incorrectly claimed the plugin automatically
cached prompts. Installed Anthropic plugin 1.6.5 defaults `caching` to
NOT_GIVEN and only emits its cache breakpoints when set to `ephemeral`.
The adapter now explicitly enables that supported option. The plugin can
reuse stable tool/prompt prefixes for five minutes; changing humanization
guidance can still invalidate later prefixes. There is no prompt padding,
message reordering, response reuse, or model switch. This is a potential
TTFT improvement, not a measured cache hit. Cache writes also have a modest
input-price premium; successful reads are cheaper than uncached input.

Generation usage now exposes provider-observed `llm_prompt_tokens` and
`llm_cached_prompt_tokens`. Zero means a reported zero; absent metrics stay
unavailable. Check for positive cached tokens and compare TTFT across later
turns. Cached tokens remain included in `llm_tokens`, so these additional
counters must not be added to it as additional usage or billing.

The same call emitted an eager `Yeah. A pain in my`, replaced it with a
complete transcript 33 ms later, cancelled the HTTP draft and established
a new TCP/TLS connection. Flux draft filtering now skips dangling English
articles/possessives in addition to incomplete phone numbers. It introduces
no waiting period: complete eager events, interim/resumed speech and every
final still pass immediately. This avoids that observed wasted draft; it
does not suppress all possible transcript revisions or their cancellation.

Verification for this follow-up is static only. The running worker has not
been restarted, and no tests or paid provider requests were executed.

Reference: https://platform.claude.com/docs/en/build-with-claude/prompt-caching

## Follow-up: the 23:54 call

The caller's next worker log confirms prompt-cache reads: one turn read 4,063
of 4,210 prompt tokens from cache, and the next read 4,142 of 4,297. Cartesia
client reuse was active. Their observed speech-stop-to-first-frame intervals
were 1,922 ms and 1,391 ms respectively. The second turn spent 1,187 ms from
LLM request to useful text, 16 ms on chunk preparation, and 219 ms from chunk
readiness to audio; preemptive generation overlapped part of turn detection.
One earlier speculative draft was still cancelled. The phrase guard does not
eliminate all possible transcript revisions.

These are user-supplied worker diagnostics, not an automated test run or
receiver audio measurement. They confirm that caching and connection reuse
are active in that local run. Consistent subsecond replies remain unproven;
Claude/network request latency remains the largest measured component.

## Deployment configuration

Repository publication does not copy ignored environment files or credentials.
The tested local Flux opt-in is:

```dotenv
UVA_DEEPGRAM_STT_MODE=flux
UVA_DEEPGRAM_FLUX_EAGER_EOT=1
UVA_DEEPGRAM_FLUX_EAGER_EOT_THRESHOLD=0.4
```

Repository defaults retain Nova with eager generation disabled. A deployment
needs its own provider credentials and these opt-ins to use the same Flux
configuration; stored per-agent overrides still apply. Never publish local
environment files or their backups. Keep the caller-selected Claude model.
