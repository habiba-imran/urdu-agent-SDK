# STEP 05 — MASTER CONTEXT SUMMARY
CodeContext Generator | Step 5 of 7
Outputs: summary-version/MASTER_CONTEXT_SUMMARY.md + HOW_TO_USE.md

---

## TASK 1 — Prerequisite Check

1. Read `codebase-context/PROGRESS.json`
2. Verify ALL of these are `"complete"`:
   - `steps.01_SCAN.status`
   - `steps.02_INDEX.status`
   - `steps.03_DATABASE.status`
   - `steps.04_ENV.status`
3. Note the `session_id`

If any prerequisite is missing, stop:
"⛔ STEP 5 CANNOT START: Steps 1–4 must all be complete. Check PROGRESS.json."

---

## TASK 2 — Load All Source Files

Read ALL of these files completely before writing anything:

1. `codebase-context/MANIFEST.json`
2. `codebase-context/00_PROJECT_OVERVIEW.md`
3. `codebase-context/01_FILE_INDEX.md` (and PART2 if it exists)
4. `codebase-context/02_DB_SCHEMA.md`
5. `codebase-context/03_ENV_KEYS.md`

Then, for EVERY file marked `"is_critical": true` in MANIFEST.json:
- Open the actual source file from the project
- Read it completely
- You will paste the FULL CODE in the summary

State: "All source files loaded. Critical files to include with full code: [list their paths]"

---

## TASK 3 — Test File Policy

Test files (category: `test`, or files matching `*.test.ts`, `*.spec.ts`, `*.test.js`,
`__tests__/`, `spec/`) are handled as follows in the SUMMARY VERSION:
- Do NOT include full code in Section 7 (even if marked critical)
- DO include a summary entry in Section 8
- Note in their summary entry: "Full test code available in full-version documentation"

This keeps the summary focused on implementation, not tests.

---

## TASK 4 — Estimate Token Count

Before writing the summary, estimate its token count:
- Each character ≈ 0.25 tokens
- Count: total characters in all source files marked critical + all summaries you'll write

**If estimated token count > 140,000 tokens:**
- Split into TWO files:
  - `codebase-context/summary-version/MASTER_CONTEXT_SUMMARY_PART1.md`
    → Contains: Sections 1, 2, 3, 4 (DB Schema), 5 (ENV)
  - `codebase-context/summary-version/MASTER_CONTEXT_SUMMARY_PART2.md`
    → Contains: Sections 6 (Folder), 7 (Critical files), 8 (All summaries), 9 (Patterns)
  - Add a header to each part noting it's part of a 2-part document
  - Update HOW_TO_USE.md instructions accordingly

State: "Estimated token count: ~[X]. [Single file | Splitting into 2 parts]."

**If ≤ 140,000 tokens:** Create a single `MASTER_CONTEXT_SUMMARY.md`

---

## TASK 5 — Generate MASTER_CONTEXT_SUMMARY.md

Create the file(s) determined in Task 4.

Use this EXACT structure:

---

