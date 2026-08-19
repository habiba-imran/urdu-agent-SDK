"""Central capability registry — Phase 3/4 of docs/UKASHA_AGENT_FACING_MULTIPLE_PROVIDERS_PLAN.md
(ADR-036). Single source of truth for which (language, layer, provider[, model]) combinations are
valid — consumed by tenant_portal_api's create/update validation (Phase 3) and the capabilities API
(Phase 4).

TTS is listed here only at the provider level. Individual VOICES are NOT duplicated here — they
live in the `voices` table (Phase 1's `provider`/`language`/`rollout_state` columns), since the
voice catalogue is data that changes independently of code, not something that belongs in a
committed Python file.

Rollout states (guide's own definition):
  planned  — documented internally, not selectable by any tenant-facing route
  testing  — selectable only by an internal/admin flow (none exists yet for agent creation —
             every current route is tenant-facing, so `testing` behaves like `planned` today)
  enabled  — selectable by tenant-facing routes

`en` combos are listed here documenting the confirmed target scope (2026-08-01: Gladia+Deepgram
STT, Gemini+Groq LLM, ElevenLabs+Fish Audio+Cartesia+Rime TTS). `en.stt.gladia` and `en.llm.gemini`
are `enabled` as of Phase 5 (2026-08-01) — both adapters needed zero new code (the Gladia adapter
was already language-parameterized in Phase 2; Gemini is prompt-driven, not language-specific).
`en.stt.deepgram` is `enabled` as of Phase 6a (2026-08-01) — package verified against PyPI +
inspect.signature, then confirmed with a real human-approved live call (real Deepgram WebSocket
connection, correct English transcripts, a coherent LLM reply proving the transcript was accurate;
see tests/test_deepgram_stt.py and the plan's Phase 6a changelog entry for the full account,
including two real bugs the live test itself surfaced and fixed: worker/main.py::prewarm() only
prewarmed one STT plugin based on a legacy env var, and scripts/mint_demo_token.py was missing the
explicit LiveKit agent dispatch call entirely).

`en.llm.groq` is `enabled` as of Phase 6b (2026-08-01) — package (`livekit-plugins-groq==1.6.5`,
pulls in `livekit-plugins-openai==1.6.5`) and constructor verified against the installed package
via inspect.signature before any code was written; models list taken from the package's own
`models.py`, not guessed. Confirmed with a real human-approved live call — coherent, contextually
appropriate replies, independently re-verified from the DB transcript, not just the terminal log.
See tests/test_groq_llm.py and the plan's Phase 6b changelog entry for the full account.

`en.tts.cartesia` is `enabled` as of Phase 6c (2026-08-02) — package (`livekit-plugins-cartesia==
1.6.5`) and constructor verified against the installed package via inspect.signature before any
code was written. One voice seeded (migration `0018_seed_cartesia_voice.sql`), using the plugin's
own baked-in default voice ID, not an invented one. This subphase also surfaced and fixed a real,
general design gap (not Cartesia-specific): the registry previously passed our internal `voices.id`
straight to every TTS adapter unresolved — worked for Uplift only by coincidence (Phase 1 backfilled
`provider_voice_id = id` for every Uplift row). `worker/main.py::build_session()` now resolves
`voices.provider_voice_id` before handing a voice ID to any adapter — see
`_resolve_provider_voice_id()`'s docstring. Confirmed with a real human-approved live call —
Deepgram transcribed correctly, Gemini replied coherently, Cartesia's WebSocket stayed connected
the whole call and produced real audio the human confirmed sounded clear and correct. `en` now has
its first fully `enabled` TTS provider — a full `agent_language="en"` agent is creatable end-to-end
through the tenant-facing API for the first time (with `tts_provider="cartesia"`). See
tests/test_cartesia_tts.py and the plan's Phase 6c changelog entry for the full account.

`en.tts.elevenlabs` is `enabled` as of Phase 6d (2026-08-02) — package
(`livekit-plugins-elevenlabs==1.6.5`) and constructor verified against the installed package via
inspect.signature before any code was written; note the kwarg is `voice_id` (not `voice` like
Cartesia's). One voice seeded (migration `0019_seed_elevenlabs_voice.sql`), using the plugin's own
baked-in default voice ID (`hpp4J3VqNfWAUOO0d1Us`, `DEFAULT_VOICE_ID` in the package's own
tts.py), not an invented one. Confirmed with a real human-approved live call — Deepgram
transcribed correctly across five exchanges, Gemini replied coherently throughout, ElevenLabs
produced real audio the human confirmed sounded clear and correct; the call ended via the agent's
own end-of-conversation tool (`end_reason: agent_ended`), a normal clean close. See
tests/test_elevenlabs_tts.py and the plan's Phase 6d changelog entry for the full account.

`en.tts.fish_audio` is `testing` as of Phase 6e (2026-08-02) — package
(`livekit-plugins-fishaudio==1.6.5`) and constructor verified against the installed package via
inspect.signature before any code was written. Unlike Cartesia/ElevenLabs, this plugin's
constructor has NO `language` parameter at all — `worker/providers/tts/fish_audio.py::build()`
intentionally takes only `voice_id`, a real (not assumed) difference in this vendor's API shape.
One voice seeded (migration `0020_seed_fish_audio_voice.sql`), using the plugin's own baked-in
default voice ID (`933563129e564b19a115bedd57b7406a`, `DEFAULT_VOICE_ID` in the package's own
tts.py), not an invented one. Awaiting its own human-approved live smoke test before `enabled` —
see tests/test_fish_audio_tts.py.

`en.tts.rime` is `enabled` as of Phase 6f (2026-08-02) — package (`livekit-plugins-rime==1.6.5`)
and constructor verified against the installed package via inspect.signature before any code was
written. Two real, non-obvious API differences from every other TTS adapter in this repo: the
voice kwarg is `speaker` (not `voice`/`voice_id`), and the language kwarg is `lang`, using 3-letter
codes (`Literal["eng", "spa", "fra", "ger", "hin"]`) rather than our internal 2-letter
`agent_language` values — `worker/providers/tts/rime.py::build()` maps `en` -> `"eng"` explicitly
and raises for anything else, rather than silently guessing. One voice seeded (migration
`0021_seed_rime_voice.sql`), using the plugin's own baked-in default speaker for its default model
(`model="arcana"` -> `speaker="astra"`, confirmed by reading the installed package's source).
Confirmed with a real human-approved live call — a long (142s, 20-turn) conversation with Deepgram
transcribing correctly throughout, Gemini staying coherent, and Rime producing audio for every
assistant turn with no dropouts in the log; a first, shorter attempt had a laggy start (treated as
a one-off warmup/network blip, not a persistent defect) before the human approved the second,
longer test as the real pass. See tests/test_rime_tts.py and the plan's Phase 6f changelog entry
for the full account.

Groq is deliberately ABSENT from `ur`'s llm dict, not merely disabled — the guide's rule ("do not
allow Groq for Urdu") is enforced structurally: a language/provider pair that isn't in this table
at all is indistinguishable from one that was checked and rejected, so there's no separate
special-case to keep in sync.
"""

