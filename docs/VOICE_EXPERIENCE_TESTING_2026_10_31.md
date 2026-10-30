# Coordinated voice experience — test build

The implementation is in the shared Python worker, so it applies to SDK integrations
after that worker is updated. The browser demo is a test surface. No npm release,
database migration or automatic phone-route change is needed for these worker fixes.
The hosted worker has not been deployed by this task.

## Start the isolated browser test

The launcher preflight passed against the existing local configuration. From the
repository root:

```powershell
Set-Location C:\Users\habiba\Desktop\SDK\sdk-agent
.\.venv\Scripts\python.exe scripts/start_voice_test.py --start
```

Then open **http://localhost:5174/?voiceTest=local**.

Choose your test agent, select Claude and the desired supported STT/TTS pairing,
enable **Humanized speech** in Agent prompt, and save. Start with Claude + Cartesia.
Use **Start conversation**, allow the microphone, and unlock audio if the browser
asks. A new call picks up the settings; an existing call keeps its existing configuration.

The launcher starts a separately named worker (`uva-humanization-dev-habiba-final`),
a local control plane on 18100, a demo backend on 13100, and the demo UI on 5174.
The explicit `voiceTest=local` URL selects the local backend instead of the demo's
usual hosted control plane. A plain demo URL keeps its normal behavior. This is not
a production dispatch or a change to the configured phone-number routing.

Environment overrides exist only in child processes. Existing `.env` files are not
overwritten. The script checks occupied ports and does not terminate existing
services. It can reuse an already running demo UI. Keep the launcher terminal open;
Ctrl+C stops only its owned child processes. Logs are under the ignored directory
`tmp/voice-experience-test/<timestamp>/`.

Check configuration without starting services:

```powershell
.\.venv\Scripts\python.exe scripts/start_voice_test.py --check
```

Phone calls continue to use their configured hosted worker. To test these changes on
PSTN, update the appropriate test worker deployment through the normal deployment
workflow; this local launcher does not redirect existing inbound or outbound routes.

## What changed

| Audit gap | Implementation |
| --- | --- |
| First chunks ended at weak phrase boundaries | Prefer clause boundaries and reject English/Urdu/Roman Urdu weak ending words. Retain literal-value and unfinished-pronunciation protection. This is a conservative heuristic, not a full syntax parser. |
| Expression settings were only prompt guidance | Cartesia uses supported, subtle volume/speed guidance. ElevenLabs uses supported stability/speed controls and avoids default style-amplification overhead. Explicit saved voice settings remain authoritative unless adaptive pace is opted in. Unsupported controls remain wording fallbacks with diagnostic capability labels. |
| Persona and interruption policy were disconnected | Enabled saved personas coordinate runtime overlap classification with native pause/recovery options. An explicit baseline overlap setting still rolls back that behavior. |
| Equivalent backchannels caused different outcomes | Normalize `mm-hmm`, `mm hmm`, `uh huh`, `uh-huh`, `mhm`, `ok` and related variants. Confirmation answers and explicit stops continue to take priority. |
| Long calls grew the active Claude context | Enabled Claude personas project recent turns into an ephemeral context; older dialogue remains in session-local memory and full framework/audit history. A local read-only `recall_conversation` tool retrieves or pages through older details. Instructions, current facts, tool pairs and write/unknown outcomes are protected. The character budget is soft when protecting those records requires more space. |
| Audio gaps were unobserved | Record frame-handoff gap samples and their maximum. Record identifiable chunk transitions on segmented synthesis paths. Unobservable continuous-context chunk boundaries remain unavailable. These are worker diagnostics, not receiver-heard measurements. |
| Slow operations could leave silence | Enabled personas can issue one delayed factual receipt for a slow lookup. Suppress receipts while the caller/agent speaks, respect cooldowns, and retire only our queued receipt when its result arrives. Writes and committed effects are not cancelled by this feature. |
| Rime probe was mislabelled | Explicit Arcana/astra or Coda/lyra selection and non-secret effective TTS settings in benchmark output. Earlier Coda-labelled results are not valid Coda evidence. |
| Delivery could sound mechanical | Remove forced emotion rotation and artificial hesitation instructions. Broaden concern cues and use content-grounded question/reassurance/good-news delivery. No invented acoustic-emotion detector, random laughter or human-identity claim was added. |

