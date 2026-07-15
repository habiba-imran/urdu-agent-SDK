# PHASE 5 — VOICE PICKER
**Goal:** browse every Uplift voice with artwork + instant preview. **Zero live TTS.**
⚠️ **BLOCKED on H9 #5** (artwork licence). Build with placeholders; do not ship art until answered.

## The rule
🔴 **Never proxy live TTS for previews.** That is a free-TTS farm — an attacker loops the picker
and bills you. Pre-render ONCE → CDN → signed URLs.

## Tasks
P5-T01 seed `voices` from Uplift's catalogue (~60+ voices: Street Vendor, Nosey Aunty, Helpdesk Agent, Prime Time Anchor…)
P5-T02 pre-render ONE line per voice, `UPLIFT_MODE=record`, **human-approved, ~4 min of the 10-min budget** (30-GUIDE §3)
P5-T03 upload to CDN, signed URLs, long cache
P5-T04 picker UI: artwork, name, gender, play
P5-T05 `agents.voice_id` FK validated against `voices.enabled`

## GATE 5
```
[ ] all voices render
[ ] preview plays
[ ] 🔴 network log during full browse -> ZERO calls to Uplift
[ ] signed URLs expire
[ ] H9 #5 answered + recorded in ADR before art ships   <- HUMAN GATE
```
