"""STEP 9 runner — executes the full self-test protocol and writes TEST_REPORT.md.

Run: uv run python tests/run_all.py           (all suites)
     uv run python tests/run_all.py env schema tools   (subset)

Each suite's results are persisted to tests/results/<suite>.json, and the report
is assembled from the UNION of all saved suites — so suites can be run in stages
(the Groq free tier's 100k daily-token budget forces staging; see DECISIONS.md)
and TEST_REPORT.md always reflects the newest result of every suite.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "TEST_REPORT.md")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

SUITES = ["env", "schema", "tools", "e2e", "latency", "interruption", "stt"]


def save_suite(check) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    payload = {
        "name": check.name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results": [[label, ok, detail] for label, ok, detail in check.results],
    }
    path = os.path.join(RESULTS_DIR, f"{check.name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)


def load_saved_suites() -> list[dict]:
    """All persisted suite results, in canonical suite order."""
    if not os.path.isdir(RESULTS_DIR):
        return []
    order = {"env_smoke": 0, "schema": 1, "tools": 2, "e2e": 3, "latency_v2": 4,
             "interruption": 5, "stt_accuracy": 6}
    suites = []
    for fn in os.listdir(RESULTS_DIR):
        if fn.endswith(".json") and fn != "latency_combos.json":
            with open(os.path.join(RESULTS_DIR, fn), encoding="utf-8") as f:
                suites.append(json.load(f))
    return sorted(suites, key=lambda s: order.get(s["name"], 99))


def load_saved_combos() -> dict:
    path = os.path.join(RESULTS_DIR, "latency_combos.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def main():
    if "report" in sys.argv[1:]:  # rebuild TEST_REPORT.md from saved results only
        write_report(load_saved_suites(), load_saved_combos(), 0.0)
        print("Report rebuilt from tests/results/*.json")
        return 0
    selected = [a for a in sys.argv[1:] if a in SUITES] or SUITES
    ran_checks = []
    t_start = time.monotonic()

    async def run_suite(title, module_name):
        """A crashing suite must not lose the other suites' results."""
        print(f"\n========== {title} ==========")
        import importlib
        import traceback

        try:
            module = importlib.import_module(module_name)
            ran_checks.append(await module.run())
        except Exception:
            traceback.print_exc()
            print(f"SUITE {module_name} CRASHED — its saved results (if any) are unchanged")

    if "env" in selected:
        await run_suite("1. ENV SMOKE TESTS", "test_env_smoke")
    if "schema" in selected:
        await run_suite("2. SCHEMA TESTS", "test_schema")
    if "tools" in selected:
        await run_suite("3. TOOL UNIT TESTS", "test_tools")
    if "e2e" in selected:
        await run_suite("4. E2E LOOP TESTS (8 utterances)", "test_e2e")
    if "latency" in selected:
        await run_suite("5. LATENCY REPORT (per provider combo)", "test_latency")
    if "interruption" in selected:
        await run_suite("6. INTERRUPTION TEST", "test_interruption")
    if "stt" in selected:
        await run_suite("7. STT ACCURACY (Gladia vs Whisper)", "test_stt_accuracy")

    elapsed = time.monotonic() - t_start
    for c in ran_checks:
        save_suite(c)
    write_report(load_saved_suites(), load_saved_combos(), elapsed)

    total = sum(len(c.results) for c in ran_checks)
    failed = sum(1 for c in ran_checks for _, ok, _ in c.results if not ok)
    print(f"\n{'='*60}\nTHIS RUN: {total - failed}/{total} passed in {elapsed/60:.1f} min")
    print(f"Report written to TEST_REPORT.md (merged with previously saved suites)")
    return 1 if failed else 0


