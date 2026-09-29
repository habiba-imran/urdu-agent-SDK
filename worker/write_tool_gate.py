"""F-C7 Phase E: gated destructive client write tools.

Two-step protocol (Option 1): first call proposes (no HTTP); second call with
``confirmation_id`` POSTs only after a user turn has advanced, schema/ownership/
budget checks pass, and the pending proposal matches.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Successful write POSTs per session (audit MAX_TOOL_CALLS / write budget).
_DEFAULT_MAX_WRITE_TOOL_CALLS = 5
_PENDING_TTL_SEC = 300.0

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WRITE_TOOLS = frozenset(
    {"book_appointment", "reschedule_appointment", "cancel_appointment"}
)


def max_write_tool_calls() -> int:
    raw = (os.environ.get("UVA_MAX_WRITE_TOOL_CALLS") or "").strip()
    if not raw:
        return _DEFAULT_MAX_WRITE_TOOL_CALLS
    try:
        n = int(raw)
    except ValueError:
        return _DEFAULT_MAX_WRITE_TOOL_CALLS
    return max(1, n)


def normalize_phone(raw: str | None) -> str:
    """Normalize for comparison: keep leading + when present; digits otherwise."""
    s = (raw or "").strip()
    if not s:
        return ""
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return ""
    if s.startswith("+"):
        return "+" + digits
    return digits


def phones_match(a: str | None, b: str | None) -> bool:
    na, nb = normalize_phone(a), normalize_phone(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # +92300… vs 92300… / 0300… — compare digit forms; strip leading zeros for
    # national vs E.164 suffix match (no country-code inventing).
    da = "".join(c for c in na if c.isdigit())
    db = "".join(c for c in nb if c.isdigit())
    if da == db:
        return True
    da_nz = da.lstrip("0") or da
    db_nz = db.lstrip("0") or db
    if da_nz == db_nz:
        return True
    shorter, longer = (da_nz, db_nz) if len(da_nz) <= len(db_nz) else (db_nz, da_nz)
    return len(shorter) >= 9 and longer.endswith(shorter)


def _parse_iso_datetime(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        # fromisoformat accepts "2026-09-18T10:00:00" and offsets with :
        datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return s


def _parse_iso_date(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip()
    if not _ISO_DATE.match(s):
        return None
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None
    return s


def validate_write_args(tool_name: str, args: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Return (normalized_args, error). Reject unknown keys for write tools."""
    if tool_name == "book_appointment":
        allowed = {"customer_name", "customer_phone", "slot_start_time", "service_name"}
        extra = set(args) - allowed
        if extra:
            return None, f"unexpected fields: {sorted(extra)}"
        name = str(args.get("customer_name") or "").strip()
        phone = normalize_phone(str(args.get("customer_phone") or ""))
        slot = _parse_iso_datetime(str(args.get("slot_start_time") or ""))
        if not name:
            return None, "customer_name is required"
        if not phone or len("".join(c for c in phone if c.isdigit())) < 7:
            return None, "customer_phone is invalid"
        if not slot:
            return None, "slot_start_time must be ISO-8601"
        out: dict[str, Any] = {
            "customer_name": name,
            "customer_phone": phone,
            "slot_start_time": slot,
        }
        svc = args.get("service_name")
        if svc is not None and str(svc).strip():
            out["service_name"] = str(svc).strip()
        return out, None

    if tool_name == "reschedule_appointment":
        allowed = {
            "customer_phone",
            "new_slot_start_time",
            "existing_date",
            "service_name",
        }
        extra = set(args) - allowed
        if extra:
            return None, f"unexpected fields: {sorted(extra)}"
        phone = normalize_phone(str(args.get("customer_phone") or ""))
        slot = _parse_iso_datetime(str(args.get("new_slot_start_time") or ""))
        if not phone or len("".join(c for c in phone if c.isdigit())) < 7:
            return None, "customer_phone is invalid"
        if not slot:
            return None, "new_slot_start_time must be ISO-8601"
        out = {"customer_phone": phone, "new_slot_start_time": slot}
        ed = _parse_iso_date(args.get("existing_date"))
        if args.get("existing_date") and not ed:
            return None, "existing_date must be YYYY-MM-DD"
        if ed:
            out["existing_date"] = ed
        svc = args.get("service_name")
        if svc is not None and str(svc).strip():
            out["service_name"] = str(svc).strip()
        return out, None

    if tool_name == "cancel_appointment":
        allowed = {"customer_phone", "existing_date", "reason"}
        extra = set(args) - allowed
        if extra:
            return None, f"unexpected fields: {sorted(extra)}"
        phone = normalize_phone(str(args.get("customer_phone") or ""))
        if not phone or len("".join(c for c in phone if c.isdigit())) < 7:
            return None, "customer_phone is invalid"
        out = {"customer_phone": phone}
        ed = _parse_iso_date(args.get("existing_date"))
        if args.get("existing_date") and not ed:
            return None, "existing_date must be YYYY-MM-DD"
        if ed:
            out["existing_date"] = ed
        reason = args.get("reason")
        if reason is not None and str(reason).strip():
            out["reason"] = str(reason).strip()[:200]
        return out, None

    return None, f"unknown write tool: {tool_name}"


