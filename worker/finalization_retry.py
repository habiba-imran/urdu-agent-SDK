"""Local durable close payloads; SQL settlement itself remains one transaction.

The directory must be on persistent worker storage in hosted deployments. It contains
transcripts and must have the same access/retention policy as session data.
"""
from __future__ import annotations
import hashlib
import json
import os
import logging
import time
from pathlib import Path
from types import SimpleNamespace

log = logging.getLogger("worker.finalization_retry")


def directory() -> Path:
    return Path(os.getenv("WORKER_FINALIZATION_DIR", "state/pending-finalizations"))


def settle_session(*, room_name, tenant_id, elapsed_sec, end_reason, session_obj=None):
    from worker.session_close import build_transcript, release_session_quota_slot
    from worker.usage import collect_model_usage
    payload = dict(room_name=room_name, tenant_id=tenant_id, elapsed_sec=elapsed_sec,
                   end_reason=end_reason, transcript=build_transcript(session_obj) if session_obj else [],
                   lifecycle_metrics=getattr(session_obj, "_awaaz_lifecycle_metrics", None),
                   usage=collect_model_usage(session_obj) if session_obj else {})
    root = directory()
    root.mkdir(parents=True, exist_ok=True)
    target = root / (hashlib.sha256(room_name.encode()).hexdigest() + ".json")
    import uuid
    temporary = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, target)
    last_error = None
    for attempt in range(3):
        try:
            outcome = release_session_quota_slot(**{k: v for k, v in payload.items() if k != "usage"},
                session_obj=SimpleNamespace(_awaaz_final_usage=payload["usage"]))
            if outcome.session_id is None and not outcome.telephony_call_id:
                # Missing/already-closed rows require no duplicate accounting. A DB
                # connect failure raises, so it cannot incorrectly clear this payload.
                log.info("finalization_no_open_row room=%s", room_name)
            target.unlink(missing_ok=True)
            return outcome
        except Exception as error:
            last_error = error
            if attempt < 2:
                time.sleep(.25 * (attempt + 1))
    log.error("finalization_pending room=%s error_type=%s", room_name, type(last_error).__name__)
    raise RuntimeError("Session finalization pending durable retry") from last_error


def retry_pending() -> int:
    from worker.session_close import release_session_quota_slot
    completed = 0
    root = directory()
    if not root.exists():
        return 0
    for target in list(root.glob("*.json"))[:100]:
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            usage = payload.pop("usage")
            release_session_quota_slot(**payload, session_obj=SimpleNamespace(_awaaz_final_usage=usage))
            target.unlink(missing_ok=True)
            completed += 1
        except Exception:
            log.exception("finalization_retry_failed file=%s", target.name)
    return completed


def start_retry_service() -> None:
    """The worker parent owns retry even while no new jobs arrive."""
    import threading
    def run():
        while True:
            time.sleep(30)
            try:
                retry_pending()
            except Exception:
                log.exception("finalization_retry_service_failed")
    threading.Thread(target=run, name="session-finalization-retry", daemon=True).start()
