# STEP 02 — COMPLETE FILE INDEX
CodeContext Generator | Step 2 of 7
Output: 01_FILE_INDEX.md + MANIFEST.json status updates

---

## TASK 1 — Prerequisite Check

Before doing anything, verify Step 1 is complete:

1. Read `codebase-context/PROGRESS.json`
2. Check that `steps.01_SCAN.status` equals `"complete"`
3. Read `codebase-context/MANIFEST.json`
4. Note the `session_id` — you will include it in your output file

If Step 1 is NOT complete, stop immediately and respond:
"⛔ STEP 2 CANNOT START: Step 1 is not complete. Please run Step 1 first using the kickoff prompt in ORCHESTRATOR.md."

If Step 1 IS complete, state:
"✅ Prerequisite check passed. Session ID: [SESSION_ID]. Manifest loaded. I will document [total_files] files ([code_files] code, [binary_files] binary)."

---

## TASK 2 — Re-read Critical Files Criteria

The CRITICAL FILE definition from Step 1 is:

A file is CRITICAL if it meets ANY ONE of these:
1. Imported/required by 5 or more other files in the project
2. Defines the application entry point
3. Initializes or exports the database client/connection
4. Contains authentication logic
5. Defines global state, context providers, or the primary store
6. Defines the primary routing configuration
7. Root-level configuration file affecting the entire build
8. Defines shared TypeScript types/interfaces used across 5+ files

You must apply this SAME definition. Do not invent new criteria.

---

## TASK 3 — Handle Large Codebases

Count the `code_files` value from MANIFEST.json.

**If code_files > 150:**
Split the FILE_INDEX into two files:
- `codebase-context/01_FILE_INDEX_PART1.md` (first 150 files)
- `codebase-context/01_FILE_INDEX_PART2.md` (remaining files)

Both files must follow the same format. The Summary section must appear in PART2.

State: "⚠️ Large codebase detected ([X] code files). Splitting FILE_INDEX into 2 parts."

**If code_files ≤ 150:** Create a single `codebase-context/01_FILE_INDEX.md`

---

## TASK 4 — Document Every File

Work through EVERY file in MANIFEST.json in order of their `id`.

For EACH file, do the following:
1. Open and read the actual file content — do not rely on filename alone
2. Search the codebase for every other file that imports/requires it
3. Write its entry using the format below
4. Update that file's entry in MANIFEST.json: set `"documented_in_index": true` and `"status": "indexed"`

**You must update MANIFEST.json after each file or batch of 10 files.**

---

### Entry Format — CODE / CONFIG / STYLE / MARKUP / TEST / DOC / ENV files:

```
---
### [ID]. `path/to/file.ext`
- **Category:** component | page | hook | service | util | config | api-route |
                middleware | type | schema | test | style | layout | store |
                context | lib | migration | seed | other
- **Is Critical:** Yes — [which criterion] | No
- **Purpose:** [2–3 sentences. What does this file actually do? Be specific — mention
               function names, what data it handles, what UI it renders.]
- **Key Exports:** [Every function, class, component, constant, type exported.
                   List them — do not write "various functions".]
- **Core Logic Summary:** [3–5 sentences describing the most important logic.
                          What decisions does it make? What algorithms?
                          What external calls does it make?]
- **Imports From (internal):** [List every internal project file this file imports.
                               Use relative paths from project root.]
- **Imported By:** [Search results — list every file in the codebase that imports this file.
                   If none: "Not imported by any other file"
                   If you cannot determine: "Could not determine — search manually"]
- **Complexity:** Low | Medium | High | Critical
- **Lines of Code:** [approximate]
- **Notes:** [Anything unusual, important patterns, potential gotchas, or
              architectural decisions visible in this file]
```

### Entry Format — BINARY files:

```
---
### [ID]. `path/to/file.ext`
- **Category:** binary
- **Type:** image | font | media | archive | executable | database | other
- **Is Critical:** No
- **Purpose:** Static asset — [brief description of what it is]
- **Notes:** —
```

---

## TASK 5 — Mandatory Progress Markers

After completing every 10 files, write this line in your output:

```
═══ PROGRESS: [X] / [TOTAL] files documented ═══
```

This is NOT optional. You must write it after files 10, 20, 30, 40... etc.
If you skip a progress marker, you have skipped files.

---

## TASK 6 — Handle Files You Cannot Read

If you cannot read a file for any reason (permissions, encoding, etc.):

```
### [ID]. `path/to/file.ext`
- **Category:** [best guess from extension]
- **Is Critical:** [from MANIFEST]
- **Status:** ⚠️ UNREADABLE — [exact error or reason]
- **Purpose:** Could not determine — file could not be read
```

Do NOT skip it. It must still appear in the index with its ID. Set its MANIFEST status to `"unreadable"`.

---

## TASK 7 — Handle Very Large Files

If a file exceeds 500 lines of code:

Add this line after the file entry:
`⚠️ LARGE FILE: [X] lines — Full code will appear in full-version documentation`

Still document all fields as normal. Do not truncate the purpose, exports, or logic summary.

---

## TASK 8 — File Index Summary

After the LAST file entry, write this Summary section:

```markdown
---
## File Index Summary
Session ID: [SESSION_ID]

| Metric | Count |
|--------|-------|
| Total files in manifest | [X] |
| Code files documented | [Y] |
| Binary files listed | [Z] |
| Unreadable files | [N] — [list their paths] |
| Critical files identified | [M] |
| Very large files (500+ lines) | [K] — [list their paths] |
| Files where "Imported By" could not be determined | [J] — [list their paths] |

### Critical Files Summary
[List every critical file with path and reason it's critical]

### Files Not Imported By Any Other File (Orphans)
[List any non-entry-point files with no importers — may indicate dead code]
```

---

## TASK 9 — Update PROGRESS.json

Update `codebase-context/PROGRESS.json`:
Set `steps.02_INDEX.status` to `"complete"`
Set `steps.02_INDEX.completed_at` to current timestamp
Set `steps.02_INDEX.files_documented` to the count of successfully documented files

---

## TASK 10 — Completion Confirmation

Reply with EXACTLY this format:

```
✅ STEP 2 COMPLETE — FILE INDEX
═══════════════════════════════════════
Session ID:                [SESSION_ID]
Files documented:          [Y] / [X total]
Critical files:            [M]
Binary files:              [Z]
Unreadable files:          [N]
Very large files (500+):   [K]
Orphaned files:            [J]
Index file(s) created:     01_FILE_INDEX.md [/ 01_FILE_INDEX_PART2.md if split]
MANIFEST.json updated:     ✅

Files created:
  ✅ codebase-context/01_FILE_INDEX.md [or PART1 + PART2]

➡️  Paste the STEP 3 kickoff prompt from ORCHESTRATOR.md to continue.
```

---

## ⛔ ANTI-SHORTCUT RULES — NON-NEGOTIABLE

1. NEVER write "similar to the file above" — every file gets its own full entry
2. NEVER skip a file because it seems simple or obvious
3. NEVER invent exports or logic you haven't confirmed by reading the file
4. NEVER write "various utilities" or "helper functions" — name them specifically
5. NEVER write a single entry covering multiple files
6. Progress markers are mandatory — their absence proves you skipped files
7. If you feel the task is taking too long — continue anyway. Completeness is the only goal.
8. The file count in the Summary MUST match the MANIFEST code_files + binary_files count
