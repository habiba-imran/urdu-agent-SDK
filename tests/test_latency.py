"""V2 RE-VERIFICATION 1 — Latency report on the new stack.

Runs real-time-paced turns through the real pipeline per provider combo
(gemini-primary and groq/llama-primary) and reports p50/p95 eos→first-audio,
per-component breakdown and measured tokens-per-turn.

The Groq free tier allows 100k llama tokens/day (~3.3k/turn measured), so combos
are runnable in stages: LATENCY_COMBOS selects which combos run in this
invocation (csv of gemini,gladia,whisper; default "gemini,gladia"), each combo's
report is persisted to tests/results/latency_combos.json as soon as it finishes,
and the acceptance checks are evaluated over ALL saved combos.

    LATENCY_TURNS         turns for the llama+gladia combo (default 10)
    LATENCY_GEMINI_TURNS  turns for the gemini combo (default 6 — 20 req/day key)
    LATENCY_WHISPER_TURNS turns for the llama+whisper STT comparison (default 3)
    LATENCY_PAUSE         seconds between turns (default 15 — keeps llama under TPM)
"""

import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import Check, synth_urdu
from helpers_pipeline import PipelineHarness

import config

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
COMBOS_PATH = os.path.join(RESULTS_DIR, "latency_combos.json")


