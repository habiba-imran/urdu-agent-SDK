# STEP 06 — FULL VERSION DOCUMENTATION
CodeContext Generator | Step 6 of 7
Output: codebase-context/full-version/[##_LAYER_NAME].md

---

## TASK 1 — Prerequisite Check

1. Read `codebase-context/PROGRESS.json`
2. Verify Steps 1–5 are all `"complete"`
3. Read `codebase-context/MANIFEST.json` — this is your checklist
4. Note the `session_id` and `total_files` / `code_files`

If any prerequisite is missing, stop:
"⛔ STEP 6 CANNOT START: Steps 1–5 must all be complete."

State: "Prerequisites verified. Manifest loaded. I have [code_files] code files and [binary_files] binary files to place into layers."

---

## TASK 2 — Layer Definitions

Every non-binary file must be assigned to EXACTLY ONE of these layers.

| Layer File | Contains |
|------------|----------|
| `01_PAGES_VIEWS.md` | Page-level components, screen files, route-level views |
| `02_COMPONENTS_UI.md` | Reusable UI components, shared visual elements |
| `03_HOOKS_COMPOSABLES.md` | Custom React hooks, Vue composables, reactive utilities (files starting with `use`) |
| `04_API_ROUTES.md` | API endpoint handlers, server actions, route handlers, controllers |
| `05_SERVICES_LOGIC.md` | Business logic, data services, external API clients, query functions |
| `06_MIDDLEWARE_GUARDS.md` | Auth middleware, route guards, validators, interceptors |
| `07_UTILS_HELPERS.md` | Pure utility functions, formatters, constants, date helpers |
| `08_TYPES_INTERFACES.md` | TypeScript type files, interface definitions, Zod schemas, enums |
| `09_CONFIG_SETUP.md` | App config files, provider wrappers, initializers, root setup |
| `10_DATABASE_ORM.md` | DB client files, ORM models, migrations, query builders, seeds |

### Layer Assignment Priority Rules
When a file could belong to multiple layers, apply these rules IN ORDER and assign to the FIRST match:

1. If it's a database model, migration, or DB client → `10_DATABASE_ORM`
2. If it's middleware or auth guard → `06_MIDDLEWARE_GUARDS`
3. If it's a TypeScript type-only file (only exports types/interfaces) → `08_TYPES_INTERFACES`
4. If it's a page/screen/route-level component with a URL path → `01_PAGES_VIEWS`
5. If it's a custom hook (`use*.ts`) → `03_HOOKS_COMPOSABLES`
6. If it's an API route handler → `04_API_ROUTES`
7. If it exports a reusable UI component → `02_COMPONENTS_UI`
8. If it contains business logic or calls external APIs → `05_SERVICES_LOGIC`
9. If it only has pure utility/helper functions → `07_UTILS_HELPERS`
10. If it's a config, provider, or initializer file → `09_CONFIG_SETUP`

If a file still doesn't fit after all 10 rules, assign it to the closest layer and add:
`**Layer Override:** Assigned here because [reason] — closest match is [layer]`

### Assignment for Special File Types
- `.env` files → `09_CONFIG_SETUP` (list without values)
- `README.md`, docs → `09_CONFIG_SETUP`
- Test files (`*.test.*`, `*.spec.*`) → assign to the SAME layer as the file they test
- Style files (`.css`, `.scss`, `.module.css`) → `02_COMPONENTS_UI` if component-specific, `09_CONFIG_SETUP` if global

---

## TASK 3 — Pre-Assignment Pass

Before creating any files, go through EVERY code file in MANIFEST.json and decide its layer.

Create a mental (or written) table:
```
file_id | path | assigned_layer
   1    | app/page.tsx | 01_PAGES_VIEWS
   2    | components/Button.tsx | 02_COMPONENTS_UI
   ...
```

State the assignment summary:
"Layer assignments complete:
- 01_PAGES_VIEWS: [X] files
- 02_COMPONENTS_UI: [X] files
- [... all layers]
- Total assigned: [X] / [total code files]
- Any unassigned: [list them or 'None']"

---

## TASK 4 — Create Each Layer File

For EACH non-empty layer, create the corresponding file in `codebase-context/full-version/`.

**SKIP empty layers** — do not create a file if no files are assigned to it.

### Layer File Structure:

```markdown
---
session_id: [SESSION_ID]
generated_at: [ISO timestamp]
step: 6 of 7
layer: [##_LAYER_NAME]
files_in_layer: [X]
---

# [Layer Name] — Full Code
Layer: [##_LAYER_NAME].md

[Brief 1-sentence description of what kind of files are in this layer]

---

[For EVERY file assigned to this layer:]

## `path/to/file.ext`
**Layer:** [layer name]
**Purpose:** [1–2 sentences — what this file does]
**Key Exports:** [all exported names]
**Depends On (internal):** [internal files it imports]
**Used By:** [internal files that import it]
**Complexity:** Low | Medium | High | Critical
**Is Critical:** Yes | No
[If large file:] **⚠️ Large File:** [X] lines

```[correct language for this file]
[COMPLETE SOURCE CODE — EVERY SINGLE LINE]
[No exceptions. No shortcuts. No truncation of any kind.]
[If this file is 1000 lines, paste all 1000 lines.]
[Do not add, remove, or modify any code from the original.]
[Copy it character-for-character.]
```

**Notes:** [Important observations — architectural decisions, gotchas, 
            key functions, patterns, or anything relevant to understand this file]

---

[Repeat for every file in this layer]

## Layer Summary
- Files in this layer: [X]
- Critical files: [Y]
- Total lines of code: [approximate]
```

---

## TASK 5 — Mandatory Layer Completion Markers

After FINISHING each complete layer file, write this in the chat:

```
✅ Layer [##_LAYER_NAME].md complete — [X] files documented
```

Only write this AFTER the layer file is fully written and saved.
If you stop writing a layer mid-way, do NOT write this marker.

---

## TASK 6 — Resume Instructions

If you stop mid-execution (context limit, timeout, or any other reason), the user will
re-paste the Step 6 kickoff prompt. When that happens:

1. Re-read this instruction file
2. Read `codebase-context/PROGRESS.json` — it will say Step 6 is pending
3. Check which layer files already exist in `codebase-context/full-version/`
4. State: "Resuming Step 6. Layers already created: [list]. Remaining layers: [list]. Continuing from [next layer]."
5. Continue from the first incomplete layer — do NOT redo layers that are already complete
6. After ALL layers are complete, proceed to Task 7

---

## TASK 7 — Cross-Check Report

After ALL layer files are created, write this report IN THE CHAT:

```
## Step 6 Cross-Check Report

| Layer File | Files Documented |
|------------|-----------------|
| 01_PAGES_VIEWS.md | [X] |
| 02_COMPONENTS_UI.md | [X] |
| 03_HOOKS_COMPOSABLES.md | [X] |
| 04_API_ROUTES.md | [X] |
| 05_SERVICES_LOGIC.md | [X] |
| 06_MIDDLEWARE_GUARDS.md | [X] |
| 07_UTILS_HELPERS.md | [X] |
| 08_TYPES_INTERFACES.md | [X] |
| 09_CONFIG_SETUP.md | [X] |
| 10_DATABASE_ORM.md | [X] |
| **TOTAL** | **[SUM]** |

Files in MANIFEST (code_files): [X]
Files documented in Full Version: [SUM]
Difference: [X - SUM — should be 0]

Unaccounted files (if any):
[List any manifest file_id that does not appear in any layer file]
[If none: All manifest files accounted for ✅]

Binary files: [X] — Listed in manifest only (no code block needed by design)
```

---

## TASK 8 — Update PROGRESS.json

Update `codebase-context/PROGRESS.json`:
- `steps.06_FULL.status` → `"complete"`
- `steps.06_FULL.completed_at` → current timestamp
- `steps.06_FULL.layers_created` → count of layer files created
- `steps.06_FULL.files_documented` → total files documented across all layers

Also update MANIFEST.json for every file processed:
- `"documented_in_full_version": true`
- `"status": "complete"`

---

## TASK 9 — Completion Confirmation

Reply with EXACTLY this format:

```
✅ STEP 6 COMPLETE — FULL VERSION DOCUMENTATION
═══════════════════════════════════════
Session ID:              [SESSION_ID]
Layer files created:     [N] (out of 10 possible)
Total files documented:  [Y]
Manifest code files:     [X]
All files accounted for: YES ✅ | NO ❌ — [list missing]

Layer breakdown:
  01_PAGES_VIEWS:       [X] files
  02_COMPONENTS_UI:     [X] files
  03_HOOKS:             [X] files
  04_API_ROUTES:        [X] files
  05_SERVICES:          [X] files
  06_MIDDLEWARE:        [X] files
  07_UTILS:             [X] files
  08_TYPES:             [X] files
  09_CONFIG:            [X] files
  10_DATABASE:          [X] files

Files created:
  [List every layer .md file created with ✅]

➡️  Paste the STEP 7 kickoff prompt from ORCHESTRATOR.md to continue.
```

---

## ⛔ ABSOLUTE NON-NEGOTIABLE RULES

1. **ZERO TRUNCATION.** Not one line of code may be omitted. Ever. Not for "simple" files.
   Not for files "similar to another". Not for large files.
   If a file has 2000 lines, all 2000 lines appear in the layer file.

2. **COPY EXACTLY.** Do not paraphrase code. Do not simplify. Do not "clean up" variable names.
   Copy every character of the original source exactly — including comments, blank lines,
   and formatting.

3. **ONE FILE, ONE ENTRY.** Never combine two files into one entry. Never reference one file's
   code as "same pattern as the file above."

4. **NEVER ADD CODE.** Do not add your own comments to the source code. Do not wrap it.
   Paste the original and only the original inside the code block.

5. **NEVER SKIP.** Binary files don't need code blocks but still need listing entries.
   Every file in the manifest must appear in a layer file.

6. **LAYER COMPLETION MARKERS ARE MANDATORY.** If you have not written
   "✅ Layer XX complete" for a layer, it means you have not finished that layer.
