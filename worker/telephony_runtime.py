"""Worker-side runtime resolver and event hooks for telephony SIP calls.

Extracts trusted LiveKit SIP participant attributes and resolves tenant, agent,
and phone number records before conversation startup.

Minimal non-intrusive hooks for worker/main.py.
Derived from docs/TELEPHONY_API_AND_SCHEMA_CONTRACT.md.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from tenant_portal_api.telephony_config import is_mock_provider_mode

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def extract_sip_participant_attributes(
    participant_metadata: dict[str, Any] | str | None = None,
    participant_attributes: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Extract LiveKit SIP attributes from participant attributes and/or metadata."""
    attrs = dict(participant_attributes or {})
    meta = _as_dict(participant_metadata)
    sip_meta = meta.get("sip") if isinstance(meta.get("sip"), dict) else meta

    def _get(*keys: str) -> str:
        for key in keys:
            if attrs.get(key):
                return str(attrs[key])
            if sip_meta.get(key):
                return str(sip_meta[key])
        return ""

    return {
        "sip_call_id": _get("sip.callID", "callID"),
        "sip_call_id_full": _get("sip.callIDFull", "callIDFull"),
        "trunk_phone_number": _get("sip.trunkPhoneNumber", "trunkPhoneNumber"),
        # LiveKit AttrSIPPhoneNumber — caller ANI (inbound) / dialed party (outbound).
        # Never confuse with trunk_phone_number (platform number).
        "caller_phone_number": _get("sip.phoneNumber", "phoneNumber"),
        "trunk_id": _get("sip.trunkID", "trunkID"),
        "rule_id": _get("sip.ruleID", "ruleID"),
    }


def is_sip_participant(
    participant: Any = None,
    *,
    participant_metadata: dict[str, Any] | str | None = None,
    participant_attributes: dict[str, Any] | None = None,
) -> bool:
    """Return True when the joining participant looks like a LiveKit SIP caller."""
    attrs = dict(participant_attributes or {})
    if participant is not None:
        raw_attrs = getattr(participant, "attributes", None) or {}
        if isinstance(raw_attrs, dict):
            attrs.update(raw_attrs)
        kind = str(getattr(participant, "kind", "") or "").lower()
        identity = str(getattr(participant, "identity", "") or "").lower()
        if "sip" in kind or identity.startswith("sip_"):
            return True
    extracted = extract_sip_participant_attributes(participant_metadata, attrs)
    return bool(
        extracted["trunk_phone_number"]
        or extracted["sip_call_id"]
        or extracted["trunk_id"]
    )


def parse_job_telephony_metadata(job_metadata: Any) -> dict[str, Any]:
    """Parse CreateAgentDispatch / RoomAgentDispatch metadata for telephony jobs."""
    meta = _as_dict(job_metadata)
    tenant_id = meta.get("tenant_id")
    agent_id = meta.get("agent_id")
    if not tenant_id or not agent_id:
        return {}
    return {
        "tenant_id": str(tenant_id),
        "agent_id": str(agent_id),
        "telephony_call_id": str(meta.get("telephony_call_id") or ""),
        "direction": str(meta.get("direction") or "outbound"),
        "e164_number": str(meta.get("e164_number") or meta.get("from_number") or ""),
        "sip_call_id": str(meta.get("sip_call_id") or ""),
        "status": "resolved",
        "source": "job_metadata",
    }


def _commit(db_conn: Any) -> None:
    """Commit when the connection is transactional (worker opens psycopg without autocommit)."""
    commit = getattr(db_conn, "commit", None)
    if callable(commit) and not getattr(db_conn, "autocommit", False):
        commit()


def _rollback(db_conn: Any) -> None:
    rollback = getattr(db_conn, "rollback", None)
    if callable(rollback):
        try:
            rollback()
        except Exception as err:  # pragma: no cover - best effort
            logger.warning("inbound call rollback failed: %s", err)


def _find_inbound_call_for_room(db_conn: Any, room_name: str) -> dict[str, Any] | None:
    row = db_conn.execute(
        """
        select id, session_id from telephony_calls
        where room_name = %s and direction = 'inbound'
        order by created_at desc limit 1
        """,
        (room_name,),
    ).fetchone()
    if not row:
        return None
    return {"telephony_call_id": str(row[0]), "session_id": str(row[1]) if row[1] else None}


