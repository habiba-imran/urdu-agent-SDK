"""One contract for every selectable provider. Only audio-side text/options vary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from html import escape

from .capabilities import ProviderCapabilities
from .intent import DeliveryIntent
from .pronunciation import PronunciationPlan, digits_plain, spell_plain


@dataclass(frozen=True)
class LanguageProfile:
    language: str = "en"
    version: str = "language_v1"

    @property
    def locale(self) -> str:
        value = self.language.lower().replace("-", "_")
        if value in {"mixed", "ur_en", "en_ur", "ur_pk_mixed", "ur_mixed"}:
            return "ur_pk_mixed"
        return "ur_pk" if value.startswith("ur") or value == "urdu" else "en"

    @property
    def script(self) -> str:
        return "latin" if self.locale == "en" else "urdu_with_literal_entities"

    @property
    def instructions(self) -> str:
        if self.locale == "en":
            return "Use concise conversational English. Preserve literal business names and structured values. No random fillers or stage directions."
        switch = ("Use natural Pakistani Urdu with useful English business terms; keep mixed phrase boundaries intact. "
                  if self.locale == "ur_pk_mixed" else "Use concise Pakistani Urdu in Urdu script. Preserve literal English brands, names and IDs. ")
        return switch + "Use respectful, gender-neutral phrasing where possible; do not guess the caller's gender. No random fillers or stage directions."

    def phrase(self, function: str) -> str:
        banks = {
            "en": {"SHORT_RECEIPT": "Okay.", "TOOL_ACK_CHECK": "I'm checking that for you.",
                   "REPAIR_CONFIRM": "Please confirm that detail.", "FALSE_INTERRUPT_RECOVERY": "Let me continue."},
            "ur_pk": {"SHORT_RECEIPT": "جی۔", "TOOL_ACK_CHECK": "ایک لمحہ، تفصیل دیکھ لیتے ہیں۔",
                      "REPAIR_CONFIRM": "براہ کرم یہ تفصیل واضح کر دیں۔", "FALSE_INTERRUPT_RECOVERY": "بات جاری رکھتے ہیں۔"},
            "ur_pk_mixed": {"SHORT_RECEIPT": "جی۔", "TOOL_ACK_CHECK": "ایک لمحہ، تفصیل چیک کر لیتے ہیں۔",
                            "REPAIR_CONFIRM": "براہ کرم یہ تفصیل کنفرم کر دیں۔", "FALSE_INTERRUPT_RECOVERY": "بات جاری رکھتے ہیں۔"},
        }
        return banks[self.locale][function]


@dataclass(frozen=True)
class ChannelProfile:
    channel: str = "webrtc"
    version: str = "channel_v1"

    @property
    def kind(self) -> str:
        return "TELEPHONY" if self.channel.lower() == "telephony" else "WEBRTC"

    @property
    def audio_lead_ms(self) -> int:
        return 1000 if self.kind == "TELEPHONY" else 2000

    def delivery(self, intent: DeliveryIntent, pronunciation: PronunciationPlan) -> DeliveryIntent:
        if self.kind == "TELEPHONY" and pronunciation.spans:
            return replace(intent, pace="slower", nonverbal="none")
        return replace(intent, nonverbal="none")


@dataclass(frozen=True)
class RenderedSpeech:
    canonical_text: str
    provider_text: str
    provider_options: dict = field(default_factory=dict)
    continuity_identity: str | None = None
    alignment_mode: str = "canonical"
    flush_hint: str = "framework_default"
    degraded: tuple[str, ...] = ()


def render(
    canonical_text: str, delivery_intent: DeliveryIntent,
    pronunciation_plan: PronunciationPlan, language_profile: LanguageProfile,
    channel_profile: ChannelProfile, provider_capabilities: ProviderCapabilities,
    *, stored_options: dict | None = None, effective: dict | None = None,
) -> RenderedSpeech:
    """No wording paraphrase, model/voice switch, task mutation, or network call."""
    caps = provider_capabilities
    options = deepcopy(stored_options or {})
    effective = effective or {}
    degraded: list[str] = []
    try:
        pronunciation_plan.validate(canonical_text)
    except (ValueError, TypeError):
        pronunciation_plan = PronunciationPlan()
        degraded.append("invalid_pronunciation_plan")
    if delivery_intent.nonverbal != "none":
        degraded.append("nonverbal")
    delivery_intent = channel_profile.delivery(delivery_intent, pronunciation_plan)
    replacements = []
    for span in pronunciation_plan.spans:
        value = span.source
        if span.mode == "SPELL":
            if "SPELL_NATIVE" in caps.pronunciation and caps.provider == "cartesia":
                value = "<spell>" + escape(value) + "</spell>"
            elif "SPELL_NATIVE" in caps.pronunciation and caps.provider == "rime" and "(" not in value and ")" not in value:
                value = "spell(" + value + ")"
            else:
                value = spell_plain(value, language_profile.language)
        elif span.mode == "ALIAS":
            value = span.alias
        elif span.mode == "DIGIT_GROUP":
            value = digits_plain(span, language_profile.language)
        elif span.mode == "PHONEME":
            degraded.append("phoneme")  # no PHONEME path is verified in current wiring
        replacements.append((span.start, span.end, value))

    # Pause at a trusted whitespace boundary, outside protected values. Never split facts.
    for pause in delivery_intent.pauses:
        offset = pause.offset
        if not 0 <= offset < len(canonical_text) or not canonical_text[offset].isspace():
            degraded.append("pause_boundary")
            continue
        if any(span.start <= offset < span.end for span in pronunciation_plan.spans):
            degraded.append("protected_pause")
            continue
        milliseconds = max(100, min(500, pause.milliseconds))
        value = (
            f'<break time="{milliseconds}ms"/> ' if caps.pause
            else ("" if offset and canonical_text[offset - 1] in ".,!?؟۔" else ",") + " "
        )
        replacements.append((offset, offset + 1, value))
    text = canonical_text
    for start, end, value in sorted(replacements, reverse=True):
        text = text[:start] + value + text[end:]

    if caps.emotion:
        emotion = {
            "neutral": "neutral", "warm": "content", "reassuring": "calm",
            "concerned": "sympathetic", "upbeat": "content", "amused": "content",
        }.get(delivery_intent.affect, "neutral")
        text = f'<emotion value="{emotion}"/> ' + text
    elif delivery_intent.affect != "neutral":
        degraded.append("affect_from_canonical_wording")
    if delivery_intent.nonverbal != "none":
        degraded.append("nonverbal")  # never literal unsupported stage directions
    if delivery_intent.emphasis:
        degraded.append("emphasis")  # no fabricated vendor emphasis control

    if caps.speed and delivery_intent.pace != "normal":
        factor = .9 if delivery_intent.pace == "slower" else 1.05
        if caps.provider == "cartesia":
            if "speed" not in options:
                options["speed"] = max(.6, min(1.5, float(effective.get("speed", .95)) * factor))
        elif caps.provider == "elevenlabs":
            settings = options.setdefault("voice_settings", {})
            if "speed" not in settings:
                settings["speed"] = max(.7, min(1.2, float(effective.get("voice_settings", {}).get("speed", 1)) * factor))
        elif caps.provider == "rime" and "speed_alpha" not in options:
            # Mist v2 reverses speed direction; Arcana is never inferred.
            multiplier = 1 / factor if caps.model == "mistv2" else factor
            options["speed_alpha"] = max(.5, min(2, float(effective.get("speed_alpha", 1)) * multiplier))
    elif delivery_intent.pace != "normal":
        degraded.append("pace_from_punctuation")
        # Existing sentence punctuation is the fallback. Do not inject pauses into entities.
    if caps.provider == "cartesia" and caps.emotion:
        # Per-utterance renderer tags own tone; constructor emotion must not fight them.
        options.pop("emotion", None)
        options["spoken_style"] = "manual_ssml"
        options["expressive"] = False
    return RenderedSpeech(
        canonical_text, text, options, delivery_intent.continuity_identity,
        degraded=tuple(sorted(set(degraded))),
    )