from __future__ import annotations

ROLLOUT_STATES = ("planned", "testing", "enabled")

# language -> layer -> provider -> {state, models, default_model}
# TTS entries have no "models" — voice selection is handled via the `voices` table.
CAPABILITIES: dict[str, dict[str, dict[str, dict]]] = {
    "ur": {
        "stt": {
            "gladia": {
                "state": "enabled",
                "models": ["default"],
                "default_model": "default",
            },
        },
        "llm": {
            "gemini": {
                "state": "enabled",
                "models": ["gemini-2.5-flash"],
                "default_model": "gemini-2.5-flash",
            },
        },
        "tts": {
            "uplift": {"state": "enabled"},
        },
    },
    "en": {
        "stt": {
            "gladia": {
                "state": "enabled",
                "models": ["default"],
                "default_model": "default",
            },
            "deepgram": {
                "state": "enabled",
                "models": ["nova-3"],
                "default_model": "nova-3",
            },
        },
        "llm": {
            "gemini": {
                "state": "enabled",
                "models": ["gemini-2.5-flash"],
                "default_model": "gemini-2.5-flash",
            },
            "groq": {
                "state": "enabled",
                # Retired Groq IDs stay listed so existing agent rows and client pickers still
                # validate; worker/providers/llm/groq.py remaps them at session start.
                "models": [
                    "openai/gpt-oss-120b",
                    "openai/gpt-oss-20b",
                    "qwen/qwen3.6-27b",
                    "llama-3.1-8b-instant",
                    "llama-3.3-70b-versatile",
                    "meta-llama/llama-4-scout-17b-16e-instruct",
                    "moonshotai/kimi-k2-instruct-0905",
                    "qwen/qwen3-32b",
                ],
                "default_model": "openai/gpt-oss-120b",
            },
        },
        "tts": {
            "elevenlabs": {"state": "enabled"},
            "fish_audio": {"state": "testing"},
            "cartesia": {"state": "enabled"},
            "rime": {"state": "enabled"},
        },
    },
}


def is_language_known(language: str) -> bool:
    return language in CAPABILITIES


def stt_capability(language: str, provider: str) -> dict | None:
    return CAPABILITIES.get(language, {}).get("stt", {}).get(provider)


def llm_capability(language: str, provider: str) -> dict | None:
    return CAPABILITIES.get(language, {}).get("llm", {}).get(provider)


def tts_capability(language: str, provider: str) -> dict | None:
    return CAPABILITIES.get(language, {}).get("tts", {}).get(provider)