def _persist_inbound_call(
    db_conn: Any,
    *,
    tenant_id: str,
    agent_id: str,
    phone_number_id: str,
    e164_number: str,
    room_name: str,
    attributes: dict[str, str],
    quota_reserved: bool,
) -> dict[str, Any]:
    """Insert the ``sessions`` + ``telephony_calls`` rows for an answered inbound call.

    A-01.4: without these rows the call is invisible to call history, never billed
    (``worker/session_close`` keys on ``sessions.room_name``), has no recording link
    (``persist_recording_urls`` updates both tables by ``room_name``) and its quota slot
    can never be released (``quota_released_at`` ledger). Mirrors the outbound insert in
    ``telephony_service.create_outbound_call``.
    """
    import uuid

    session_id = str(uuid.uuid4())
    call_id = str(uuid.uuid4())

    db_conn.execute(
        "insert into sessions (id, tenant_id, agent_id, room_name) values (%s, %s, %s, %s)",
        (session_id, tenant_id, agent_id, room_name),
    )

    inbound_trunk_record_id = None
    dispatch_rule_record_id = None
    try:
        rule_row = db_conn.execute(
            """
            select id, inbound_trunk_record_id from livekit_sip_dispatch_rules
            where tenant_id = %s and phone_number_id = %s and disabled_at is null
            order by created_at desc limit 1
            """,
            (tenant_id, phone_number_id),
        ).fetchone()
        if rule_row:
            dispatch_rule_record_id = str(rule_row[0]) if rule_row[0] else None
            inbound_trunk_record_id = (
                str(rule_row[1]) if len(rule_row) > 1 and rule_row[1] else None
            )
    except Exception as err:
        logger.info("inbound call: routing record lookup skipped: %s", err)

    db_conn.execute(
        """
        insert into telephony_calls (
            id, tenant_id, session_id, agent_id, phone_number_id, direction, room_name,
            from_number, to_number, inbound_trunk_record_id, sip_dispatch_rule_record_id,
            livekit_sip_call_id, livekit_sip_call_id_full, sip_trunk_phone_number,
            platform_status, provider_status, quota_reserved_at, started_at, answered_at
        ) values (%s, %s, %s, %s, %s, 'inbound', %s,
                  %s, %s, %s, %s,
                  %s, %s, %s,
                  'in_progress', 'answered', case when %s then now() else null end, now(), now())
        """,
        (
            call_id,
            tenant_id,
            session_id,
            agent_id,
            phone_number_id,
            room_name,
            attributes.get("caller_phone_number") or None,
            e164_number,
            inbound_trunk_record_id,
            dispatch_rule_record_id,
            attributes.get("sip_call_id") or None,
            attributes.get("sip_call_id_full") or None,
            e164_number,
            bool(quota_reserved),
        ),
    )
    return {"telephony_call_id": call_id, "session_id": session_id}


