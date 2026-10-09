# Provider humanization: verified codebase context

Prepared: 2026-10-08 (Asia/Karachi). Repository: `sdk-agent`. Branch inspected: `main`. Git HEAD: `c37fd73fd7bce0766496d7068c49d400f1c36e17`.

**Purpose:** give ChatGPT, Claude, or another reviewer the implementation context needed to produce a humanization audit and further provider research. This document describes the current code and identifies questions to investigate; it does not claim that the desired humanization quality has already been achieved.

**Product goal:** an extremely humanized, expressive, engaging voice agent that listens accurately, understands the caller, responds naturally, starts useful audio promptly, pauses appropriately, handles interruption and correction gracefully, and maintains conversational continuity. Humanization covers STT, turn handling, LLM wording/reasoning, TTS delivery, tools, and the audio transport together. More emotion tags or lower latency alone do not establish success.

**Ownership requirement:** the reusable humanization policy should live on the SDK/platform side, so a customer integrating this system does not have to implement their own prompt, prosody, endpointing, or interruption engine. Customer business facts and business tools remain inputs. Browser permissions, playback, microphone hardware, host endpoint performance, carrier/network conditions, and deployment region still affect the experience.

## 1. Evidence boundary and how to use this document

The evidence here comes from implementation files in `worker/`, `worker/providers/`, `worker/humanization/`, `tenant_portal_api/`, `control_plane/`, `sdk/`, `sdk-server/`, the current integration test application, installed dependency source, and relevant tests. Existing `docs/` reports and plans were **not read as implementation evidence**. Comments inside code were checked against executable branches where relevant.

The working tree was already dirty, including `worker/main.py`, `worker/session_close.py`, `worker/telephony_runtime.py`, and portal/telephony files. This document describes the inspected working tree, including those changes, rather than assuming HEAD alone reproduces it. Existing changes were preserved. `graphify-out/graph.json` was absent, so graph queries were not available. This task adds documentation only.

Evidence labels used below:

- **Verified in source:** an inspected definition, branch, call site, or installed dependency behavior.
- **Verified by focused tests:** an existing regression test ran successfully during this review.
- **Audit concern / inference:** a consequence or possible failure inferred from code; its user-visible impact needs a targeted runtime test.
- **Not verified:** live provider availability, current vendor support, deployment configuration, actual DB rows, real network timings, heard audio quality, or conversational quality.

Model names in this file are **strings currently configured by this repository**. References in comments to retired models, vendor performance, account limits, supported emotions, or upgrade versions are not independent current vendor verification. The downstream research should check primary vendor documentation and the exact installed plugin before treating those claims as current.

## 2. System boundaries and response flow

There are two relevant SDK packages:

| Surface | Actual responsibility | Humanization implication |
| --- | --- | --- |
| `sdk/`, package `@awaazlabs-uva/voice` (manifest version `1.1.0`) | Browser microphone, host session endpoint, LiveKit connection, remote audio playback, transcripts and events | Applies browser capture defaults and transports the conversation; it does not construct STT/LLM/TTS or compose the humanization prompt |
| `sdk-server/`, package `@awaazlabs-uva/agents` (manifest version `0.1.0`) | Backend-only HMAC client for agent configuration and provider capabilities | Lets the host create/update provider and voice settings; validated settings are persisted for the worker |
| `tenant_portal_api/` | Agent configuration validation/persistence and capability exposure | Determines which provider/language/model/voice/options combinations a client can actually select |
| `control_plane/` | Session minting, identity and agent dispatch | Influences connection/setup latency and can forward a greeting override |
| `worker/` | LiveKit agent session and provider pipeline | Owns the principal humanization behavior and response latency controls |

```text
Host backend uses agents SDK / machine agent API
    -> validate language + providers + models + voice + options
    -> persist agents row and voice reference

Browser voice SDK
    -> host-owned sessionEndpoint
    -> control-plane mint + agent dispatch
    -> LiveKit room + microphone + remote audio

Worker job
    -> resolve tenant/agent identity and audio channel
    -> load AgentConfig + resolve vendor voice ID
    -> effective-provider resolution (configured providers remain sticky)
    -> provider registry/cache constructs STT + LLM + TTS
    -> turn profile + Silero VAD + retry policy + pre-TTS transform
    -> Agent(trusted spoken policy, framed tenant persona, fixed tools)
    -> AgentSession.start(...)
    -> opening disclosure if applicable, then greeting or wait for user

In-call turn (LiveKit orchestrates the streaming and cancellation)
    user audio -> VAD/STT -> turn decision / possible speculative generation
    -> LLM text and/or tool call -> provider-specific text transform
    -> TTS audio -> LiveKit room -> browser playback or SIP/carrier audio
    -> conversation events, history cleanup, diagnostics and usage
```

Main entry points: [worker/main.py](../worker/main.py), `build_agent` at line 109, `build_session` at 219, `_await_opening_and_speak` at 478, `_tts_agent_session_extra` at 590, `_wire_session_diagnostics` at 901, `entrypoint` at 1110, and `prewarm` at 1456. The runtime uses LiveKit Agents, not an application-owned Pipecat pipeline.

`build_agent()` instantiates the standard LiveKit `Agent`. The application does not subclass it to override `stt_node`, `llm_node`, `tts_node`, or `on_user_turn_completed`. Those hooks exist in the installed framework, but a bespoke confidence-repair, emotion-state, backchannel, or delivery-planning hook is not implemented in this construction path.

## 3. Configuration and who can control it

Sources: [worker/config.py](../worker/config.py), [worker/providers/types.py](../worker/providers/types.py), [tenant_portal_api/app.py](../tenant_portal_api/app.py), [tenant_portal_api/queries.py](../tenant_portal_api/queries.py), [tenant_portal_api/provider_validation.py](../tenant_portal_api/provider_validation.py), [sdk-server/src/index.ts](../sdk-server/src/index.ts).

`AgentConfig` contains:

- Identity/business data: `agent_id`, `tenant_id`, `name`, `prompt`.
- Language and input: `agent_language`, `stt_provider`, `stt_model`, `stt_options`.
- Generation: `llm_provider`, `llm_model`, `llm_options`.
- Speech: legacy `voice_id`, `tts_provider`, `tts_voice_id`, `tts_options`.
- Opening: `greeting`, `first_speaker`.
- Business tools: `tools_base_url`, `tools_auth_secret`.
- Recording: `recording_enabled`.

There is no persisted, unified `humanization_profile`, per-agent turn-profile object, expressivity intensity, empathy state, or humanization version in this dataclass/API path. Current behavior is distributed across platform constants, prompt overlays, provider options and process environment variables.

The backend SDK exposes camelCase create/update inputs such as `agentLanguage`, `sttProvider`, `sttModel`, `sttOptions`, `llmProvider`, `llmModel`, `llmOptions`, `ttsProvider`, `ttsVoiceId`, `ttsOptions`, `greeting`, `firstSpeaker`, and tool gateway fields. It serializes these to snake_case machine API fields.

`POST /machine/agents` and `PATCH /machine/agents/{agent_id}` use the same provider resolver as the corresponding portal routes. `GET /machine/provider-capabilities` and `/portal/provider-capabilities` expose enabled providers/models and enabled voice rows. Capability responses are a selection contract, not proof of acoustic quality or live vendor availability.

Important resolution details:

