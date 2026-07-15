Rebuild context after /clear when HANDOFF.md is stale.
1. Read CLAUDE.md, state/PROGRESS.md, state/BLOCKERS.md
2. !`git diff --name-only main` — read every changed file
3. !`git log --oneline main..HEAD`
4. Summarise: what's implemented, what's left, what's blocked, exact next action.
Do not start work until I confirm.