def resolve_inbound_sip_call(
    participant_metadata: dict[str, Any] | str | None = None,
    db_conn: Any = None,
    participant_attributes: dict[str, Any] | None = None,
    *,
    room_name: str | None = None,
) -> dict[str, Any]:
    """Resolve tenant, agent, and number routing from LiveKit SIP participant attributes.

    With ``room_name`` and a DB connection this also reserves the concurrency slot and
    persists the ``sessions`` / ``telephony_calls`` rows for the call in one committed
    transaction, returning ``telephony_call_id`` and ``session_id``. Re-resolving a room
    that already has a call row reuses it (no second reservation).

    Raises ValueError on unknown, unassigned or not-ready numbers and on quota exhaustion.
    """
    attributes = extract_sip_participant_attributes(
        participant_metadata, participant_attributes
    )
    trunk_num = attributes["trunk_phone_number"]

    # Explicit local/test mock mode. Real staging must provide a DB connection.
    if not db_conn:
        if not is_mock_provider_mode():
            raise ValueError(
                "Database connection is required for live inbound SIP resolution"
            )
        logger.info(
            "Resolving inbound SIP call for number: %s (mock mode)",
            trunk_num or "+15551234567",
        )
        return {
            "tenant_id": "tenant_test_123",
            "agent_id": "agent_test_456",
            "e164_number": trunk_num or "+15551234567",
            "sip_call_id": attributes["sip_call_id"] or "sip_call_mock_inbound",
            "direction": "inbound",
            "status": "resolved",
            "source": "sip_attributes",
        }

    if not trunk_num:
        raise ValueError("Inbound SIP participant is missing sip.trunkPhoneNumber")

    # DB Resolution using parameterized query
    row = db_conn.execute(
        """
        select n.tenant_id, n.assigned_agent_id, n.e164_number, n.routing_status, t.status, n.id
        from telephony_phone_numbers n
        join tenants t on t.id = n.tenant_id
        where n.e164_number = %s and n.disabled_at is null
        """,
        (trunk_num,),
    ).fetchone()

    if not row:
        logger.warning("Rejecting inbound call: unknown number %s", trunk_num)
        raise ValueError(f"Unknown inbound phone number: {trunk_num}")

    tenant_id, agent_id, e164_num, routing_status, tenant_status, phone_number_id = row

    if tenant_status != "active":
        raise ValueError(f"Tenant {tenant_id} is not active")

    if not agent_id:
        raise ValueError(f"Number {e164_num} is not assigned to an agent")

    if routing_status != "ready":
        raise ValueError(f"Number {e164_num} routing is not ready")

    result: dict[str, Any] = {
        "tenant_id": str(tenant_id),
        "agent_id": str(agent_id),
        "e164_number": e164_num,
        "phone_number_id": str(phone_number_id),
        "sip_call_id": attributes["sip_call_id"],
        "caller_phone_number": attributes["caller_phone_number"],
        "direction": "inbound",
        "status": "resolved",
        "source": "sip_attributes",
        "room_name": (room_name or "").strip() or None,
        "telephony_call_id": None,
        "session_id": None,
    }

    room = result["room_name"]
    if room:
        try:
            existing = _find_inbound_call_for_room(db_conn, room)
        except Exception as err:
            existing = None
            logger.warning("inbound call: existing-row lookup failed room=%s: %s", room, err)
        if existing:
            # Worker retry / second participant for a room we already persisted.
            logger.info(
                "inbound call: reusing call row room=%s call=%s", room, existing["telephony_call_id"]
            )
            result.update(existing)
            return result

    quota_reserved = False
    try:
        from tenant_portal_api import telephony_queries as queries
        if not queries.reserve_call_quota(db_conn, str(tenant_id)):
            logger.warning("Rejecting inbound call for tenant %s: concurrency limit reached", tenant_id)
            _rollback(db_conn)
            raise ValueError(f"Tenant {tenant_id} concurrency limit reached")
        quota_reserved = True
    except Exception as err:
        if isinstance(err, ValueError):
            raise
        logger.warning("Could not verify call quota during inbound resolution: %s", err)

    if room:
        try:
            result.update(
                _persist_inbound_call(
                    db_conn,
                    tenant_id=str(tenant_id),
                    agent_id=str(agent_id),
                    phone_number_id=str(phone_number_id),
                    e164_number=e164_num,
                    room_name=room,
                    attributes=attributes,
                    quota_reserved=quota_reserved,
                )
            )
        except Exception as err:
            # Fail open on persistence: the caller is already connected, dropping them
            # for a DB blip is worse than an untracked call. Reservation is rolled back
            # with the rows so nothing leaks.
            _rollback(db_conn)
            logger.error(
                "inbound call: failed to persist sessions/telephony_calls rows room=%s tenant=%s: %s",
                room,
                tenant_id,
                err,
            )
            return result
    else:
        logger.warning(
            "inbound call: no room_name supplied — quota reserved for tenant %s but no "
            "telephony_calls row written; the slot can only be released by reconciliation",
            tenant_id,
        )

    try:
        _commit(db_conn)
    except Exception as err:
        _rollback(db_conn)
        logger.error("inbound call: commit failed room=%s tenant=%s: %s", room, tenant_id, err)
        result["telephony_call_id"] = None
        result["session_id"] = None

    return result