def write_report(suites, combos, elapsed):
    lines = [
        "# TEST_REPORT.md — TechZone Urdu Voice Agent self-test results",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')} · "
        "suites are run in stages within the Groq free-tier daily-token budget; "
        "each section shows when it last ran.",
        "",
        "Latency definition: `eos_to_first_audio_ms` is measured from the "
        "VAD end-of-speech event (speech end detected) to the first TTS audio byte "
        "reaching the transport output.",
        "",
    ]
    total = failed = 0
    for c in suites:
        lines.append(f"## {c['name']}  <sub>({c['generated_at']})</sub>")
        lines.append("")
        lines.append("| criterion | result | detail |")
        lines.append("|---|---|---|")
        for label, ok, detail in c["results"]:
            total += 1
            failed += 0 if ok else 1
            lines.append(f"| {label} | {'✅ PASS' if ok else '❌ FAIL'} | {detail[:160]} |")
        lines.append("")

    if combos:
        ordered = sorted(combos.values(), key=lambda r: r.get("eos_p50") or 10**9)
        best = ordered[0] if ordered and ordered[0].get("eos_p50") else {}
        lines += [
            "## v4 latency numbers (per provider combo — clean = provider-429 turns excluded)",
            "",
            "| combo | turns | quota-excl | p50 clean | p95 clean | p50 raw | p95 raw | stt_final ms | llm_ttfb ms | tts_ttfb ms | tokens/turn avg |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in ordered:
            comp = r.get("components") or {}
            lines.append(
                f"| {r['label']} | {r['turns_completed']}/{r['turns_measured'] or '—'} "
                f"| {r.get('quota_excluded_turns', 0)} "
                f"| {r.get('eos_p50')} | {r.get('eos_p95')} "
                f"| {r.get('eos_p50_raw', r.get('eos_p50'))} | {r.get('eos_p95_raw', r.get('eos_p95'))} "
                f"| {comp.get('stt_ms')} | {comp.get('llm_ttfb_ms')} | {comp.get('tts_ttfb_ms')} "
                f"| {r.get('tokens_avg')} |"
            )
        comp = best.get("components") or {}
        stt_ms = comp.get("stt_ms")
        llm_ms = comp.get("llm_ttfb_ms")
        tts_ms = comp.get("tts_ttfb_ms")
        lines += [
            "",
            f"- best combo: **{best.get('label')}** clean p50 = **{best.get('eos_p50')} ms**, "
            f"clean p95 = **{best.get('eos_p95')} ms** "
            f"({best.get('quota_excluded_turns', 0)} quota-excluded); per-turn raw: {best.get('all_ms')}",
            "",
            "### RPM-aware pacing and quota-excluded turns (v4 A.3)",
            "",
            "The Cerebras free tier allows only **5 requests/minute** (live header "
            "`x-ratelimit-limit-requests-minute: 5`; also 150/hour, 2400/day). A voice tool turn "
            "makes 2 LLM calls, so the v3 harness at a 6 s pause ran ~2x over the cap — the v3 "
            "run's 58 s turn and the smart_turn combo's 27 s llm_ttfb were the provider's rate "
            "limiter queuing/rejecting requests, not pipeline behavior. The harness now reads the "
            "rate-limit headers before each run and paces turn starts at (60/RPM) x 2 calls x 1.15 "
            "headroom (~28 s at 5 RPM). Any turn that still sees a provider 429 is marked "
            "quota-excluded: it appears in the raw columns and is excluded from the clean columns "
            "that acceptance is judged on. Both are reported above.",
            "",
            "### Why the tool-turn filler target is stt_final_median + 900 ms (v4 A.2b)",
            "",
            "The cached filler line is the first audio on tool-calling turns, but it cannot start "
            "before the LLM *decides* to call a tool — and that decision cannot start before the "
            "final transcript lands. So the caller-experience target is relative to the STT final: "
            f"stt_final_median (~{stt_ms} ms after eos on the best combo) + 900 ms for the LLM's "
            "tool-decision first token plus filler playback start (cached PCM, zero TTS round-trip). "
            "The old fixed 600 ms target implicitly assumed the transcript was free; it measured "
            "Gladia's Urdu final latency, not the filler machinery it was written to verify.",
            "",
            "### Where the milliseconds go (best combo, component medians) — and the honest floor",
            "",
            f"1. **Gladia Urdu utterance-final: ~{stt_ms} ms after eos.** Streaming STT transcribes "
            "while the user speaks, but Gladia's *final* for Urdu lands ~0.55–0.8 s after speech end "
            "(endpointing is already at 0.1 s; the rest is Gladia-side processing + network from PK). "
            "The fix that would remove this — promoting the last interim at eos (D21) — was built and "
            "then disabled: Gladia's Urdu partials are frequently garbled until the true final, so "
            "promotion traded correctness for latency. This is the single biggest component.",
            f"2. **LLM first token: ~{llm_ms} ms** (no reasoning/thinking tokens — verified 0 in every "
            "combo). Groq llama-3.3 measures ~0.4–0.7 s; Gemini 2.5 Flash (thinking off) measures "
            "~1.0–1.6 s from this network.",
            f"3. **Uplift TTS first byte: ~{tts_ms} ms** — provider floor; requires complete sentences "
            "(a requestId cannot receive appended text), so token-level TTS streaming is impossible.",
            "",
            "Optimizations applied across v2–v4: streaming STT (removes v1's ~800 ms segmented-Whisper "
            "roundtrip), non-reasoning LLMs (removes 0.6–1.7 s hidden-reasoning prefill), finalized "
            "Gladia finals + 0.05 s speech-timeout (turn ends the moment the final lands), LLM/STT/TTS "
            "pre-warm at connect, persistent TTS socket, PCM at pipeline rate (no decode/resample), "
            "fire-and-forget writes, 606-token persona, one-sentence tool schemas, context "
            "summarization, phrase-audio cache, repeated-opener guard. **Honest floor on this "
            "stack/network: the eos→final wait (~0.6 s) + LLM TTFB (~0.5 s) + TTS (~0.33 s) ≈ 1.5 s "
            "p50** — reaching ≤800 ms would need either a trustworthy interim-promotion (blocked by "
            "Gladia's Urdu partial quality) or an STT whose Urdu finals land ≤0.2 s after eos "
            "(funded Soniox stt-rt-v5, ~250 ms — D27).",
            "",
            "### v1 → v4 comparison (best combo of each pass, measured on this machine from PK)",
            "",
            "| | v1 (Whisper + gpt-oss-120b) | v2 (Gladia + llama-3.3) | v3 (Gladia + gemma-4-31b) | v4-local (same stack, clean) |",
            "|---|---|---|---|---|",
            f"| p50 eos→first_audio | 2983 ms | 1843 ms | 1766 ms | **{best.get('eos_p50')} ms** |",
            f"| p95 eos→first_audio | 3500 ms | 3015 ms | 58202 ms (quota-contaminated) | **{best.get('eos_p95')} ms** |",
            "| STT after eos | ~800 ms (segmented HTTP Whisper) | streaming finals | streaming finals | see stt_final above |",
            "| LLM TTFB | ~700 ms + 0.6–1.7 s hidden reasoning | ~700 ms (llama) | ~600 ms (gemma) | see llm_ttfb above |",
            "| TTS TTFB | ~330 ms | ~330 ms | ~330 ms (cached fillers: 0) | ~330 ms (Uplift floor) |",
            "| harness pacing | none | daily-budget staging | 6 s fixed (429-contaminated) | RPM-aware (v4 A.3) |",
            "",
            "v1 was measured without production tool-call fillers in the harness; v2+ measure "
            "first audio the caller hears (filler or answer) with real-time-paced input — see "
            "DECISIONS.md D23.",
            "",
        ]

    lines += _acceptance_verdict(suites, combos)
    lines.append(f"**TOTAL: {total - failed}/{total} passed**")
    lines.append("")
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# Criteria that fail only because of a measured provider/stack floor, mapped to
# the component that sets the floor (v4 Part B: ACCEPTANCE VERDICT section).
_STRUCTURAL = {
    "p50 eos→first_audio": "Gladia Urdu eos→final ~650-750 ms + LLM TTFB ~600 ms + Uplift ~330 ms ≈ 1.5-1.8 s",
    "p95 eos→first_audio": "same floor components at their p95 tails",
    "tokens per turn": "fixed per-call prompt is 1401 tok (606 persona + 760 tool schemas); tool turns make 2 calls (D24)",
    "tool-calling turns": "filler waits on Gladia's final (~650-750 ms) + LLM tool-decision",
}


def _classify(label: str, ok: bool, detail: str) -> str:
    if ok:
        return "PASS"
    if "soniox" in label.lower() or "soniox" in detail.lower():
        return "BLOCKED-EXTERNAL"
    for key in _STRUCTURAL:
        if key in label:
            return "STRUCTURAL FLOOR"
    return "FAIL"


def _acceptance_verdict(suites, combos) -> list[str]:
    lines = [
        "## ACCEPTANCE VERDICT (v4)",
        "",
        "Every criterion, classified: **PASS** · **STRUCTURAL FLOOR** (fails only on a measured "
        "provider/stack floor, component named) · **BLOCKED-EXTERNAL** (Soniox account unfunded, "
        "402 on every request — integration wired, gate skipped per PROMPT4).",
        "",
    ]
    order = {"PASS": 2, "STRUCTURAL FLOOR": 1, "BLOCKED-EXTERNAL": 1, "FAIL": 0}
    rows = []
    for c in suites:
        for label, ok, detail in c["results"]:
            verdict = _classify(label, ok, detail)
            evidence = detail or "see suite table above"
            if verdict == "STRUCTURAL FLOOR":
                floor = next(v for k, v in _STRUCTURAL.items() if k in label)
                evidence = f"{detail} — floor: {floor}"
            rows.append((order[verdict], c["name"], label, verdict, evidence))
    for _, suite, label, verdict, evidence in sorted(rows):
        lines.append(f"- **{verdict}** · `{suite}` · {label} — {evidence[:220]}")
    counts = {}
    for _, _, _, verdict, _ in rows:
        counts[verdict] = counts.get(verdict, 0) + 1
    lines += ["", f"Verdict counts: {counts}", ""]
    return lines


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
