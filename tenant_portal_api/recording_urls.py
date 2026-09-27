"""Short-lived signed recording URLs for portal/session reads (F-C4 D.3).

Worker stores ``recording_storage_path`` only. Portal re-signs on read via Storage REST
(httpx — no supabase-py dep on the slim portal image).
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger("tenant_portal_api.recording_urls")

BUCKET_ID = "session-recordings"
# Match worker/session_recording.py reserved TTL; short enough that stale URLs expire.
SIGNED_URL_TTL_SECONDS = 60 * 60


def _supabase_rest() -> tuple[str, str] | None:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE") or "").strip()
    if not url or not key:
        return None
    return url, key


def create_signed_recording_url(
    storage_path: str | None, *, ttl_seconds: int = SIGNED_URL_TTL_SECONDS
) -> str | None:
    """Return a full signed GET URL for ``storage_path``, or None if unavailable."""
    path = (storage_path or "").strip().lstrip("/")
    if not path:
        return None
    creds = _supabase_rest()
    if creds is None:
        return None
    base, key = creds
    # Path may contain slashes — encode each segment but keep separators.
    encoded = "/".join(quote(seg, safe="") for seg in path.split("/") if seg)
    endpoint = f"{base}/storage/v1/object/sign/{BUCKET_ID}/{encoded}"
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {key}",
                    "apikey": key,
                    "Content-Type": "application/json",
                },
                json={"expiresIn": int(ttl_seconds)},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("recording re-sign failed path=%s: %s", path, exc)
        return None

    signed = data.get("signedURL") or data.get("signedUrl") or data.get("signed_url")
    if not signed or not isinstance(signed, str):
        return None
    if signed.startswith("http://") or signed.startswith("https://"):
        return signed
    if not signed.startswith("/"):
        signed = "/" + signed
    return f"{base}/storage/v1{signed}"


def enrich_session_recording(session: dict[str, Any]) -> dict[str, Any]:
    """Set ``recording_url`` / ``recordingUrl`` from storage path when possible.

    Leaves existing ``recording_url`` if re-sign fails (legacy rows that still have one).
    Never returns ``recording_storage_path`` to clients — path is internal.
    """
    path = session.get("recording_storage_path")
    signed = create_signed_recording_url(path if isinstance(path, str) else None)
    if signed:
        session["recording_url"] = signed
        session["recordingUrl"] = signed
    elif session.get("recording_url"):
        session["recordingUrl"] = session["recording_url"]
    session.pop("recording_storage_path", None)
    return session
