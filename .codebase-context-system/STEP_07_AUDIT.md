# STEP 07 — FINAL AUDIT
CodeContext Generator | Step 7 of 7
Output: codebase-context/AUDIT_REPORT.md

---

## YOUR ROLE FOR THIS STEP

You are the AUDIT AGENT. You trust nothing. You verify everything.
You do not care how long Steps 1–6 took. You do not give credit for effort.
You only care about one thing: is the documentation complete and accurate?

Your output is a binary verdict: 🟢 PASSED or 🔴 FAILED.

---

## TASK 1 — Load Everything

Read ALL of these files before writing a single line of the report:

1. `codebase-context/MANIFEST.json` ← THE GROUND TRUTH
2. `codebase-context/PROGRESS.json`
3. `codebase-context/HOW_TO_USE.md`
4. `codebase-context/00_PROJECT_OVERVIEW.md`
5. `codebase-context/01_FILE_INDEX.md` (and PART2 if it exists)
6. `codebase-context/02_DB_SCHEMA.md`
7. `codebase-context/03_ENV_KEYS.md`
8. `codebase-context/summary-version/MASTER_CONTEXT_SUMMARY.md` (and PART1/PART2 if split)
9. Every `.md` file inside `codebase-context/full-version/`

After reading everything, state:
"All documentation files loaded. Beginning audit of [total_files] manifest entries."

---

## TASK 2 — Create AUDIT_REPORT.md

Create `codebase-context/AUDIT_REPORT.md` with the following structure.
Complete EVERY check. Do not skip any.

---

```markdown
---
session_id: [SESSION_ID from MANIFEST]
generated_at: [ISO timestamp]
step: 7 of 7
manifest_total_files: [X]
manifest_code_files: [Y]
manifest_binary_files: [Z]
---

# CodeContext Audit Report

---

## AUDIT 1 — Session ID Consistency

Check that the same session_id appears in ALL of these files:
- MANIFEST.json
- PROGRESS.json
- 00_PROJECT_OVERVIEW.md
- 01_FILE_INDEX.md
- 02_DB_SCHEMA.md
- 03_ENV_KEYS.md
- MASTER_CONTEXT_SUMMARY.md
- Each full-version layer file

Session ID in MANIFEST: [ID]
Files with matching session_id: [list them]
Files with MISSING or DIFFERENT session_id: [list them]

**Result: ✅ PASS — All files share session ID | ❌ FAIL — [X] files have wrong/missing session ID**

---

## AUDIT 2 — File Coverage: FILE_INDEX

Ground truth: MANIFEST.json has [Y] code files + [Z] binary files = [X] total.

Go through EVERY file_id in MANIFEST.json.
Check if each path appears in 01_FILE_INDEX.md.

Files found in FILE_INDEX: [count]
Files MISSING from FILE_INDEX:
[List every file path in MANIFEST not found in FILE_INDEX]
[If none: "None ✅"]

**Result: ✅ PASS — [Y]/[Y] files indexed | ❌ FAIL — [N] files missing**

---

## AUDIT 3 — File Coverage: FULL VERSION

Go through EVERY non-binary file in MANIFEST.json.
Check if each path appears in any file inside `codebase-context/full-version/`.

Files found in full-version: [count]
Files MISSING from full-version:
[List every non-binary manifest path not found in any layer file]
[If none: "None ✅"]

Verify no file appears in MORE THAN ONE layer file (duplicate check):
Duplicates found: [list any path that appears in 2+ layer files]
[If none: "No duplicates ✅"]

**Result: ✅ PASS — [Y]/[Y] non-binary files documented | ❌ FAIL — [N] files missing or duplicated**

---

## AUDIT 4 — File Coverage: SUMMARY VERSION

### 4A — Critical Files
MANIFEST reports [M] critical files.
Check that each critical file path appears with FULL CODE in Section 7 of MASTER_CONTEXT_SUMMARY.md.
(Test files are exempt from Section 7 — they should be in Section 8.)

Critical files with full code in Section 7: [count]
Critical files MISSING from Section 7:
[List any critical non-test file not found in Section 7]
[If none: "None ✅"]

### 4B — Non-Critical Files
Check that every non-critical, non-binary file has a summary entry in Section 8.

Files with summaries in Section 8: [count]
Files MISSING from Section 8:
[List any non-critical, non-binary file not in Section 8]
[If none: "None ✅"]

**Result: ✅ PASS | ❌ FAIL — [details]**

---

## AUDIT 5 — Code Integrity: Truncation Detection

Scan ALL code blocks (content between triple backticks) in EVERY file inside
`codebase-context/full-version/` AND in `MASTER_CONTEXT_SUMMARY.md`.

Search for EVERY variation of these truncation indicators INSIDE code blocks:
- `// ...`
- `/* ... */`
- `// rest of`
- `// ... rest`
- `// other methods`
- `// similar to`
- `...more`
- `[truncated]`
- `// implementation`
- `// TODO: add`  ← only flag if it appears to be an audit-added comment, not original
- `# ...`
- `# rest of`
- `''' ... '''`

