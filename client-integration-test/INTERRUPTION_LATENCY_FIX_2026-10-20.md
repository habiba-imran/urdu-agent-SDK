# Interruption latency correction, 20 October 2026

The supplied outbound log shows Groq first text after about 650 ms, followed by
1,812 ms from TTS node entry to the first provider audio frame. A new Cartesia
WebSocket was established during that interval. Bare-VAD force cancellation then
cut the reply about 94 ms after the first TTS frame, with no new final transcript
in the remainder of the excerpt. Another turn included a 2,109 ms escalation tool
write. The excerpt does not show a Groq rate-limit error and does not establish
the cause of every slow inbound or long-call turn.

Both phone directions share the corrected session setup:

- Bare-VAD force flush now defaults off. Native interruption stays enabled with
  its existing duration threshold. `UVA_FORCE_BARGE_IN_FLUSH=1` remains an override.
- Actual speech interruption starts one bounded Cartesia connection preparation
  task. The pinned plugin discards cancelled sockets; its startup prewarm task
  cannot run a second time. The adapter borrows and returns a clean socket through
  that same pool, without synthesizing speech or reusing cancelled audio.
- Repeated triggers share preparation. Session close cancels pending preparation;
  provider close also awaits its cleanup. Tools and business writes are unchanged.

A standalone real-provider check returned first PCM in 1,625 ms after cancellation
without recovery. With transport prepared in advance, two subsequent cancelled-turn
checks returned PCM in 422 / 313 ms using a pooled socket. Background preparation
took 1,125 / 906 ms. This moves connection work into caller/STT/LLM time; it does not
make that work disappear. No worker, telephone call, business tool, or audio file
was created by that provider check.

Implementation verification includes actual installed `AgentSession` native
interruption and successful next speech, repeated cancellation against the real
connection-pool implementation, task cleanup and provider error handling.

Restart the user-managed worker after active calls end to load the correction:

```powershell
cd C:\Users\habiba\Desktop\SDK\sdk-agent
.\.venv\Scripts\python.exe -m worker.main dev
```

If the terminal previously set `UVA_FORCE_BARGE_IN_FLUSH=1`, remove that override
before launching. The worker was not started or stopped during this work. Actual
PSTN interruption recovery, minute-long conversations and caller-heard latency
remain to be verified with the restarted worker.