- `tts_voice_id` takes priority over `voice_id` on management writes; the resolver writes the same resolved internal voice ID into both columns.
- The worker still falls back to `tts_voice_id or voice_id` and then resolves `voices.provider_voice_id`. Known `rime-arcana-` and `rime-coda-` prefixes have a local resolution shortcut.
- Config loading uses a tenant-scoped transaction with `authenticated` role and `request.jwt.claims.tenant_id`, offloaded through `asyncio.to_thread`.
- `load_agent_session_bundle()` has a process cache keyed by `(tenant_id, agent_id)`, executable TTL **30 seconds**. It caches only rows with a nonblank greeting. Comments suggesting approximately 1–2 second freshness do not match this TTL.
- `worker/db_pool.py` reuses one locked DB connection per process. This avoids repeated connection setup but serializes concurrent checkouts; contention is an audit consideration, not measured here.
- `llm_options` exists in types and cache keys, but public validation requires `{}` and the registry calls LLM builders with the model only. Arbitrary client-supplied generation settings are not honored.
- Gladia and Uplift options must currently be `{}` through this management path. They do not have per-agent pronunciation or expressive-option passthrough here.
- English CREATE defaults are Deepgram / `nova-3`, Groq / `openai/gpt-oss-20b`, Cartesia. Urdu CREATE defaults are Gladia / `default`, Gemini / `gemini-3.6-flash`, Uplift. The caller must still supply a compatible enabled voice.
- The backend SDK itself still serializes omitted `llmModel` as `gemini-2.5-flash`. Server validation accommodates this English legacy default, and the Gemini adapter can remap it. Record requested and effective model separately in experiments.

Platform-owned prompting instructs the model to treat tenant persona text as data and preserve delivery rules; it does not guarantee that the model always follows that boundary. Tenants can also select allowed provider options. A future platform-owned humanization policy must explicitly define which defaults are fixed, which bounded overrides are allowed, and how existing integrations inherit changes. That policy is a design question for the next audit, not an existing versioned feature.

## 4. Provider coverage: active path versus files merely present

Sources: [worker/providers/registry.py](../worker/providers/registry.py), [worker/providers/capabilities.py](../worker/providers/capabilities.py), [tenant_portal_api/provider_capabilities.py](../tenant_portal_api/provider_capabilities.py), [worker/factories.py](../worker/factories.py).

| Layer | Urdu (`ur`) selectable in source | English (`en`) selectable in source | Present but not registered/selectable in the normal session path |
| --- | --- | --- | --- |
| STT | Gladia, model `default` | Gladia `default`; Deepgram `nova-3` | Soniox adapter and legacy factory branch |
| LLM | Gemini `gemini-3.6-flash` | Gemini `gemini-3.6-flash`; Groq `openai/gpt-oss-20b` / `openai/gpt-oss-120b` | No additional LLM provider branch in this registry |
| TTS | Uplift | Cartesia, ElevenLabs, Rime | Fish Audio adapter, option resolver, spoken overlay and sanitizer |

TTS voice availability also requires the actual `voices` row to have matching provider/language, `rollout_state='enabled'`, and `enabled=true`. No live catalogue rows were queried during this review.

The session registry has no Fish Audio or Soniox branch. Calling it with those IDs raises `UnsupportedProviderError`. The Fish adapter docstring saying “enabled for en” is not evidence that a tenant session can select it. Soniox is also absent from `requirements.txt`.

`worker/factories.py` is a legacy compatibility wrapper; `build_session()` uses `build_components_cached()` -> the provider registry. Auditing only factories would miss the real per-agent path.

`resolve_effective_providers()` calls the historical `force_cartesia_for_telephony`, `force_groq_for_telephony`, and `force_groq_for_english_webrtc` helpers. Their current implementations are **no-ops** in [worker/telephony_tts.py](../worker/telephony_tts.py). Configured STT/LLM/TTS remain selected on both channels. `UVA_FORCE_GROQ_ENGLISH` is deprecated/ignored. LLM **model alias remapping** remains separate from provider selection.

## 5. LLM humanization and conversational output

Sources: [worker/humanization/spoken.py](../worker/humanization/spoken.py), [worker/cartesia_spoken_output.py](../worker/cartesia_spoken_output.py), [worker/rime_spoken_output.py](../worker/rime_spoken_output.py), `worker/main.py::build_agent`.

### 5.1 Prompt composition and trust boundary

The trusted instruction body is composed in this order:

```text
SYSTEM_INSTRUCTIONS_BASE
+ CLIENT_TOOLS_DISCIPLINE (only when a tool gateway resolves)
+ UNIVERSAL_SPOKEN_RULES
+ LLM overlay (Groq or Gemini)
+ language overlay (Urdu when applicable)
+ TTS delivery overlay
+ main.py response-language directive
```

The tenant persona is separate: `ChatContext.add_message(role='system', content=_PERSONA_FRAME + persona_prompt)`. Its framing says that persona facts/tone are data, not authority for tool definitions or platform delivery rules. It is nevertheless an LLM system-role message; descriptive framing is not a hard sandbox or proof against prompt injection.

### 5.2 Shared response rules

The current universal prompt asks for one or two short spoken sentences, answering the present question, short follow-ups, ordinary wording/contractions, and no corporate filler, repeated paraphrase, catalogue dump, markdown, headings, bullets or emoji. It asks for occasional brief hesitation on casual turns, avoiding repeated fillers and fillers on firm facts.

The base prompt also says to begin the first clause promptly, speak a brief line before a tool, avoid tools for greetings/small talk or facts already in the persona, and use tools only when needed. Its separate instruction preferring “two or three short sentences” is inconsistent with the universal “one or two” rule. The next audit should resolve the desired response-length policy.

These are model instructions, not hard runtime enforcement of sentence count, repetition, filler frequency, emotion transitions, or timely pre-tool speech. Sanitizers remove some formatting; they do not rewrite an unhelpful answer into a natural one.

### 5.3 Language behavior

Urdu has a dedicated language overlay: Pakistani Urdu, proper Urdu script rather than Roman Urdu, simple oral narration, concise replies, spoken dates/numbers where natural, clear English brands/codes/emails, no invented facts, and no English/Cartesia emotion markup. Both this overlay and `_language_directive()` constrain response language.

The directive permits language switching when the caller explicitly asks, while STT remains configured with its selected language. In particular, Gladia uses a single language and `code_switching=False`. Natural bilingual conversations therefore need a separate input/output-language audit; a permissive response-language sentence does not implement bilingual recognition.

### 5.4 Generation settings actually sent

| Adapter | Executable settings | Controls and limits |
| --- | --- | --- |
| `worker/providers/llm/gemini.py` | `temperature=0.35`, `max_output_tokens=180`, Google HTTP timeout `30_000` ms; Gemini-3 strings use `ThinkingConfig(thinking_level=...)`, other strings try `thinking_budget=0` | `GEMINI_THINKING_LEVEL` defaults to `minimal`; accepted values `minimal`, `low`, `medium`, `high`. `GEMINI_LLM_MODEL` fills empty/deprecated IDs; it is not an unconditional override of every explicit model |
| `worker/providers/llm/groq.py` | HTTP timeout 30 seconds, underlying client `max_retries=0`, default completion cap 96, `reasoning_effort='low'` for `openai/gpt-oss*`; a remaining `qwen/` branch uses `none` | `GROQ_MAX_COMPLETION_TOKENS` defaults to 96 and is parsed at import. `GROQ_LLM_MODEL` supplies empty/dead-model replacements; otherwise the requested model is retained. No explicit temperature setting in this adapter |