def check_ownership(tool_name: str, args: dict[str, Any], verified_caller_phone: str | None) -> str | None:
    """Return error message or None if ownership OK."""
    verified = normalize_phone(verified_caller_phone)
    phone = str(args.get("customer_phone") or "")

    if tool_name in ("cancel_appointment", "reschedule_appointment"):
        if not verified:
            return (
                "verified_caller_phone is required for cancel/reschedule — "
                "host must pass it at mint (browser) or PSTN ANI must be available"
            )
        if not phones_match(phone, verified):
            return "customer_phone does not match verified caller identity"
        return None

    if tool_name == "book_appointment" and verified:
        if not phones_match(phone, verified):
            return "customer_phone does not match verified caller identity"
    return None


def args_hash(tool_name: str, args: dict[str, Any]) -> str:
    blob = f"{tool_name}|{sorted(args.items())!r}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def make_confirmation_id() -> str:
    return uuid.uuid4().hex


def make_idempotency_key(
    *,
    tenant_id: str,
    agent_id: str,
    room_name: str,
    tool_name: str,
    normalized_args: dict[str, Any],
    confirmation_id: str,
) -> str:
    raw = "|".join(
        [
            tenant_id,
            agent_id,
            room_name,
            tool_name,
            args_hash(tool_name, normalized_args),
            confirmation_id,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def summarize_write(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "book_appointment":
        return (
            f"Book {args.get('customer_name')} at {args.get('slot_start_time')} "
            f"phone {args.get('customer_phone')}"
        )
    if tool_name == "reschedule_appointment":
        return (
            f"Reschedule phone {args.get('customer_phone')} to {args.get('new_slot_start_time')}"
        )
    if tool_name == "cancel_appointment":
        return f"Cancel appointment for phone {args.get('customer_phone')}"
    return tool_name


@dataclass
class PendingWrite:
    tool: str
    args_hash: str
    args: dict[str, Any]
    confirmation_id: str
    created_at: float
    propose_user_turn_id: int
    path: str


@dataclass
class WriteGateState:
    pending_write: PendingWrite | None = None
    write_tool_calls: int = 0
    user_turn_count: int = 0
    verified_caller_phone: str | None = None
    last_idempotency_key: str | None = None
    last_write_result: dict[str, Any] | None = None
    # confirmation_id → {tool, args_hash, result, idempotency_key}
    completed_writes: dict[str, dict[str, Any]] = field(default_factory=dict)


def get_write_gate_state(userdata: Any) -> WriteGateState:
    state = getattr(userdata, "write_gate", None)
    if isinstance(state, WriteGateState):
        return state
    state = WriteGateState(
        verified_caller_phone=getattr(userdata, "verified_caller_phone", None),
        user_turn_count=int(getattr(userdata, "user_turn_count", 0) or 0),
    )
    userdata.write_gate = state
    # Keep flat fields in sync for diagnostics / older readers.
    userdata.verified_caller_phone = state.verified_caller_phone
    userdata.user_turn_count = state.user_turn_count
    return state


def note_user_turn(userdata: Any) -> None:
    state = get_write_gate_state(userdata)
    state.user_turn_count += 1
    userdata.user_turn_count = state.user_turn_count


def set_verified_caller_phone(userdata: Any, phone: str | None) -> None:
    state = get_write_gate_state(userdata)
    normalized = normalize_phone(phone) or None
    state.verified_caller_phone = normalized
    userdata.verified_caller_phone = normalized


def _clear_expired_pending(state: WriteGateState) -> None:
    pending = state.pending_write
    if pending is None:
        return
    if (time.monotonic() - pending.created_at) > _PENDING_TTL_SEC:
        state.pending_write = None


def propose_or_confirm_write(
    userdata: Any,
    *,
    tool_name: str,
    path: str,
    raw_args: dict[str, Any],
    confirmation_id: str | None,
) -> tuple[str, dict[str, Any]]:
    """Return (action, payload).

    action:
      - ``propose`` — do not POST; return value is the tool response
      - ``confirm`` — POST; payload has normalized_args + idempotency_key
      - ``reject`` — do not POST; return value is the tool error response
      - ``replay`` — do not POST; return cached success for same confirmation_id
    """
    if tool_name not in _WRITE_TOOLS:
        return "reject", {"error": f"{tool_name} is not a gated write tool", "success": False}

    state = get_write_gate_state(userdata)
    _clear_expired_pending(state)

    normalized, err = validate_write_args(tool_name, raw_args)
    if err or normalized is None:
        return "reject", {"error": err or "invalid args", "success": False}

    own_err = check_ownership(tool_name, normalized, state.verified_caller_phone)
    if own_err:
        return "reject", {"error": own_err, "success": False}

    # Overwrite book phone with verified when present (plan: match or overwrite).
    if (
        tool_name == "book_appointment"
        and state.verified_caller_phone
        and phones_match(normalized["customer_phone"], state.verified_caller_phone)
    ):
        normalized["customer_phone"] = state.verified_caller_phone

    conf = (confirmation_id or "").strip() or None
    digest = args_hash(tool_name, normalized)

    if conf:
        # Replay completed confirmation (idempotent) — only for same tool+args.
        prior = state.completed_writes.get(conf)
        if prior is not None:
            if prior.get("tool") == tool_name and prior.get("args_hash") == digest:
                return "replay", dict(prior["result"])
            return "reject", {
                "error": "confirmation_id already used for a different action",
                "success": False,
            }

        pending = state.pending_write
        if pending is None:
            return "reject", {
                "error": "no pending action to confirm — call without confirmation_id first",
                "success": False,
            }
        if pending.confirmation_id != conf:
            return "reject", {"error": "confirmation_id does not match pending action", "success": False}
        if pending.tool != tool_name or pending.args_hash != digest:
            return "reject", {
                "error": "confirmation args do not match the pending proposal",
                "success": False,
            }
        if state.user_turn_count <= pending.propose_user_turn_id:
            return "reject", {
                "error": (
                    "caller has not confirmed yet — wait for the caller to say yes, "
                    "then call again with confirmation_id"
                ),
                "success": False,
                "needs_confirmation": True,
                "confirmation_id": pending.confirmation_id,
            }
        if (time.monotonic() - pending.created_at) > _PENDING_TTL_SEC:
            state.pending_write = None
            return "reject", {"error": "confirmation expired — propose again", "success": False}
        if state.write_tool_calls >= max_write_tool_calls():
            return "reject", {
                "error": f"write tool budget exceeded (max {max_write_tool_calls()} per session)",
                "success": False,
            }

        idem = make_idempotency_key(
            tenant_id=str(getattr(userdata, "tenant_id", "")),
            agent_id=str(getattr(userdata, "agent_id", "")),
            room_name=str(getattr(userdata, "room_name", "")),
            tool_name=tool_name,
            normalized_args=normalized,
            confirmation_id=conf,
        )
        return "confirm", {
            "normalized_args": normalized,
            "idempotency_key": idem,
            "confirmation_id": conf,
            "path": pending.path,
        }

    # Propose path — no confirmation_id.
    if state.write_tool_calls >= max_write_tool_calls():
        return "reject", {
            "error": f"write tool budget exceeded (max {max_write_tool_calls()} per session)",
            "success": False,
        }

    new_id = make_confirmation_id()
    state.pending_write = PendingWrite(
        tool=tool_name,
        args_hash=digest,
        args=dict(normalized),
        confirmation_id=new_id,
        created_at=time.monotonic(),
        propose_user_turn_id=state.user_turn_count,
        path=path,
    )
    return "propose", {
        "needs_confirmation": True,
        "confirmation_id": new_id,
        "summary": summarize_write(tool_name, normalized),
        "success": False,
        "voiceSummary": (
            "Please confirm with the caller: "
            + summarize_write(tool_name, normalized)
            + ". When they say yes, call this tool again with the same details and confirmation_id."
        ),
    }


def mark_write_success(
    userdata: Any,
    *,
    confirmation_id: str,
    idempotency_key: str,
    result: dict[str, Any],
    tool_name: str,
    args_hash: str,
) -> None:
    state = get_write_gate_state(userdata)
    state.write_tool_calls += 1
    state.pending_write = None
    state.last_idempotency_key = idempotency_key
    state.last_write_result = dict(result)
    state.completed_writes[confirmation_id] = {
        "tool": tool_name,
        "args_hash": args_hash,
        "result": dict(result),
        "idempotency_key": idempotency_key,
    }
