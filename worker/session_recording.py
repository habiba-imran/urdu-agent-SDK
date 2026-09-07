"""Upload LiveKit RecorderIO audio.ogg and persist URLs on sessions / telephony_calls."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("worker.session_recording")

BUCKET_ID = "session-recordings"
SIGNED_URL_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days — enough for CRM archive retries


def _supabase_client() -> Any | None:
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE") or "").strip()
    if not url or not key:
        logger.warning(
            "session recording upload skipped — SUPABASE_URL / SUPABASE_SERVICE_ROLE not set"
        )
        return None
    try:
        from supabase import create_client

        return create_client(url, key)
    except Exception as exc:
        logger.warning("session recording: failed to create supabase client: %s", exc)
        return None


def _ensure_bucket(storage: Any) -> bool:
    try:
        existing = {b.id for b in storage.list_buckets()}
        if BUCKET_ID not in existing:
            storage.create_bucket(BUCKET_ID, options={"public": False})
        return True
    except Exception as exc:
        logger.warning("session recording: bucket ensure failed: %s", exc)
        return False


def find_session_audio(session_directory: Path | None) -> Path | None:
    if session_directory is None:
        return None
    candidate = Path(session_directory) / "audio.ogg"
    if candidate.is_file() and candidate.stat().st_size > 0:
        return candidate
    return None


def upload_session_audio(
    *,
    audio_path: Path,
    tenant_id: str,
    room_name: str,
) -> tuple[str, str] | None:
    """Upload audio.ogg → (storage_path, signed_url) or None on failure."""
    client = _supabase_client()
    if client is None:
        return None

    storage = client.storage
    if not _ensure_bucket(storage):
        return None

    safe_tenant = (tenant_id or "unknown").strip() or "unknown"
    safe_room = (room_name or "unknown").replace("/", "_").strip() or "unknown"
    storage_path = f"{safe_tenant}/{safe_room}.ogg"

    try:
        data = audio_path.read_bytes()
        if not data:
            logger.warning("session recording: empty audio file for room %s", room_name)
            return None

        bucket = storage.from_(BUCKET_ID)
        # Upsert — LiveKit may retry jobs; replace prior object for same room.
        try:
            bucket.remove([storage_path])
        except Exception:
            pass
        bucket.upload(
            storage_path,
            data,
            file_options={"content-type": "audio/ogg", "upsert": "true"},
        )
        signed = bucket.create_signed_url(storage_path, SIGNED_URL_TTL_SECONDS)
        signed_url = None
        if isinstance(signed, dict):
            signed_url = (
                signed.get("signedURL")
                or signed.get("signedUrl")
                or (signed.get("data") or {}).get("signedUrl")
            )
        if not signed_url:
            logger.warning("session recording: signed URL missing for %s", storage_path)
            return None
        return storage_path, str(signed_url)
    except Exception as exc:
        logger.warning("session recording: upload failed for room %s: %s", room_name, exc)
        return None


def persist_recording_urls(
    *,
    room_name: str,
    storage_path: str,
    recording_url: str,
) -> None:
    """Write recording fields onto sessions + telephony_calls for this room."""
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "scripts"))
    try:
        from scripts.dbconn import conn_kwargs
    except ImportError:
        from dbconn import conn_kwargs  # type: ignore

    import psycopg

    try:
        with psycopg.connect(**conn_kwargs(), connect_timeout=5, autocommit=True) as conn:
            conn.execute(
                """
                update sessions
                   set recording_url = %s,
                       recording_storage_path = %s
                 where room_name = %s
                """,
                (recording_url, storage_path, room_name),
            )
            conn.execute(
                """
                update telephony_calls
                   set recording_url = %s,
                       recording_storage_path = %s,
                       updated_at = now()
                 where room_name = %s
                """,
                (recording_url, storage_path, room_name),
            )
        logger.info(
            "session recording persisted room=%s path=%s",
            room_name,
            storage_path,
        )
    except Exception as exc:
        logger.warning(
            "session recording: failed to persist URLs for room %s: %s",
            room_name,
            exc,
        )


async def finalize_and_persist_session_recording(
    *,
    job_ctx: Any,
    room_name: str,
    tenant_id: str,
) -> None:
    """Close RecorderIO if needed, upload audio.ogg, and store URLs."""
    try:
        session = getattr(job_ctx, "_primary_agent_session", None)
        recorder_io = getattr(session, "_recorder_io", None) if session is not None else None
        if recorder_io is not None and getattr(recorder_io, "recording", False):
            try:
                await recorder_io.aclose()
            except Exception as exc:
                logger.warning("session recording: recorder close failed: %s", exc)

        session_dir = getattr(job_ctx, "session_directory", None)
        audio_path = find_session_audio(session_dir)
        if audio_path is None:
            logger.info("session recording: no audio.ogg for room %s", room_name)
            return

        uploaded = upload_session_audio(
            audio_path=audio_path,
            tenant_id=tenant_id,
            room_name=room_name,
        )
        if not uploaded:
            return
        storage_path, recording_url = uploaded
        persist_recording_urls(
            room_name=room_name,
            storage_path=storage_path,
            recording_url=recording_url,
        )
    except Exception as exc:
        logger.warning(
            "session recording: finalize failed for room %s: %s",
            room_name,
            exc,
        )
