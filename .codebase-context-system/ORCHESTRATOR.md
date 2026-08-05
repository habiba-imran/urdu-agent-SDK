# CodeContext Generator — Orchestrator
Version: 1.0.0
Purpose: Generate complete, LLM-ready codebase documentation in two formats.

---

## What This System Produces

```
codebase-context/
├── HOW_TO_USE.md                         ← Read this before pasting into Claude
├── MANIFEST.json                          ← Ground truth file index
├── PROGRESS.json                          ← Step completion tracker
├── AUDIT_REPORT.md                        ← Final audit results
├── 00_PROJECT_OVERVIEW.md                 ← Architecture, tech stack, data flow
├── 01_FILE_INDEX.md                       ← Every file: purpose, exports, dependencies
├── 02_DB_SCHEMA.md                        ← Full database documentation
├── 03_ENV_KEYS.md                         ← All env keys (no real values)
├── summary-version/
│   └── MASTER_CONTEXT_SUMMARY.md          ← Paste THIS into Claude every time
└── full-version/
    ├── 01_PAGES_VIEWS.md
    ├── 02_COMPONENTS_UI.md
    └── ...                                ← Full code by layer, paste when Claude asks
```

---

## KICKOFF PROMPTS — Copy & Paste These Into Cursor Agent

Run each step in order. Wait for the ✅ confirmation before moving to the next.

---

### ▶ STEP 1 of 7 — SCAN & MANIFEST

```
You are a codebase documentation agent executing Step 1 of 7.
Read the COMPLETE contents of the file `.codebase-context-system/STEP_01_SCAN.md` before doing anything else.
Once you have fully read it, execute every task inside it in order.
Do not skip any task. Do not begin execution until you have read the entire file.
```

---

### ▶ STEP 2 of 7 — FILE INDEX

```
You are a codebase documentation agent executing Step 2 of 7.
Read the COMPLETE contents of the file `.codebase-context-system/STEP_02_INDEX.md` before doing anything else.
Once you have fully read it, execute every task inside it in order.
Do not skip any task. Do not begin execution until you have read the entire file.
```

---

### ▶ STEP 3 of 7 — DATABASE SCHEMA

```
You are a codebase documentation agent executing Step 3 of 7.
Read the COMPLETE contents of the file `.codebase-context-system/STEP_03_DATABASE.md` before doing anything else.
Once you have fully read it, execute every task inside it in order.
Do not skip any task. Do not begin execution until you have read the entire file.
Note: You may need to pause and ask the user for their database schema depending on the DB type detected.
```

---

### ▶ STEP 4 of 7 — ENVIRONMENT VARIABLES

```
You are a codebase documentation agent executing Step 4 of 7.
Read the COMPLETE contents of the file `.codebase-context-system/STEP_04_ENV.md` before doing anything else.
Once you have fully read it, execute every task inside it in order.
Do not skip any task. Do not begin execution until you have read the entire file.
```

---

### ▶ STEP 5 of 7 — MASTER CONTEXT SUMMARY

```
You are a codebase documentation agent executing Step 5 of 7.
Read the COMPLETE contents of the file `.codebase-context-system/STEP_05_SUMMARY.md` before doing anything else.
Once you have fully read it, execute every task inside it in order.
Do not skip any task. Do not begin execution until you have read the entire file.
```

---

### ▶ STEP 6 of 7 — FULL VERSION

```
You are a codebase documentation agent executing Step 6 of 7.
Read the COMPLETE contents of the file `.codebase-context-system/STEP_06_FULL.md` before doing anything else.
Once you have fully read it, execute every task inside it in order.
Do not skip any task. Do not begin execution until you have read the entire file.
```

---

### ▶ STEP 7 of 7 — AUDIT

```
You are a codebase documentation agent executing Step 7 of 7 — the final audit.
Read the COMPLETE contents of the file `.codebase-context-system/STEP_07_AUDIT.md` before doing anything else.
Once you have fully read it, execute every task inside it in order.
Do not skip any task. Do not begin execution until you have read the entire file.
```

---

## If a Step Fails or Stops Mid-Way

1. Open `codebase-context/PROGRESS.json` — check which tasks within the step completed
2. Open the step's output file — find where it stopped
3. Paste the same kickoff prompt again into a new Cursor Agent session
4. The step file contains resume instructions for exactly this situation

---

## How to Use the Output With Claude

After all 7 steps complete and audit passes (🟢):

1. Open a new Claude conversation
2. Paste `codebase-context/HOW_TO_USE.md` — this tells Claude how to work with the docs
3. Paste `codebase-context/summary-version/MASTER_CONTEXT_SUMMARY.md`
4. Describe the feature you want to build
5. When Claude asks to see a specific file's code, find it in `codebase-context/full-version/` and paste the relevant section

---

## When to Re-run

- Before starting any significant new feature → run all 7 steps fresh
- Minor codebase changes → re-run Steps 5, 6, and 7 only
- DB schema changed → re-run Steps 3, 5, and 7
- New env variables added → re-run Steps 4, 5, and 7

---

## Important Notes

- `codebase-context/` is gitignored (auto-added by Step 1) — never commit it
- `.codebase-context-system/` should be committed — it's your instruction set
- This system is universal — it works for any language, framework, or project size
- Average run time: 15–30 minutes depending on codebase size
