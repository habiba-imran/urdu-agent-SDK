# Humanization fast-track Batch B verification

Date: 2026-10-09 (Asia/Karachi).

PHASE / SUBPHASE: Fast-track Batch B; original Phase 6 P0, all currently registered/selectable TTS paths.
STATUS: CODE_COMPLETE_ACTIVATION_BLOCKED.
IMPLEMENTATION GATE: PASS for the requested Batch B contract and regression scope.
ACTIVATION GATE: BLOCKED independently for Cartesia, Rime, ElevenLabs and Uplift; all language/channel lanes lack paired live evidence.
DEFAULT ENABLEMENT: baseline for every provider; all candidate renderer switches OFF.
NEXT SAFE PHASE / SUBPHASE: STOP after Batch B. Original Phase 7 not started.

## Preflight and source evidence

The supplied `C:\Users\habib\Desktop\SDK\sdk-agent` path does not exist on this host. Work used verified `C:\Users\habiba\Desktop\SDK\sdk-agent` with approved shell access. First checks captured dirty status, `main` and HEAD `c37fd73fd7bce0766496d7068c49d400f1c36e17`; no commit/branch change. Existing portal, telephony, SDK, frontend, latency and earlier-humanization work and deleted deliverables preserved.

Read the entire implementation status, universal plan invariants, original Phase 6, provider baselines and execution/gate rules. `docs/HUMANIZATION_RESEARCH_MASTER.md` is still absent; the requested relevant TTS/delivery sections could not be read. Implementation follows explicit Batch B requirements, the available plan and current source. No missing research content is assumed.

FILES READ:

- `AGENTS.md`, status, scoped plan sections, CI manifest and test network guard.
- Active provider registry/types/capabilities and Cartesia, Rime, ElevenLabs, Uplift adapters and option resolvers. Fish registration checked and absent.
- Cartesia/Rime/ElevenLabs, common/plain sanitizers, provider spoken-output instructions, platform/Groq overlays and tenant/session prompt assembly.
- `worker/humanization/{agent,runtime,state,policy,turn_plan,spoken,history}.py`, main agent/session/greeting construction, telephony TTS handling, session opening, greeting/client cache and `services/tts_cache.py`.
- Installed agents 1.6.5 Agent/AgentSession hooks, history/transcript fan-out, synthesis streams/cancellation/metrics, and all four installed plugin constructors/options/implementations. No dependency upgrade.
- Provider constructor/options/selection/sanitizer, cache/opening, installed framework, earlier humanization, write/tool safety, telemetry/latency and telephony regressions.

