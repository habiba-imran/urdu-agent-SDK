# Claude voice latency: changes and measurement boundaries

These changes run in the shared Python worker used by SDK integrations, browser
sessions and telephony. The integration-test UI is not the implementation boundary.
Claude remains the selected LLM; agent-selected voices, models and provider options
are preserved. No running worker was restarted or deployed during this work.

## Gaps addressed

1. **Changing system instructions defeated prefix caching.** Conversational turn
   guidance was appended to the first system block. The owned Anthropic client now
   places the cache breakpoint before that changing suffix. Concatenated system
   text, order, authority, conversation data and tool definitions are unchanged.
   Request-local context keeps concurrent speculative turns isolated. Useless
   downstream cache markers are removed only for these transformed requests;
   explicit top-level caller cache policy takes precedence. No context/history
   truncation was added.
2. **Punctuation could delay the first synthesis request indefinitely.** Claude
   paths now have a 120 ms soft first-chunk deadline. When enough ordinary text
   exists, they release an exact 4–12 word prefix with word lookahead. Literal
   values, unfinished pronunciation spans and numeric sequences remain protected.
   The deadline can therefore be exceeded. Pending model reads survive timer
   expiry; cancellation closes only owned speech work. Native provider tokenizers
   also receive this behavior when humanization streaming is disabled. Native
   Uplift buffers a complete segment before synthesis; Claude's baseline Uplift
   path now uses LiveKit's public segment adapter with the same protected tokenizer.
   The wrapper forwards warm-up/recovery and owns shutdown of the wrapped client.
   Fixture mode and other LLMs retain their existing paths.
3. **Some delivery clients were rebuilt every generation.** Claude sessions now
   retain exclusive, exact-option TTS client leases for ElevenLabs, Rime and Uplift,
   alongside existing Cartesia reuse. Interrupted/failed leases are retired.
   Transport-only preparation runs while the LLM is working: no filler synthesis,
   extra completion, early tool execution or premature speech authorization.
   Rime preparation opens a socket only when its configured transport is WebSocket.
4. **Claude transport used HTTP/1.1.** The owned persistent Anthropic client now
   enables HTTP/2 with HTTP/1.1 fallback. This permits independent HTTP/2 stream
   cancellation while sharing a TLS connection. The response hook records only the
   negotiated protocol. `h2==4.4.1` is now a pinned worker dependency.
5. **Uplift startup warm-up was not executed by LiveKit.** Its async hook caused an
   unawaited-coroutine warning during the live session probe. The hook now starts
   and returns a single owned task, supporting both LiveKit's synchronous call and
   the worker's explicit awaited warm-up. Shutdown cancels and gathers it.

Claude's existing low-effort setting, model-specific thinking policy, output limit,
streaming, zero SDK retry budget and connection warm-up remain intact. Gemini and
Groq generation policies were not tuned. STT endpointing/accuracy settings and
LiveKit's final turn/tool authorization were not changed.

## Live evidence from this checkout

Synthetic requests used the actual provider adapters and pinned LiveKit 1.6.5.
These are small diagnostic samples from a Windows development machine, not a
controlled before/after experiment, percentile result, or service guarantee.

Final-version appointment probes (English except labelled Urdu), Claude Haiku 5.5 / low effort:

| TTS | First worker PCM, first turn | First worker PCM, second turn | Claude TTFT, second turn |
| --- | ---: | ---: | ---: |
| Cartesia | 1,873 ms | 1,499 ms | 802 ms |
| ElevenLabs | 2,227 ms | 2,211 ms | 1,134 ms |
| Rime Coda | 1,795 ms | 1,885 ms | 961 ms |
| Uplift (Urdu, after warm-up fix) | 2,047 ms | 1,531 ms | 991 ms |

Cartesia and ElevenLabs reported reused TTS connections. Uplift's earlier probe
exposed the warm-up defect; the final probe completed without an unawaited-coroutine
warning. Rime's earlier Arcana probe is not a Coda measurement.
The default Uplift path, without humanization, also completed a live Urdu turn:
2,214 ms request-to-first-worker-PCM, including 1,053 ms Claude TTFT. Its regression
test proves PCM is delivered while the upstream text input remains open.

The model-only HTTP/2 probe confirmed actual `HTTP/2` negotiation and a real
1,135-token cache read. TTFT was 1,155 / 1,379 ms even with caching. Other paired
requests reached approximately 800 ms Claude TTFT. Caching and HTTP/2 do not
guarantee that every response starts sooner.

