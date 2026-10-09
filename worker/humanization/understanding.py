"""Small deterministic critical-entity parser and fail-closed write checks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from .evidence import TranscriptEvidence

DAYS = {
    "monday": "Monday", "mon": "Monday", "peer": "Monday", "پیر": "Monday",
    "tuesday": "Tuesday", "mangal": "Tuesday", "منگل": "Tuesday",
    "wednesday": "Wednesday", "budh": "Wednesday", "بدھ": "Wednesday",
    "thursday": "Thursday", "jumerat": "Thursday", "جمعرات": "Thursday",
    "friday": "Friday", "jumma": "Friday", "جمعہ": "Friday",
    "saturday": "Saturday", "hafta": "Saturday", "ہفتہ": "Saturday",
    "sunday": "Sunday", "itwar": "Sunday", "اتوار": "Sunday",
}
CORRECTION = re.compile(r"(?i)\b(no|not|actually|instead|sorry|nahi|nahin|balke|balkay)\b|نہیں|نہيں|بلکہ")
AMBIGUOUS = re.compile(r"(?i)\b(or|maybe|perhaps|ya|shayad)\b|شاید|یا")
NEGATION = re.compile(r"(?i)\b(not|nahi|nahin)\b|نہیں")
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


@dataclass(frozen=True)
class InputUnderstanding:
    entities: tuple[tuple[str, str], ...]
    unresolved: tuple[str, ...]
    correction: bool


def understand(evidence: TranscriptEvidence, *, pending_field: str | None = None) -> InputUnderstanding:
    if not evidence.is_final:
        return InputUnderstanding((), (), False)
    text = evidence.text.translate(DIGITS).strip()
    correction = bool(CORRECTION.search(text))
    found: dict[str, list[str]] = {}
    unresolved: set[str] = set()
    negated_fields: set[str] = set()
    locally_scoped_fields: set[str] = set()

    def add(field, value, start=None, end=None):
        if start is not None:
            locally_scoped_fields.add(field)
            prefix = text[max(0, start-60):start]
            suffix = text[end:]
            # "No/nahi Monday" is a repair discourse marker. English "not"
            # before a value, or Urdu negation after it, rejects that value.
            before = re.search(r"(?i)\bnot\s+(?:(?:my name is|name is|doctor|dr\.?|booking id|reference code)\s+)?$", prefix)
            after = re.match(r"(?i)^\s+(?:nahi\b|nahin\b|نہیں)(?:[.!،, ]|$)", suffix)
            if before or after:
                negated_fields.add(field)
                return
        found.setdefault(field, []).append(value)
    date_pattern = r"(?<!\w)(" + "|".join(DAYS) + r")(?!\w)|\b\d{4}-\d{2}-\d{2}\b"
    for match in re.finditer(date_pattern, text, re.I):
        value = match.group().lower()
        prefix = text[max(0, match.start()-35):match.start()]
        existing = re.search(r"(?i)(?:existing|old|current|purani|پرانی)\s+(?:(?:appointment|booking|date|تاریخ)\s*)?[: ]*$", prefix)
        add("existing_date" if existing else "date", DAYS.get(value, value), match.start(), match.end())
    for match in re.finditer(r"(?<!\d)(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)(?!\w)", text, re.I):
        hour, minute = int(match[1]), int(match[2] or 0)
        if 1 <= hour <= 12 and minute < 60:
            add("time", f"{hour % 12 + (12 if match[3].lower().startswith('p') else 0):02}:{minute:02}", match.start(), match.end())
        else:
            unresolved.add("time")
    for match in re.finditer(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d|\s*(?:am|pm))", text, re.I):
        if int(match[1]) > 12 and int(match[1]) < 24 and int(match[2]) < 60:
            add("time", f"{int(match[1]):02}:{int(match[2]):02}", match.start(), match.end())
        elif "time" not in found:
            unresolved.add("time")
    if re.search(r"(?i)\b\d{1,2}\s*(baje|o'clock)\b|\d{1,2}\s*بجے", text) and "time" not in found:
        unresolved.add("time")
    if re.search(r"(?i)\bkal\b|کل", text) and "date" not in found:
        unresolved.add("date")
    for match in re.finditer(r"(?<!\w)\+?\d[\d ()-]{5,}\d(?!\w)", text):
        raw = match.group().strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            continue
        value = ("+" if raw.startswith("+") else "") + "".join(c for c in raw if c.isdigit())
        if 7 <= len(value.lstrip("+")) <= 15:
            add("phone", value, match.start(), match.end())
    for match in re.finditer(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text):
        add("email", match.group().lower(), match.start(), match.end())
    name_pattern = r"(?i)(?:\b(?:my name is|name is|naam|doctor|dr\.?)\s+|میرا نام\s+|ڈاکٹر\s+)([^\W\d_]+(?:[ '-][^\W\d_]+){0,2})"
    for match in re.finditer(name_pattern, text):
        # Bound names at repair/discourse markers, never absorb the replacement.
        value = re.split(r"(?i)\s+(?:not|no|nahi|nahin|balke|balkay|actually|hai|is|at|on)\b|\s+(?:نہیں|بلکہ|ہے)", match[1])[0].strip()
        field = "doctor_name" if re.match(r"(?i)(doctor|dr|ڈاکٹر)", match[0]) else "name"
        add(field, value, match.start(1), match.start(1) + len(value))
    for field, pattern in (
        ("booking_id", r"(?i)(?:booking|appointment)\s*(?:id|identifier|number|نمبر)\s*[:#]?\s*([A-Za-z0-9-]+)"),
        ("reference_code", r"(?i)(?:confirmation|reference|code|ریفرنس|کوڈ)\s*(?:code|number|نمبر)?\s*[:#]?\s*([A-Za-z0-9-]+)"),
    ):
        for match in re.finditer(pattern, text):
            add(field, match[1], match.start(), match.end())
    # Contextual answers only for the field explicitly requested by our safety gate.
    if pending_field and pending_field not in found and pending_field not in unresolved:
        if pending_field in {"name", "doctor_name"} and re.fullmatch(r"[^\W\d_]+(?:[ '-][^\W\d_]+){0,2}", text) and not CORRECTION.search(text) and text.lower() not in {"yes", "ok", "haan", "جی", "ہاں"}:
            add(pending_field, text)
    unresolved.update(negated_fields - found.keys())
    entities = []
    for field, values in found.items():
        unique = list(dict.fromkeys(values))
        if AMBIGUOUS.search(text) or (len(unique) > 1 and not correction):
            unresolved.add(field)
        elif field not in locally_scoped_fields and NEGATION.search(text) and len(unique) == 1 and (
            re.match(r"(?i)\s*not\b", text)
            or re.search(r"(?i)(nahi|nahin|نہیں)[.! ]*$", text)
        ):
            unresolved.add(field)
        else:
            entities.append((field, unique[-1]))
    return InputUnderstanding(tuple(entities), tuple(sorted(unresolved)), correction)


def apply_understanding(runtime: Any, evidence: TranscriptEvidence, turn_id: str) -> InputUnderstanding:
    parsed = understand(evidence, pending_field=runtime.state.repair_state.pending_field)
    if parsed.correction and not parsed.entities and not parsed.unresolved:
        replacement = re.sub(r"(?i)^(?:no|actually|nahi|nahin|نہیں)[, ]*", "", evidence.text).strip(" .")
        names = [name for name in ("name", "doctor_name") if current_value(runtime.state, name)]
        if re.fullmatch(r"[^\W\d_]+(?:[ '-][^\W\d_]+){0,2}", replacement) and replacement != evidence.text.strip(" ."):
            if len(names) == 1:
                parsed = InputUnderstanding(((names[0], replacement),), (), True)
            elif names:
                parsed = InputUnderstanding((), tuple(names), True)
    for field in parsed.unresolved:
        runtime.observe("ground_unresolved", field_name=field)
    for field, value in parsed.entities:
        old = runtime.state.task_state.critical_values.get(field, [])
        current = next((v for v in reversed(old) if v.status not in {"superseded", "unresolved"}), None)
        if current and current.value != value and current.status == "confirmed" and not parsed.correction:
            runtime.observe("ground_unresolved", field_name=field)
            continue
        # Explicit caller correction can replace confirmed evidence. Weak inference cannot.
        if parsed.correction and current and current.value != value:
            runtime.observe("ground_superseded", field_name=field, observation_id=current.observation_id)
        runtime.observe("ground_value", field_name=field, value=value, status="heard",
                        turn_id=turn_id, observation_id=f"{turn_id}:{field}:{value}")
        if field == runtime.state.repair_state.pending_field:
            runtime.observe("repair_pending", field_name=None)
    remaining = runtime.state.grounding_state.unresolved_fields
    if remaining:
        runtime.observe("repair_pending", field_name=sorted(remaining)[0])
    return parsed


def current_value(state: Any, field: str) -> str | None:
    if field in state.grounding_state.unresolved_fields:
        return None
    return next((v.value for v in reversed(state.task_state.critical_values.get(field, []))
                 if v.status in {"heard", "confirmed"}), None)


def write_uncertainties(runtime: Any, tool: str, args: dict, verified_phone: str | None) -> tuple[str, ...]:
    from worker.write_tool_gate import phones_match
    state = runtime.state
    required = {"phone"}
    if tool == "book_appointment":
        required |= {"name", "date", "time"}
    elif tool == "reschedule_appointment":
        required |= {"date", "time"}
    if args.get("existing_date"):
        required.add("existing_date")
    slot = args.get("slot_start_time") or args.get("new_slot_start_time")
    # Only current accepted backend slots or literal caller dates/times can ground a slot.
    offered = slot in runtime.offered_slots
    missing = set(state.grounding_state.unresolved_fields)
    # Optional target fields cannot be silently omitted to bypass an unresolved intent.
    service = str(args.get("service_name") or "")
    doctor = current_value(state, "doctor_name")
    if tool in {"book_appointment", "reschedule_appointment"} and doctor is not None:
        if not re.search(r"(?<!\w)" + re.escape(doctor) + r"(?!\w)", service, re.I):
            missing.add("doctor_name")
    for value in state.task_state.critical_values.get("doctor_name", []):
        if value.status == "superseded" and value.value.casefold() != (doctor or "").casefold() and re.search(r"(?<!\w)" + re.escape(value.value) + r"(?!\w)", service, re.I):
            missing.add("doctor_name")
    for field in required:
        source = ("existing_date" if current_value(state, "existing_date") is not None or tool == "reschedule_appointment" else "date") if field == "existing_date" else field
        value = current_value(state, source)
        if source in state.grounding_state.unresolved_fields:
            missing.add(source)
            continue
        if field == "phone":
            if not phones_match(args.get("customer_phone"), value or verified_phone):
                missing.add(field)
        elif field == "name":
            if value is None or value.casefold() != str(args.get("customer_name", "")).casefold():
                missing.add(field)
        elif field == "existing_date":
            # Target lookup date has a separate role; require the exact observed date.
            if value != args[field]:
                missing.add(source)
        else:
            try:
                date = datetime.fromisoformat(str(slot).replace("Z", "+00:00"))
            except ValueError:
                missing.add(field)
                continue
            matches = value == (date.strftime("%A") if value in DAYS.values() else date.date().isoformat()) if field == "date" else value == date.strftime("%H:%M")
            if not matches or (field == "date" and value in DAYS.values() and not offered):
                missing.add(field)
    return tuple(sorted(missing))