Gemini alias list includes the 2.0/2.5 Flash variants and `gemini-3.1-flash-lite`; Groq remaps listed legacy Llama/Qwen/Kimi IDs. The adapters log requested -> effective model. Their statements about model retirement and vendor speed were not validated against vendors in this task.

The cap can affect not just reply length but structured tool calls, expressive tags and reasoning/output budgets. Whether these exact settings preserve good conversation, Urdu phrasing, factual accuracy and tool arguments is not established by unit tests.

### 5.5 Persona compaction and history

[worker/prompt_compact.py](../worker/prompt_compact.py) compacts **Groq only** before persona framing. `GROQ_PROMPT_SOFT_CHARS` defaults to 3000. Despite its name, the code enforces a hard character ceiling. It removes structured voice-duplicate Section 3, preserves/slims recognized business/accuracy/security/intake sections, trims a knowledge digest, and may finally truncate the entire result. Unstructured prompts are also truncated. Facts late in a large persona can therefore be lost; this is a source-derived concern requiring representative tenant prompts.

[worker/humanization/history.py](../worker/humanization/history.py) mutates assistant message content to plain text on `conversation_item_added` and truncates `session.history` with `UVA_CHAT_HISTORY_MAX_ITEMS` default **48**. `0`/`off` disables it; valid positive values below 8 are raised to 8. The installed `ChatContext.truncate()` keeps the last N items, removes leading tool items and may reinsert one instruction message, so it can retain N+1 items. It is an item count, not a token budget.

**Important context distinction verified in installed source:** `AgentSession.history` returns the session's `_chat_ctx`; generation uses the current agent's chat context. LiveKit inserts the same newly committed message object into both histories, so mutating that object's text can affect both. Truncating the session history list does not itself truncate the separate agent history list. The current helper does not call `current_agent.update_chat_ctx()`. Therefore do not claim that this helper proves bounded LLM request history or reduced long-call token use. Its unit test uses a fake session exposing one history object.

The shutdown transcript is built from `session.history.messages()` in [worker/session_close.py](../worker/session_close.py). **Audit concern:** truncating that same session history can omit earlier transcript turns. Confirm the desired full-session transcript and context retention semantics with a long conversation.

## 6. STT output, endpointing and turn taking

Sources: [worker/providers/stt/gladia.py](../worker/providers/stt/gladia.py), [worker/providers/stt/deepgram.py](../worker/providers/stt/deepgram.py), [worker/humanization/turn.py](../worker/humanization/turn.py), [worker/latency.py](../worker/latency.py).

### 6.1 Gladia

The active builder calls `gladia.STT(languages=[agent_language], code_switching=False)`. The registry does not pass `stt_options` to it. The tenant validation layer accepts only empty options. The repository does not add a custom transcript-normalization/confidence-repair stage in `build_agent()`.

Historical CER figures in Gladia comments belong to an older integration and were not reproduced. They are not current benchmark evidence. The default `GLADIA_MODE` fixture flag set by the test harness is not read by this active Gladia builder; do not assume it makes the real adapter a fixture.

### 6.2 Deepgram Nova

For English, `en` is sent as `en-US`. The active constructor receives:

```python
deepgram.STT(
    model=cfg.stt_model,  # normally nova-3
    language="en-US",
    no_delay=True,
    endpointing_ms=resolved_endpointing,
    interim_results=True,
    smart_format=False,
)
```

Endpointing resolution: stored `stt_options.endpointing_ms` -> `UVA_DEEPGRAM_ENDPOINTING_MS` -> **100 ms**. Invalid/nonpositive runtime values fall back to 100. The adapter docstring saying a 200 ms default is stale relative to the resolver and passing tests.

API validation permits `endpointing_ms` from 0 to 5000 using `int(...)`, while the runtime treats 0 as fallback 100. Validation does not strictly reject booleans or all fractional/coercible values. Document actual effective values in experiments; do not infer 0 disables endpointing.

With `smart_format=False`, downstream handling of names, numbers, dates and codes merits testing. The prompt may request spoken words or spelling, but no provider-independent semantic normalization stage was found in the response construction path.

### 6.3 Deepgram Flux experiment

The mode comes from options `stt_mode` / internal alias `backend`, then `UVA_DEEPGRAM_STT_MODE`, then Nova. Public validation exposes `stt_mode`, not `backend`.

- English Flux constructs `deepgram.STTv2(model='flux-general-en', sample_rate=16000)`.
- Non-English Flux requests log a fallback to Nova within the Deepgram adapter. This is a backend fallback, not a different provider.
- Eager EOT is disabled by default and always disabled for Groq by `build_session()`'s LLM-aware resolution.
- Gemini/non-Groq eager experiments can use `UVA_DEEPGRAM_FLUX_EAGER_EOT=1` or stored `flux_eager_eot=True`. Explicit stored False disables it.
- Eager threshold comes from options -> `UVA_DEEPGRAM_FLUX_EAGER_EOT_THRESHOLD` -> 0.5; the resolver accepts 0.3–0.9 and falls back to 0.5 otherwise.
- Above 0.7, the adapter also raises `eot_threshold`, bounded at 0.9.
- Installed `stt_v2.py` maps `EagerEndOfTurn` to `PREFLIGHT_TRANSCRIPT`, `TurnResumed` to interim text, and `EndOfTurn` to final text plus end-of-speech.

The portal allowlists `flux_eager_eot` and `eager_eot_threshold` but does not validate their value types/ranges as thoroughly as the resolver. Direct adapter calls can differ from the session path because the session folds LLM-aware resolved values into options first.

### 6.4 Effective turn defaults

The runtime uses `build_turn_profile()`, not the standalone dataclass defaults. Both channels have endpointing min/max **0.12 / 1.2 seconds**, `turn_detection='stt'`, interruptions enabled, false-interruption resume **False**, false-interruption timeout **0.6 seconds**, and speculative maximum speech duration **12 seconds**.

| Effective combination | Preemptive LLM | Preemptive TTS | Speculative retries | Interruption min duration | Discard audio during uninterruptible speech |
| --- | --- | --- | --- | --- | --- |
| WebRTC, non-Groq | True | True | 3 | 0.65 s | True |
| Telephony, non-Groq | True | True | 2 | 0.55 s | False |
| WebRTC, Groq | False | False | 0 | 0.65 s | True |
| Telephony, Groq | False | False | 0 | 0.55 s | False |

These are session policy inputs; the actual speculative trigger still depends on the STT/framework behavior. Enabling a flag does not prove that useful speculative work occurs on a given Gladia/Nova/Flux turn.

Silero VAD settings in `worker/latency.py`: `min_speech_duration=0.12`, `min_silence_duration=0.32`, `prefix_padding_duration=0.32`, `activation_threshold=0.45`. These timers overlap with other turn logic; they should not be summed into a presumed fixed response delay.

`UVA_INTERRUPTION_MODE` defaults to `vad`; `adaptive` opts into the framework adaptive detector. Invalid values resolve to `vad`. The reason given in comments is avoiding cloud-detector startup latency, but this task did not measure the difference.

`UVA_TURN_DETECTOR=off` is the default. `v1-mini` / `v1` materialize `livekit.agents.inference.TurnDetector(version=...)`. The code checks an explicit language list and rejects Urdu/unsupported languages; current selectable language coverage makes this primarily an English experiment. It does not enable Urdu turn prediction.

### 6.5 Interruptions and conversational recovery

`wire_barge_in_flush()` tracks user/agent speaking states and may force `session.interrupt(force=True)` while the agent speaks. Force flushing defaults **off for WebRTC, on for telephony**, overridden by `UVA_FORCE_BARGE_IN_FLUSH`. It skips force flushing while `userdata.opening_active` is true.