def session_audio_channel(resolved: dict[str, Any]) -> str:
    """Return ``telephony`` when the session is PSTN/SIP-bound, else ``webrtc``.

    Uses the ``telephony`` block from :func:`resolve_session_metadata` — present for inbound SIP,
    outbound dispatch jobs, and other telephony-bound sessions.
    """
    if resolved.get("telephony"):
        return "telephony"
    return "webrtc"




def resolve_session_metadata(
    *,
    job_metadata: Any = None,
    participant: Any = None,
    db_conn: Any = None,
    room_name: str | None = None,
) -> dict[str, Any]:
    """Resolve tenant/agent session metadata for web or telephony jobs.

    Priority:
    1. Explicit agent-dispatch job metadata (outbound / pre-resolved inbound)
    2. SIP participant attributes → DB number lookup
    3. Participant JWT metadata (browser /v1/session mint path)
    """
    from_job = parse_job_telephony_metadata(job_metadata)
    if from_job:
        if db_conn:
            e164 = from_job.get("e164_number")
            if e164:
                try:
                    row = db_conn.execute(
                        """
                        select n.tenant_id, n.assigned_agent_id, n.provisioning_status, n.routing_status
                        from telephony_phone_numbers n
                        where n.e164_number = %s
                        """,
                        (e164,),

                    ).fetchone()
                    if row:
                        db_tenant_id, db_agent_id, db_prov_status, db_route_status = row
                        if db_prov_status == "disabled" or db_route_status == "disabled":
                            logger.warning("Rejecting job metadata: phone number %s is disabled in DB", e164)
                            raise ValueError(f"Phone number {e164} is disabled")
                        if str(db_tenant_id) != from_job["tenant_id"] or (db_agent_id and str(db_agent_id) != from_job["agent_id"]):
                            logger.warning(
                                "Job metadata divergence detected for %s: enqueued tenant/agent (%s, %s) vs DB (%s, %s)",
                                e164, from_job["tenant_id"], from_job["agent_id"], db_tenant_id, db_agent_id
                            )
                            from_job["tenant_id"] = str(db_tenant_id)
                            if db_agent_id:
                                from_job["agent_id"] = str(db_agent_id)
                except ValueError:
                    raise
                except Exception as err:
                    logger.warning("Could not revalidate job metadata against DB: %s", err)
        return {
            "tenant_id": from_job["tenant_id"],
            "agent_id": from_job["agent_id"],
            "telephony": from_job,
        }


    participant_metadata = (
        getattr(participant, "metadata", None) if participant is not None else None
    )
    participant_attributes = (
        getattr(participant, "attributes", None) if participant is not None else None
    )
    if isinstance(participant_attributes, dict) and is_sip_participant(
        participant,
        participant_metadata=participant_metadata,
        participant_attributes=participant_attributes,
    ):
        resolved = resolve_inbound_sip_call(
            participant_metadata=participant_metadata,
            participant_attributes=participant_attributes,
            db_conn=db_conn,
            room_name=room_name,
        )
        return {
            "tenant_id": resolved["tenant_id"],
            "agent_id": resolved["agent_id"],
            "telephony": resolved,
        }

    md = _as_dict(participant_metadata)
    return {
        "tenant_id": md.get("tenant_id", ""),
        "agent_id": md.get("agent_id", ""),
        "telephony": None,
    }


def transport_diagnostics(resolved: dict[str, Any], *, participant: Any = None) -> dict[str, Any]:
    meta = resolved.get("telephony") or {}
    attrs = getattr(participant, "attributes", None) or {}
    return {
        "channel": session_audio_channel(resolved).upper(),
        "direction": meta.get("direction") or "UNKNOWN",
        "route": meta.get("trunk_id") or attrs.get("sip.trunkID") or "UNKNOWN",
        "provider": meta.get("provider") or "UNKNOWN",
        "codec": meta.get("codec") or attrs.get("sip.codec") or "UNKNOWN",
        "playback_ready": None,
        "rtt_ms": None, "jitter_ms": None, "loss": None,
    }
