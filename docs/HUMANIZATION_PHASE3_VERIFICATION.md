# Phase 3 verification and completion report

**Execution:** 2026-10-09 (Asia/Karachi). **Scope:** Phase 3A–3I only. Phase 4 was not started.

```text
PHASE / SUBPHASE: Phase 3A–3I
IMPLEMENTATION GATE: PASS
ACTIVATION GATE: BLOCKED; policy remains SHADOW
DEFAULT ENABLEMENT: baseline; candidate behavior OFF
```

## Design and implementation

| Subphase | Evidence |
| --- | --- |
| 3A | Immutable provider-neutral `TurnPlan` contains every planned field; no TTS or LLM options. |
| 3B | Pure deterministic derivation gives critical uncertainty priority over correction and write; correction blocks write; pending write asks for confirmation; an observed affirmative remains subject to the existing write gate. Complaint forbids humor and laughter, simple facts use MICRO, running tools signal wait. |
| 3C | `ContextProjection` includes current confirmed facts, unresolved fields, recent repair when relevant, turn act/budget and language. It excludes IDs, provider state and stale values. Limits expose an omitted count. Pending repair and unresolved fields suppress conflicting confirmed facts. |
| 3D | `preview_ephemeral_context` uses the installed public `ChatContext.copy()` and `add_message()` API. It only prepares a disposable copy. Phase 3 never sends the preview to the model or appends it to persistent history. |
| 3E | The existing public `Agent.on_user_turn_completed` hook computes a shadow plan after base handling; session events compare the committed assistant response structurally. Trace logs contain enum policy, counts and response length/question shape only. Raw facts, caller text and IDs stay out of logs. No second planner LLM exists. |
| 3F | Defined target authority order: platform safety/business invariants → TurnPlan → language profile → tenant persona DATA → provider renderer. The audit checks actual layer order and DATA framing. The active stack still has both the known “two or three” versus “one or two” sentence conflict and a tenant persona carried in a `system` role message alongside platform instructions. Both block activation; Phase 3 leaves the audible prompt unchanged. Cartesia manual SSML, ElevenLabs tags, Rime, Fish and Uplift delivery text are marked for Phase 6 removal from the LLM path where the migrated renderer permits. |
| 3G | Groq compaction is audited against labeled identity, services, hours, rules, policy and address facts. These source facts enter the separate, bounded shadow projection as lower-authority DATA, independent of stylistic persona text; missing or omitted facts and unverifiable unstructured prose are explicit activation blockers. Logs omit values. Source persona/audit transcript remains intact. No cap increase or active-context rewrite occurred. |
| 3H | Adversarial persona fixture attempts to override confirmation, tool truth, safety, Urdu language and provider markup. Deterministic assembly frames it as DATA and the write gate remains unchanged. The audit explicitly flags its equal `system` message role as an unresolved model trust boundary. These are assembly/gate proofs, not a claim that a live model obeyed. |
| 3I | `natural_v1` still resolves to `natural_v1_shadow`; `behavior_enabled=False`. Baseline is the immediate rollback setting. Audible activation remains blocked by missing lane baselines, the prompt conflict and persona role boundary, any lost/unverified Groq facts, and Phase 4 certainty/repair integration. |

## Verification

| Check | Result |
| --- | --- |
| New focused Phase 3 suites | **12 passed**: deterministic English/Urdu/mixed planning; safety precedence; projection exclusions, bounded business facts and ephemeral copy; prompt stack/trust boundary; Groq fact-loss detection; build-agent wiring; structural privacy; installed-framework synthetic speech/history parity. |
| Full offline CI manifest | **345 passed, 10 skipped, 0 failed**, one existing Starlette warning. Nine skipped cases require `SUPABASE_DB_URL`; one SSRF case was blocked by the offline guard. |
| Focused static/lint and whitespace | Scoped Ruff **PASS**; tracked-file `git diff --check` **PASS**. |
| Graph refresh | Attempted `graphify update .`; the existing uv trampoline failed to canonicalize its script path. |

The synthetic `generate_reply` API bypasses LiveKit's user-turn hook, so the parity test explicitly invokes that public hook before the same synthetic reply. Equal generated audio frame counts and session history demonstrate that shadow observation does not alter that tested path. They do not establish live caller audio, WebRTC/PSTN timing, provider behavior or model compliance.

The Phase 0 corpus and its current lane baselines are unchanged. No live provider, paid call, database migration, prompt/voice/provider option update, deployment or Phase 4 repair implementation occurred. The missing `HUMANIZATION_RESEARCH_MASTER.md` and graph-tool environment limitation from earlier phases remain open.