Native interruption remains configured even when force flushing is off. Opening greetings are interruptible by default through `UVA_GREETING_INTERRUPTIBLE=1`; `0` locks them. Comments mention false-interruption resume as protection, but executable turn defaults disable that resume behavior. Echo, a short “mm-hm,” real corrections, noise and silence after interruption all need listening tests. The application has no explicit distinction between a backchannel and an interruption in this handler.

## 7. TTS delivery: settings, streaming and audio format

### 7.1 Cartesia

Sources: [worker/providers/tts/cartesia.py](../worker/providers/tts/cartesia.py), [worker/providers/tts/cartesia_options.py](../worker/providers/tts/cartesia_options.py), [worker/cartesia_spoken_output.py](../worker/cartesia_spoken_output.py), [worker/cartesia_spoken_sanitize.py](../worker/cartesia_spoken_sanitize.py).

Executable platform defaults: model **`sonic-3.5`**, speed **0.95**, `expressive=False`, `spoken_style='manual_ssml'`. The baseline emotion list `['calm', 'content']` is sent only for light style or an explicit emotion override; manual SSML omits constructor emotion by default so per-turn tags can control delivery.

Allowed overrides: `model`, `speed` (0.6–1.5), `volume` (0.5–2.0), nonempty `emotion` string/list, `expressive` boolean, `spoken_style` (`manual_ssml` / `light`). Model and emotion strings are not vendor capability allowlists. Stored `model` wins; `CARTESIA_TTS_MODEL` fills an omitted model; then the code default applies. Listed Sonic 3.6 experiment IDs are opt-in strings, not proof they are available today.

Manual delivery prompt asks for one complete emotion tag before nearly every reply, contextual emotion choice and rotation, bounded casual fillers, 250–400 ms example breaks, `<spell>` for IDs/phone numbers, and appropriate `[laughter]`. It does not enforce allowed emotions, maximum break duration, or emotion rotation in executable state.

Light style uses a plain-oriented overlay and constructor baseline emotion. **Prompt mismatch to audit:** it currently reuses `CARTESIA_SPOKEN_OUTPUT_RULES_EXPRESSIVE`, whose wording says “LiveKit injects delivery tags,” even though light mode does not enable that injection.

The installed `AgentSession` has no public `expressive` constructor parameter and sets `_expressive=False`. Its internal expressive resolver also requires `inference.TTS`; this repository constructs direct `cartesia.TTS`. Therefore `tts_options.expressive=True` does not activate that framework feature on the inspected installation. It logs a warning and uses the manual profile unless light style was separately chosen. A future signature-only availability check would still need to verify the actual TTS type and injection path.

Cartesia uses a customized blingfire sentence tokenizer: `min_sentence_len=1`, `stream_context_len=1`, `min_token_len=1`, `max_token_len=100`, `retain_format=True`, `xml_aware=True`. It is still tokenizer-mediated streaming, not a guarantee of sending every LLM token immediately. `word_timestamps=False`; the session also sets `use_tts_aligned_transcript=False`.

**Both channels request linear PCM `pcm_s16le` at 16 kHz.** The adapter's old docstring referring to telephony mu-law/8 kHz disagrees with the option resolver. Installed Cartesia emitters initialize `mime_type='audio/pcm'`; the current code relies on the downstream SIP path for carrier format conversion. No PSTN acoustic proof was produced here.

### 7.2 Rime

Sources: [worker/providers/tts/rime.py](../worker/providers/tts/rime.py), [worker/providers/tts/rime_options.py](../worker/providers/tts/rime_options.py), [worker/rime_spoken_output.py](../worker/rime_spoken_output.py), [worker/rime_spoken_sanitize.py](../worker/rime_spoken_sanitize.py).

Defaults: **`arcana`**, `speed_alpha=1.1`, `use_websocket=True`, `segment='immediate'`. A stale adapter comment says Coda; executable defaults and catalogue-oriented logic say Arcana. English maps to `lang='eng'`; other languages raise. The voice constructor parameter is `speaker`.

Allowed overrides: `model` in `arcana`, `coda`, `mistv2`, `mistv3`; `speed_alpha` and `time_scale_factor` each 0.5–2.0. Coda/Mist do not inherit Arcana speed unless the caller explicitly supplies it. `time_scale_factor` is only passed when WebSocket mode is off, while this resolver always defaults WebSocket on and does not expose a mode override. Thus that accepted field currently has no effect through the ordinary configuration path.

Rime audio is PCM at **16 kHz WebRTC / 8 kHz telephony**. The adapter filters kwargs against the installed constructor signature. Installed source supports WebSocket, immediate segmentation and those constructor fields; that does not validate every model/speaker pairing. An explicit non-Arcana model can still be paired with an Arcana catalogue speaker and needs provider verification.

The current Rime prompt forbids SSML and bracket stage cues for **all** Rime model choices. It permits `spell(ID)`, punctuation/rare ellipses and at most one disfluency per reply. Sanitization strips Mist numeric pause markup too. Selecting Mist therefore does not select a model-specific expressive prompt/sanitizer.

### 7.3 ElevenLabs

Sources: [worker/providers/tts/elevenlabs.py](../worker/providers/tts/elevenlabs.py), [worker/providers/tts/elevenlabs_options.py](../worker/providers/tts/elevenlabs_options.py), [worker/elevenlabs_spoken_sanitize.py](../worker/elevenlabs_spoken_sanitize.py).

Repository defaults: model **`eleven_flash_v2_5`**, `auto_mode=True`, text normalization **off**, SSML parsing **False**, spoken style **plain**. Voice settings: stability **0.5**, similarity boost **0.75**, style **0.25**, speed **1.0**, speaker boost **False**. These differ from the plugin defaults mentioned in comments.

Allowed overrides: `model`, `voice_settings`, `auto_mode`, `apply_text_normalization` (`auto` / `off` / `on`), `enable_ssml_parsing`, `spoken_style` (`plain` / gated `audio_tags`). Nested voice-setting values are checked for numeric/boolean type but not bounded to provider-valid numeric ranges here. Constructor kwargs are filtered against the installed signature.

The installed plugin sends streaming requests to `multi-stream-input`, has `eleven_v3` in its model literal, but does not have a `text-to-dialogue` route or `eleven_v3_conversational` literal. The local availability check requires both of the latter. Consequently this repository rejects `eleven_v3*` model overrides and `spoken_style='audio_tags'` on this installation. Do not claim current v3 expressivity merely because a literal/model name exists.

The enabled path uses plain text, punctuation for prosody and no Cartesia/bracket cues. A future gated audio-tag sanitizer has a small laugh/sigh/exhale/throat-clearing allowlist. This is implemented conditional code, not an enabled current feature. The adapter does not choose a different sample rate by channel; plugin defaults apply.

### 7.4 Uplift / Urdu

Sources: [worker/providers/tts/uplift.py](../worker/providers/tts/uplift.py), [worker/uplift_spoken_sanitize.py](../worker/uplift_spoken_sanitize.py), [services/tts_cache.py](../services/tts_cache.py).

`UPLIFT_MODE` defaults to **fixture**. Fixture TTS is nonstreaming, reads voice/text-matched WAV data, emits PCM using 22,050 Hz / mono assumptions and `wav[44:]`, and raises on a cache miss rather than silently making a live call. It is not evidence of live prosody or latency. `record` / `live` instantiate `upliftai.TTS(voice_id=..., output_format='PCM_22050_16', phrase_replacement_config_id=...)`. An unrecognized mode has no explicit final exception branch and can return `None`; validate effective runtime mode.