For each instance found:
- File it appears in
- Line number (approximate)
- The exact truncation text found
- Which source file's code was being documented

Truncation instances found: [X]
**Locations:**
[File → approximate location → truncation text]
[If none: "Zero truncations detected ✅"]

**Result: ✅ PASS — Zero truncations | ❌ FAIL — [X] truncations found**

---

## AUDIT 6 — Code Accuracy Spot-Check

Select 5 files at random from MANIFEST.json (avoid binary files, pick a mix of layers).
For each:
1. Open the ACTUAL source file from the project
2. Find the same file's code block in the full-version layer file
3. Compare: are the first 20 lines, last 20 lines, and a middle section identical?

Spot-check results:

| File Path | Layer File | Lines Match | Result |
|-----------|-----------|-------------|--------|
| [path] | [layer] | First/Last/Mid | ✅/❌ |
| [path] | [layer] | First/Last/Mid | ✅/❌ |
| [path] | [layer] | First/Last/Mid | ✅/❌ |
| [path] | [layer] | First/Last/Mid | ✅/❌ |
| [path] | [layer] | First/Last/Mid | ✅/❌ |

**Result: ✅ PASS — All spot-checks match | ❌ FAIL — [X] files have discrepancies**

---

## AUDIT 7 — Database Schema Coverage

Tables documented in 02_DB_SCHEMA.md: [X]
Tables present in MASTER_CONTEXT_SUMMARY.md Section 4: [Y]
Tables MISSING from summary Section 4:
[List any table in DB_SCHEMA not found in summary]
[If none: "DB schema fully replicated in summary ✅"]

Functions documented in DB_SCHEMA: [A]
Functions in summary Section 4: [B]
Missing functions: [list or "None ✅"]

**Result: ✅ PASS — Full DB schema in summary | ❌ FAIL — [details]**

---

## AUDIT 8 — Environment Variables Coverage

Variables documented in 03_ENV_KEYS.md: [X]
Variables present in MASTER_CONTEXT_SUMMARY.md Section 5: [Y]
Variables MISSING from summary Section 5:
[List any variable in ENV_KEYS not in summary]
[If none: "ENV keys fully replicated in summary ✅"]

**Result: ✅ PASS | ❌ FAIL — [details]**

---

## AUDIT 9 — Required Files Exist

Check that every file in this list exists and is non-empty:

| File | Exists | Non-Empty |
|------|--------|-----------|
| codebase-context/MANIFEST.json | ✅/❌ | ✅/❌ |
| codebase-context/PROGRESS.json | ✅/❌ | ✅/❌ |
| codebase-context/HOW_TO_USE.md | ✅/❌ | ✅/❌ |
| codebase-context/AUDIT_REPORT.md | ✅/❌ | ✅/❌ |
| codebase-context/00_PROJECT_OVERVIEW.md | ✅/❌ | ✅/❌ |
| codebase-context/01_FILE_INDEX.md | ✅/❌ | ✅/❌ |
| codebase-context/02_DB_SCHEMA.md | ✅/❌ | ✅/❌ |
| codebase-context/03_ENV_KEYS.md | ✅/❌ | ✅/❌ |
| codebase-context/summary-version/MASTER_CONTEXT_SUMMARY.md | ✅/❌ | ✅/❌ |
| codebase-context/full-version/ (folder, at least 1 file) | ✅/❌ | ✅/❌ |
| .gitignore contains codebase-context/ | ✅/❌ | N/A |
| PROGRESS.json shows all 6 steps "complete" | ✅/❌ | N/A |

