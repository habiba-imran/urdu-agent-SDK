"""Joint phrase, prosody, context, overlap and waiting behavior contracts."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from livekit.agents.llm import ChatContext, FunctionCall, FunctionCallOutput

from worker.humanization.coordinator import TurnCoordinator
from worker.humanization.context_memory import ConversationMemory, recall_tool
from worker.humanization.delivery.intent import DeliveryIntent
from worker.humanization.persona import PersonaProfile
from worker.humanization.streaming import SpeechChunkPlanner, SpeechPlan


def test_first_phrase_prefers_a_clause_over_a_dangling_article():
    text = 'I can help you choose a suitable appointment by first checking the available times for tomorrow'
    planner = SpeechChunkPlanner('cartesia', conversational=True)
    assert not planner.feed(text)
    first = planner.release_first_safe_prefix()[0]
    assert first.text.strip() == 'I can help you choose a suitable appointment'
    assert ''.join(c.text for c in [first, *planner.finish()]) == text


@pytest.mark.parametrize('text', ['Please ask the receptionist for the', 'براہ کرم اپائنٹمنٹ کی تفصیل کے'])
def test_first_phrase_never_ends_in_a_weak_link_word(text):
    planner = SpeechChunkPlanner('uplift')
    planner.feed(text+' available information')
    chunks = planner.release_first_safe_prefix()
    assert all(c.text.split()[-1] not in {'the', 'for', 'کے', 'کی'} for c in chunks)


@pytest.mark.parametrize('text', ['mm-hmm', 'mm hmm', 'uh huh', 'uh-huh', 'mhm', 'hmmm', 'ok'])
def test_equivalent_short_backchannels_preserve_speech_but_not_confirmation_answers(text):
    coordinator = TurnCoordinator(state='AGENT_SPEAKING')
    assert coordinator.decide_overlap(text, agent_speaking=True, duration=.3) == 'CONTINUE'
    assert coordinator.decide_overlap(text, agent_speaking=True, duration=.3, awaiting_answer=True) == 'YIELD'
    assert coordinator.decide_overlap(text, agent_speaking=True, duration=None) == 'YIELD'
    assert coordinator.decide_overlap('stop '+text, agent_speaking=True, duration=.3) == 'YIELD'


def test_enabled_persona_coordinates_runtime_and_native_turn_options_and_rolls_back(monkeypatch):
    from test_humanization_conversational import runtime
    from worker.humanization.runtime import HumanizationRuntime
    from worker.humanization.turn import build_turn_profile
    monkeypatch.delenv('UVA_OVERLAP_POLICY', raising=False)
    rt = HumanizationRuntime(tenant_id='fixture', agent_id='fixture', session_id='fixture',
        language='en', channel='webrtc', policy=runtime().policy, persona_profile=PersonaProfile(enabled=True))
    assert rt.overlap_enabled and rt.tools.bridges_enabled
    assert build_turn_profile(audio_channel='webrtc', persona_enabled=True).resume_false_interruption
    monkeypatch.setenv('UVA_OVERLAP_POLICY', 'baseline')
    monkeypatch.setenv('UVA_TOOL_ACKNOWLEDGEMENTS', '0')
    rt = HumanizationRuntime(tenant_id='fixture', agent_id='fixture', session_id='fixture',
        language='en', channel='webrtc', policy=runtime().policy, persona_profile=PersonaProfile(enabled=True))
    assert not rt.overlap_enabled and not rt.tools.bridges_enabled
    assert not build_turn_profile(audio_channel='webrtc', persona_enabled=True).resume_false_interruption


@pytest.mark.parametrize('provider', ['cartesia', 'elevenlabs'])
def test_expression_changes_verified_acoustic_controls_without_changing_words(provider):
    from test_humanization_batch_b import context
    from worker.humanization.delivery.renderers import render
    from worker.humanization.delivery.pronunciation import PronunciationPlan
    ctx = context(provider)
    text = 'I can help with the appointment details.'
    low = DeliveryIntent(affect='warm', energy='low', intensity='low', adaptive_pace=True)
    high = replace(low, energy='high', intensity='medium')
    a = render(text, low, PronunciationPlan(), ctx.language, ctx.channel, ctx.capabilities,
               effective=ctx.effective, stored_options={})
    b = render(text, high, PronunciationPlan(), ctx.language, ctx.channel, ctx.capabilities,
               effective=ctx.effective, stored_options={})
    assert a.canonical_text == b.canonical_text == text
    assert a.provider_options != b.provider_options
    if provider == 'cartesia':
        assert '<volume ratio=' in a.provider_text and a.provider_text != b.provider_text
    else:
        assert a.provider_options['voice_settings']['stability'] > b.provider_options['voice_settings']['stability']


def test_memory_bounds_recent_context_preserves_authority_and_can_recall_older_preferences():
    from test_humanization_conversational import runtime
    ctx = ChatContext.empty()
    ctx.add_message(id='rules', role='system', content='Trusted platform rules.')
    ctx.add_message(id='awaaz_persona_data', role='user', content='Descriptive persona DATA.')
    for index in range(30):
        ctx.add_message(role='user', content=f'Preference {index}: choose violet room {index}.')
        ctx.add_message(role='assistant', content=f'Noted preference {index}.')
    before = ctx.to_dict()
    memory = ConversationMemory()
    projected = memory.project(ctx, runtime().state)
    assert len(projected.items) < 25 and ctx.to_dict() == before
    assert projected.items[0].id == 'rules' and 'Trusted platform rules.' in projected.items[0].text_content
    assert any(item.id == 'awaaz_persona_data' for item in projected.items)
    assert 'Preference 29' in str(projected.to_dict())
    result = memory.recall('Preference 2 violet room 2')
    assert result['matches'] and any('Preference 2:' in match['quoted_text'] for match in result['matches'])
    assert ConversationMemory().recall('violet')['matches'] == []


def test_context_window_keeps_tool_pairs_and_old_write_truth_even_if_over_budget():
    from test_humanization_conversational import runtime
    rt = runtime()
    ctx = ChatContext.empty()
    ctx.add_message(role='system', content='Platform rules.')
    ctx.items.extend([
        FunctionCall(call_id='write1', name='book_appointment', arguments='{}'),
        FunctionCallOutput(call_id='write1', name='book_appointment', output='OUTCOME_UNKNOWN synthetic reference AB_19', is_error=False),
    ])
    for index in range(20):
        ctx.add_message(role='user', content=f'New request {index} '+'x'*100)
        ctx.add_message(role='assistant', content='A response.')
    memory = ConversationMemory()
    projected = memory.project(ctx, rt.state, soft_chars=120)
    retained = [item for item in projected.items if getattr(item, 'call_id', None) == 'write1']
    assert len(retained) == 2 and 'OUTCOME_UNKNOWN' in retained[1].output
    assert memory.last_projection['protected_overflow']
    assert ctx.items[-1] is projected.items[-1]  # ordinary items were never rewritten


@pytest.mark.asyncio
async def test_recall_tool_is_session_local_read_only():
    memory = ConversationMemory()
    memory.archive['old'] = {'id': 'old', 'role': 'user', 'text': 'My preferred room is violet.'}
    tool = recall_tool(memory)
    result = await tool(query='violet')
    assert result['matches'][0]['quoted_text'] == 'My preferred room is violet.'
    assert result['source'] == 'same_session_conversation_data'


def test_archive_can_be_browsed_and_paged_without_remembering_an_exact_keyword():
    memory = ConversationMemory()
    for index in range(10):
        memory.archive[str(index)] = {'id': str(index), 'role': 'user', 'text': f'Unusual preference {index}.'}
    seen, page = [], 0
    while page is not None:
        result = memory.recall('*', page=page)
        seen.extend(match['id'] for match in result['matches'])
        page = result['next_page']
    assert len(seen) == len(set(seen)) == 10


@pytest.mark.asyncio
@pytest.mark.parametrize('speaking,tool_name,expected', [(False, 'check_availability', 1),
    (True, 'check_availability', 0), (False, 'book_appointment', 0)])
async def test_slow_tool_ack_is_once_only_does_not_delay_or_cancel_business(speaking, tool_name, expected):
    from test_humanization_conversational import runtime
    from worker.humanization.orchestrator import ToolOrchestrator, execution_plan
    rt = runtime()
    rt.coordinator.state = 'USER_SPEAKING' if speaking else 'LISTENING'
    orchestrator = ToolOrchestrator(rt, bridges_enabled=True, delay=.01)
    spoken = []
    orchestrator.bridge_callback = spoken.append
    finished = False
    async def operation():
        nonlocal finished
        await asyncio.sleep(.04)
        finished = True
        return {'success': True}
    plan = execution_plan(tool_name, 'fixture', rt.semantic_revision)
    result = await orchestrator.run(plan, operation)
    assert finished and result['outcome'] == 'SUCCESS' and len(spoken) == expected


@pytest.mark.asyncio
async def test_result_cancels_only_our_queued_ack():
    from test_humanization_conversational import runtime
    from worker.humanization.orchestrator import ToolOrchestrator, execution_plan
    rt = runtime()
    receipt = SimpleNamespace(done=lambda: False, interrupt=MagicMock())
    rt._session = SimpleNamespace(current_speech=object())
    orchestrator = ToolOrchestrator(rt, bridges_enabled=True, delay=.01)
    orchestrator.bridge_callback = lambda text: receipt
    async def operation():
        await asyncio.sleep(.04)
        return {'success': True}
    await orchestrator.run(execution_plan('lookup_business_info', 'lookup', rt.semantic_revision), operation)
    receipt.interrupt.assert_called_once()


def test_gap_metrics_measure_worker_handoff_and_keep_caller_timing_unknown():
    plan = SpeechPlan('fixture', 'uplift', DeliveryIntent())
    frame = SimpleNamespace(duration=.02)
    plan.provider_context['audio_chunk_start'] = 0
    plan.observe_audio(frame, now=1)
    plan.observe_audio(frame, now=1.02)
    plan.provider_context['audio_chunk_start'] = 12
    plan.observe_audio(frame, now=1.09)
    assert plan.worker_audio_gap_ms == [0, 50]
    assert plan.worker_audio_gap_max_ms == 50
    assert plan.inter_chunk_gap_ms == [50]
    assert plan.metrics()['caller_heard_latency_ms'] is None


def test_emotional_cues_include_concern_and_do_not_force_rotating_emotions():
    from worker.humanization.turn_plan import conversational_signals
    from worker.cartesia_spoken_output import CARTESIA_SPOKEN_OUTPUT_RULES
    assert conversational_signals('I’m really scared about this.').complaint_or_frustration
    assert 'Rotate —' not in CARTESIA_SPOKEN_OUTPUT_RULES
    assert 'Prefer one natural opener' not in CARTESIA_SPOKEN_OUTPUT_RULES


@pytest.mark.asyncio
async def test_long_conversation_projects_actual_model_input_and_registers_local_recall(monkeypatch):
    from livekit.agents import AgentSession, llm
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
    from test_humanization_observability_framework import SyntheticSink, SyntheticTTS
    from test_humanization_conversational import config
    from worker.humanization.runtime import HumanizationRuntime
    from worker.humanization.policy import resolve_humanization_policy
    from worker.main import build_agent
    cfg = replace(config(llm_provider='anthropic'), llm_options={'humanization': {'enabled': True}})
    rt = HumanizationRuntime(tenant_id='fixture', agent_id='fixture', session_id='fixture', language='en',
        channel='webrtc', policy=resolve_humanization_policy('conversational_v1'), persona_profile=PersonaProfile(enabled=True))
    contexts = []
    class Model(llm.LLM):
        def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
            contexts.append((chat_ctx, tools))
            return Stream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)
    class Stream(llm.LLMStream):
        async def _run(self):
            self._event_ch.send_nowait(llm.ChatChunk(id='fixture', delta=llm.ChoiceDelta(content='I can check the details for you.')))
    monkeypatch.setattr('worker.providers.registry._build_tts', lambda *args, **kwargs: SyntheticTTS())
    agent = build_agent(cfg, humanization_runtime=rt)
    initial = agent.chat_ctx.copy()
    for index in range(30):
        initial.add_message(role='user', content=f'Preference {index}: violet room.')
        initial.add_message(role='assistant', content='Noted.')
    await agent.update_chat_ctx(initial)
    session = AgentSession(llm=Model(), tts=SyntheticTTS())
    session.output.audio = SyntheticSink()
    rt.attach_session(session)
    await session.start(agent, record=False)
    try:
        handle = session.generate_reply(user_input='Can you check the latest details?')
        await asyncio.wait_for(handle.wait_for_playout(), 5)
        assert handle.exception() is None and contexts
        projected, tools = contexts[0]
        assert len(projected.items) < 30
        assert any(getattr(tool, '__name__', '') == 'recall_conversation' for tool in tools)
        assert 'Preference 0:' in str(rt.context_memory.recall('Preference 0')['matches'])
        assert len(agent.chat_ctx.items) > 60  # full underlying history survives
    finally:
        await session.aclose()
        await agent.delivery_context.aclose()


@pytest.mark.asyncio
async def test_repeated_native_false_pause_resume_then_takeover_keeps_room_output_usable(caplog):
    import time
    from unittest.mock import AsyncMock
    from livekit import rtc
    from livekit.agents import AgentSession
    from livekit.agents.voice.room_io._output import _ParticipantAudioOutput
    from test_humanization_observability_framework import SyntheticTTS
    from test_smooth_interruption import SlowCleanupAgent
    from worker.interruption import wire_interruption_output_stop
    room = SimpleNamespace(local_participant=SimpleNamespace(publish_track=AsyncMock(
        return_value=SimpleNamespace(wait_for_subscription=AsyncMock()))))
    sink = _ParticipantAudioOutput(room, sample_rate=16000, num_channels=1,
                                   track_publish_options=rtc.TrackPublishOptions())
    await sink.start()
    paused, resumed = asyncio.Event(), asyncio.Event()
    original_pause, original_resume = sink.pause, sink.resume
    def pause():
        original_pause()
        paused.set()
    def resume():
        original_resume()
        resumed.set()
    sink.pause, sink.resume = pause, resume
    session = AgentSession(tts=SyntheticTTS(), aec_warmup_duration=0,
        turn_handling={'interruption': {'mode': 'vad', 'min_duration': .3,
                                       'resume_false_interruption': True, 'false_interruption_timeout': .04}})
    session.output.audio = sink
    agent = SlowCleanupAgent()
    wire_interruption_output_stop(session)
    await session.start(agent, record=False)
    try:
        speech = session.say('A continuous synthetic reply.', audio=agent.audio_source())
        async with asyncio.timeout(3):
            while session.agent_state != 'speaking':
                await asyncio.sleep(.01)
        for _ in range(3):
            paused.clear()
            resumed.clear()
            # Reset the native backchannel cooldown between synthetic VAD episodes.
            session._activity._restore_interruption_by_audio_activity()
            session._activity.on_start_of_speech(None, time.time())
            session._activity.on_vad_inference_done(SimpleNamespace(speech_duration=.4,
                raw_accumulated_silence=0, speaking=True))
            await asyncio.wait_for(paused.wait(), .5)
            session._activity.on_end_of_speech(None)
            await asyncio.wait_for(resumed.wait(), .5)
            assert not speech.interrupted
        completion = session.interrupt()
        agent.release_cleanup.set()
        await asyncio.wait_for(completion, 3)
        async def short_audio():
            yield rtc.AudioFrame(data=bytes(3200), sample_rate=16000, num_channels=1, samples_per_channel=1600)
        fresh = session.say('The next reply completes.', audio=short_audio())
        await asyncio.wait_for(fresh.wait_for_playout(), 3)
        assert not fresh.interrupted and fresh.exception() is None
    finally:
        agent.release_cleanup.set()
        await session.aclose()
        await sink.aclose()
    assert 'on_playback_started called after start_fut is set' not in caplog.text
