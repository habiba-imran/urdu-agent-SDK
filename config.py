"""Central configuration for the TechZone Urdu voice agent.

All latency-relevant knobs live here so they can be tuned during testing
(STEP 3 requirement: VAD settings exposed in a config file).
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- API keys / providers ---------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
SONIOX_API_KEY = os.environ.get("SONIOX_API_KEY", "")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
UPLIFTAI_API_KEY = os.environ.get("UPLIFTAI_API_KEY", "")
UPLIFT_VOICE_ID = os.environ.get("UPLIFT_VOICE_ID", "v_meklc281")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE", "")

# v3: "cerebras" (llama-3.3-70b, 1M tokens/day — operating default), "groq"
# (llama-3.3-70b, 100k tokens/day) or "gemini" (emergency only: 20 req/day on
# this key, Roman-Urdu output — D20/D26). Failover: cerebras → groq → gemini.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "cerebras").lower()

# v2: non-reasoning models only (D15). gpt-oss-120b removed entirely.
# v3: PROMPT3 specified cerebras llama-3.3-70b, but Cerebras no longer serves it
# (available: gemma-4-31b, gpt-oss-120b, zai-glm-4.7). gemma-4-31b won the probe:
# proper Urdu script, 0 reasoning tokens, clean streamed tool calls (D28).
CEREBRAS_LLM_MODEL = os.environ.get("CEREBRAS_LLM_MODEL", "gemma-4-31b")
GROQ_LLM_MODEL = os.environ.get("GROQ_LLM_MODEL", "llama-3.3-70b-versatile")
GEMINI_LLM_MODEL = os.environ.get("GEMINI_LLM_MODEL", "gemini-3.1-flash-lite")
GROQ_STT_MODEL = "whisper-large-v3"  # fallback STT (STT_PROVIDER=groq)
# Cerebras free tier caps context at 8,192 tokens; hard-trim any request that
# would approach this (estimator: urdu chars ≈ 1 tok, other chars ≈ 1/4 tok)
CEREBRAS_CONTEXT_TOKEN_GUARD = 7000

# --- STT provider ---------------------------------------------------------------
# PRIMARY STT selector. Default "gladia" (streaming, best Urdu+English code-switch).
# Automatic fallback: when DEEPGRAM_API_KEY is set (and STT_FALLBACK_ENABLED), the
# primary fails over to Deepgram nova-3 on a non-fatal STT error, mirroring the LLM
# failover chain (ServiceSwitcher + ServiceSwitcherStrategyFailover — D29).
# Other selectable primaries: "soniox" (stt-rt-v5, needs funds), "groq" (segmented
# Whisper), "deepgram" (use Deepgram as primary — disables the fallback wrap).
STT_PROVIDER = os.environ.get("STT_PROVIDER", "gladia").lower()

# --- Deepgram (STT FALLBACK behind the primary) ---------------------------------
# nova-3 is the ONLY Deepgram model with Urdu ("ur") support (monolingual; English
# code-switching is weaker than Gladia's, which is exactly why it is the fallback,
# not the primary — research D29). Fallback activates only when a key is present.
DEEPGRAM_STT_MODEL = os.environ.get("DEEPGRAM_STT_MODEL", "nova-3")
DEEPGRAM_LANGUAGE = os.environ.get("DEEPGRAM_LANGUAGE", "ur")
# endpointing (ms of silence → Deepgram utterance final); local Silero VAD still
# owns turn taking, so keep this tight to keep Deepgram finals ahead of VAD stop.
DEEPGRAM_ENDPOINTING_MS = int(os.environ.get("DEEPGRAM_ENDPOINTING_MS", "100"))
DEEPGRAM_TTFS_P99 = float(os.environ.get("DEEPGRAM_TTFS_P99", "0.7"))
# Master switch for the automatic Gladia→Deepgram failover (on by default; the
# wrap is skipped anyway when no DEEPGRAM_API_KEY is set or primary is deepgram).
STT_FALLBACK_ENABLED = os.environ.get("STT_FALLBACK_ENABLED", "1").lower() not in (
    "0",
    "false",
    "no",
    "off",
)

# --- Soniox (v3 CHANGE 1) --------------------------------------------------------
SONIOX_MODEL = "stt-rt-v5"
# context_version 2 object (dict form of pipecat's SonioxContextObject)
SONIOX_CONTEXT = {
    "general": [
        {
            "key": "domain",
            "value": "laptop shop customer support call, Islamabad, Pakistan",
        },
        {
            "key": "language",
            "value": "Urdu with embedded English tech terms, Urdu script",
        },
    ],
    "text": "Customer calls TechZone Laptops about MacBook prices, warranty, reservations.",
    "terms": [
        "TechZone",
        "MacBook",
        "MacBook Air",
        "MacBook Pro",
        "AppleCare",
        "M1",
        "M2",
        "M3",
        "M4",
        "RAM",
        "SSD",
        "Islamabad",
        "warranty",
    ],
}

GLADIA_API_KEY = os.environ.get("GLADIA_API_KEY", "")
# picked by measured per-turn final latency from this machine (see DECISIONS.md D17)
GLADIA_REGION = os.environ.get("GLADIA_REGION", "eu-west")
GLADIA_MODEL = "solaria-1"
# ur-only DEFAULT: D19 measured CER 0.42 with "en" in the list vs 0.14 ur-only on
# THIS deployment (Gladia returned whole-sentence English). Research (D41) says
# code-switching transcribes each language in its native script (translation only
# with translation=true) — so it *should* help embedded tech terms. Left as an
# env A/B toggle rather than flipped blind: set GLADIA_CODE_SWITCHING=1 and
# GLADIA_LANGUAGES=ur,en to try the research config against the proven default.
GLADIA_LANGUAGES = [
    s.strip() for s in os.environ.get("GLADIA_LANGUAGES", "ur").split(",") if s.strip()
]
GLADIA_CODE_SWITCHING = os.environ.get("GLADIA_CODE_SWITCHING", "0").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# v5 noise defense at the STT layer (research D41). speech_threshold near 1 makes
# Gladia stricter about calling background sound "speech"; 0.8 rejects shop-floor
# noise without clipping soft-spoken digits. audio_enhancer pre-cleans the stream
# (better accuracy in noise, small latency cost) — env-toggleable if latency regresses.
GLADIA_SPEECH_THRESHOLD = float(os.environ.get("GLADIA_SPEECH_THRESHOLD", "0.8"))
GLADIA_AUDIO_ENHANCER = os.environ.get("GLADIA_AUDIO_ENHANCER", "1").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# silence (s) after which Gladia finalizes an utterance. 0.1 keeps finals ahead
# of the VAD stop event (0.3 measured ~700ms of post-eos final latency — D16)
GLADIA_ENDPOINTING = 0.1
# measured P99 eos→final for this deployment; feeds the turn-stop safety net
GLADIA_TTFS_P99 = 0.7
# Promote the last interim transcript to a final if Gladia's utterance-final
# hasn't arrived this many seconds after the VAD stop event (D21).
# DISABLED by default: measured Gladia Urdu partials at VAD-stop time are often
# garbled/incomplete («میکوکہ ہے ام دو کی کی میکر» for a price question) — the
# accurate text only exists once the real final lands, so promotion would trade
# correctness for latency. Set >0 (e.g. 0.12) to enable if quality improves.
STT_PROMOTE_INTERIM_AFTER_SECS = 0.0
GLADIA_CUSTOM_VOCAB = [
    "TechZone",
    "MacBook",
    "MacBook Air",
    "MacBook Pro",
    "AppleCare",
    "M1",
    "M2",
    "M3",
    "M4",
    "RAM",
    "SSD",
    "Islamabad",
    "warranty",
]

# --- LLM generation ----------------------------------------------------------
LLM_TEMPERATURE = 0.4
LLM_MAX_TOKENS = 200

# --- STT ----------------------------------------------------------------------
STT_LANGUAGE = "ur"
# Whisper prompt biases proper nouns (<= 224 tokens)
STT_PROMPT = (
    "MacBook, MacBook Air, MacBook Pro, AppleCare, AirPods, Islamabad, Rawalpindi, "
    "warranty, delivery, M1, M2, M3, M4, RAM, SSD, TechZone, Dell XPS, ThinkPad, "
    "battery health, laptop, 0300, 03001234567"
)

# --- VAD (Silero) — tuned to REJECT BACKGROUND NOISE (v5) --------------------
# The prior 0.7/0.2/0.6 was over-sensitive: background chatter and transient
# clatter opened turns and caused false barge-ins (a known Pipecat issue). These
# are the research-backed noise-robust values (env-overridable to re-tune per
# room): higher confidence + higher min_volume reject low-energy background;
# longer start_secs makes brief noise bursts fail to open a turn. Note the
# browser client's auto-gain can BOOST ambient noise toward speech level during
# silence, which is why we lean on confidence/min_volume, not volume alone.
VAD_CONFIDENCE = float(os.environ.get("VAD_CONFIDENCE", "0.8"))  # was 0.7
VAD_START_SECS = float(os.environ.get("VAD_START_SECS", "0.35"))  # was 0.2
VAD_STOP_SECS = float(os.environ.get("VAD_STOP_SECS", "0.5"))
VAD_MIN_VOLUME = float(os.environ.get("VAD_MIN_VOLUME", "0.7"))  # was 0.6

# --- Turn taking ---------------------------------------------------------------
# "vad"        → SpeechTimeoutUserTurnStopStrategy (pure VAD + transcript gate)
# "smart_turn" → LocalSmartTurnAnalyzerV3 (probed for Urdu; see DECISIONS.md)
TURN_STOP_MODE = os.environ.get("TURN_STOP_MODE", "vad").lower()
# Extra wait after VAD stop in which the user may resume speaking. With Gladia's
# streaming finals (often arriving BEFORE the VAD stop event) this is the only
# post-eos wait on the happy path (D16).
USER_SPEECH_TIMEOUT_SECS = 0.05

# Barge-in: interrupt the bot only after this many transcribed words. Raised
# 2→3 (v5) so a single stray word transcribed from background noise can no
# longer cut the bot off mid-sentence (research: min-words gate is the
# framework-native anti-false-interruption mechanism).
INTERRUPT_MIN_WORDS = int(os.environ.get("INTERRUPT_MIN_WORDS", "3"))

# --- Guardrails ----------------------------------------------------------------
MAX_RESPONSE_CHARS = 350  # hard cap on a single spoken response
MAX_UTTERANCE_CHARS = 500  # cap on a single user utterance injected into context
IDLE_PROMPT_SECS = 12.0  # "Kya aap line par hain?"
IDLE_HANGUP_SECS = 25.0  # polite close
SESSION_MAX_SECS = 600.0  # 10 minutes session cap
TOOL_READ_TIMEOUT_SECS = 2.5  # Supabase reads inside tools

# --- Audio ----------------------------------------------------------------------
AUDIO_IN_SAMPLE_RATE = 16000
AUDIO_OUT_SAMPLE_RATE = 22050  # matches Uplift PCM_22050_16 → no resampling needed

# --- TTS pacing (v5: "agent talks too fast" fix) --------------------------------
# Uplift Orator has NO speaking-rate parameter (research D42) — pace is intrinsic
# to the voice. The one lever we control in the audio path is a short silence
# inserted between the sentences of a turn so replies don't run together and feel
# rushed. 0 disables. Also try a calmer UPLIFT_VOICE_ID (helpdesk-agent is warm;
# late-night-rj / paediatrician read slower) if it still feels quick.
TTS_INTERSENTENCE_PAUSE_MS = int(os.environ.get("TTS_INTERSENTENCE_PAUSE_MS", "180"))

# --- Server / deployment (v4 Part C) -----------------------------------------------
# Bind all interfaces so PaaS ingress (Render) can reach the app; PORT is injected
# by Render, 7860 stays the local default.
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "7860"))

# Transport: "webrtc" (default; UDP media, best locally / with TURN) or
# "websocket" (TCP audio streaming — survives Render's HTTP-only ingress).
TRANSPORT = os.environ.get("TRANSPORT", "webrtc").lower()

# ICE servers for WebRTC (server AND browser get these via /config). On Render,
# WebRTC may connect via server-reflexive candidates or may need the TURN relay.
STUN_URL = os.environ.get("STUN_URL", "stun:stun.l.google.com:19302")
TURN_URL = os.environ.get("TURN_URL", "")
TURN_USERNAME = os.environ.get("TURN_USERNAME", "")
TURN_PASSWORD = os.environ.get("TURN_PASSWORD", "")

# Header token protecting the /diag/* endpoints (empty disables them).
DIAG_TOKEN = os.environ.get("DIAG_TOKEN", "")

# Uplift phrase replacement config id (created by scripts/create_phrase_config.py)
_cfg_path = os.path.join(os.path.dirname(__file__), ".uplift_phrase_config")
UPLIFT_PHRASE_CONFIG_ID = None
if os.path.exists(_cfg_path):
    UPLIFT_PHRASE_CONFIG_ID = open(_cfg_path, encoding="utf-8").read().strip() or None
