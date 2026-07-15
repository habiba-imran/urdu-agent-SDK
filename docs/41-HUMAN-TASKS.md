# 41-HUMAN-TASKS.md — only you can do these

## Blocking Phase 0
| # | Task | Done |
|---|---|---|
| H1 | Supabase: create **two** projects `uva-dev`, `uva-prod`. Agent touches dev ONLY. | ☐ |
| H2 | LiveKit Cloud → **Build (free)**. Save `LIVEKIT_URL/API_KEY/API_SECRET`. | ☐ |
| H3 | Uplift → free. Save `UPLIFT_API_KEY`. ⚠️ **10 minutes total — read 30-GUIDE-FREE-TIER.md** | ☐ |
| H4 | Gladia → free. Save `GLADIA_API_KEY`. | ☐ |
| H5 | Google AI Studio → free Gemini key. | ☐ |
| H6 | All keys → `.env.local`. Confirm `.env*` in `.gitignore` **before first commit**. | ☐ |
| H7 | `node -v` works (ponytail hooks need it; nvm/Nix must resolve in non-login shells). | ☐ |
| H8 | `git init`, first commit, **private** repo. | ☐ |

## H9 — EMAIL UPLIFT TODAY. Blocks Phase 8. Answer #1 can invalidate the capacity model.
> 1. What is the **concurrency limit** — simultaneous TTS streams per account?
> 2. What triggers a **429**? What is the rate limit?
> 3. What happens at **minute 1,501** on Pro — hard stop, 429, or auto-upgrade?
> 4. What is the **Enterprise rate above 200h/month**? (No published price exists above Growth.)
> 5. May we use your **character artwork** in a commercial voice picker? (Blocks P5.)

Same question 1+2 to **Gladia**. (Soniox advertises "hundreds of thousands of concurrent streams" — not a concern.)

## Per-phase human gates — the agent CANNOT self-approve these
| Phase | You personally do this |
|---|---|
| 0 | Confirm Gate 0 output. Say "begin Phase 1". |
| 1 | **Read every RLS policy by hand.** The one thing you verify personally. |
| 2 | Attempt to widen a minted token yourself. It must fail. |
| 3 | Listen to a real Urdu call. Is it good? Only a human can answer. |
| 4 | Inspect `dist/` yourself for secrets. |
| 5 | Confirm H9 #5 licence answer before shipping any Uplift artwork. |
| 7 | Attempt one cross-tenant read + one token-widening attack. Both must fail. |
| 8 | Merge to main. **The agent never merges.** |
| all | Approve every `UPLIFT_MODE=record` session. Agent never records unattended. |
