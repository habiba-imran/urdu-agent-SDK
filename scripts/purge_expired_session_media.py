#!/usr/bin/env python3
"""Purge expired / deletion-requested session media (F-C4 Phase D).

Usage:
    python scripts/purge_expired_session_media.py [--dry-run] [--limit N]

What it does:
1. Finds ``sessions`` rows (when retention columns exist) with
   ``retention_until < now()`` OR ``deletion_requested_at`` set, and ``deleted_at`` null.
2. Finds ``telephony_calls`` rows with the same predicates (columns exist since 0014).
3. Deletes Supabase Storage objects at ``recording_storage_path`` (bucket ``session-recordings``).
4. Nulls ``recording_url``, ``recording_storage_path``, ``transcript`` (sessions);
   redacts ``escalations.contact_info`` for related session ids;
   sets ``deleted_at`` / ``redacted_at`` where columns exist.

Scheduling (cron / Render / GitHub Actions) is owned by Ehsan — this script is the
worker-side correctness piece. See ``docs/WAVE2-SESSION-MEDIA-ERASURE.md``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from dbconn import conn_kwargs
except ImportError:
    from scripts.dbconn import conn_kwargs  # type: ignore # noqa: E402

logger = logging.getLogger("purge_expired_session_media")

BUCKET_ID = "session-recordings"


@dataclass
class PurgeStats:
    sessions_scanned: int = 0
    telephony_scanned: int = 0
    storage_deleted: int = 0
    storage_failed: int = 0
    sessions_purged: int = 0
    telephony_purged: int = 0
    escalations_redacted: int = 0
    skipped_no_session_cols: bool = False


@dataclass
class PurgeTarget:
    kind: str  # "session" | "telephony"
    row_id: str
    room_name: str | None
    storage_path: str | None
    session_id: str | None = None  # for escalations (sessions.id)


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        select 1
          from information_schema.columns
         where table_schema = 'public'
           and table_name = %s
           and column_name = %s
         limit 1
        """,
        (table, column),
    ).fetchone()
    return row is not None


def _supabase_storage() -> Any | None:
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE") or "").strip()
    if not url or not key:
        logger.warning("SUPABASE_URL / SUPABASE_SERVICE_ROLE not set — storage deletes skipped")
        return None
    try:
        from supabase import create_client

        return create_client(url, key).storage
    except Exception as exc:
        logger.warning("supabase client failed: %s", exc)
        return None


def delete_storage_object(storage: Any | None, storage_path: str) -> bool:
    if not storage_path:
        return True
    if storage is None:
        return False
    try:
        storage.from_(BUCKET_ID).remove([storage_path])
        return True
    except Exception as exc:
        logger.warning("storage delete failed path=%s: %s", storage_path, exc)
        return False


def select_session_targets(conn: Any, *, limit: int) -> list[PurgeTarget]:
    if not _column_exists(conn, "sessions", "retention_until"):
        return []
    if not _column_exists(conn, "sessions", "deleted_at"):
        return []
    rows = conn.execute(
        """
        select id::text, room_name, recording_storage_path
          from sessions
         where deleted_at is null
           and (
                (retention_until is not null and retention_until < now())
                or deletion_requested_at is not null
           )
         order by coalesce(retention_until, deletion_requested_at) asc nulls last
         limit %s
        """,
        (limit,),
    ).fetchall()
    return [
        PurgeTarget(
            kind="session",
            row_id=str(r[0]),
            room_name=r[1],
            storage_path=r[2],
            session_id=str(r[0]),
        )
        for r in rows
    ]


def select_telephony_targets(conn: Any, *, limit: int) -> list[PurgeTarget]:
    rows = conn.execute(
        """
        select id::text, room_name, recording_storage_path, session_id::text
          from telephony_calls
         where deleted_at is null
           and (
                (retention_until is not null and retention_until < now())
                or deletion_requested_at is not null
           )
         order by coalesce(retention_until, deletion_requested_at) asc nulls last
         limit %s
        """,
        (limit,),
    ).fetchall()
    return [
        PurgeTarget(
            kind="telephony",
            row_id=str(r[0]),
            room_name=r[1],
            storage_path=r[2],
            session_id=str(r[3]) if r[3] else None,
        )
        for r in rows
    ]


def purge_session_row(conn: Any, target: PurgeTarget) -> None:
    has_redacted = _column_exists(conn, "sessions", "redacted_at")
    if has_redacted:
        conn.execute(
            """
            update sessions
               set recording_url = null,
                   recording_storage_path = null,
                   transcript = null,
                   deleted_at = coalesce(deleted_at, now()),
                   redacted_at = coalesce(redacted_at, now())
             where id = %s::uuid
            """,
            (target.row_id,),
        )
    else:
        conn.execute(
            """
            update sessions
               set recording_url = null,
                   recording_storage_path = null,
                   transcript = null,
                   deleted_at = coalesce(deleted_at, now())
             where id = %s::uuid
            """,
            (target.row_id,),
        )