```markdown
---
session_id: [SESSION_ID]
generated_at: [ISO timestamp]
step: 5 of 7
document_type: SUMMARY VERSION
critical_files_with_full_code: [X]
files_summarized: [Y]
estimated_tokens: [Z]
part: 1 of 1 | 1 of 2 | 2 of 2
---

# [Project Name] — Master Context for LLM

> **How to use this document:**
> Paste this entire file when starting a new conversation in Claude or another LLM.
> Tell the LLM what feature you want to build.
> When the LLM asks to see a specific file's full code, find it in `codebase-context/full-version/`.
> The LLM should ask for any files it needs — do not hesitate to paste them.

---

## Section 1 — What This App Is

[One strong, specific paragraph. What does this app do? Who uses it?
What problem does it solve? What is its current state?
Be concrete — mention actual features, not vague descriptions.]

---

## Section 2 — Complete Tech Stack

[Every technology confirmed in the codebase. One line each.
Format: **[Name]** vX.X — [specific role in THIS project]]

---

## Section 3 — Architecture & Data Flow

[Comprehensive explanation of how the entire app works:
- Frontend: how views/pages are structured and rendered
- Routing: how navigation works
- API: how server-side requests are handled
- Auth: exactly where and how authentication happens
- Data fetching: how the frontend gets data from the backend
- State: where and how application state is managed
- External services: how third-party integrations work

Include an ASCII data flow diagram specific to this project:]

User performs action
        │
        ▼
[Specific Component] ──→ [Specific Hook/State] ──→ [Specific API Route]
                                                           │
                                                           ▼
                                                   [Service Layer]
                                                           │
                                                           ▼
                                                    [Database/Supabase]
                                                           │
                        ◄──────────────────────────────────
                  [Data flows back to component and renders]

---

## Section 4 — Database Schema (COMPLETE)

[Copy the COMPLETE content of 02_DB_SCHEMA.md here.
Do NOT summarize. Do NOT shorten. Do NOT skip any table, column, or policy.
The LLM needs this complete to reason correctly about any feature touching the DB.]

[Paste full 02_DB_SCHEMA.md content here]

---

## Section 5 — Environment & External Services

[Copy the COMPLETE content of 03_ENV_KEYS.md here.
All variables. All service maps. All issues.]

[Paste full 03_ENV_KEYS.md content here]

---

## Section 6 — Complete Folder Structure

[Copy the complete folder tree from 00_PROJECT_OVERVIEW.md.
Every file and folder — no collapsing.]

---

## Section 7 — Critical Files — Full Source Code

[For EVERY file with "is_critical": true in MANIFEST.json (excluding test files):]

---
### `path/to/critical-file.tsx`
**Why Critical:** [which criterion — e.g., "Imported by 9 files, defines app entry point"]
**Purpose:** [one clear sentence]

```[language]
[PASTE THE COMPLETE, UNTRUNCATED SOURCE CODE OF THE FILE]
[Every single line must be here]
[Do NOT write // ... or // rest of code or anything similar]
[If the file is 800 lines, all 800 lines appear here]
[Do not add comments that weren't in the original file]
```
---

[Repeat for every critical non-test file]

---

## Section 8 — All Other Files — Detailed Summaries

[For EVERY file in MANIFEST.json that is:
 - NOT binary (is_binary: false)
 - NOT already in Section 7 (not critical OR is a test file)
 
 Each file gets its OWN entry. No grouping. No skipping.]

---
### `path/to/file.ext`
- **Purpose:** [What this file does — 2–3 specific sentences. Name actual functions and data.]
- **Key Exports:** [Every export — be specific, name them]
- **Core Logic:** [4–6 sentences about the most important logic in this file.
                  What decisions does it make? What data does it transform?
                  What does it call? Be specific — mention function/variable names.]
- **Depends On (internal):** [project files this imports]
- **Used By:** [project files that import this]
- **Test Files:** [if test files exist for this file, list them]

[For test files:]
### `path/to/file.test.ts`
- **Tests:** `path/to/file.ts`
- **Test cases covered:** [list what is being tested]
- **Full code:** Available in `codebase-context/full-version/` layer file
---

[After ALL file summaries, write:]

## File Count Verification
- Critical files with full code (Section 7): [X]
- Summarized files (Section 8, non-test): [Y]
- Test files summarized (Section 8): [T]
- Binary files (not documented, by design): [Z]
- Total accounted for: [X + Y + T] should equal MANIFEST code_files + binary files are excluded

---

## Section 9 — Coding Patterns & Conventions

[Document every consistent pattern observed in this codebase.
These help the LLM write code that matches the existing style:]

- **File naming:** [how are different file types named?]
- **Import style:** [absolute paths? path aliases? @/components? relative?]
- **Component patterns:** [functional components? class? hooks pattern?]
- **API call pattern:** [how does the app call APIs — fetch, axios, SDK?]
- **Error handling:** [try/catch? error boundaries? toast notifications?]
- **Data validation:** [Zod? Yup? manual? where does validation happen?]
- **Styling approach:** [Tailwind? CSS Modules? styled-components?]
- **Type safety:** [strict TypeScript? JSDoc? no types?]
- **Auth checks:** [where and how are protected routes implemented?]
- **State mutations:** [how is data updated after mutations?]
- **Code organization conventions:** [any other patterns the LLM should follow]

---

## Section 10 — Feature Integration Checklist

[A reusable checklist for the LLM to use when planning ANY new feature in this codebase.
Customize this to the actual project patterns:]

When building a new feature, the LLM should ask about:
- [ ] Which database tables does this feature need? New or existing?
- [ ] Which existing components can be reused?
- [ ] Where do new API routes go?
- [ ] What RLS policies need to be added/modified?
- [ ] What new env variables are needed (if any)?
- [ ] Where does authentication need to be checked?
- [ ] What TypeScript types need to be created?
- [ ] What validation is needed?
- [ ] What are the loading and error states?
- [ ] What files need to be modified vs created from scratch?
```

---

## TASK 6 — Generate HOW_TO_USE.md

Create `codebase-context/HOW_TO_USE.md`:

```markdown
# How to Use This Documentation With Claude

Generated: [timestamp]
Session ID: [SESSION_ID]
Project: [project name]

---

## Quick Start

1. Open a new Claude conversation
2. Paste the contents of `MASTER_CONTEXT_SUMMARY.md` (below)
   [If split: paste PART1 first, then say "Part 2 follows:" and paste PART2]
3. Say: "I want to build [your feature]. Based on this codebase context, give me a complete 
   integration plan including: files to create, files to modify, DB changes needed, 
   and implementation steps."
4. When Claude asks for specific files, find them in `full-version/` and paste them

---

## File Map — What to Paste When

| What Claude needs | Where to find it |
|------------------|-----------------|
| Full project context | `summary-version/MASTER_CONTEXT_SUMMARY.md` |
| Full code for a specific file | `full-version/` — find the right layer file |
| Complete DB schema | `02_DB_SCHEMA.md` (also inside summary) |
| A specific component's code | `full-version/02_COMPONENTS_UI.md` |
| An API route's code | `full-version/04_API_ROUTES.md` |
| A service file's code | `full-version/05_SERVICES_LOGIC.md` |
| Types and interfaces | `full-version/08_TYPES_INTERFACES.md` |
| Auth logic | `full-version/06_MIDDLEWARE_GUARDS.md` |

---

## Recommended Opening Message for Claude

Copy and adapt this:

---
"I am sharing the complete context of my codebase below. Please read it carefully before 
responding. After reading it, I want to build [FEATURE NAME]. 

Please:
1. Confirm you understand the current architecture
2. Identify which existing files will be affected
3. List any DB schema changes needed
4. Give me a step-by-step implementation plan
5. Ask me for any specific file's code you need to see in full

[PASTE MASTER_CONTEXT_SUMMARY.md HERE]"
---

## Tips

- Always paste the summary at the START of a conversation, not mid-way
- If Claude seems confused about the architecture, paste `00_PROJECT_OVERVIEW.md` too
- For DB-heavy features, explicitly tell Claude to reference Section 4 of the summary
- After Claude gives a plan, ask: "Are there any files you need to see in full before 
  finalizing the plan?" — then paste from full-version/
- Regenerate this documentation before starting work on any new major feature

---

## Files in This Documentation Run

Session ID: [SESSION_ID]
Generated: [timestamp]

| File | Purpose |
|------|---------|
| `MANIFEST.json` | Ground truth list of every file in the project |
| `PROGRESS.json` | Step completion tracking |
| `00_PROJECT_OVERVIEW.md` | Architecture and tech stack |
| `01_FILE_INDEX.md` | Every file with purpose and dependencies |
| `02_DB_SCHEMA.md` | Complete database documentation |
| `03_ENV_KEYS.md` | All environment variables |
| `AUDIT_REPORT.md` | Documentation quality audit results |
| `summary-version/MASTER_CONTEXT_SUMMARY.md` | Paste this into Claude |
| `full-version/*.md` | Full code by layer — paste sections when Claude asks |
```

---

## TASK 7 — Update PROGRESS.json

Update `codebase-context/PROGRESS.json`:
- `steps.05_SUMMARY.status` → `"complete"`
- `steps.05_SUMMARY.completed_at` → current timestamp
- `steps.05_SUMMARY.token_estimate` → estimated token count
- `steps.05_SUMMARY.split` → true | false

---

## TASK 8 — Completion Confirmation

Reply with EXACTLY this format:

```
✅ STEP 5 COMPLETE — MASTER CONTEXT SUMMARY
═══════════════════════════════════════
Session ID:                  [SESSION_ID]
Critical files (full code):  [X]
Files summarized:            [Y]
Test files summarized:       [T]
Binary files excluded:       [Z]
Total accounted for:         [X+Y+T]
Estimated token count:       ~[N]
Split into 2 parts:          Yes / No

Files created:
  ✅ codebase-context/HOW_TO_USE.md
  ✅ codebase-context/summary-version/MASTER_CONTEXT_SUMMARY.md [or PART1 + PART2]

➡️  Paste the STEP 6 kickoff prompt from ORCHESTRATOR.md to continue.
```

---

## ⛔ ANTI-SHORTCUT RULES

1. Section 4 (DB Schema) must be COMPLETE — copy the entire 02_DB_SCHEMA.md, every line
2. Section 5 (ENV) must be COMPLETE — copy the entire 03_ENV_KEYS.md, every line
3. Critical files in Section 7: ZERO truncation — paste every line of the actual source file
4. Section 8 must have an entry for EVERY non-critical non-binary file
5. NEVER write "// ..." or "// rest of implementation" inside any code block
6. NEVER combine multiple files into one summary entry
7. NEVER write "similar to the pattern above" — each file's summary stands alone
8. Test files go in Section 8 with a summary, NEVER in Section 7 with full code