Phrase replacement precedence: `UPLIFT_DISABLE_PHRASE_CONFIG=1` disables; otherwise explicit `UPLIFT_PHRASE_CONFIG_ID`; otherwise, only with `UPLIFT_USE_PHRASE_CONFIG_FILE=1`, read `.uplift_phrase_config`. An explicitly empty ID resolves to none. This is worker/account configuration, not a per-tenant dictionary API. The account/config-file contents were not opened or verified.

The Uplift prompt asks for plain oral Urdu, brief turns and no foreign delivery markup. No platform-level Uplift emotion/speed/delivery option schema is passed through the registry. Natural Urdu expression therefore currently depends on wording, voice/provider behavior and optional phrase replacement rather than an implemented dynamic prosody controller.

### 7.5 Fish Audio and Soniox research boundary

Fish has code for `s2.1-pro`, `latency_mode='balanced'`, plain/restrained style, optional speed/volume, and a restrained bracket allowlist. Its sanitizer allows exact entries or cues whose first word is allowlisted; the prompt and sanitizer lists are not identical. It is not reachable through the normal provider registry/capabilities, so it must be treated as an unexposed adapter candidate, not current tenant functionality.

Soniox has a minimal `soniox.STT()` adapter and a legacy factory branch, but no registry/capability entry or pinned requirement. The next research can evaluate these providers, but must distinguish integration work from tuning an existing selectable provider.

## 8. Streaming text transformations and transcript integrity

Sources: [worker/spoken_sanitize.py](../worker/spoken_sanitize.py), [worker/plain_spoken_sanitize.py](../worker/plain_spoken_sanitize.py), provider sanitizers listed above, `main.py::_tts_agent_session_extra`.

Each recognized TTS provider selects its own whole-string sanitizer, wrapped by `make_stream_sanitizer()` and passed as `tts_text_transforms` when the installed session supports the parameter. The transform buffers an unfinished `<...>` or `[...]` tail until it closes. An incomplete-only buffer exceeding 256 characters is flushed through the whole-string sanitizer; remaining text is also flushed at stream end.

| Provider | Kept / transformed | Removed |
| --- | --- | --- |
| Cartesia | Complete recognized `<break>`, `<emotion>`, `<spell>`, `<speed>`, `<volume>` tags and exact `[laughter]` | Markdown markers, bullets/numbered-list prefixes, emoji, other bracket cues |
| Rime | `spell(...)`; whole-string `<spell>X</spell>` converted to `spell(X)` | Cartesia tags, Mist numeric pauses, bracket cues, markdown markers/bullets and emoji |
| ElevenLabs | Plain text; small audio-tag allowlist only when gated v3 tag mode is available | Foreign tags, most/all brackets, markdown/URLs/emoji |
| Uplift | Plain language text | Foreign delivery tags, brackets, markdown/URLs/emoji |
| Fish (unexposed) | Plain or restrained bracket mode | Foreign XML, disallowed brackets, markdown/URLs/emoji |

The plain helper strips Markdown links/URLs and formatting. Cartesia and Rime have separate cleanup implementations and do not have identical URL, ordered-list, malformed-tag, or whitespace handling. Sanitization is not a semantic guarantee: preserving tag-shaped text does not validate it against the provider's actual grammar.

**Streaming audit concerns:**

- Buffering an unfinished tag is different from buffering an entire paired construct such as `<spell>...</spell>` or `spell(...)`. Opening and closing pieces can be processed independently, so whole-string conversion tests do not prove arbitrary streamed spell conversion.
- Some sanitizers call `.strip()` on every emitted piece. Word/space chunk boundaries can therefore affect the concatenated text. Test exact reconstructed text under different chunk splits, including Urdu and identifiers.
- A malformed tag that is never closed can stall buffered text or survive the overflow/end-of-stream fallback. The existing split-emotion regression proves one well-formed split case, not all malformed cases.
- Cartesia's tokenizer may further buffer transformed text for punctuation/XML safety. Minimum token settings alone do not establish first meaningful audio time or good clause-level prosody.

History/DB transcript sanitization removes TTS-only markup separately. The browser SDK forwards LiveKit transcript segment text verbatim; it does not run the worker sanitizer on every event. Dashboard Test Studio imports its own `stripTranscriptMarkup` helper. Audio text, model history, transport transcripts and final stored transcripts are distinct evidence surfaces.

## 9. Openings, warm-up and connection latency

Sources: [worker/session_opening.py](../worker/session_opening.py), [worker/greeting_cache.py](../worker/greeting_cache.py), `worker/main.py`, `worker/latency.py`, [worker/provider_client_cache.py](../worker/provider_client_cache.py).

Opening resolution:

1. `first_speaker != 'agent'` -> wait for caller.
2. Nonblank greeting surviving cleanup -> static `session.say()`; no LLM greeting request.
3. Otherwise -> `session.generate_reply()` with platform greeting instructions.

Management accepts `first_speaker='agent'|'user'` and at most **500 greeting characters**. A mint/dispatch greeting override can replace the loaded greeting and set first speaker to agent for that session. Greetings remain spoken data, not appended to trusted instructions.

Cartesia static greetings are sanitized and then enriched with a content emotion tag and, when two sentences are detected, a 300 ms break, unless markup is already present or light/expressive style was selected. Other TTS providers do not receive that enrichment.

The process-local greeting PCM cache has maximum **32 entries**, LRU eviction and no TTL. The key includes agent ID, TTS provider, resolved voice, greeting hash, channel and stored TTS-option fingerprint. Cache hits replay cloned audio frames through `session.say(..., audio=...)`.

Misses start/join a single-flight synthesis request and collect the greeting's audio frames before playback. The opening waits up to **5 seconds** for this synthesis; if unavailable, it falls back to live `say()`. Because the waiting uses `asyncio.shield`, a timed-out synthesis can continue while fallback requests another synthesis. The “single-flight” normal path therefore does not prove absence of duplication on timeout.

The key fingerprints stored options, not every effective environment setting. A process model/default or phrase-config change can require cache invalidation/restart. The in-flight map and PCM cache are process-global while provider clients are thread-local; cross-thread/event-loop behavior deserves a concurrency test, especially on the Windows thread runner.

Provider warm-up:

- TTS/STT `prewarm()` hooks run on the event-loop thread if available.
- Static say uses PCM synthesis/cache instead of TTS prewarm. Interruptible openings warm STT in the background; locked static openings defer STT warm-up until after applying the opening.
- Generated greeting waits up to **2 seconds** on selected TTS/STT prewarm.
- LLM warm-up runs in the background after the selected warm steps, with a 12-second wrapper budget. `await_llm` is accepted but explicitly ignored.
- Groq warm-up is skipped. Other LLM warm-up sends `ok`, consumes the first stream chunk and closes; the comment calling this “one-token” is not a hard output-token cap on that request.
- Framework/plugin modules, Silero VAD and DB are prewarmed. Optional environment seeding can synthesize PCM and construct a default provider stack. Those flags may make real provider requests; they were not activated by this review.
- Client cache is thread-local, up to **16 entries**, keyed by language/provider/model/voice/channel and option fingerprints. It excludes tenant ID and several environment-derived settings. Credentials are process/provider-owned in the inspected builders, not browser-owned. Cache identity and lifecycle need rechecking before adding tenant BYO keys or runtime profile changes.

