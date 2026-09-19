"""Upload LiveKit RecorderIO audio.ogg and persist URLs on sessions / telephony_calls."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from worker.recording_policy import may_persist_recording

logger = logging.getLogger("worker.session_recording")

BUCKET_ID = "session-recordings"
# D.3: do not persist long-lived signed URLs. Path is source of truth; portal re-signs on read.
SIGNED_URL_TTL_SECONDS = 60 * 60  # reserved if a future helper re-signs locally (not persisted)

# F-L15: ensure bucket once per process (None=not tried, True=ok, False=last attempt failed).
_bucket_ensured: bool | None = None


def reset_bucket_ensure_cache() -> None:
    """Test helper — clear process-level bucket cache."""
    global _bucket_ensured
    _bucket_ensured = None


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
    """Create/list bucket at most once per process (F-L15)."""
    global _bucket_ensured
    if _bucket_ensured is True:
        return True
    try:
        existing = {b.id for b in storage.list_buckets()}
        if BUCKET_ID not in existing:
            storage.create_bucket(BUCKET_ID, options={"public": False})
        _bucket_ensured = True
        return True
    except Exception as exc:
        logger.warning("session recording: bucket ensure failed: %s", exc)
        _bucket_ensured = False
        return False


def find_session_audio(session_directory: Path | None) -> Path | None:
    if session_directory is None:
        return None
    candidate = Path(session_directory) / "audio.ogg"
    if candidate.is_file() and candidate.stat().st_size > 0:
        return candidate
    return None


def _delete_local_audio(audio_path: Path | None) -> None:
    if audio_path is None:
        return
    try:
        audio_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning(
            "session recording: failed to delete local audio %s: %s",
            audio_path,
            exc,
        )


def upload_session_audio(
    *,
    audio_path: Path,
    tenant_id: str,
    room_name: str,
) -> str | None:
    """Upload audio.ogg → storage_path or None on failure.

    Does not return a signed URL (F-C4 D.3 — path is source of truth).
    """
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
        except Exception as exc:
            # F-M1: do not swallow silently — prior object may be absent (ok) or delete failed.
            logger.warning(
                "session recording: prior object remove failed path=%s: %s",
                storage_path,
                exc,
            )
        bucket.upload(
            storage_path,
            data,
            file_options={"content-type": "audio/ogg", "upsert": "true"},
        )
        return storage_path
    except Exception as exc:
        logger.warning("session recording: upload failed for room %s: %s", room_name, exc)
        return None


def persist_recording_urls(
    *,
    room_name: str,
    storage_path: str,
    recording_url: str | None = None,
) -> None:
    """Write storage path on sessions + telephony_calls; clear long-lived recording_url (D.3)."""
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "scripts"))
    try:
        from scripts.dbconn import conn_kwargs
    except ImportError:
        from dbconn import conn_kwargs  # type: ignore

    import psycopg

    # Explicit null — do not store signed URLs as source of truth.
    url_value = recording_url  # callers should pass None

    try:
        with psycopg.connect(**conn_kwargs(), connect_timeout=5, autocommit=True) as conn:
            conn.execute(
                """
                update sessions
                   set recording_url = %s,
                       recording_storage_path = %s
                 where room_name = %s
                """,
                (url_value, storage_path, room_name),
            )
            conn.execute(
                """
                update telephony_calls
                   set recording_url = %s,
                       recording_storage_path = %s,
                       updated_at = now()
                 where room_name = %s
                """,
                (url_value, storage_path, room_name),
            )
        logger.info(
            "session recording persisted room=%s path=%s url_stored=%s",
            room_name,
            storage_path,
            bool(url_value),
        )
    except Exception as exc:
        logger.warning(
            "session recording: failed to persist URLs for room %s: %s",
            room_name,
            exc,
        )


def _recording_persist_allowed(job_ctx: Any) -> bool:
    session = getattr(job_ctx, "_primary_agent_session", None)
    userdata = getattr(session, "userdata", None) if session is not None else None
    may_start = bool(getattr(userdata, "recording_may_start", False))
    consent = getattr(userdata, "recording_consent_status", None)
    return may_persist_recording(may_start=may_start, consent_status=consent)


async def finalize_and_persist_session_recording(
    *,
    job_ctx: Any,
    room_name: str,
    tenant_id: str,
) -> None:
    """Close RecorderIO if needed; upload only when persist policy allows."""
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

        if not _recording_persist_allowed(job_ctx):
            logger.info(
                "session recording: persist skipped by policy room=%s",
                room_name,
            )
            _delete_local_audio(audio_path)
            return

        uploaded = upload_session_audio(
            audio_path=audio_path,
            tenant_id=tenant_id,
            room_name=room_name,
        )
        if not uploaded:
            return
        persist_recording_urls(
            room_name=room_name,
            storage_path=uploaded,
            recording_url=None,
        )
        _delete_local_audio(audio_path)
    except Exception as exc:
        logger.warning(
            "session recording: finalize failed for room %s: %s",
            room_name,
            exc,
        )