def _load_combos() -> dict:
    if os.path.exists(COMBOS_PATH):
        with open(COMBOS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_combo(report: dict) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    combos = _load_combos()
    combos[report["label"]] = report
    with open(COMBOS_PATH, "w", encoding="utf-8") as f:
        json.dump(combos, f, ensure_ascii=False, indent=1)

UTTERANCES = [
    "MacBook Air M2 کی قیمت کیا ہے؟",
    "دکان کے اوقات کیا ہیں؟",
    "کیا آپ راولپنڈی ڈیلیوری کرتے ہیں؟",
    "سب سے سستا MacBook کون سا ہے؟",
    "MacBook Pro 14 کی قیمت بتائیں",
    "استعمال شدہ لیپ ٹاپ کی وارنٹی کتنی ہے؟",
    "کیا ThinkPad دستیاب ہے؟",
    "M4 والا MacBook کتنے کا ہے؟",
    "نئے یونٹ کی وارنٹی کیا ہے؟",
    "تین لاکھ میں کون سا لیپ ٹاپ ملے گا؟",
]

RESULTS: dict = {}
_WAV_CACHE: list[bytes] | None = None


def pctl(values, p):
    if not values:
        return None
    vs = sorted(values)
    idx = min(len(vs) - 1, round(p / 100 * (len(vs) - 1)))
    return vs[idx]


async def _wavs(n):
    global _WAV_CACHE
    if _WAV_CACHE is None:
        _WAV_CACHE = [await synth_urdu(u) for u in UTTERANCES]
    return _WAV_CACHE[:n]


async def gemini_available() -> bool:
    from openai import AsyncOpenAI

    try:
        client = AsyncOpenAI(
            api_key=config.GOOGLE_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        await client.chat.completions.create(
            model=config.GEMINI_LLM_MODEL,
            messages=[{"role": "user", "content": "ok"}],
            max_completion_tokens=1,
        )
        return True
    except Exception as e:
        print(f"  gemini unavailable: {str(e)[:100]}")
        return False


async def cerebras_turn_pause(default_pause: float) -> float:
    """Derive RPM-aware harness pacing from Cerebras rate-limit headers (v4 A.3).

    The free tier allows only 5 requests/MINUTE (measured header
    x-ratelimit-limit-requests-minute: 5); a voice tool turn makes 2 LLM calls,
    so back-to-back turns at the old 6s pause ran ~2x over the cap — the v3
    run's 58s turn and the smart_turn 27s llm_ttfb were that limiter, not the
    pipeline. Pace turn starts at (60/RPM) * 2 calls * 1.15 headroom.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {config.CEREBRAS_API_KEY}"},
                json={
                    "model": config.CEREBRAS_LLM_MODEL,
                    "messages": [{"role": "user", "content": "ok"}],
                    "max_completion_tokens": 1,
                },
            )
        rl = {k.lower(): v for k, v in r.headers.items() if "ratelimit" in k.lower()}
        rpm = float(rl.get("x-ratelimit-limit-requests-minute", 5))
        remaining_hour = rl.get("x-ratelimit-remaining-requests-hour")
        if remaining_hour is not None and float(remaining_hour) < 30:
            print(f"  ⚠️ cerebras hourly request budget low: {remaining_hour} left")
        # 2.6 requests/turn budget: tool turns make 2 completions, and the
        # context summarizer (D18) fires an EXTRA request every ~10 messages —
        # at 2.0 the summarizer burst still tripped the 5-RPM limiter (v4)
        pause = (60.0 / max(rpm, 1)) * 2.6 * 1.15
        print(f"  cerebras RPM={rpm:.0f}/min → paced {pause:.0f}s between turn starts")
        return max(default_pause, pause)
    except Exception as e:
        print(f"  cerebras RPM probe failed ({str(e)[:80]}); assuming 5 RPM")
        return max(default_pause, 35.9)


async def run_combo(
    label: str,
    n_turns: int,
    *,
    llm_provider: str,
    turn_stop_mode: str = "vad",
    vad_stop_secs: float | None = None,
    stt_provider: str | None = None,
    pause: float = 8.0,
) -> dict:
    print(
        f"\n--- combo: {label} (llm={llm_provider}, stt={stt_provider or config.STT_PROVIDER}, "
        f"stop={turn_stop_mode}, vad_stop={vad_stop_secs or config.VAD_STOP_SECS}s, "
        f"{n_turns} turns, pause {pause:.0f}s) ---"
    )
    wavs = await _wavs(n_turns)
    harness = PipelineHarness(
        turn_stop_mode=turn_stop_mode,
        llm_provider=llm_provider,
        vad_stop_secs=vad_stop_secs,
        stt_provider=stt_provider,
    )
    await harness.start()
    completed = 0
    quota_flags: list[bool] = []  # one per MEASURED turn: hit a provider 429?
    try:
        for i, wav in enumerate(wavs):
            measured_before = len(harness.session.latencies_ms)
            t0 = time.monotonic()
            ok = await harness.user_turn(wav, timeout=60)
            contaminated = any(t >= t0 for t in harness.quota_watcher.times)
            if ok:
                completed += 1
            else:
                print(f"  turn {i+1}: TIMED OUT" + (" (quota 429)" if contaminated else ""))
            new = len(harness.session.latencies_ms) - measured_before
            quota_flags.extend([contaminated] * new)
            if contaminated:
                print(f"  turn {i+1}: provider 429 during turn → quota-excluded in clean stats")
            await asyncio.sleep(pause)
    finally:
        await harness.stop()

    s = harness.session
    lat = s.latencies_ms
    clean = [l for l, bad in zip(lat, quota_flags) if not bad]
    toks = [t for t in s.tokens_per_turn if t > 0]
    tool_flags = s.tool_turn_flags
    tool_lat = [
        l for l, is_tool, bad in zip(lat, tool_flags, quota_flags) if is_tool and not bad
    ]
    # v3 humanness check: consecutive replies must not open with the same word
    openers = [r.split()[0] for r in harness.tap.responses if r.strip()]
    repeated_openers = sum(1 for a, b in zip(openers, openers[1:]) if a == b)
    report = {
        "label": label,
        "llm": llm_provider,
        "turn_stop": turn_stop_mode,
        "vad_stop": vad_stop_secs or config.VAD_STOP_SECS,
        "turns_requested": n_turns,
        "turns_completed": completed,
        "turns_measured": len(lat),
        "llm_failovers": s.llm_failovers,
        # clean stats (quota-excluded) drive acceptance; raw kept for honesty
        "quota_excluded_turns": sum(quota_flags),
        "eos_p50": pctl(clean, 50),
        "eos_p95": pctl(clean, 95),
        "eos_p50_raw": pctl(lat, 50),
        "eos_p95_raw": pctl(lat, 95),
        "all_ms": lat,
        "clean_ms": clean,
        "tool_turn_count": len(tool_lat),
        "tool_turn_first_audio_p50": pctl(tool_lat, 50),
        "openers": openers,
        "repeated_openers": repeated_openers,
        "tokens_avg": round(sum(toks) / len(toks)) if toks else None,
        "tokens_max": max(toks) if toks else None,
        "reasoning_tokens": s.reasoning_tokens_seen,
        "conversation_id": s.conversation_id,
    }
    print(
        f"  {label}: {completed}/{n_turns} turns | clean p50={report['eos_p50']}ms "
        f"p95={report['eos_p95']}ms (raw {report['eos_p50_raw']}/{report['eos_p95_raw']}, "
        f"{report['quota_excluded_turns']} quota-excluded) | tokens/turn avg={report['tokens_avg']} "
        f"max={report['tokens_max']} | reasoning_tokens={s.reasoning_tokens_seen}"
    )
    return report


async def component_medians(conversation_id: str) -> dict:
    import db

    client = await db.get_client()
    rows = (
        await client.table("turn_metrics")
        .select("stt_ms, llm_ttfb_ms, tts_ttfb_ms")
        .eq("conversation_id", conversation_id)
        .execute()
    ).data
    out = {}
    for k in ("stt_ms", "llm_ttfb_ms", "tts_ttfb_ms"):
        vals = [r[k] for r in rows if r[k] is not None]
        out[k] = statistics.median(vals) if vals else None
    out["rows"] = len(rows)
    return out


async def run() -> Check:
    check = Check("latency_v2")

    selected = [
        c.strip()
        for c in os.environ.get("LATENCY_COMBOS", "gladia,groq,whisper,smart_turn").split(",")
        if c.strip()
    ]
    n_main = int(os.environ.get("LATENCY_TURNS", "10"))
    n_gemini = int(os.environ.get("LATENCY_GEMINI_TURNS", "6"))
    n_probe = int(os.environ.get("LATENCY_WHISPER_TURNS", "3"))
    pause = float(os.environ.get("LATENCY_PAUSE", "6"))
    # v4 A.3: Cerebras free tier allows only 5 requests/min — pace cerebras
    # combos from the live rate-limit headers so 429s never contaminate stats
    cerebras_pause = await cerebras_turn_pause(pause)

    if "gladia" in selected:
        # v3 main combo: cerebras gemma-4-31b + Gladia streaming, vad 0.4 (winner
        # of the v2 0.4/0.5 comparison: p50 1843 vs 2233, no false cutoffs)
        r = await run_combo(
            "cerebras+gladia@vad0.4", n_main, llm_provider="cerebras",
            vad_stop_secs=0.4, pause=cerebras_pause,
        )
        _save_combo(r)

    if "groq" in selected:
        # LLM TTFB comparison: groq llama-3.3 fallback on the same STT
        # (paced 20s for the groq 100k/day budget)
        r = await run_combo(
            "groq+gladia@vad0.4", n_probe, llm_provider="groq",
            vad_stop_secs=0.4, pause=max(pause, 20.0),
        )
        _save_combo(r)

    if "whisper" in selected:
        # STT comparison: segmented Whisper (v1's STT) on the v3 LLM
        r = await run_combo(
            "cerebras+whisper@vad0.4", n_probe, llm_provider="cerebras",
            vad_stop_secs=0.4, stt_provider="groq", pause=cerebras_pause,
        )
        _save_combo(r)

    if "smart_turn" in selected:
        # re-probe Smart Turn v3 with streaming transcripts (v3's verdict was
        # contaminated by Cerebras RPM 429s; RPM-aware pacing decontaminates it)
        r = await run_combo(
            "cerebras+gladia@smart_turn", n_probe, llm_provider="cerebras",
            turn_stop_mode="smart_turn", vad_stop_secs=0.4, pause=cerebras_pause,
        )
        _save_combo(r)

    if "gemini" in selected:
        if await gemini_available():
            r = await run_combo(
                "gemini+gladia@vad0.4", n_gemini, llm_provider="gemini",
                vad_stop_secs=0.4, pause=pause,
            )
            _save_combo(r)
        else:
            print("  gemini combo SKIPPED (free-tier daily quota exhausted)")

    # --- evaluate over ALL saved combos (staged runs accumulate) ----------------
    combos = list(_load_combos().values())
    for r in combos:
        if r["conversation_id"] and not r.get("components"):
            r["components"] = await component_medians(r["conversation_id"])
            print(f"  {r['label']} components: {r['components']}")
            _save_combo(r)

    # acceptance is judged on a full 10-turn conversation — 3-turn probes exist
    # for comparison only and must not win "best combo" on a lucky small sample
    full_runs = [r for r in combos if r.get("eos_p50") and (r.get("turns_measured") or 0) >= 10]
    best = min(
        full_runs or [r for r in combos if r.get("eos_p50")],
        key=lambda r: r["eos_p50"],
        default=None,
    )
    RESULTS["combos"] = combos
    RESULTS["best"] = best

    check.ok(
        "10-turn conversation completed on at least one combo (no 429s/failovers at RPM-aware pacing)",
        any(
            r["turns_completed"] >= 10
            and r["turns_completed"] >= r.get("turns_requested", 10)
            and r.get("llm_failovers", 0) == 0
            for r in combos
        ),
        str([
            (r["label"], f"{r['turns_completed']}/{r.get('turns_requested', '?')}",
             f"failovers={r.get('llm_failovers', '?')}",
             f"quota_excluded={r.get('quota_excluded_turns', 0)}")
            for r in combos
        ]),
    )
    p50 = best["eos_p50"] if best else None
    p95 = best["eos_p95"] if best else None
    check.ok(
        "p50 eos→first_audio ≤ 800ms stretch / ≤ 1000ms hard (best combo, clean)",
        p50 is not None and p50 <= 1000,
        f"best={best['label'] if best else None} p50={p50}ms clean "
        f"(raw {best.get('eos_p50_raw') if best else None}ms; stretch 800: "
        f"{'MET' if p50 is not None and p50 <= 800 else 'missed'})",
    )
    check.ok(
        "p95 eos→first_audio ≤ 1500ms (best combo, clean)",
        p95 is not None and p95 <= 1500,
        f"p95={p95}ms clean (raw {best.get('eos_p95_raw') if best else None}ms, "
        f"{best.get('quota_excluded_turns', 0) if best else 0} quota-excluded turns)",
    )
    # v4 A.2b: the filler cannot start before the LLM decides to call the tool,
    # and that decision needs the final transcript — so the honest target is
    # stt_final_median + 900ms (LLM tool-decision + filler playback start).
    tool_p50 = best.get("tool_turn_first_audio_p50") if best else None
    stt_median = (best.get("components") or {}).get("stt_ms") if best else None
    tool_target = (stt_median + 900) if stt_median is not None else None
    check.ok(
        "tool-calling turns: first audio (cached filler) ≤ stt_final_median + 900ms at p50",
        tool_p50 is not None and tool_target is not None and tool_p50 <= tool_target,
        f"tool-turn p50={tool_p50}ms vs target {tool_target}ms "
        f"(stt_final_median {stt_median}ms + 900) over "
        f"{best.get('tool_turn_count') if best else 0} tool turns",
    )
    check.ok(
        "no repeated consecutive reply openers (10-turn conversation)",
        all((r.get("repeated_openers") or 0) == 0 for r in combos if r.get("openers")),
        str([(r["label"], r.get("repeated_openers")) for r in combos]),
    )
    toks = best["tokens_avg"] if best else None
    check.ok(
        "tokens per turn ≤ 1200 (best combo, measured)",
        toks is not None and toks <= 1200,
        f"avg={toks} max={best['tokens_max'] if best else None} — floor is structural: "
        "fixed per-call prompt is 1401 tok (606 persona + 760 tool schemas), tool turns make 2 calls",
    )
    check.ok(
        "no reasoning/thinking tokens produced",
        all((r["reasoning_tokens"] or 0) == 0 for r in combos),
        str([(r["label"], r["reasoning_tokens"]) for r in combos]),
    )
    check.ok(
        "turn_metrics rows landed in Supabase",
        all(
            r.get("components", {}).get("rows", 0) > 0
            for r in combos
            if r["turns_measured"]
        ),
        "",
    )
    return check


if __name__ == "__main__":
    c = asyncio.run(run())
    sys.exit(0 if c.passed else 1)