Entrypoint overlaps `ctx.connect()` and session building when dispatch identity is already available. The early path starts the session before awaiting full participant activation and then applies the opening. Stale-job checks, identity lookup, DB lock waits, model/plugin construction and recording behavior still contribute to setup latency.

Recording disclosure is a separate opening stage in [worker/recording_disclosure.py](../worker/recording_disclosure.py). When recording policy allows it, it calls `say(..., allow_interruptions=False)`, awaits playout, then persists consent via `asyncio.to_thread` **before** the normal greeting. It runs even with first speaker user. Measure first audio, disclosure duration and first interactive response separately. This document records behavior; it does not assess recording-consent policy.

`control_plane/warm.py` probes DB and LiveKit API; it does not synthesize a voice or prove all providers are ready. Worker readiness checks LiveKit environment presence, VAD and DB, not successful live STT/LLM/TTS operation. The worker Docker image pins Python 3.12.14 and runs `python -m worker.main start`; deployment region and actual worker environment were not inspected.

## 10. Tools and their effect on natural conversation

Sources: [worker/tools.py](../worker/tools.py), [worker/write_tool_gate.py](../worker/write_tool_gate.py), `worker/cartesia_spoken_output.py::CLIENT_TOOLS_DISCIPLINE`.

Always registered: `end_conversation_summary`, `escalate_to_human`. When a per-agent or environment tool gateway resolves, add `lookup_business_info`, `check_availability`, `book_appointment`, `reschedule_appointment`, `cancel_appointment`.

The model is prompted to speak before tools and call at most one scheduling tool per turn. The application does not implement a deterministic pre-tool acknowledgement/filler scheduler. A prompt requesting immediate speech does not prove a model emits useful audio before returning a tool call.

Client tool HTTP timeout components: connect **1 s**, read **4 s**, write **2 s**, pool **1 s**. These are component budgets, not a single 4-second wall-clock deadline. A keep-alive client is reused with 8 keep-alive / 16 total connection limits. Gateway URL/secret can come from per-agent settings or `UVA_TOOLS_BASE_URL` / `TOOL_GATEWAY_SECRET` fallbacks. Results are slimmed to a `voiceSummary`, essential flags, string result capped at 1000 characters and up to four slots.

Host business-tool processing and network latency are outside the provider itself. The platform owns when/how the agent communicates around that wait. Tool results can trigger another LLM/TTS phase, so first acknowledgement and final useful answer should be measured separately.

Writes use a deterministic propose -> user turn -> confirm gate with confirmation/idempotency tracking and verified caller ownership. Humanization changes must preserve that sequence and avoid sounding as though a proposed booking has already succeeded. User conversation events advance the gate. Lifecycle DB writes are offloaded with `asyncio.to_thread`; `end_conversation_summary` shuts down with `drain=True` after saving. `escalate_to_human` creates an escalation record; its implementation is not a live audio transfer to a human.

## 11. Latency telemetry: definitions and limits

Source: [worker/latency.py](../worker/latency.py), `RollingLatencyStats` line 561, `build_turn_latency_payload` 603, `TurnLatencyTracker` 650, `wire_turn_latency` 802.

Metrics are correlated primarily by framework `speech_id`, with `_default` fallback:

| Published field | Current source | Correct interpretation |
| --- | --- | --- |
| `sttMs` | EOU metric `transcription_delay` | Transcript availability delay after speech end; not all STT processing or an accuracy score |
| `turnMs` | EOU metric `end_of_utterance_delay` | Framework turn-commit delay after speech end |
| `llmMs`, alias `llmTtftMs` | LLM `ttft` | Provider/request first-token metric, not entire LLM reply duration |
| `ttsMs` | TTS `duration` | Synthesis/stream elapsed time, not caller playback duration |
| `ttsTtfbMs`, alias `ttsLatencyMs` | TTS `ttfb` | TTS stream first-byte/frame metric, not first audible useful word at the caller |
| `toolMs` / `toolName` | Tool wrappers plus `tool_execution_updated` timing | Accumulated pending tool durations; may span multiple tool operations |
| `e2eMs`, alias `roundTripMs` | Formula below | Diagnostic estimate/elapsed bound; not a directly measured caller first-audio interval |

Current executable formula:

```text
eouMs = max(sttMs, turnMs) when both exist; otherwise whichever exists
estimate = sum(available eouMs, llmMs, ttsTtfbMs, toolMs)
if userStoppedAt and ttsTtfbMs exist:
    e2eMs = max(estimate, monotonic_now_at_TTS_metrics_event - userStoppedAt)
else:
    e2eMs = estimate
```

`userStoppedAt` is stamped on a framework user-state change to `listening`, not on a captured acoustic reference in the customer's recording. The installed TTS base emits metrics after a chunked stream finishes or a streamed segment is final, rather than at its first frame. Thus the elapsed bound can include synthesis after first audio. With speculative generation, stage durations can also overlap; summing them is not necessarily an actual critical path.

Additional audit concerns verified from wiring:

- `_post_client_tool()` records its own duration and the tracker also records framework tool lifecycle duration. Installed LiveKit emits those lifecycle events. A gateway call can potentially contribute twice to pending tool time. Current tests cover each mechanism, not an integrated deduplication contract.
- TTS metrics trigger emission and remove the speech-ID entry. Multi-segment/multiple-request ordering or late LLM/tool metrics needs verification.
- Pending tool time is attached to the next relevant LLM/TTS metric; it has no explicit tool-to-user-turn ownership map here.
- The tracker does not exclude cancelled, interrupted, errored, partial or otherwise invalid samples using a success status.
- A standalone static TTS greeting with no matching EOU/LLM metric is intentionally skipped. The tracker is therefore not a startup first-audio measurement.
- Rolling “p50” is the median of growing per-session lists. There is no p95/p99, bounded rolling window, acoustic timestamp, transport/jitter breakdown or per-provider outcome filter in this class.
- Null/missing fields mean unavailable measurements, not zero latency. `toolMs` alone defaults to 0.

`UVA_PUBLISH_TURN_LATENCY` is **off by default**. Server INFO logs still run, but room `turn_latency` / `metrics_updated` payloads are sent only when explicitly enabled. The browser SDK has listeners for these events; that does not make them arrive by default. The SDK comment saying a breakdown is emitted on every user turn is broader than the worker's executable behavior.

No database write of this per-turn tracker payload was found in its wiring. Session transcript and usage persistence are separate; do not assume a dashboard session row contains a complete latency timeline.

For a real humanization audit, independently measure at least: acoustic user speech end -> first useful audible agent word; user pause -> turn commit; first acknowledgement -> final tool answer; interruption onset -> audio stop; recovery after false interruption; and connection start -> first audio. Keep provider TTFT/TTFB, framework timings and caller-observed timings separate.

## 12. Browser playback, integration and diagnostics

Source: [sdk/src/index.ts](../sdk/src/index.ts). The browser SDK requests `echoCancellation`, `noiseSuppression` and `autoGainControl` all True. It acquires microphone permission concurrently with session fetching and then connects to LiveKit. `connect_timing` splits **mint HTTP** from **LiveKit room.connect**, and includes room hostname/connection quality when available. It does not measure greeting arrival or audible playback.

Remote audio tracks are attached to hidden audio elements, autoplay/playsinline are set, and `play()` is attempted. `audio_blocked` reflects LiveKit playback status; a host should call `startAudio()` from a user gesture when necessary. A connected room or a TTS metric does not prove audio was heard.

