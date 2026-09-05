"""Write the live session prompt bundle to disk for inspection (size + text)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DUMP = _ROOT / "docs" / "last_session_prompt.txt"


def estimate_tokens(chars: int) -> int:
    return max(0, (chars + 3) // 4)


def dump_session_prompt(
    *,
    agent_id: str,
    llm_provider: str,
    llm_model: str,
    system_instructions: str,
    persona_raw: str,
    persona_effective: str,
    tools_registered: list[str],
    compacted: bool,
) -> Path | None:
    """Always write ``docs/last_session_prompt.txt`` unless UVA_DUMP_PROMPTS=0.

    Only SYSTEM + PERSONA (effective) are sent to the model. Raw DB persona is
    appended for diffing compaction — it is never part of the LLM request.
    """
    flag = (os.getenv("UVA_DUMP_PROMPTS") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return None

    out = Path(os.getenv("UVA_DUMP_PROMPTS_PATH") or _DEFAULT_DUMP)
    out.parent.mkdir(parents=True, exist_ok=True)

    sys_chars = len(system_instructions or "")
    raw_chars = len(persona_raw or "")
    eff_chars = len(persona_effective or "")
    combined = sys_chars + eff_chars

    lines = [
        f"dumped_at={datetime.now(timezone.utc).isoformat()}",
        f"agent_id={agent_id}",
        f"llm={llm_provider}/{llm_model}",
        f"persona_raw_chars={raw_chars} (~{estimate_tokens(raw_chars)} tok)  # DB only — NOT sent",
        f"persona_effective_chars={eff_chars} (~{estimate_tokens(eff_chars)} tok)  # sent",
        f"persona_compacted={compacted}",
        f"system_instructions_chars={sys_chars} (~{estimate_tokens(sys_chars)} tok)  # sent",
        f"system+persona_chars={combined} (~{estimate_tokens(combined)} tok)  # what the model sees",
        f"tools_registered={','.join(tools_registered) or '(none)'}",
        "note=Groq also bills tool JSON schemas + chat history on top of system+persona.",
        "note=Raw persona below is DEBUG ONLY for compaction diffs — never sent to the LLM.",
        "",
        "======== SENT TO MODEL: SYSTEM INSTRUCTIONS ========",
        system_instructions or "",
        "",
        "======== SENT TO MODEL: PERSONA (effective) ========",
        persona_effective or "",
        "",
        "======== DEBUG ONLY — NOT SENT: persona raw from DB ========",
        persona_raw or "",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
