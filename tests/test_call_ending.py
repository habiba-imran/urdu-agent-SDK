"""Model-selected call ending and lifecycle safety; no external I/O."""
import asyncio
from types import SimpleNamespace as NS

import pytest
from livekit.agents import llm

from worker.call_ending import CALL_ENDING_INSTRUCTIONS
from worker.tools import AgentUserdata, end_conversation_summary


def test_shared_platform_prompt_gives_the_conversation_model_ending_authority():
    from worker.cartesia_spoken_output import SYSTEM_INSTRUCTIONS_BASE
    assert CALL_ENDING_INSTRUCTIONS in SYSTEM_INSTRUCTIONS_BASE
    assert "whole conversation, in any language" in CALL_ENDING_INSTRUCTIONS
    assert "When intent is ambiguous, ask one brief clarification" in CALL_ENDING_INSTRUCTIONS
    assert "Choose the goodbye wording yourself" in CALL_ENDING_INSTRUCTIONS
    assert "end_conversation_summary in the same turn" in CALL_ENDING_INSTRUCTIONS


def context(text="Goodbye", previous=""):
    history = llm.ChatContext.empty()
    if previous:
        history.add_message(role="assistant", content=previous)
    history.add_message(role="user", content=text)
    history.add_message(role="assistant", content="Wishing you a pleasant afternoon.")
    shutdowns = []
    session = NS(history=history, user_state="listening", shutdown=lambda **kw: shutdowns.append(kw),
                 options=NS(session_close_transcript_timeout=2))
    async def wait():
        pass
    return NS(userdata=AgentUserdata("t", "a", "r"), session=session,
              wait_for_playout=wait, speech_handle=NS(interrupted=False)), shutdowns


def test_summary_failure_does_not_veto_intentional_hangup(monkeypatch):
    def fail(**kwargs):
        raise OSError("database unavailable")
    monkeypatch.setattr("worker.tools._save_conversation_summary", fail)
    ctx, shutdowns = context()
    result = asyncio.run(end_conversation_summary(ctx, summary="Caller finished."))
    assert result["callEnding"] is True and result["summarySaved"] is False
    assert result["outcome"] != "SUCCESS"  # Never claim that the save succeeded.
    assert shutdowns == [{"drain": True}]


@pytest.mark.parametrize("interruption", ["speaking", "interrupted", "new_turn"])
def test_interruption_during_goodbye_cancels_hangup_but_preserves_saved_summary(monkeypatch, interruption):
    saves = []
    monkeypatch.setattr("worker.tools._save_conversation_summary", lambda **kw: saves.append(kw))
    ctx, shutdowns = context()
    async def wait():
        if interruption == "speaking":
            ctx.session.user_state = "speaking"
        elif interruption == "interrupted":
            ctx.speech_handle.interrupted = True
        else:
            ctx.session.history.add_message(role="user", content="Wait, one more thing")
    ctx.wait_for_playout = wait
    result = asyncio.run(end_conversation_summary(ctx, summary="Caller finished."))
    assert result["status"] == "continued" and result["callEnding"] is False
    assert len(saves) == 1 and shutdowns == []
    assert not ctx.userdata.ended_by_agent and not ctx.userdata.ending_in_progress


def test_duplicate_end_tools_only_save_and_shutdown_once(monkeypatch):
    async def run():
        ctx, shutdowns = context()
        started, release = asyncio.Event(), asyncio.Event()
        saves = []
        async def operation(fn, **kwargs):
            saves.append(kwargs)
            started.set()
            await release.wait()
            return {"status": "saved"}
        monkeypatch.setattr("worker.tools._lifecycle_call", operation)
        first = asyncio.create_task(end_conversation_summary(ctx, summary="Finished"))
        await started.wait()
        duplicate = await end_conversation_summary(ctx, summary="Duplicate")
        assert duplicate["status"] == "already_ending"
        release.set()
        await first
        await end_conversation_summary(ctx, summary="Late duplicate")
        assert len(saves) == 1 and shutdowns == [{"drain": True}]
    asyncio.run(run())


def test_end_without_committed_caller_turn_does_not_save_or_hangup(monkeypatch):
    monkeypatch.setattr("worker.tools._save_conversation_summary", lambda **kw: pytest.fail("must not save"))
    ctx, shutdowns = context()
    ctx.session.history = llm.ChatContext.empty()
    result = asyncio.run(end_conversation_summary(ctx, summary="No caller turn"))
    assert result["status"] == "not_ending" and shutdowns == []


@pytest.mark.parametrize("text", [
    "That takes care of everything on my side, cheers for sorting it.",
    "I need to dash; let's leave our conversation here.",
    "Shall we leave it there?", "No, thank you", "بس اب اجازت دیں", "Hasta luego",
])
def test_model_selected_end_is_not_vetoed_by_caller_phrasing(monkeypatch, text):
    # The model has already selected the tool. This checks execution, not NLP quality.
    monkeypatch.setattr("worker.tools._save_conversation_summary", lambda **kw: None)
    ctx, shutdowns = context(text)
    result = asyncio.run(end_conversation_summary(ctx, summary="Caller chose to finish."))
    assert result["callEnding"] is True and shutdowns == [{"drain": True}]


def test_stale_model_end_is_rejected_before_persistence(monkeypatch):
    monkeypatch.setattr("worker.humanization.orchestrator.ToolOrchestrator.current", lambda *args: False)
    monkeypatch.setattr("worker.tools._save_conversation_summary", lambda **kw: pytest.fail("stale save"))
    ctx, shutdowns = context()
    result = asyncio.run(end_conversation_summary(ctx, summary="Old model decision"))
    assert result["status"] == "continued" and shutdowns == []


def test_unfinished_playout_keeps_call_open(monkeypatch):
    monkeypatch.setattr("worker.tools._save_conversation_summary", lambda **kw: None)
    ctx, shutdowns = context()
    async def wait():
        raise TimeoutError()
    ctx.wait_for_playout = wait
    result = asyncio.run(end_conversation_summary(ctx, summary="Finished"))
    assert result["status"] == "playout_incomplete" and shutdowns == []
    assert not ctx.userdata.ended_by_agent


def test_silent_model_tool_call_cannot_skip_goodbye(monkeypatch):
    monkeypatch.setattr("worker.tools._save_conversation_summary", lambda **kw: None)
    ctx, shutdowns = context()
    ctx.session.history = llm.ChatContext.empty()
    ctx.session.history.add_message(role="user", content="Let's wrap up here")
    result = asyncio.run(end_conversation_summary(ctx, summary="Finished"))
    assert result["status"] == "closing_speech_missing" and shutdowns == []