Transcripts carry `id`, `text`, `final`, and `speaker`; matching IDs should replace interim/final updates. Speaking events are derived from LiveKit active speakers and emit only on changes. They are not high-resolution acoustic ground truth. Every `turn_latency` payload is also forwarded as `metrics_updated`, so a consumer listening to both must avoid treating those as two independent turns.

The inspected browser API accepts `connect({agentId, voiceId?})`; it has no client-side humanization prompt/expressivity/turn-profile constructor input. Provider settings are set on the backend agent, not negotiated as arbitrary browser credentials or parameters.

Current testing surfaces:

- [dashboard/src/app/test-studio/page.tsx](../dashboard/src/app/test-studio/page.tsx) constructs the real voice SDK and uses [tenant_portal_api/test_studio.py](../tenant_portal_api/test_studio.py), which signs control-plane `/v1/session` requests server-side. This checkout's Test Studio is not merely a simulated conversation. Its inspected listeners focus on transcript/speaking/error/playback lifecycle rather than a full stage-timing laboratory.
- [client-integration-test/frontend/src/main.ts](../client-integration-test/frontend/src/main.ts) listens for connect/latency metrics and has pipeline preparation/debug UI. [client-integration-test/backend/src/createApp.js](../client-integration-test/backend/src/createApp.js) resolves public capabilities and PATCHes language/providers/model/default voice before connecting. Its capability cache TTL is 60 seconds; it also caches applied selections. That host-side preparation time and cache behavior should be recorded separately from provider turn latency.
- The current integration picker selects pipeline identity, not a full humanization profile. Switching providers while retaining old option objects can interact with provider-specific validation; use resolved configuration snapshots in experiments.

Transport-aware research must assess browser echo versus headset use, autoplay, microphone permissions, LiveKit region/quality, and SIP/carrier bandwidth separately from TTS delivery. Improving the worker does not remove those host/environment constraints.

## 13. Failure behavior, retry policy and observability

Source: [worker/provider_retries.py](../worker/provider_retries.py). Effective session defaults for each STT/LLM/TTS `APIConnectOptions`: **max_retry=1**, retry interval **1 second**, timeout **30 seconds**. Overrides are `UVA_PROVIDER_MAX_RETRY` (0–5), `UVA_PROVIDER_RETRY_INTERVAL` (0.1–30), and `UVA_PROVIDER_CONNECT_TIMEOUT` (1–120). Invalid/out-of-range values fall back to defaults. Groq's underlying client separately sets `max_retries=0`; this does not disable framework session retries.

Recovery and perceived responsiveness need auditing together. The constructor's retry/timeout budgets do not imply a short silence budget or a deterministic spoken recovery message. Provider exceptions are logged by source/model, speech handles log failed/interrupted/completed states, and session close shuts the job down. A provider-aware fallback utterance or automatic fallback provider is not implemented in the inspected response path.

Diagnostic logs include effective pipeline identity, requested/effective LLM model, turn profile, selected audio profile, config/component/session constructor timings, cache hits, session-start timing, opening mode and prewarm/synthesis waits, agent/user states, false interruptions, speech completion and provider metrics.

[worker/transcript_logging.py](../worker/transcript_logging.py) defaults caller/agent text logging off; `UVA_LOG_TRANSCRIPTS=1` enables it with `UVA_LOG_TRANSCRIPT_CHARS` default 200. [worker/prompt_dump.py](../worker/prompt_dump.py) defaults prompt dumps off; `UVA_DUMP_PROMPTS=1` enables a local prompt bundle, optionally redirected by `UVA_DUMP_PROMPTS_PATH`. Its character/4 token estimate is approximate, not actual tokenizer accounting.

[worker/usage.py](../worker/usage.py) reads `session.usage.model_usage` and sums STT/TTS audio duration plus LLM input/output tokens for shutdown persistence. This is separate from turn latency. It is not vendor invoice reconciliation, and standalone prewarm/synthesis/cache activity should be checked for attribution before making cost comparisons.

## 14. Focused verification performed

An existing **23-file** focused Python suite completed with **185 passed, 0 skipped, 0 failed, 1 warning**, in **26.26 seconds**. The warning was Starlette/FastAPI test-client deprecation concerning `httpx`; it did not fail the suite.

Files executed:

```text
tests/test_humanization_phase1.py
tests/test_humanization_phase2.py
tests/test_humanization_phase3.py
tests/test_humanization_phase4.py
tests/test_humanization_phase5.py
tests/test_humanization_phase6.py
tests/test_humanization_phase7.py
tests/test_humanization_gap_fixes_e2e.py
tests/test_latency_phase1.py
tests/test_latency_phase2.py
tests/test_latency_phase3.py
tests/test_latency_phase4.py
tests/test_cartesia_tts_options.py
tests/test_cartesia_spoken_sanitize.py
tests/test_rime_tts_options.py
tests/test_rime_spoken_sanitize.py
tests/test_rime_spoken_output.py
tests/test_prompt_compact.py
tests/test_greeting_cache.py
tests/test_session_opening.py
tests/test_provider_retries.py
tests/test_start_path_cache.py
tests/test_fl6_turn_latency_publish.py
```

The repository `.venv` launcher failed because `pyvenv.cfg` points to a Python installation under the old `C:\Users\habib` account. Tests were run with installed `C:\Users\habiba\AppData\Local\Programs\Python\Python312\python.exe`, inserting this checkout's `.venv\Lib\site-packages` into `sys.path` and invoking `pytest.main(['-q', ...the files above...])`. The environment was not repaired or dependencies upgraded.

These tests validate composition/resolution, option defaults, selected constructor wiring, sanitizers, caches, opening logic, turn policies, retries and synthetic metrics behavior. Despite its filename, `test_humanization_gap_fixes_e2e.py` exercises local helpers/mocked components; it is not a live microphone-to-provider-to-speaker E2E call.

`tests/conftest.py` excludes paid-provider network access, and `pytest.ini` deselects `live` tests by default. The harness can convert certain failures into skips when credentials are absent or a network guard trips; the observed zero-skipped result matters. Some legacy CER/latency/interruption test modules are in `collect_ignore`, so their existence is not proof they participate in this suite. No current STT accuracy benchmark or listening score was produced.

Installed source spot checks confirmed LiveKit Agents and Cartesia/ElevenLabs metadata version **1.6.5**, the public session transform parameter, internal expressive disablement/inference requirement, TTS metric emission timing, separate session/agent contexts, in-place chat truncation, Rime WebSocket fields, and Flux transcript event mapping. The pinned requirements also list the other LiveKit provider plugins at 1.6.5, Google GenAI 2.12.1, OpenAI client 2.45.0, and LiveKit RTC 1.1.13. These are repository/local installation observations, not deployed package proof or a claim that the local files are unmodified upstream releases.

**Not run:** live provider requests, browser microphone/audio interaction, PSTN calls, listening evaluation, production latency measurement, actual tenant/voice DB inspection, full repository tests, full lint/typecheck/build, deployment checks, or current vendor research. No implementation behavior was changed for this context task.

## 15. Audit questions justified by this code

These are investigation inputs, not a finished severity-ranked audit or approved implementation plan.

