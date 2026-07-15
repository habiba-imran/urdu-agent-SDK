# 42-RESEARCH-QUEUE.md — questions the agent cannot answer alone

## How this works
1. Agent hits strike 3 → writes `state/BLOCKERS.md`
2. Agent appends the question here, **STATUS: OPEN**, and **STOPS**
3. Human takes it to Claude chat for research
4. Human pastes the answer here, **STATUS: ANSWERED**, and appends an ADR if it's a decision
5. Agent resumes

## Template
```
### RQ-nnn | STATUS: OPEN | blocks P<n>-T<nn>
**Question:** one sentence
**Why blocked:** what was tried (link BLOCK-nnn)
**What a good answer looks like:** a signature / a flag / a doc URL / a yes-no
--- ANSWER ---
(human pastes; cite source)
```

## Open
_(none yet)_

## Known-unknowns already queued
```
### RQ-001 | STATUS: OPEN | blocks P8
**Question:** Uplift concurrent TTS stream limit?
**Why:** If it's below LiveKit's cap, IT is our real ceiling, not LiveKit. Whole capacity
model depends on this. Sent as H9 #1.

### RQ-002 | STATUS: OPEN | blocks P5
**Question:** Licence to use Uplift character artwork commercially? Sent as H9 #5.

### RQ-003 | STATUS: OPEN | blocks P3 (soft)
**Question:** Does livekit-plugins-upliftai resample Uplift's 22.05kHz PCM to 48k, or must we?
**Why:** old repo D3/D5 documented 22.05kHz Socket.IO. Plugin behaviour UNVERIFIED BY US.
**Good answer:** plugin source line, or a working config.
```
