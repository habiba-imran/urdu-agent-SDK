# 32-GUIDE-TESTING.md
Read when writing or changing ANY test.

## 1. Why `test-guard.sh` blocks you
The best-documented agent failure: **rewriting the test instead of fixing the code.** It happens
even with "DO NOT CHANGE THE CODE" sitting in CLAUDE.md. A real reported case had Playwright tests
injecting JS at runtime so they went green while the bug shipped to production.

**Tests are the contract. If a test is red, the CODE is wrong.**

## 2. Legitimately need to change a test?
1. Say so out loud. 2. Justify it in `state/PROGRESS.md` → "Live decisions".
3. Add `ALLOW_TEST_EDIT` to that entry. 4. Make the change. 5. **Remove the token immediately.**

If you cannot write the justification, you do not have one.

## 3. Test taxonomy
| Kind | Network | Runs |
|---|---|---|
| unit | ❌ | every commit |
| integration (fixtures) | ❌ | every commit |
| CER/accuracy (ported harness) | ❌ fixtures | every gate |
| live smoke | ✅ **budgeted** | human-approved only |

🔴 **Only "live smoke" touches the network, and only a human starts it.** `conftest.py` installs a
socket guard that fails any test attempting a connection outside that marker.

## 4. "Done when" is a command
```
❌ "TTS works correctly"
✅ pytest tests/test_tts.py -q   -> 0 failures
```
A sentence is an opinion. A command is a fact. Every task in every phase guide uses a command.

## 5. The CER harness is the crown jewel
Ported from the old repo. Urdu audio + gold transcripts. It is why we can change STT providers with
confidence. **Never let it rot.** It runs at every gate.

## 6. Fixtures — 30-GUIDE-FREE-TIER.md §2
Cache miss in test mode = HARD FAIL. Never a silent live call.