| Question | Source-grounded reason | Evidence needed |
| --- | --- | --- |
| What constitutes “extremely humanized” for this product? | Current rules focus on short turns, ordinary wording, selected tags and timing flags; no scoring/acceptance model exists in this path | Define caller listening scores, task success, interruption comfort, expressivity appropriateness and language-specific expectations |
| Are measurements suitable for latency decisions? | `e2eMs` uses segment-end metrics/overlapping stage estimates and lacks outcome filtering | Correlated acoustic/first-audio timeline with interrupted/error/tool cases and p50/p95/p99 |
| Does context windowing constrain actual LLM requests? | Helper truncates session history while generation uses agent context | Inspect outbound request history through a long call; preserve full transcript separately |
| Do tags improve delivery without delaying meaningful speech? | Cartesia requires markup nearly every reply; stream transforms/tokenizer can buffer | Paired listening/latency A/B of manual/light styles with identical voices and prompts |
| Are fillers, emotion rotation and short replies natural in different situations? | Prompt rules are global and not backed by conversation state | Casual/helpful/urgent/frustrated/factual/tool scenarios; measure repetitive or misplaced cues |
| Are STT finals accurate enough to support natural repair? | Single-language Gladia, Nova formatting disabled, no custom confidence/repair hook | Names, codes, phone numbers, dates, Urdu script, English brands, noise, accents, pauses and corrections |
| Which turn policy balances pause tolerance and response speed? | 100 ms Nova endpointing, multiple VAD/session timers, different channel interruption thresholds | Trailing pauses, mid-sentence pauses, backchannels, real barge-in, echo and recovery tests |
| Can expressive provider features actually reach the selected adapter? | Cartesia framework expressivity is unavailable; ElevenLabs v3 is refused; Rime Mist shares plain rules; Fish is unregistered | Exact plugin/API path, model/voice compatibility and live acoustic evidence before exposure |
| Are streaming sanitizers exact and resilient? | Whole-string regexes operate on partial stream pieces with differing whitespace/tag policies | Arbitrary chunk-boundary/property cases, paired spelling, malformed tags, URLs and multilingual text |
| Is tool waiting communicated naturally and timed accurately? | Acknowledgement is prompt-only; wrapper and lifecycle timing both exist | Tool-call event/audio timeline, deduped execution duration, failure handling and final-answer latency |
| Are experiment/caching boundaries trustworthy? | Stored-option fingerprints omit some environment defaults; PCM/inflight globals and thread-local clients differ | Cold/warm/concurrent sessions, profile/model/voice changes and cache attribution |
| How should the platform own tuning across client integrations? | Humanization is spread across constants, environment and allowed client options | A bounded, versioned platform policy design with clear defaults/overrides and migration compatibility |

## 16. Requested downstream audit and research brief

The following can accompany this file when sending it to ChatGPT or Claude:

> Audit this voice-agent SDK/platform toward an extremely humanized, expressive and engaging agent experience. Use the attached source-grounded context as the current implementation snapshot. Humanization must be controlled primarily by the platform/worker and reusable SDK defaults so customer platforms do not need to build their own humanization engine.
>
> Cover STT accuracy and repair, turn taking, latency, speculative generation, LLM conversational quality, TTS prosody/emotion/pronunciation, streaming/chunking, tools, greetings, interruption recovery, history continuity and WebRTC/PSTN differences. Separate currently implemented behavior, disabled/unreachable features, code risks, hypotheses, and research proposals.
>
> For every code finding, identify the file/symbol, relevant evidence, user-visible consequence, confidence and smallest useful verification. If the context is insufficient, request the exact missing source or runtime artifact instead of inventing behavior. Do not treat mock tests, comments, vendor marketing, framework flags or stored model names as live proof.
>
> Research current capabilities only using primary provider/framework documentation, with URLs and access dates. Check our installed plugin path and version against those capabilities. Distinguish a provider feature, plugin support, actual platform wiring and a feature exposed through the SDK/API. Verify models, languages, voices, markup, streaming transport, pricing/cost and rate limits before using them in recommendations.
>
> Produce a prioritized audit and staged experiment plan. Define measurable listening and latency acceptance criteria, a fixed scenario corpus for English and Urdu, and cold/warm/WebRTC/PSTN/tool/interruption test matrices. Assess accuracy, task success, conversational continuity and cost alongside responsiveness; do not optimize solely for short TTFT or extra nonverbal cues. Include required evidence, instrumentation changes, implementation ownership, bounded settings, compatibility risks and rollback criteria. Do not present untested improvements as achieved results.

## 17. Source navigation for the next reviewer

This index names the concrete implementation areas to request if the reviewer receives only this Markdown file.

| Concern | Files / symbols |
| --- | --- |
| Session construction and lifecycle | `worker/main.py::{build_agent,build_session,_tts_agent_session_extra,_await_opening_and_speak,entrypoint,prewarm}` |
| Agent persistence / vendor voice mapping | `worker/config.py::{AgentConfig,load_agent_session_bundle,_load_agent_and_provider_voice,resolve_provider_voice_id_local}`, `worker/db_pool.py`, `tenant_portal_api/queries.py` |
| Provider selection and exposure | `worker/providers/{types,registry,capabilities}.py`, `worker/humanization/resolve.py`, `worker/telephony_tts.py`, `tenant_portal_api/{provider_validation,provider_capabilities}.py` |
| Universal, LLM, language and delivery rules | `worker/humanization/{spoken,types}.py`, `worker/{cartesia_spoken_output,rime_spoken_output,prompt_compact}.py` |
| STT and turn policy | `worker/providers/stt/{gladia,deepgram,soniox}.py`, `worker/humanization/turn.py`, `worker/latency.py::{VAD_OPTIONS,TURN_HANDLING_OPTIONS,wire_barge_in_flush}` |
| LLM settings | `worker/providers/llm/{gemini,groq}.py` |
| TTS settings and audio | `worker/providers/tts/{cartesia,cartesia_options,rime,rime_options,elevenlabs,elevenlabs_options,uplift,fish_audio,fish_audio_options}.py`, `services/tts_cache.py` |
| Streaming text sanitation | `worker/{spoken_sanitize,plain_spoken_sanitize,cartesia_spoken_sanitize,rime_spoken_sanitize,elevenlabs_spoken_sanitize,uplift_spoken_sanitize,fish_spoken_sanitize}.py` |
| Openings/cache/startup | `worker/{session_opening,greeting_cache,provider_client_cache,stale_jobs,recording_disclosure,recording_policy}.py`, `worker/latency.py::{schedule_provider_prewarm,prewarm_llm}`, `control_plane/app.py::{_dispatch_agent,_opening_greeting}`, `control_plane/warm.py`, `worker/health_http.py`, `docker/worker.Dockerfile` |
| Tools, confirmation and timing | `worker/{tools,write_tool_gate}.py`, `worker/latency.py::TurnLatencyTracker` |
| History, transcript, usage and debug | `worker/humanization/history.py`, `worker/{session_close,usage,prompt_dump,transcript_logging}.py`, `tenant_portal_api/queries.py` |
| Integration contract and playback | `sdk/src/index.ts`, `sdk-server/src/index.ts`, `tenant_portal_api/app.py`, `tenant_portal_api/test_studio.py`, `dashboard/src/app/test-studio/page.tsx`, `client-integration-test/{frontend/src/main.ts,backend/src/createApp.js}` |
| Dependency behavior checked locally | `.venv/Lib/site-packages/livekit/agents/voice/{agent,agent_session,agent_activity,generation,events,tool_executor}.py`, `livekit/agents/llm/chat_context.py`, `livekit/agents/tts/tts.py`, `livekit/agents/metrics/base.py`, `livekit/plugins/{cartesia,rime,elevenlabs}/tts.py`, `livekit/plugins/elevenlabs/models.py`, `livekit/plugins/deepgram/stt_v2.py` |
| Verification boundary | `requirements.txt`, `pytest.ini`, `tests/conftest.py`, the 23 executed test files listed above |
