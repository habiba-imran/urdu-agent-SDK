"""Provider-independent tool effects, safe outcomes and concurrent waiting."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

import httpx


@dataclass(frozen=True)
class ToolExecutionPlan:
    tool_call_id: str
    tool_name: str
    request_identity: int
    category: str
    may_cancel: bool
    may_retry: bool
    idempotency_required: bool
    acknowledgement: str


@dataclass(frozen=True)
class ToolResult:
    outcome: str
    data: dict = field(default_factory=dict)
    speech_summary: str | None = None
    business_effect: str = "none"
    retry_safe: bool = False
    idempotency_key: str | None = None

    def payload(self) -> dict:
        out = dict(self.data)
        out.update(outcome=self.outcome, businessEffect=self.business_effect, retrySafe=self.retry_safe)
        if self.speech_summary:
            out["voiceSummary"] = self.speech_summary
        if self.outcome not in {"SUCCESS", "NO_RESULT"}:
            out.update(success=False, error=self.speech_summary)
        return out


MESSAGES = {
    "VALIDATION_ERROR": "Some details need clarification before this action can proceed.",
    "CONFLICT": "The requested action conflicts with the current booking or availability.",
    "DEPENDENCY_TIMEOUT": "The service did not respond in time. The result is unavailable.",
    "DEPENDENCY_UNAVAILABLE": "The service is unavailable right now.",
    "RATE_LIMITED": "The service is busy. Please try again later.",
    "OUTCOME_UNKNOWN": "The action may have completed, but its outcome is unverified. Do not repeat it; check the booking status first.",
    "CANCELLED": "The lookup was cancelled.",
}
WRITE_TOOLS = {"book_appointment", "reschedule_appointment", "cancel_appointment"}


def execution_plan(name: str, call_id: str, revision: int, *, proposal: bool = False) -> ToolExecutionPlan:
    category = (
        "WRITE_PROPOSAL" if proposal else "WRITE_COMMIT" if name in WRITE_TOOLS
        else "ESCALATION_RECORD" if name == "escalate_to_human"
        else "SESSION_FINALIZATION" if name == "end_conversation_summary"
        else "VARIABLE_READ" if name in {"check_availability", "lookup_business_info"}
        else "FAST_READ"
    )
    read = category in {"FAST_READ", "VARIABLE_READ"}
    return ToolExecutionPlan(call_id, name, revision, category, read, read,
                             category == "WRITE_COMMIT", "delayed" if category == "VARIABLE_READ" else "none")


def failure(exc: BaseException, *, write: bool, dispatched: bool, idempotency_key: str | None = None) -> ToolResult:
    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    definite_pre_delivery = isinstance(exc, (httpx.ConnectTimeout, httpx.PoolTimeout, httpx.ConnectError))
    definite_rejection = status is not None and 400 <= status < 500
    uncertain = dispatched and write and not definite_pre_delivery and not definite_rejection
    outcome = (
        "OUTCOME_UNKNOWN" if uncertain else
        "CANCELLED" if isinstance(exc, asyncio.CancelledError) else
        "RATE_LIMITED" if status == 429 else "CONFLICT" if status == 409 else
        "NO_RESULT" if status == 404 else
        "VALIDATION_ERROR" if status is not None and 400 <= status < 500 else
        "DEPENDENCY_TIMEOUT" if isinstance(exc, (httpx.TimeoutException, TimeoutError)) else "DEPENDENCY_UNAVAILABLE"
    )
    return ToolResult(outcome, speech_summary=MESSAGES.get(outcome),
                      business_effect="unknown" if uncertain else "none",
                      retry_safe=not write, idempotency_key=idempotency_key)


def normalize(body: dict, plan: ToolExecutionPlan, *, idempotency_key: str | None = None) -> ToolResult:
    write = plan.category in {"WRITE_COMMIT", "ESCALATION_RECORD", "SESSION_FINALIZATION"}
    declared = body.get("outcome")
    if body.get("error") or body.get("success") is False or declared not in {None, "SUCCESS", "NO_RESULT"}:
        outcome = (declared if declared in MESSAGES else
                   "OUTCOME_UNKNOWN" if write and declared is not None else
                   "DEPENDENCY_UNAVAILABLE" if declared is not None else "VALIDATION_ERROR")
        return ToolResult(outcome, speech_summary=MESSAGES[outcome], retry_safe=not write,
                          business_effect="unknown" if outcome == "OUTCOME_UNKNOWN" else "none",
                          idempotency_key=idempotency_key)
    outcome = "NO_RESULT" if declared == "NO_RESULT" or body.get("found") is False or body.get("available") is False else "SUCCESS"
    summary = body.get("voiceSummary")
    effect = "committed" if write and outcome == "SUCCESS" else "none"
    data = dict(body)
    if plan.category == "ESCALATION_RECORD":
        effect = "escalation_recorded"
        data["liveTransfer"] = False
        summary = "A request for human follow-up has been recorded. No live transfer has started."
    return ToolResult(outcome, data, summary, effect, not write, idempotency_key)


class ToolOrchestrator:
    def __init__(self, runtime: Any = None, *, bridges_enabled: bool = False, delay: float = 0.8) -> None:
        self.runtime = runtime
        self.bridges_enabled = bridges_enabled
        self.delay = delay
        self.bridge_callback: Callable | None = None
        self.results: dict[str, ToolResult] = {}
        self.plans: dict[str, ToolExecutionPlan] = {}

    def plan(self, ctx: Any, name: str, *, proposal: bool = False) -> ToolExecutionPlan:
        call_id = getattr(getattr(ctx, "function_call", None), "call_id", None) or uuid4().hex
        revision = self.runtime.semantic_revision if self.runtime else 0
        if self.runtime:
            revision = self.runtime.tool_request_revisions.get(call_id, revision)
        plan = execution_plan(name, call_id, revision, proposal=proposal)
        self.plans[call_id] = plan
        return plan

    def current(self, plan: ToolExecutionPlan) -> bool:
        return not self.runtime or (plan.request_identity == self.runtime.semantic_revision and not self.runtime.state.session_closed)

    def complete(self, plan: ToolExecutionPlan, result: ToolResult) -> dict:
        self.results[plan.tool_call_id] = result
        if self.runtime:
            prior = self.runtime.state.tool_state.calls.get(plan.tool_call_id)
            if prior and prior.business_effect in {"committed", "unknown", "escalation_recorded"} and result.business_effect == "none":
                return result.payload()
            self.runtime.observe("tool_result", tool_call_id=plan.tool_call_id,
                                 outcome=result.outcome, business_effect=result.business_effect,
                                 result_data=result.payload(), request_identity=plan.request_identity)
            self.runtime.snapshot("after_tool_result")
        if plan.category in {"FAST_READ", "VARIABLE_READ"} and not self.current(plan):
            # LiveKit removes output and suppresses the continuation for this call.
            from livekit.agents.llm import StopResponse
            raise StopResponse()
        if self.runtime and plan.tool_name == "check_availability" and result.outcome == "SUCCESS":
            self.runtime.offered_slots = {
                slot.get("startTime") or slot.get("start_time")
                for slot in result.data.get("slots", []) if isinstance(slot, dict)
            } - {None}
        return result.payload()

    async def run(self, plan: ToolExecutionPlan, operation: Callable, *, idempotency_key: str | None = None) -> dict:
        if plan.may_cancel and not self.current(plan):
            from livekit.agents.llm import StopResponse
            raise StopResponse()
        if self.runtime:
            self.runtime.observe("tool_started", tool_call_id=plan.tool_call_id)
        finished = False
        async def bridge():
            await asyncio.sleep(self.delay)
            if not finished and self.current(plan) and self.bridge_callback:
                if self.runtime and self.runtime.coordinator.state in {"USER_SPEAKING", "INTERRUPTION_CANDIDATE"}:
                    return
                # say() queues interruptible audio; never await playout before HTTP.
                text = (self.runtime.functional_phrase("TOOL_ACK_CHECK")
                        if self.runtime else "I'm checking that for you.")
                if text:
                    self.bridge_callback(text)
        waiting = None
        if self.bridges_enabled and plan.acknowledgement == "delayed":
            waiting = asyncio.create_task(bridge())
        try:
            async with asyncio.timeout(6.0):
                raw = await operation()
            result = raw if isinstance(raw, ToolResult) else normalize(raw, plan, idempotency_key=idempotency_key)
        except asyncio.CancelledError as exc:
            result = failure(exc, write=not plan.may_cancel, dispatched=True, idempotency_key=idempotency_key)
            self.complete(plan, result)
            raise
        except Exception as exc:
            result = failure(exc, write=not plan.may_cancel, dispatched=True, idempotency_key=idempotency_key)
        finally:
            finished = True
            if waiting:
                waiting.cancel()
                # The cancelled scheduler has no I/O; consume completion without
                # another await between a known business result and recording it.
                def consume(task):
                    if not task.cancelled():
                        task.exception()
                waiting.add_done_callback(consume)
        return self.complete(plan, result)


def for_userdata(userdata: Any) -> ToolOrchestrator:
    runtime = getattr(userdata, "humanization_runtime", None)
    if runtime:
        return runtime.tools
    existing = getattr(userdata, "tool_orchestrator", None)
    if existing is None:
        existing = ToolOrchestrator()
        userdata.tool_orchestrator = existing
    return existing
