# 63-GUIDE-WORKER-DEPLOYMENT-DEFERRAL.md — why the worker gets no Dockerfile yet

P9. Explicit scope note, not an oversight: `docker/control-plane.Dockerfile` and
`docker/admin.Dockerfile` exist; `worker/` does not get one in this pass. Per direct instruction,
worker deployment is deferred to Phase 12. This doc records why, so a future reader doesn't
wonder whether it was forgotten.

## Why the worker is structurally different from control_plane/admin

`control_plane/app.py` and `admin/app.py` are both request-triggered FastAPI services: they sit
idle, wake up to handle one HTTP request, and go back to idle. That shape fits almost any modern
hosting model, including scale-to-zero / request-triggered free tiers (Cloud Run, Vercel
Functions, etc.) — a container that only runs (and only costs anything) while actively serving a
request.

`worker/main.py` is not that shape at all. Confirmed by reading the actual entrypoint
(`worker/main.py`'s `__main__` block, `cli.run_app(WorkerOptions(...))`): it's a **long-running
LiveKit Agents worker process** that:
- registers itself with LiveKit Cloud ONCE at startup (`"registered worker"` in the log) and
  stays connected, waiting for job dispatches — not triggered by an inbound HTTP request at all.
- runs `prewarm()` at true process startup (ADR-007) to get provider plugins registered on the
  real main thread BEFORE any job thread/process exists — a process-lifecycle assumption that
  breaks if the process is torn down and cold-started per request.
- holds live, in-process state for the DURATION of a voice call (the `AgentSession`, STT/LLM/TTS
  connections, `_session_started_at` for usage-ledger accounting) — a voice call can run for
  minutes; a request-triggered/scale-to-zero host would kill the process mid-call.

**A persistent-process host is a real, different infrastructure requirement** — something like a
long-running container/VM/managed-compute service that keeps one process alive continuously, not
a request-triggered function platform. That's a different deployment shape from
`control_plane`/`admin`, needs its own hosting decision (and likely its own ADR — cost, scaling
model, how LiveKit Cloud's own worker-registration/job-dispatch model interacts with the chosen
host), and is explicitly not decided or built here.

## What this means right now

The worker keeps running exactly as it has all along: locally, via `python -m worker.main dev`
(or `start`), started by a human, per every gate/live-listen session so far in this build. No
Dockerfile, no container config, no hosting decision for it in this pass — building one now
would be guessing at a hosting model nobody has chosen yet.

## What Phase 12 will need to actually decide, when it starts

Not answered here, flagged so it isn't rediscovered from scratch:
- Which persistent-process host (a VM, a long-running container service, a dedicated compute
  tier) — cost and operational model differ a lot between options.
- How prewarm/plugin-registration (ADR-007's Windows-specific fix, and the more portable
  `PROCESS`-executor path for non-Windows) behaves on whatever host is chosen — the ADR-007
  account is Windows-dev-specific; a Linux container host uses the `PROCESS` executor path by
  default, which the code already supports (`prewarm_fnc` stays wired for exactly this reason)
  but has never been run/verified on this project's own infrastructure.
- Scaling model for concurrent calls — one worker process handles N concurrent job dispatches
  (per ADR-014's findings, LiveKit's own room-join cap was never reproduced up to n=6-plus); at
  real production volume, whether one worker instance is enough or multiple need to run behind
  LiveKit's own dispatch is a capacity question, not a Phase 9 one.
- All the `UPLIFT_MODE`/`STT_PROVIDER`/provider-key env vars the worker actually needs (already
  catalogued in `docs/61-GUIDE-DEV-TO-PROD.md` §1-2) — those docs list WHAT changes; Phase 12
  decides WHERE the running process that reads them actually lives.