One synthetic English STT fixture, with connection setup excluded:

| STT | Event after last voiced source window |
| --- | ---: |
| Deepgram Nova | final transcript 698 ms |
| Deepgram Flux | eager preflight 1,688 ms; final 1,934 ms |
| Gladia | final transcript 1,227 ms |

The source boundary is an RMS threshold on a synthetic WAV, not a human-labelled
end of speech. These samples are not accuracy comparisons or a reason to switch
provider defaults. A live Flux eager draft may overlap model work with finalization;
its full finalization time must not simply be added to an overlapping LLM duration.

**Under one second end-to-end is not demonstrated.** Text-to-worker-PCM excludes
STT, turn commitment, network delivery and receiver playout. It cannot establish
what a browser listener or phone caller hears. Some measured Claude first-text
times already exceed the entire one-second budget. Deployment placement, provider
latency/jitter, actual prompts and tools still require room-correlated live traces.

A separate two-request live probe changed trusted system guidance between requests
and received 1,135 cache-read tokens in both, with 940 / 974 ms TTFT. This verifies
that the stable-prefix cache survives the changing suffix.

## Activation and rollback

Install the updated worker requirements and start/redeploy the updated worker using
the normal deployment workflow. Existing running processes do not pick up these
edits. No client SDK API change is required.

```dotenv
UVA_CLAUDE_LOW_LATENCY=1
UVA_CLAUDE_FIRST_CHUNK_WAIT_MS=120
```

`UVA_CLAUDE_LOW_LATENCY=0` restores the previous Claude cache layout, HTTP/1.1,
first-chunk behavior and delivery-reuse scope on newly constructed sessions.
Existing Cartesia reuse and the independent Uplift warm-up correctness fix remain.
The deadline accepts finite values from 30 to 500 ms; invalid values fall back to
120 ms. It never forces a split through protected values.

Existing local `.env.local` was not rewritten. It selected Haiku 5.5, low effort,
160 output tokens, Flux with eager EOT, and live Uplift. Increasing output limits
or changing models/endpointing is an explicit quality/cost decision, not a hidden
latency fix.

## Reproduce without tenant changes

Validation: the broader offline provider/humanization/interruption regression set
passed **723 tests**, with six skips and two database-required voice lookup tests
explicitly deselected. A final affected-path run after the speech-invalidation guard
passed **252 tests** (overlaps the broader set). After extending native Uplift
streaming, the affected provider/delivery/interruption run passed **327 tests**,
with three skips (also overlaps; these counts must not be summed).
Ruff and `git diff --check` passed.
Two legacy live-smoke files (`test_latency.py`, `test_interruption.py`) could not
collect because they import an unavailable top-level `config` module; they were excluded
from the offline run. This is not a full repository or live caller acceptance run.
The required `graphify update .` was attempted but failed with
`uv trampoline failed to canonicalize script path`; the graph was not refreshed.

Offline tests do not call paid providers. The scripts below require explicit
`--live`, use synthetic inputs and print metrics without response/transcript text
or credentials. They consume bounded real provider requests; they do not create
phone calls, execute business tools or write tenant records.

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_claude_latency.py --live --runs 2 --vary-guidance
.\.venv\Scripts\python.exe scripts/benchmark_claude_tts.py --live --provider cartesia --runs 2
.\.venv\Scripts\python.exe scripts/benchmark_claude_tts.py --live --provider elevenlabs --runs 2
.\.venv\Scripts\python.exe scripts/benchmark_claude_tts.py --live --provider rime --runs 2
.\.venv\Scripts\python.exe scripts/benchmark_claude_tts.py --live --provider uplift --runs 2
.\.venv\Scripts\python.exe scripts/benchmark_claude_tts.py --live --provider uplift --native --runs 1
.\.venv\Scripts\python.exe scripts/benchmark_stt_finalization.py --live --provider deepgram-flux --audio path/to/synthetic.wav
```

The pairing probe defaults to the actual humanization/delivery streaming path;
`--native` checks the default Agent path without humanization. Both use a paced
PCM sink and do not play audio or test microphone/room/phone routing. `--baseline`
on the pairing probe disables the new Claude optimizations for that process;
provider variation and cache warmness still need to be controlled for a comparison.

Provider references: [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
and [latency guidance](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency).