def purge_telephony_row(conn: Any, target: PurgeTarget) -> None:
    conn.execute(
        """
        update telephony_calls
           set recording_url = null,
               recording_storage_path = null,
               deleted_at = coalesce(deleted_at, now()),
               redacted_at = coalesce(redacted_at, now()),
               updated_at = now()
         where id = %s::uuid
        """,
        (target.row_id,),
    )


def redact_escalations_for_session(conn: Any, session_id: str) -> int:
    has_redacted = _column_exists(conn, "escalations", "redacted_at")
    has_deleted = _column_exists(conn, "escalations", "deleted_at")
    if has_redacted and has_deleted:
        cur = conn.execute(
            """
            update escalations
               set contact_info = null,
                   redacted_at = coalesce(redacted_at, now()),
                   deleted_at = coalesce(deleted_at, now())
             where session_id = %s::uuid
               and (contact_info is not null or deleted_at is null)
            """,
            (session_id,),
        )
    else:
        cur = conn.execute(
            """
            update escalations
               set contact_info = null
             where session_id = %s::uuid
               and contact_info is not null
            """,
            (session_id,),
        )
    return int(cur.rowcount or 0) if cur is not None else 0


def run_purge(*, dry_run: bool = False, limit: int = 200) -> PurgeStats:
    stats = PurgeStats()
    storage = None if dry_run else _supabase_storage()

    with psycopg.connect(
        **conn_kwargs(), connect_timeout=10, autocommit=not dry_run
    ) as conn:
        has_session_cols = _column_exists(conn, "sessions", "retention_until") and _column_exists(
            conn, "sessions", "deleted_at"
        )
        if not has_session_cols:
            stats.skipped_no_session_cols = True
            print(
                "[purge] sessions retention/deleted_at columns missing — "
                "purging telephony_calls only until Ehsan A.3 migration lands."
            )

        session_targets = select_session_targets(conn, limit=limit) if has_session_cols else []
        telephony_targets = select_telephony_targets(conn, limit=limit)
        stats.sessions_scanned = len(session_targets)
        stats.telephony_scanned = len(telephony_targets)

        print(
            f"[purge] targets sessions={stats.sessions_scanned} "
            f"telephony={stats.telephony_scanned} dry_run={dry_run}"
        )

        # Dedupe storage deletes by path (only after successful delete).
        paths_done: set[str] = set()
        paths_failed: set[str] = set()

        def _handle(target: PurgeTarget) -> None:
            path = (target.storage_path or "").strip()
            if path:
                if path in paths_failed:
                    stats.storage_failed += 1
                    print(
                        f"  skip {target.kind} id={target.row_id} — "
                        f"storage already failed for {path}"
                    )
                    return
                if path not in paths_done:
                    if dry_run:
                        print(f"  [dry-run] would delete storage {path}")
                        stats.storage_deleted += 1
                        paths_done.add(path)
                    else:
                        ok = delete_storage_object(storage, path)
                        if ok:
                            stats.storage_deleted += 1
                            paths_done.add(path)
                        else:
                            stats.storage_failed += 1
                            paths_failed.add(path)
                            print(
                                f"  skip DB purge for {target.kind} id={target.row_id} — "
                                f"storage delete failed for {path}"
                            )
                            return

            if dry_run:
                print(
                    f"  [dry-run] would purge {target.kind} id={target.row_id} "
                    f"room={target.room_name}"
                )
                return

            if target.kind == "session":
                purge_session_row(conn, target)
                stats.sessions_purged += 1
                if target.session_id:
                    stats.escalations_redacted += redact_escalations_for_session(
                        conn, target.session_id
                    )
            else:
                purge_telephony_row(conn, target)
                stats.telephony_purged += 1
                if target.session_id:
                    stats.escalations_redacted += redact_escalations_for_session(
                        conn, target.session_id
                    )

        for t in session_targets:
            _handle(t)
        for t in telephony_targets:
            _handle(t)

        if dry_run:
            conn.rollback()

    print(
        f"[purge] done storage_deleted={stats.storage_deleted} "
        f"storage_failed={stats.storage_failed} "
        f"sessions_purged={stats.sessions_purged} "
        f"telephony_purged={stats.telephony_purged} "
        f"escalations_redacted={stats.escalations_redacted}"
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Select targets and print actions without writing or deleting",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max rows per table per run (default 200)",
    )
    args = parser.parse_args(argv)
    stats = run_purge(dry_run=args.dry_run, limit=max(1, args.limit))
    if stats.storage_failed > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