FILES CHANGED (relative to this chat's dirty preflight, not a clean Git checkout):

- `worker/humanization/{agent,history,spoken}.py`.
- `worker/main.py`, `worker/cartesia_spoken_output.py`, `worker/session_opening.py`, `worker/greeting_cache.py`, `worker/provider_client_cache.py`, `worker/latency.py`.
- `worker/providers/tts/uplift.py`, `services/tts_cache.py`.
- `tests/ci_unit_manifest.txt`, `tests/test_cartesia_tts.py`, `tests/test_greeting_cache.py`.
- `docs/HUMANIZATION_IMPLEMENTATION_STATUS.md`.

NEW FILES:

- `worker/humanization/delivery/{__init__,policy,intent,pronunciation,canonical,capabilities,renderers,context,cache}.py`.
- `tests/test_humanization_batch_b.py`.
- This report.

## Behavior and authority

BEHAVIOR BEFORE: provider prompt overlays owned XML/emotion/spell syntax. Legacy TTS transforms stripped provider cues differently; canonical history depended on later sanitization. Greeting/client keys did not encode renderer/pronunciation policy or all effective environment-resolved knobs. Uplift fixtures allowed a text-only fallback.

BEHAVIOR AFTER, when a provider's explicit candidate flag is selected:

1. Awaaz derives a small neutral DeliveryIntent from existing authoritative TurnPlan/platform state: affect, intensity, pace, energy, optional emphasis/pause/nonverbal, continuity identity, speech mode and interruptibility. Sensitive repair/confirmation suppresses inappropriate amusement/nonverbals. An ephemeral plain-language delivery hint requests conversational wording; business/task authority and existing write safeguards remain unchanged.
2. Candidate provider prompts no longer ask the LLM for provider markup. Buffered LLM text is canonicalized before LiveKit branches it into history, user-visible transcript and TTS. Legacy spell/XML/bracket directions are removed or unwrapped, including incomplete trailing cues. Literal emails, underscore codes, numeric facts and tool IDs/arguments/usage survive. Audit/history compatibility sanitization also protects these facts.
3. Pronunciation is separate: exact offset/source validation, non-overlap and trusted aliases; NORMAL, SPELL, ALIAS, DIGIT_GROUP and unsupported PHONEME fallback. Auto planning protects current heard/confirmed names/business/doctor entities, emails, digit phones/IDs/codes and English terms in Urdu. Names stay literal unless trusted alias/account phrase configuration exists; no phoneme/name pronunciation is guessed.
4. One renderer contract returns untouched `canonical_text`, audio-only `provider_text`, provider options, continuity identity, canonical alignment, framework-default flush hint and structural degradation reasons. It does not paraphrase business facts, mutate state, change voice/model or call providers. Invalid pronunciation plans fail to original facts; pause offsets cannot split protected spans.
5. Capabilities reflect effective model/options, actual installed constructor path/version/source hash, channel and Uplift mode/account phrase setting. Unreviewed plugin versions/models fail closed for advanced controls. Provider alignment capability is recorded separately; candidate transcript remains canonical, not a transformed provider transcript. Fast caller-side cancellation and natural nonverbals are not claimed verified.
6. Session-local synthesis invokes existing adapters with rendered text/options, preserving the selected effective model/voice. Each utterance owns and closes its provider shell, so shared cached instances are never mutated. Actual isolated-provider metrics/errors forward to the existing session component; diagnostic policy/render/pronunciation versions update without changing billing or double-counting tool duration.
7. Greeting synthesis, static/generated instructions and prewarm use the same policy boundary. Rollback retains original prompt, sanitizer, session transforms and TTS path. The baseline remains available independently per provider.

| Provider / preserved default | Candidate realization in current installed path | Safe degradation |
| --- | --- | --- |
| Cartesia / Sonic 3.5 | Audio-only verified emotion XML, protected native spell tags, bounded pause tags and modest speed option where no explicit tenant speed exists; existing voice/model/audio channel retained | Unknown model/plugin uses plain pronunciation/punctuation. No natural laugh or advanced continuation claim |
| Rime / Arcana | Shared canonical wording/affect hint, protected plain spelling/digit grouping and punctuation; existing Arcana speed_alpha and WS segment behavior preserved | Arcana native spell/speed direction lacks current account proof, so no guessed control or Cartesia XML. If an already configured Coda/Mist model is selected, capability mapping uses its audited controls/direction without switching models |
| ElevenLabs / Flash 2.5 plain | Shared conversational wording and protected plain pronunciation; existing VoiceSettings preserved, mild verified speed when unspecified | No v4/TTD/audio tags; unsupported nonverbals/phonemes omitted. Existing normalization/SSML/auto_mode/audio encoding unchanged |
| Uplift / current Urdu voice | Shared DeliveryIntent/PronunciationPlan, Urdu/plain mixed speech, punctuation and existing account phrase-replacement configuration | No English-provider tags. Fixture mode is not live support/acoustic proof; `PCM_22050_16` unchanged; unsupported controls omitted |

FEATURE FLAGS / POLICY VERSIONS:

- `UVA_TTS_RENDERER_CARTESIA`, `UVA_TTS_RENDERER_RIME`, `UVA_TTS_RENDERER_ELEVENLABS`, `UVA_TTS_RENDERER_UPLIFT` independently resolve unset/`baseline` to the existing path. The sole candidate value is `delivery_v1`; unknown values reject instead of silently activating.
- Candidate component versions: `delivery_v1`, `renderer_v1`, `pronunciation_v1`; baseline components remain `baseline`.
- No deployment/environment file enables any renderer. Existing `natural_v1` shadow request does not enable delivery, spoken clarification or bridges. Policy flags are evaluation mechanisms, not evidence of activation approval.

## Cache audit

Greeting audio and prewarm keys, and provider-client identity, now hash provider/effective model/voice/options, language/channel, available tenant scope, policy/render/pronunciation versions, installed plugin path/version/source identity. Effective environment Cartesia model, Eleven native encoding/settings and Uplift fixture/live/phrase configuration participate. Greeting text/agent identity remain separate existing key fields. No transcript or credential appears in the public key.

`services/tts_cache.py` is the existing Uplift fixture store, not a new production audio cache. Optional candidate rendered identity requires its own versioned voice/text fixture entry and refuses old or text-only PCM. Legacy callers retain legacy fixtures on rollback. No independent pre-synthesized acknowledgement/tool-bridge cache was found; bridges are disabled and use session speech. A candidate Uplift fixture must be regenerated deliberately before fixture synthesis can succeed; an old cached waveform is not reused as new-policy evidence.

## Verification

TESTS RUN / TEST RESULT:

- Final new common contract suite: **86 passed, 0 skipped/failed**, `final-contracts.xml`.
- Final 26-file focused provider/options/sanitizer/humanization/framework/tool/cache/opening/latency/telephony run: **314 passed, 0 skipped/failed**, `final-focused-offline.xml`.
- Complete current CI manifest: **481 passed, 10 skipped, 0 failed**, one existing Starlette httpx warning, `final-offline.xml`. Nine tests explicitly require a nonempty process DB URL; the existing offline SSRF `https://127.1/hook` case is skipped.
- Additional isolated `tests/test_latency_phase2.py`: **9 passed**, `latency-phase2-isolated.xml`. Its pre-existing package/sys.modules mock order conflicts in a combined run after importing the real Google plugin. Isolated evidence verifies it without changing unrelated mocks.
- Scoped Ruff PASS, including all changed Python and the new suite; existing invalid-noqa warning in main retained. CRLF-aware added-line whitespace/UTF-8 and preflight SHA-256 preservation audit PASS; see `integrity.json`.
- Required `graphify update .` attempted: existing `uv trampoline failed to canonicalize script path` failure; graph absent at preflight. No fabricated graph evidence.

The installed AgentSession tests use synthetic LLM/TTS/sinks and real public framework hooks. They verify raw provider syntax cannot enter assistant history, active context or UI transcript; renderer text reaches each provider boundary; static speech uses the renderer; isolated providers close and forward metrics once; real framework read-tool continuation preserves Batch A truth/safety. Constructor tests use dummy credentials and assert existing models/audio rates and Uplift phrase-config arguments. They make no paid synthesis request.

Paid provider network calls are blocked by the existing test guard. The focused existing provider tests additionally connect to the configured development database and create/clean their established synthetic tenant/agent fixtures via `scripts/dbconn.py` dotenv fallback; setting an empty process DB URL does not disable that fallback. This is development test execution, not a production/schema migration or deployed-backend proof. The CI manifest skips nine process-URL-dependent DB tests. No live caller/audio test or deployment occurred.

Required user assertions map to the contract suite:

1. Canonical semantic text/facts unchanged across all four provider outputs.
2. No unsupported provider markup/nonverbal cue emitted.
3. Installed framework canonical history/transcript stays plain and provider-neutral.
4. Audited native controls or plain semantic/phonetic approximations for each provider.
5. Unsupported laughter/phonemes/emphasis/unreviewed models safely degrade.
6. Provider switching preserves identical business facts and state; tool continuation retains truth.
7. Existing constructor/options/selection/sanitizer and audio-format regressions pass.
8. Effective config/policy/render/pronunciation changes produce cache misses; actual greeting PCM and Uplift stale-fixture rejection tested.
9. All provider baseline flags/prompts/transforms and legacy fixture semantics remain available.

## Limits and gates

KNOWN LIMITATIONS:

- This P0 candidate intentionally buffers complete utterances at the canonical/renderer boundary. It can delay first audio and creates isolated provider shells, with possible connection overhead. There is no incremental normalizer, new chunk planner, cancellation tuning or latency-improvement claim. That work belongs to original Phase 7 and remains untouched.
- Natural laughter, advanced emphasis/phonemes, provider continuation, subjective prosody ranking and rich energy/intensity controls are not fabricated. Rime Arcana uses shared ordinary wording/plain pronunciation; vendor controls beyond current proof remain unavailable.
- No new durable provider pronunciation dictionary or arbitrary alias configuration UI. Trusted offset aliases are supported by the contract; names remain literal without trusted mapping. Native Urdu/mixed pronunciation requires listening validation.
- Existing tenant prompt/persona and Batch A clarification/bridge activation constraints remain. Generative compliance and original Phase 6 deep provider optimization are not claimed complete.
- Missing research master, unavailable graph update and prior live baseline gaps are recorded, not substituted with fixture evidence.

UNVERIFIED LIVE ITEMS: provider acoustic behavior/deployed options, English and native Urdu/mixed review, real WebRTC/PSTN first useful word and interruption stop, long calls/continuity, concurrency/load, network/connection overhead, costs, deployment and production backend execution. No audible/default activation is authorized by deterministic tests.

Primary control references used to corroborate inspected source (not live evidence): [Cartesia SSML](https://docs.cartesia.ai/build-with-cartesia/capability-guides/ssml-tags), [Rime spell](https://docs.rime.ai/docs/spell), [Rime speed](https://docs.rime.ai/docs/speed), [Rime pronunciation](https://docs.rime.ai/platform/pronunciation-control), [ElevenLabs speed](https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/can-i-change-the-pace-of-the-voice). Current Arcana baseline is preserved despite documentation focusing on other models.

IMPLEMENTATION GATE: PASS, all four selectable providers implemented and verified at the shared contract/framework boundary.
ACTIVATION GATE: BLOCKED, provider/language/channel-specific paired live evidence still required.
DEFAULT ENABLEMENT: baseline/OFF for every renderer.
STOP: Batch B complete; original Phase 7 not started.