**Result: ✅ PASS — All required files present | ❌ FAIL — [list missing files]**

---

## AUDIT 10 — MANIFEST Integrity

Verify MANIFEST.json internal consistency:
- `total_files` = count of entries in `files` array → ✅/❌ (actual: [X])
- `code_files` = count of entries where `is_binary: false` → ✅/❌ (actual: [X])
- `binary_files` = count of entries where `is_binary: true` → ✅/❌ (actual: [X])
- `critical_files_count` = count of entries where `is_critical: true` → ✅/❌ (actual: [X])
- `code_files + binary_files = total_files` → ✅/❌

All entries with `status: "pending"` (should be 0 after all steps):
[List any pending entries or "None ✅"]

**Result: ✅ PASS — MANIFEST is internally consistent | ❌ FAIL — [details]**

---

## AUDIT SCORECARD

| # | Audit Check | Result | Detail |
|---|-------------|--------|--------|
| 1 | Session ID consistency | ✅/❌ | |
| 2 | FILE_INDEX coverage | ✅/❌ | [Y]/[X] files |
| 3 | Full-version coverage | ✅/❌ | [Y]/[X] files |
| 4 | Summary version coverage | ✅/❌ | |
| 5 | Zero code truncations | ✅/❌ | [X] found |
| 6 | Code accuracy spot-check | ✅/❌ | 5/5 match |
| 7 | DB schema in summary | ✅/❌ | |
| 8 | ENV keys in summary | ✅/❌ | |
| 9 | Required files exist | ✅/❌ | |
| 10 | MANIFEST integrity | ✅/❌ | |

Checks passed: [X] / 10
Checks failed: [Y] / 10

---

## REMEDIATION PLAN

[For every ❌ check, write exactly what must be fixed:]

### Issue [N]: [Check name]
**Problem:** [exact description of what is wrong]
**Files affected:** [list]
**Fix:** Re-run [Step X kickoff prompt] from ORCHESTRATOR.md.
**Specifically:** [exact instruction for what the agent must fix]

[If no issues:]
"No remediation needed. All 10 checks passed."

---

## FINAL VERDICT

[Count failed checks]
```

---

After writing AUDIT_REPORT.md, deliver the final verdict in chat:

**If all 10 checks ✅:**

```
🟢 AUDIT PASSED — DOCUMENTATION COMPLETE
═══════════════════════════════════════
Session ID:              [SESSION_ID]
All checks passed:       10 / 10
Zero truncations:        ✅
All files documented:    ✅

Documentation stats:
  Total files:           [X]
  Critical files (code): [N]
  Summarized files:      [M]
  DB tables:             [T]
  ENV variables:         [E]
  Layer files:           [L]

Your codebase-context/ documentation is complete and ready to use.
See codebase-context/HOW_TO_USE.md for instructions on using it with Claude.
```

**If ANY check ❌:**

```
🔴 AUDIT FAILED — [N] ISSUES FOUND
═══════════════════════════════════════
Session ID:          [SESSION_ID]
Checks passed:       [X] / 10
Checks failed:       [Y] / 10

Failed checks: [list them]

See codebase-context/AUDIT_REPORT.md → REMEDIATION PLAN for exact fix instructions.
Run the indicated step kickoff prompt(s) to fix the issues, then re-run Step 7.
```

---

## TASK 3 — Update PROGRESS.json

Update `codebase-context/PROGRESS.json`:
- `steps.07_AUDIT.status` → `"complete"`
- `steps.07_AUDIT.completed_at` → current timestamp
- `steps.07_AUDIT.verdict` → `"PASSED"` or `"FAILED"`
- `steps.07_AUDIT.issues_found` → count of failed checks

---

## ⛔ AUDIT AGENT RULES

1. You are an auditor. You do not fix problems — you report them.
2. A check is ✅ ONLY when it is 100% correct. 98% is not a pass.
3. Do not skip any check because "the previous steps looked careful."
4. Do not award partial credit. Each check is binary: pass or fail.
5. If you cannot determine the result of a check (e.g., cannot open a file), mark it ❌ with the reason.
6. The spot-check in Audit 6 requires reading actual source files from the project — do it.
7. Your verdict in the AUDIT_REPORT.md must match your verdict in chat.
