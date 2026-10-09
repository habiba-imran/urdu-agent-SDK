"""Conservative Phase 3 audit of structured facts lost by Groq compaction.

These tenant facts remain DATA. The audit cannot authorize instructions or writes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FACT_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(business name|company name|identity|services?|"
    r"operating hours|business hours|hours|booking rules?|cancellation rules?|"
    r"polic(?:y|ies)|address)\s*:\s*(\S.*)$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class BusinessFact:
    kind: str
    value: str


@dataclass(frozen=True)
class PersonaFactAudit:
    source_facts: tuple[BusinessFact, ...]
    retained_facts: tuple[BusinessFact, ...]
    missing_facts: tuple[BusinessFact, ...]
    compacted: bool
    unstructured_unverified: bool

    @property
    def activation_safe(self) -> bool:
        return not self.missing_facts and not self.unstructured_unverified

    def log_fields(self) -> dict[str, object]:
        return {
            "source_fact_count": len(self.source_facts),
            "retained_fact_count": len(self.retained_facts),
            "missing_fact_count": len(self.missing_facts),
            "missing_kinds": tuple(f.kind for f in self.missing_facts),
            "unstructured_unverified": self.unstructured_unverified,
            "activation_safe": self.activation_safe,
        }


def extract_business_facts(persona: str) -> tuple[BusinessFact, ...]:
    return tuple(
        BusinessFact(match.group(1).lower().strip(), match.group(2).strip())
        for match in _FACT_RE.finditer(persona or "")
    )


def audit_persona_compaction(raw: str, effective: str, *, compacted: bool) -> PersonaFactAudit:
    source = extract_business_facts(raw)
    retained = extract_business_facts(effective)
    retained_set = set(retained)
    missing = tuple(fact for fact in source if fact not in retained_set)
    # Any compacted prose outside labeled facts may contain unknown critical rules.
    unstructured = compacted and any(
        line.strip() and _FACT_RE.fullmatch(line) is None
        for line in (raw or "").splitlines()
    )
    return PersonaFactAudit(source, retained, missing, compacted, unstructured)
