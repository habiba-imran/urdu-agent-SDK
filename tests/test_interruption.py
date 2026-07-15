"""STEP 9.6 — Interruption (barge-in) test.

Starts a long agent reply, injects user audio mid-playback, and asserts:
- the min-words gate: 1 word does NOT interrupt while the bot speaks, 2+ words do
- TTS halts promptly (no further audio after the interruption)
- Uplift's in-flight requests are cancelled server-side
- the conversation context keeps only what was actually spoken (truncation)
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import Check, synth_urdu
from helpers_pipeline import PipelineHarness


async def test_min_words_gate(check: Check):
    """Unit-level check of the barge-in gate configuration."""
    from pipecat.frames.frames import BotStartedSpeakingFrame, TranscriptionFrame
    from pipecat.turns.types import ProcessFrameResult
    from pipecat.utils.time import time_now_iso8601

    import bot as bot_module

    strategies = bot_module.build_turn_strategies()
    strategy = strategies.start[0]

    triggered = []

    async def on_trigger(*a, **k):
        triggered.append(1)

    strategy._trigger_user_turn_started = on_trigger  # observe trigger calls
    if hasattr(strategy, "add_event_handler"):
        pass

    await strategy.process_frame(BotStartedSpeakingFrame())
    r1 = await strategy.process_frame(TranscriptionFrame("ہاں", "u", time_now_iso8601()))
    one_word_blocked = r1 == ProcessFrameResult.CONTINUE
    r2 = await strategy.process_frame(TranscriptionFrame("رکیے ذرا سنیں", "u", time_now_iso8601()))
    two_words_pass = r2 == ProcessFrameResult.STOP
    check.ok("min-words gate: 1 word ignored while bot speaks", one_word_blocked)
    check.ok("min-words gate: 2+ words interrupt", two_words_pass)


async def run() -> Check:
    check = Check("interruption")

    await test_min_words_gate(check)

    # Synthesize inputs up front
    warmup_q = await synth_urdu("MacBook Air M2 کی قیمت کیا ہے؟")
    long_q = await synth_urdu("مجھے تمام MacBook ماڈلز کے بارے میں تفصیل سے بتائیں، ہر ایک کی خصوصیات کیا ہیں؟")
    barge = await synth_urdu("رکیے رکیے، مجھے صرف سب سے سستے کی قیمت بتائیں")

    harness = PipelineHarness(turn_stop_mode="vad")
    await harness.start()
    try:
        # 0. Warm-up turn (absorbs the scripted greeting; realistic mid-call state)
        await harness.user_turn(warmup_q, timeout=60)
        await asyncio.sleep(8)

        # 1. Trigger the reply we will interrupt
        n_before_longq = len(harness.tap.responses)
        harness.sink.reset_turn()
        harness.sink.text_log.clear()
        await harness.feed_wav(long_q)

        # wait until the ACTUAL reply (not the tool-call filler, which is excluded
        # from context by design) starts being released with playback — barging
        # during the filler would legitimately leave zero reply text in context
        import persona

        _fillers = {" ".join(f.split()) for f in persona.TOOL_FILLERS}

        def reply_playing() -> bool:
            return any(" ".join(t.split()) not in _fillers for _, t in harness.sink.text_log)

        t0 = time.monotonic()
        while not reply_playing() and time.monotonic() - t0 < 40:
            await asyncio.sleep(0.05)
        check.ok("reply (non-filler sentence) started playing", reply_playing())

        await asyncio.sleep(1.0)  # mid-playback (sink paces audio at real time)
        n_responses_before = len(harness.tap.responses)
        contexts_before = set(harness.tts._context_order.keys())

        # 2. Barge in (>= 2 words, real audio through VAD + STT).
        #    Old audio legitimately keeps playing until 2+ words are transcribed.
        harness.sink.interrupted_at = None
        await harness.feed_wav(barge)

        t0 = time.monotonic()
        while harness.sink.interrupted_at is None and time.monotonic() - t0 < 20:
            await asyncio.sleep(0.02)
        interrupted = harness.sink.interrupted_at is not None
        check.ok("barge-in triggered an interruption", interrupted)

        if interrupted:
            # 3. TTS halts: the old stream must produce (almost) no audio after the
            #    interruption. The new reply cannot start within ~1.2s (STT+LLM+TTS
            #    floor is >2s), so any audio in this window is stale audio.
            audio_at_interrupt = len(harness.sink.audio)
            await asyncio.sleep(1.2)
            stale_bytes = len(harness.sink.audio) - audio_at_interrupt
            stale_ms = stale_bytes / 2 / 22.05
            check.ok(
                "TTS halted: ≤300ms of trailing audio after interruption",
                stale_ms <= 300,
                f"{stale_ms:.0f}ms of stale audio after the interruption",
            )
            remaining = contexts_before & set(harness.tts._context_order.keys())
            check.ok(
                "Uplift in-flight requests of the interrupted turn cancelled",
                len(remaining) == 0,
                f"interrupted-turn contexts still pending: {remaining or 'none'}",
            )

        # 4. Wait for the answer to the barge-in question, then check truncation
        try:
            await asyncio.wait_for(harness.sink.turn_done.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
        await asyncio.sleep(1.5)

        full_responses = harness.tap.responses
        messages = harness.context.get_messages()
        assistant_msgs = [
            m
            for m in messages
            if m.get("role") == "assistant"
            and isinstance(m.get("content"), str)
            and m.get("content")
        ]
        # The context must contain exactly the sentences that started playing
        # before the interruption (sentence-level truncation; Uplift has no
        # word timestamps). Sentences released downstream by the (paced) sink
        # before interrupted_at are "spoken"; anything else must be dropped.
        truncated_ok = False
        detail = f"responses={len(full_responses)} assistant_msgs={len(assistant_msgs)}"
        if len(full_responses) > n_before_longq and interrupted:
            import persona

            # tool-call filler lines are spoken but deliberately excluded from
            # context (TTSSpeakFrame append_to_context=False) — don't count them
            # as "spoken" when comparing against context (D23 harness fillers)
            fillers = {" ".join(f.split()) for f in persona.TOOL_FILLERS}
            norm = lambda s: " ".join(s.split())
            # sentence released well before the barge MUST be in context; one
            # released within ~0.3s of the InterruptionFrame is a boundary case
            # (the queue clear may drop it before the aggregator sees it) and MAY be
            interrupt_at = harness.sink.interrupted_at
            released = [
                (t, norm(txt))
                for t, txt in harness.sink.text_log
                if norm(txt) not in fillers and t <= interrupt_at + 0.05
            ]
            must_spoken = " ".join(txt for t, txt in released if t <= interrupt_at - 0.3).strip()
            may_spoken = " ".join(txt for t, txt in released).strip()
            full = max(
                (r.strip() for r in full_responses[n_before_longq:]), key=len, default=""
            )
            ctx = next(
                (
                    norm(m["content"])
                    for m in assistant_msgs
                    if m["content"].strip()
                    and norm(m["content"])[:25] == may_spoken[:25]
                ),
                "",
            )
            truncated_ok = (
                bool(may_spoken)
                and bool(ctx)
                and ctx.startswith(must_spoken)
                and may_spoken.startswith(ctx)
                and len(ctx) <= len(norm(full))
            )
            detail = (
                f"context kept {len(ctx)} chars; released-before-barge {len(may_spoken)} chars "
                f"(full response was {len(full)} chars)"
            )
        check.ok("context matches exactly what was spoken before the barge", truncated_ok, detail)
        check.ok(
            "bot answered the barge-in question",
            len(full_responses) >= n_responses_before + 1 and len(harness.sink.audio) > 0,
            f"{len(full_responses)} LLM responses in session",
        )
    finally:
        await harness.stop()

    return check


if __name__ == "__main__":
    c = asyncio.run(run())
    sys.exit(0 if c.passed else 1)
