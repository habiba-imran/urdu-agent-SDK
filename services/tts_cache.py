import hashlib
import io
import json
import pathlib
import wave

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
FIX_DIR = ROOT_DIR / "tests/fixtures/tts"
MAN_PATH = FIX_DIR / "manifest.json"
SAMPLE_RATE = 22050
SAMPLE_WIDTH = 2
CHANNELS = 1


def key(voice_id: str, text: str, *, rendered_identity: str | None = None) -> str:
    payload = f"{voice_id}|{text}" if rendered_identity is None else json.dumps(
        [voice_id, text, rendered_identity], ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _load_manifest() -> dict:
    if MAN_PATH.exists():
        try:
            return json.loads(MAN_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def get(voice_id: str, text: str, *, rendered_identity: str | None = None) -> bytes | None:
    manifest = _load_manifest()
    k = key(voice_id, text, rendered_identity=rendered_identity)
    if k in manifest:
        wav_path = FIX_DIR / f"{k}.wav"
        if wav_path.exists():
            return wav_path.read_bytes()

    # Candidate rendered audio must never fall back to an old policy or another voice.
    if rendered_identity is not None:
        return None
    # Legacy synthetic fixture-only compatibility fallback (never a live audio cache).
    # Search by text match fallback
    for k_id, item in manifest.items():
        if item.get("text") == text:
            wav_path = FIX_DIR / f"{k_id}.wav"
            if wav_path.exists():
                return wav_path.read_bytes()
    return None


def require(voice_id: str, text: str, *, rendered_identity: str | None = None) -> bytes:
    data = get(voice_id, text, rendered_identity=rendered_identity)
    if data is not None:
        return data

    raise LookupError(
        f"FIXTURE MISS: no cached wav for voice {voice_id} and text {text[:30]!r}"
    )


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buf.getvalue()