Cartesia Sonic-3-family English has the most direct controls in the current
integration. Rime Arcana and Uplift still depend primarily on their selected voice,
wording and punctuation for emotional expression. No unsupported vendor controls
or unreviewed plugin upgrade were introduced to disguise those limits.

The context archive and recall tool are per session. Retrieved dialogue is quoted
DATA rather than new instructions or write authorization. Protected records can
exceed the soft context budget rather than being silently discarded.

## Verification status — read before calling this production-ready

- Full demo verification passed: **44 backend + 31 frontend tests**, typecheck,
  production build and independent installed-package checks. After adding the
  explicit local-test URL test, the targeted playground suite passed **15 tests**.
  The production frontend code was already included in the full verification.
- The broader worker run reached **752 passes, six skips and two database-test
  exclusions**, with one explicit-voice-settings assertion failing. The implementation
  was corrected to preserve saved settings; the subsequent affected suite passed
  **144 tests**. These runs overlap and must not be summed.
- Focused static checks passed on the implementation. `git diff --check` passed.
- The new native repeated pause/resume test and the final post-correction regression
  recheck were **not executed**: the latest execution approval was declined. The
  queued follow-up live probe did not start. Do not describe this as a fully green
  final regression run.
- The required graph update was attempted and failed with the existing environment
  error `uv trampoline failed to canonicalize script path`.

Live diagnostic samples used synthetic text and the actual provider adapters:

| Probe | Result and boundary |
| --- | --- |
| Claude–Cartesia concern, two-turn repeat | First worker PCM 2,010 / 1,777 ms; actual Sonic 3.5 settings reported. An earlier cold concern sample took 3,543 ms. |
| Corrected Claude–Rime Arcana/astra | First worker PCM 2,352 ms in one turn; effective model and speaker verified in output. |
| Claude–ElevenLabs concern | The probe hit its 25-second total playout timeout. The harness was updated to bound the response length, expose progress and allow 40 seconds; that diagnostic rerun has not executed. This pairing still needs a successful live retest. |

The benchmarks exclude STT and receiver playback, use a paced synthetic sink and
are not a matched statistical comparison. Under-one-second caller-heard response,
natural prosody, native Urdu quality and real microphone/PSTN barge-in are not
proven by these results. The intended next step is your listening test, followed by
the pending automated/native checks before production rollout.

## Listening checklist

Use the same selected voice and microphone across comparisons:

1. Ask a normal question; listen for a complete first phrase and a settled ending.
2. Say “mm-hmm” or “uh huh” while the agent explains something; it should avoid
   treating ordinary listener feedback as a new request. Say “yes” to an actual
   confirmation question and check that the answer is accepted.
3. Say “stop” or “wait” mid-answer, then ask a different question. Check both how
   quickly the old voice stops and whether the next reply starts cleanly.
4. Create a false interruption, let the agent continue, then interrupt deliberately.
   Repeat several times and check for stuck, overlapping or duplicated speech.
5. Express concern, then return to a neutral question. Listen for restrained,
   appropriate tone changes rather than exaggerated emotion or forced fillers.
6. Correct a phone number/date and confirm the replacement. Check precise read-back
   and that no cancelled speech repeats a business action.
7. Use a slow lookup. Any receipt should be factual and once-only; a quick lookup
   should not acquire an unnecessary receipt.
8. Continue for 20+ turns, then ask about an early preference. Check that local recall
   retrieves it and that old action outcomes are not replayed.

Record failures with the selected model/voice, approximate turn and whether you used
headphones or speakers. Worker `speech_stream_metrics` includes handoff gaps;
it must not be used as a measurement of what your speakers or phone caller heard.

## Rollback controls for new sessions

```dotenv
# Unset overlap/receipt settings follow the enabled saved persona.
UVA_OVERLAP_POLICY=baseline
UVA_TOOL_ACKNOWLEDGEMENTS=0
UVA_CLAUDE_CONTEXT_WINDOW=0
# Previous Claude transport/chunk behavior from the earlier latency work:
UVA_CLAUDE_LOW_LATENCY=0
```

Disabling the saved humanization profile retains the baseline delivery path. The
isolated development launcher explicitly enables candidate policies only in its
owned process environment; production settings were not activated by this task.

Provider control references used for the implementation:
[Cartesia controls](https://docs.cartesia.ai/build-with-cartesia/capability-guides/volume-speed-emotion)
and [ElevenLabs voice settings](https://elevenlabs.io/docs/api-reference/voices/settings/update).
