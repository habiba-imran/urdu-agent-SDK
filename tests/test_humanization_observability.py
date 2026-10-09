"""Phase 1 of HUMANIZATION_IMPLEMENTATION_PLAN_CODEX; offline structural contracts."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import httpx
import pytest

from worker.telemetry import (
    OUTCOMES, LatencyDistributions, measurement, new_id, percentile_report, provider_snapshot,
)
from worker.latency import TurnLatencyTracker, observe_agent_nodes, wire_turn_latency
from worker.tools import AgentUserdata, _post_client_tool


class Handle:
    def __init__(self, speech_id="speech_1"):
        self.id = speech_id
        self.interrupted = False
        self.error = None
        self.callbacks = []

    def add_done_callback(self, cb):
        self.callbacks.append(cb)

    def exception(self):
        return self.error

    def finish(self, *, interrupted=False, error=None):
        self.interrupted, self.error = interrupted, error
        for callback in self.callbacks:
            callback(self)


def created(tracker, handle, source="generate_reply"):
    tracker.on_speech_created(NS(speech_handle=handle, source=source))


def tracker_and_payloads(monkeypatch, *, lifecycle=True):
    monkeypatch.setenv("UVA_PUBLISH_TURN_LATENCY", "1")
    monkeypatch.setenv("UVA_LOG_TRANSCRIPTS", "0")
    room = MagicMock()
    tracker = TurnLatencyTracker(room, MagicMock(), lifecycle=lifecycle,
                                snapshot={"language": "en", "channel": "webrtc"})
    return tracker, lambda: [json.loads(call.args[0]) for call in room.local_participant.publish_data.call_args_list
                            if call.kwargs["topic"] == "turn_latency"]


def metrics(tracker, speech_id, *, cancelled=False, request_id="req1"):
    tracker.on_metrics(NS(speech_id=speech_id, ttft=.08, cancelled=cancelled,
                          total_tokens=20, request_id="llm_" + request_id))
    tracker.on_metrics(NS(speech_id=speech_id, ttfb=.04, duration=.1, audio_duration=.2,
                          cancelled=cancelled, request_id="tts_" + request_id))


def test_unique_ids_across_semantics_and_sessions(monkeypatch):
    ids = {new_id(kind) for kind in ("session", "user_turn", "assistant_turn", "generation", "tool_call", "speech_chunk")
           for _ in range(200)}
    assert len(ids) == 1200
    a, _ = tracker_and_payloads(monkeypatch)
    b, _ = tracker_and_payloads(monkeypatch)
    a.mark_user_started_speaking()
    b.mark_user_started_speaking()
    created(a, Handle())
    created(b, Handle())
    assert a.session_id != b.session_id
    assert a._generation("speech_1").identity() != b._generation("speech_1").identity()


@pytest.mark.parametrize("outcome", sorted(OUTCOMES - {"completed"}))
def test_invalid_samples_excluded_from_completed_distribution(monkeypatch, outcome):
    tracker, payloads = tracker_and_payloads(monkeypatch)
    h = Handle()
    created(tracker, h)
    metrics(tracker, h.id)
    tracker._generation(h.id).outcome = outcome
    h.finish()
    assert payloads()[0]["outcome"] == outcome
    assert tracker._rolling.e2e_ms == []
    assert tracker._rolling.record_turn(stt_ms=None, llm_ms=None, tts_ttfb_ms=None, e2e_ms=None)["sampleCounts"]["e2e"] == 0
    assert any(key[0] == outcome for key in tracker._distributions.buckets)


def test_completed_sample_waits_for_terminal_and_late_cancel_does_not_resurrect(monkeypatch):
    tracker, payloads = tracker_and_payloads(monkeypatch)
    tracker.mark_user_stopped_speaking()
    h = Handle()
    created(tracker, h)
    tracker.mark_turn_committed("user_message_1", h.id)
    metrics(tracker, h.id)
    assert payloads() == []
    h.finish(interrupted=True)
    metrics(tracker, h.id, request_id="late")
    h.finish()
    assert len(payloads()) == 1
    assert payloads()[0]["outcome"] == "interrupted"
    assert tracker._rolling.e2e_ms == []
    assert payloads()[0]["user_turn_id"] == tracker._user_turn_id


def test_speculation_cancel_and_tool_lifetime_are_independent(monkeypatch):
    tracker, payloads = tracker_and_payloads(monkeypatch)
    h = Handle()
    created(tracker, h)
    tracker.on_tool_execution(NS(update=NS(type="tool_call_started", function_call=NS(call_id="call_1", name="book_appointment"))))
    h.finish(interrupted=True)
    assert payloads()[0]["outcome"] == "cancelled_speculation"
    assert tracker._tools["call_1"]["outcome"] is None
    tracker.on_tool_execution(NS(update=NS(type="tool_call_ended", call_id="call_1", status="done", message="PRIVATE BACKEND RESULT")))
    assert tracker._tools["call_1"]["outcome"] == "completed"
    assert tracker._tools["call_1"]["tool_call_id"] != tracker._tools["call_1"]["generation_id"]


def test_gateway_counted_once_despite_framework_and_wrapper(monkeypatch):
    async def run():
        import worker.ssrf_guard as ssrf
        import worker.tools as tools
        tracker, payloads = tracker_and_payloads(monkeypatch)
        clock = [100.0]
        monkeypatch.setattr(tracker, "_now", lambda: clock[0])
        h = Handle()
        created(tracker, h)
        tracker.mark_turn_committed("msg1", h.id)
        tracker.on_tool_execution(NS(update=NS(type="tool_call_started", function_call=NS(call_id="call_1", name="lookup_business_info"))))
        async def post(*args, **kwargs):
            clock[0] += .05
            return NS(raise_for_status=lambda: None, json=lambda: {"success": True, "result": "PRIVATE PERSON"})
        async def client():
            return NS(post=post)
        monkeypatch.setattr(tools, "_shared_http_client", client)
        monkeypatch.setattr(ssrf, "prepare_tools_post_url", lambda url: (url, {}))
        ud = AgentUserdata("t1", "a1", "room", tools_base_url="https://tools.example",
                           tools_auth_secret="secret-value", latency_tracker=tracker)
        result = await _post_client_tool(NS(userdata=ud, function_call=NS(call_id="call_1"), speech_handle=h),
                                         path="/read", payload={"email": "person@example.com"}, tool_name="lookup_business_info")
        assert result["success"] is True
        terminal = NS(update=NS(type="tool_call_ended", call_id="call_1", status="done", message="PRIVATE PERSON"))
        tracker.on_tool_execution(terminal)
        tracker.on_tool_execution(terminal)
        metrics(tracker, h.id)
        h.finish()
        row = payloads()[0]
        assert row["toolMs"] == 50
        assert len(row["tools"]) == 1
        assert row["e2eMs"] == 120  # nested tool timing is not added to the proxy
        assert row["tools"][0]["generation_id"] == row["generation_id"]
        serialized = json.dumps(row) + str(tracker._logger.info.call_args_list)
        for private in ("secret-value", "PRIVATE PERSON", "person@example.com", "https://tools.example"):
            assert private not in serialized
    asyncio.run(run())


@pytest.mark.parametrize("write,exc,outcome", [
    (False, httpx.ReadTimeout("secret https://backend"), "tool_timeout"),
    (True, httpx.ReadTimeout("secret https://backend"), "tool_outcome_unknown"),
    (True, httpx.ConnectTimeout("secret https://backend"), "tool_timeout"),
    (False, RuntimeError("private payload"), "tool_error"),
])
def test_gateway_outcome_annotations_do_not_change_result_or_write_safety(monkeypatch, write, exc, outcome):
    async def run():
        import worker.ssrf_guard as ssrf
        import worker.tools as tools
        tracker, _ = tracker_and_payloads(monkeypatch)
        h = Handle()
        created(tracker, h)
        tracker.on_tool_execution(NS(update=NS(type="tool_call_started", function_call=NS(call_id="call_1", name="book_appointment"))))
        async def post(*args, **kwargs):
            raise exc
        async def client():
            return NS(post=post)
        monkeypatch.setattr(tools, "_shared_http_client", client)
        monkeypatch.setattr(ssrf, "prepare_tools_post_url", lambda url: (url, {}))
        ud = AgentUserdata("t", "a", "r", tools_base_url="https://example.com", tools_auth_secret="test", latency_tracker=tracker)
        result = await _post_client_tool(NS(userdata=ud, function_call=NS(call_id="call_1"), speech_handle=h),
                                         path="/tool", payload={}, tool_name="book_appointment",
                                         idempotency_key="idem" if write else None)
        assert result["success"] is False
        tracker.on_tool_execution(NS(update=NS(type="tool_call_ended", call_id="call_1", status="done")))
        assert tracker._tools["call_1"]["outcome"] == outcome
        assert str(exc) not in str(tracker._logger.info.call_args_list)
    asyncio.run(run())


def test_missing_invalid_values_remain_null(monkeypatch):
    tracker, payloads = tracker_and_payloads(monkeypatch)
    h = Handle()
    created(tracker, h)
    tracker.on_metrics(NS(speech_id=h.id, ttft=-1))
    tracker.on_metrics(NS(speech_id=h.id, ttfb=float("nan"), duration=None))
    h.finish()
    row = payloads()[0]
    assert all(row[key] is None for key in ("e2eMs", "llmMs", "ttsMs", "ttsTtfbMs", "sttMs", "toolMs"))
    assert row["stages"]["first_speakable_chunk_ready"] is None
    assert row["latencyKind"] == "server_diagnostic_proxy"
    assert measurement(float("inf")) is None


def test_percentiles_counts_minimum_tail_samples_and_bounds():
    report = percentile_report([10])
    assert report["sampleCount"] == 1 and report["p95Ms"] is None and report["p99Ms"] is None
    assert percentile_report(range(1, 101))["p99Ms"] == 99
    assert percentile_report(range(1, 21))["p95Ms"] == 19
    distributions = LatencyDistributions(window=100, max_buckets=2)
    for i in range(110):
        result = distributions.record(outcome="completed", lane=("groq", "m", "en", "webrtc"), values={"e2e": i})
    assert result["metrics"]["e2e"]["sampleCount"] == 100
    for language in ("ur", "mixed"):
        distributions.record(outcome="cancelled", lane=("gemini", "n", language, "telephony"), values={"e2e": 1})
    assert len(distributions.buckets) == 2


def test_snapshot_effective_model_and_options_excludes_private_fields(monkeypatch):
    from worker.providers.types import AgentRuntimeConfig
    monkeypatch.delenv("UVA_DEMO_CARTESIA_MODEL", raising=False)
    runtime = AgentRuntimeConfig("en", "deepgram", "nova-3", {"endpointing_ms": 200}, "groq",
                                  "llama-3.1-8b-instant", {"api_key": "private"}, "cartesia", "voice1", {})
    cfg = NS(stt_model="nova-3", llm_model=runtime.llm_model, tts_options={})
    components = NS(stt=NS(model="nova-3", _opts=NS(endpointing_ms=345, api_key="SECRET")),
                    llm=NS(model="openai/gpt-oss-20b", _opts=NS(extra_headers={"secret": "SECRET"})), tts=NS())
    snapshot = provider_snapshot(cfg, runtime, components)
    assert snapshot["llm"]["requested_model"] == "llama-3.1-8b-instant"
    assert snapshot["llm"]["effective_model"] == "openai/gpt-oss-20b"
    assert snapshot["stt"]["effective_options"]["endpointing_ms"] == 345
    assert "SECRET" not in json.dumps(snapshot)
    assert "api_key" not in json.dumps(snapshot)


def test_snapshot_omits_arbitrary_config_text_and_urls(monkeypatch):
    from worker.providers.types import AgentRuntimeConfig
    from worker.telemetry import identifier
    options = {"model": "customer@example.com", "emotion": ["calm", "Private patient details"]}
    runtime = AgentRuntimeConfig("en", "deepgram", "nova-3", {}, "groq", "openai/gpt-oss-20b",
                                {}, "cartesia", "https://private.example/voice", options)
    cfg = NS(stt_model="nova-3", llm_model=runtime.llm_model, tts_options=options)
    snapshot = provider_snapshot(cfg, runtime, NS(stt=NS(), llm=NS(), tts=NS()))
    encoded = json.dumps(snapshot)
    assert all(value not in encoded for value in ("customer@example.com", "Private patient details", "private.example"))
    assert snapshot["tts"]["effective_options"]["emotion"] == ["calm", None]
    assert snapshot["tts"]["effective_options"]["model"] is None
    assert identifier("https://private.example") is None


def test_orphan_metric_and_out_of_order_callbacks_do_not_join_current_turn(monkeypatch):
    tracker, payloads = tracker_and_payloads(monkeypatch)
    created(tracker, Handle("current"))
    metrics(tracker, "foreign")
    assert "foreign" not in tracker._speeches
    assert payloads() == []
    assert tracker._rolling.e2e_ms == []


def test_node_observers_preserve_objects_capture_first_only_and_close(monkeypatch):
    async def run():
        tracker, payloads = tracker_and_payloads(monkeypatch)
        llm_objects = [NS(delta=NS(content=" ")), NS(delta=NS(content="Hello")), NS(delta=NS(content=" caller@example.com"))]
        frames = [object(), object(), object()]
        closed = []
        async def llm_node(*args):
            try:
                for chunk in llm_objects:
                    yield chunk
            finally:
                closed.append("llm")
        async def tts_node(*args):
            try:
                for frame in frames:
                    yield frame
            finally:
                closed.append("tts")
        agent = NS(llm_node=llm_node, tts_node=tts_node)
        observe_agent_nodes(agent, tracker)
        h = Handle()
        created(tracker, h)
        tracker.mark_turn_committed("msg1", h.id)
        assert [item async for item in agent.llm_node(None, [], None)] == llm_objects
        assert [item async for item in agent.tts_node(None, None)] == frames
        metrics(tracker, h.id)
        h.finish()
        row = payloads()[0]
        assert closed == ["llm", "tts"]
        assert all(row["stages"][s] is not None for s in ("llm_request_start", "first_useful_llm_text", "tts_request_start", "tts_first_audio"))
        assert row["humanization_policy_version"] == "baseline"
        assert "caller@example.com" not in str(tracker._logger.info.call_args_list)
        events = [json.loads(call.args[1]) for call in tracker._logger.info.call_args_list if call.args[0] == "humanization_event %s"]
        assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
        assert sum(e["event"] == "tts_first_audio" for e in events) == 1
    asyncio.run(run())


def test_parallel_tasks_and_multiple_generations_keep_ownership(monkeypatch):
    async def run():
        tracker, payloads = tracker_and_payloads(monkeypatch)
        async def llm_node(*args):
            await asyncio.sleep(0)
            yield "safe text"
        agent = NS(llm_node=llm_node, tts_node=llm_node)
        observe_agent_nodes(agent, tracker)
        h1, h2 = Handle("one"), Handle("two")
        created(tracker, h1)
        first = asyncio.create_task(collect(agent.llm_node(None, [], None)))
        created(tracker, h2)
        second = asyncio.create_task(collect(agent.llm_node(None, [], None)))
        await asyncio.gather(first, second)
        await collect(agent.llm_node(None, [], None))  # second generation on "two"
        h1.finish()
        h2.finish()
        rows = payloads()
        assert len(rows[0]["generations"]) == 1 and len(rows[1]["generations"]) == 2
        assert len({g["generation_id"] for row in rows for g in row["generations"]}) == 3
    asyncio.run(run())


async def collect(stream):
    return [item async for item in stream]


@pytest.mark.parametrize("node", ["llm", "tts"])
def test_observer_initial_failure_restores_context_and_preserves_exception(monkeypatch, node):
    async def run():
        from worker.latency import _generation_scope
        tracker, payloads = tracker_and_payloads(monkeypatch)
        failure = RuntimeError("PRIVATE_PROVIDER_ERROR")
        async def failing(*args):
            raise failure
        agent = NS(llm_node=failing, tts_node=failing)
        observe_agent_nodes(agent, tracker)
        h = Handle()
        created(tracker, h)
        prior = _generation_scope.get()
        args = (None, [], None) if node == "llm" else (None, None)
        with pytest.raises(RuntimeError) as caught:
            await collect(getattr(agent, node + "_node")(*args))
        assert caught.value is failure and _generation_scope.get() is prior
        h.finish(error=failure)
        assert payloads()[0]["outcome"] == "provider_error"
        assert payloads()[0]["stages"]["speech_complete"] is not None
        assert "PRIVATE_PROVIDER_ERROR" not in str(tracker._logger.info.call_args_list)
    asyncio.run(run())


@pytest.mark.parametrize("node", ["llm", "tts"])
def test_observer_cancellation_closes_generator_and_records_interruption(monkeypatch, node):
    async def run():
        tracker, payloads = tracker_and_payloads(monkeypatch)
        started, closed = asyncio.Event(), asyncio.Event()
        async def pending(*args):
            try:
                started.set()
                await asyncio.Event().wait()
                yield object()
            finally:
                closed.set()
        agent = NS(llm_node=pending, tts_node=pending)
        observe_agent_nodes(agent, tracker)
        h = Handle()
        created(tracker, h)
        tracker.mark_turn_committed("user1", h.id)
        args = (None, [], None) if node == "llm" else (None, None)
        task = asyncio.create_task(collect(getattr(agent, node + "_node")(*args)))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()
        h.finish(interrupted=True)
        assert payloads()[0]["outcome"] == "interrupted"
        assert payloads()[0]["stages"]["speech_interrupted"] is not None
        assert tracker._rolling.e2e_ms == []
    asyncio.run(run())


def test_user_resumption_dedup_and_tool_identity_across_sessions(monkeypatch):
    trackers = [tracker_and_payloads(monkeypatch)[0] for _ in range(2)]
    tool_ids = []
    for tracker in trackers:
        tracker.mark_user_started_speaking()
        user = tracker._user_turn_id
        tracker.mark_user_stopped_speaking()
        tracker.mark_user_started_speaking()
        assert tracker._user_turn_id == user
        h = Handle()
        created(tracker, h)
        tracker.mark_turn_committed("user1", h.id)
        tracker.mark_turn_committed("user1", h.id)
        assert tracker._user_turn_id == user
        tracker.on_tool_execution(NS(update=NS(type="tool_call_started", function_call=NS(call_id="same_vendor_id", name="lookup_business_info"))))
        tool = tracker._tools["same_vendor_id"]
        tool_ids.append(tool["tool_call_id"])
        assert tool["tool_call_id"] != tool["generation_id"]
        tracker.mark_user_started_speaking()
        assert tracker._user_turn_id != user
    assert tool_ids[0] != tool_ids[1]


def test_overlapping_turns_preserve_their_own_user_stage_timestamps(monkeypatch):
    tracker, payloads = tracker_and_payloads(monkeypatch)
    clock = [1.0]
    monkeypatch.setattr(tracker, "_now", lambda: clock[0])
    tracker.mark_user_started_speaking()
    first = Handle("first")
    created(tracker, first)  # speculative generation before speech end
    clock[0] = 2.0
    tracker.mark_user_stopped_speaking()
    tracker.mark_turn_committed("first_user", first.id)
    clock[0] = 3.0
    tracker.mark_user_started_speaking()
    second = Handle("second")
    created(tracker, second)
    tracker.mark_turn_committed("second_user", second.id)
    continuation = tracker._generation(first.id, fresh=True)
    assert continuation.stages["user_speech_started"] == 1.0
    assert continuation.stages["user_speech_stopped"] == 2.0
    tracker.on_metrics(NS(speech_id=first.id, end_of_utterance_delay=.2, transcription_delay=.1))
    assert continuation.stages["turn_committed"] == 2.0  # receipt is not a new commit
    first.finish()
    assert payloads()[0]["generations"][0]["stages"]["user_speech_stopped"] == 2.0
    assert payloads()[0]["stages"]["user_speech_started"] == 1.0


def test_wire_public_events_and_close_preserve_baseline(monkeypatch):
    session = NS(on=MagicMock(), userdata=AgentUserdata("t", "a", "r"))
    tracker = wire_turn_latency(session, MagicMock(), MagicMock())
    hooks = {call.args[0]: call.args[1] for call in session.on.call_args_list}
    assert {"speech_created", "close", "error", "conversation_item_added", "agent_false_interruption"} <= set(hooks)
    h = Handle()
    hooks["user_state_changed"](NS(old_state="listening", new_state="speaking"))
    hooks["speech_created"](NS(speech_handle=h, source="generate_reply"))
    hooks["close"](NS())
    assert tracker._generation(h.id).outcome == "cancelled"


def test_duplicate_metrics_do_not_double_usage(monkeypatch):
    tracker, _ = tracker_and_payloads(monkeypatch)
    tracker.mark_user_started_speaking()
    h = Handle()
    created(tracker, h)
    tracker.mark_turn_committed("user1", h.id)
    metrics(tracker, h.id)
    metrics(tracker, h.id)
    h.finish()
    report = tracker.usage_report()
    assert report["categories"]["normal_turn"]["llm_tokens"] == 20
    assert report["categories"]["normal_turn"]["synthesized_audio_seconds"] == .2
    assert report["invoiceAccurate"] is False
    assert report["retry_usage"] is None and report["unplayed_audio_seconds"] is None


@pytest.mark.parametrize("language,stt,llm_provider,tts_provider", [
    ("en", "deepgram", "groq", "cartesia"),
    ("en", "deepgram", "groq", "rime"),
    ("en", "deepgram", "groq", "elevenlabs"),
    ("ur", "gladia", "gemini", "uplift"),
])
def test_snapshot_current_provider_constructors_offline(monkeypatch, language, stt, llm_provider, tts_provider):
    async def run():
        from worker.providers.registry import build_components
        from worker.providers.types import AgentRuntimeConfig
        for env in ("DEEPGRAM_API_KEY", "GROQ_API_KEY", "CARTESIA_API_KEY", "RIME_API_KEY", "ELEVEN_API_KEY", "GOOGLE_API_KEY", "UPLIFTAI_API_KEY"):
            monkeypatch.setenv(env, "CREDENTIAL_SENTINEL")
        monkeypatch.setenv("UPLIFT_MODE", "live")
        runtime = AgentRuntimeConfig(language, stt, "nova-3" if stt == "deepgram" else "default",
                                      {"endpointing_ms": 200} if stt == "deepgram" else {}, llm_provider,
                                      "openai/gpt-oss-20b" if llm_provider == "groq" else "gemini-3.6-flash",
                                      {}, tts_provider, "andromeda" if tts_provider == "rime" else "voice1", {})
        components = build_components(runtime)
        try:
            snapshot = provider_snapshot(runtime, runtime, components)
            assert snapshot["tts"]["effective_model"] == (components.tts.model if components.tts.model != "unknown" else None)
            assert snapshot["llm"]["effective_model"] == components.llm.model
            assert snapshot["language"] == language
            assert "CREDENTIAL_SENTINEL" not in json.dumps(snapshot)
            assert "api_key" not in json.dumps(snapshot)
            assert snapshot["tts"]["plugin_version"] == "1.6.5"
        finally:
            for component in (components.stt, components.llm, components.tts):
                await component.aclose()
    asyncio.run(run())


def test_greeting_does_not_enter_normal_turn_distribution(monkeypatch):
    tracker, payloads = tracker_and_payloads(monkeypatch)
    h = Handle()
    created(tracker, h, source="say")
    metrics(tracker, h.id)
    h.finish()
    assert payloads()[0]["operation"] == "platform_speech"
    assert tracker._rolling.e2e_ms == []


def test_recoverable_provider_error_does_not_poison_completed_outcome(monkeypatch):
    session = NS(on=MagicMock(), userdata=AgentUserdata("t", "a", "r"))
    tracker = wire_turn_latency(session, MagicMock(), MagicMock())
    h = Handle()
    created(tracker, h)
    callbacks = {call.args[0]: call.args[1] for call in session.on.call_args_list}
    callbacks["error"](NS(error=NS(recoverable=True)))
    assert tracker._generation(h.id).outcome is None
    assert tracker.usage_report()["activities"][0]["category"] == "retry"
