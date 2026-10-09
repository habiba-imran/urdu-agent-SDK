# Humanization baseline corpus v1

Phase 0 freezes evaluation inputs and provisional semantic reference labels. It does not implement a conversation simulator, renderer, state reducer, telemetry or any later-phase feature.

`corpus.v1.json` contains 30 stable scenarios covering all 18 required categories and English, Pakistani Urdu and mixed speech. Inputs, business facts, tools and identities are synthetic. The `.test` email and example phone are fixture data only: never call the phone, send email, book real appointments, or use a production tenant with these fixtures.

Reference labels are authored expectations for subsequent deterministic and listening evaluation, **not measured baseline outcomes**. Pakistani Urdu and mixed phrases, overlap intent labels, register and gender fit require native review. No reviewed listener labels or reference audio are available yet. Preserve scenario IDs; increase `corpus_version` whenever inputs, reference labels, facts, run matrix or scoring change. Record SHA-256 of the exact UTF-8 file in each baseline/candidate bundle.

For every run record scenario ID, corpus version/hash, git HEAD and dirty-source hashes, policy, exact requested/effective providers/models/voice/options/plugin versions, language, channel, cold/warm state, network condition and harness version. Missing measurements are `null` with a reason, never zero. Results must distinguish pass, fail, unavailable and not applicable. A scenario recipe or fixture TTS playback is not an executed call or native-language approval.

Semantic scoring checks the `reference` fields against resulting task/tool state and spoken meaning. Consequential-write, unknown-outcome, stale-result, supersession, markup and cancelled-audio violations are hard failures. For each one-word takeover, a miss blocks activation. Read/write events are fake dependency outcomes for future harness replay; `expected_write_count` describes the intended safe dispatch count, not today's implementation proof.

Timing evaluation must use caller-side acoustic speech end to first useful audible word, and interruption onset to old speech inaudible. Existing `e2eMs` is a diagnostic proxy. Pair baseline/candidate recordings in the same environment; preserve cold/warm and WebRTC/telephony lanes separately. Do not change provider, policy and transport simultaneously. Long-call recipes must be expanded and actually executed with duration recorded before claiming 10–20 minute evidence.

Human review records should include reviewer pseudonym, language competence, randomized A/B assignment, decisive preference, 1–5 naturalness/intelligibility/trust ratings, entity capture on first hearing, overlap intent/action, repetition and pronunciation comments; Urdu/mixed review also covers code switching, register and voice/gender grammar. Leave these fields unavailable until review occurs. Initial product targets come from the implementation plan's Phase 11; they are goals, not current scores or formal standardized MOS.

Store recordings/transcripts only under the existing recording, consent and retention policy in a local approved artifact location, never in this committed fixture directory. The initial local baseline location and evidence gaps are documented in `docs/HUMANIZATION_PHASE0_BASELINE.md`.
