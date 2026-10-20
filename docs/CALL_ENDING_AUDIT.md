# Shared call endings

Scope: worker-owned caller intent, goodbye and transport teardown, plus browser SDK
terminal event delivery. No client-integration-specific hangup logic, schema change,
secret change, publication or deployment is included.

## Findings and fixes

1. Call completion and goodbye wording belong to the existing conversation LLM.
   `worker/call_ending.py` contains the shared platform prompt and execution checks;
   it has no caller phrase matcher or fixed closing line. The model interprets the
   whole context across platforms/languages, clarifies ambiguity and invokes
   `end_conversation_summary` after its own natural closing line. This uses the
   normal conversation generation, without an additional classifier/rewrite call.
   Local delivery cues no longer override the model with a forced CLOSE response.
2. The end tool validates the latest committed user turn, tool-generation revision,
   caller speaking state and interrupted speech handle before shutdown. It does
   not veto a model-selected end because of the caller's wording. After playout,
   it also requires an assistant message after that user turn, without inspecting
   goodbye keywords. It cannot independently verify semantic intent; that is the
   model's responsibility under the shared prompt and needs live evaluation.
   Duplicate end tools cannot save or shut down twice. Already committed effects
   are retained. Incomplete playout leaves the call open rather than cutting audio.
3. A failed summary save previously vetoed shutdown. Saving still uses the existing
   bounded tool orchestrator off the audio loop, but failure no longer blocks a
   valid hangup or gets reported as a successful save.
4. Telephony room options disabled room deletion, leaving SIP callers connected
   after the agent left. Browser and telephony now delete on session close.
   The tool waits for goodbye playout, then invokes `shutdown(drain=True)`;
   framework RoomIO deletes only after its drained close event. LiveKit tracks the
   deletion task during job shutdown. See the [LiveKit job lifecycle docs](https://docs.livekit.io/agents/server/job/).
5. Browser `disconnect()` missed terminal events if a callable transport did not
   emit its event, and a late old-room event could reset a new connection. Shared
   SDK cleanup now emits `disconnected`/`ended` exactly once for the active room.

## Runtime contract

Conversation model interprets completion intent -> model-generated closing line
through the configured TTS pipeline and end tool call -> playout completes ->
recheck turn freshness/interruption and closing speech presence -> drained session
shutdown -> room deletion/SIP disconnect ->
existing shutdown hooks close session history and release quota -> browser SDK
emits `ended` and cleans up media/timers.

The worker always registers platform lifecycle tools, whether or not the tenant
has a business tool gateway. The ending path does not require conversational or
experimental TTS feature flags. The shared platform prompt reaches all configured
LLM/TTS lanes. Existing identity handling and unrelated humanization flags remain
unchanged. After a successful end the agent suppresses duplicate goodbye/tool
continuations; a result with callEnding=false returns to normal model generation.

Summary persistence has the existing bounded tool timeout. If playout fails to
complete within its safety budget, the tool records `playout_incomplete` and does
not disconnect mid-utterance. Provider failure shutdown remains owned by the
existing provider retry/error path. Manual SDK disconnect stays immediate.

## Validation boundaries

Automated coverage uses scripted LLM output through the installed LiveKit
AgentSession with synthetic TTS/audio output. It checks unfamiliar caller wording,
variable model-generated closing lines, contextual inputs reaching the model,
baseline/conversational policies, successful versus cancelled continuation, all four
selectable TTS renderer lanes, WebRTC/telephony options, interruption, duplicate
tools, summary failure, persistent effects and browser terminal-event fallback.
These are implementation checks, not proof of live LLM intent accuracy, audible
caller playback or a real SIP hangup. Activation requires a worker deployment, a browser package release for
the browser cleanup fix, and live WebRTC and PSTN acceptance.
