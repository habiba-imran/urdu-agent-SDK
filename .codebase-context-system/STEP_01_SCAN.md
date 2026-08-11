# STEP 01 — SCAN & MANIFEST
CodeContext Generator | Step 1 of 7
Outputs: MANIFEST.json, PROGRESS.json, 00_PROJECT_OVERVIEW.md, .gitignore update

---

## YOUR ROLE
You are a codebase documentation agent. Your output will be used by Claude and other LLMs
to understand this codebase without having direct access to it. Completeness and accuracy
are your only priorities. Speed is irrelevant.

---

## TASK 1 — Generate Session ID

Before anything else, generate a SESSION_ID using this format:
`CCGEN-[YYYYMMDD]-[HHMM]`
Example: `CCGEN-20250601-1430`

State it out loud:
"Session ID for this run: CCGEN-XXXXXXXX-XXXX"

You will use this SESSION_ID in EVERY file you create during this run. This links all
output files to the same generation run.

---

## TASK 2 — Create Output Folder Structure

Create these folders if they do not already exist:
```
codebase-context/
codebase-context/summary-version/
codebase-context/full-version/
```

---

## TASK 3 — Detect Project Type

Scan the project root. Read whichever of these files exists to determine the tech stack:

| File | Indicates |
|------|-----------|
| package.json | Node.js / JavaScript / TypeScript project |
| requirements.txt / pyproject.toml / Pipfile | Python project |
| Cargo.toml | Rust project |
| go.mod | Go project |
| pubspec.yaml | Flutter / Dart project |
| composer.json | PHP project |
| Gemfile | Ruby project |
| pom.xml / build.gradle / build.gradle.kts | Java / Kotlin project |
| *.csproj / *.sln | .NET / C# project |

Read the identified file(s) and note:
- Primary language
- Runtime version (if specified)
- All frameworks and libraries

### Monorepo Detection
Look for any of these signs of a monorepo:
- `packages/` folder containing multiple sub-folders with their own package.json
- `apps/` folder containing multiple sub-applications
- `workspaces` key in root package.json
- `turbo.json` at root (Turborepo)
- `nx.json` at root (Nx)
- `lerna.json` at root (Lerna)
- Multiple `package.json` files at depth 2

If monorepo detected, state:
"⚠️ MONOREPO DETECTED. Workspaces found: [list every sub-app/package path]"

Document the monorepo as ONE project — ALL files from ALL workspaces go into the single
MANIFEST. Do not skip sub-apps.

---

## TASK 4 — Define Critical Files Criteria

A file is CRITICAL if it meets ANY ONE of these criteria. This definition is the SINGLE
SOURCE OF TRUTH and will be referenced by all subsequent steps.

**CRITICAL FILE CRITERIA (in order of priority):**
1. Imported/required by 5 or more other files in the project
2. Defines the application entry point (layout.tsx, App.tsx, main.py, server.js, index.ts at root, etc.)
3. Initializes or exports the database client/connection
4. Contains authentication logic (sign-in, session management, JWT handling)
5. Defines global state, context providers, or the primary store
6. Defines the primary routing configuration
7. Root-level configuration file that affects the entire build (next.config.js, vite.config.ts, tailwind.config.ts, tsconfig.json, webpack.config.js, etc.)
8. Defines shared TypeScript types or interfaces used across 5+ files

Save this criteria to memory — you will use it in Tasks 5 and every subsequent step.

---

## TASK 5 — Build Exclusion Lists

### Directories — NEVER recurse into these:
```
node_modules/
.git/
.next/
dist/
build/
.nuxt/
__pycache__/
.cache/
.parcel-cache/
coverage/
.turbo/
.vercel/
.netlify/
out/
storybook-static/
.expo/
.svelte-kit/
.output/
tmp/
temp/
vendor/
codebase-context/        ← NEVER document yourself
.codebase-context-system/ ← NEVER document yourself
```

### Files — EXCLUDE ENTIRELY (do not add to manifest):
```
package-lock.json
yarn.lock
pnpm-lock.yaml
bun.lockb
Cargo.lock
poetry.lock
Pipfile.lock
composer.lock
Gemfile.lock
*.min.js
*.min.css
*.map
*.chunk.js
*.bundle.js
*.generated.ts
*.generated.js
```

### File Extensions — Mark as BINARY (add to manifest but do not read content):
```
Images:     .png .jpg .jpeg .gif .svg .ico .webp .avif .bmp .tiff .raw
Fonts:      .woff .woff2 .ttf .otf .eot
Media:      .mp4 .mp3 .wav .avi .mov .webm .ogg .flac
Archives:   .zip .tar .gz .rar .7z .tar.gz .tgz
Executables: .exe .dll .so .dylib .bin .app
DB files:   .db .sqlite .sqlite3
Other:      .pdf .psd .ai .sketch .fig
```

---

## TASK 6 — Generate MANIFEST.json

Scan the ENTIRE project directory recursively, applying the exclusion lists from Task 5.

**Before writing the file, count ALL files and state:**
"I found [X] total files to document ([Y] code files, [Z] binary files). [N] lock/generated files excluded."

Then check import counts for each file (grep/search for import statements referencing each file path) to apply the Critical Files Criteria from Task 4.

For every critical file found, note it explicitly:
"Marking as CRITICAL: [path] — Reason: [which criterion it meets]"

Write `codebase-context/MANIFEST.json`:

```json
{
  "session_id": "[SESSION_ID from Task 1]",
  "generated_at": "[ISO 8601 timestamp]",
  "project_type": "[e.g. Next.js 14 TypeScript / Python FastAPI / etc.]",
  "is_monorepo": false,
  "monorepo_workspaces": [],
  "total_files": 0,
  "code_files": 0,
  "binary_files": 0,
  "critical_files_count": 0,
  "excluded_dirs": ["node_modules", ".git", "..."],
  "excluded_files": ["package-lock.json", "yarn.lock", "..."],
  "files": [
    {
      "id": 1,
      "path": "relative/path/to/file.ext",
      "extension": ".tsx",
      "category": "code",
      "is_binary": false,
      "is_critical": true,
      "critical_reason": "Imported by 8 other files + defines app entry point",
      "import_count": 8,
      "status": "pending",
      "documented_in_index": false,
      "documented_in_full_version": false,
      "documented_in_summary": false
    }
  ]
}
```

**Category values:** `code` | `config` | `style` | `markup` | `test` | `env` | `doc` | `binary` | `other`

**Rules:**
- Every file gets exactly one entry — no grouping
- Binary files: `"is_binary": true`, all boolean fields false
- `status` starts as `"pending"` for all files — subsequent steps update this
- If you cannot determine import count for a file, set `"import_count": null`

---

## TASK 7 — Generate 00_PROJECT_OVERVIEW.md

Create `codebase-context/00_PROJECT_OVERVIEW.md`:

```markdown
---
session_id: [SESSION_ID]
generated_at: [ISO timestamp]
step: 1 of 7
total_files: [must match MANIFEST total_files]
code_files: [must match MANIFEST code_files]
binary_files: [must match MANIFEST binary_files]
critical_files: [must match MANIFEST critical_files_count]
---

# Project Overview

## Detected Project Type
[Be specific. Example: "Next.js 14 full-stack application using App Router, TypeScript,
Supabase PostgreSQL backend, Tailwind CSS, and Stripe for payments"]

## Monorepo
[Yes — Workspaces: [list paths] | No — Single application]

## Complete Tech Stack
[Read all package manager files. List EVERY dependency with its role in THIS project.
Format each as:]
- **[package-name]** vX.X.X — [What it does specifically in this project]

[Do not list packages you haven't confirmed exist in the package files]

## Complete Folder Structure
[Output a full recursive directory tree. Include every folder and file.
Do NOT collapse any section. Do NOT write "and X more files" or "...".
Every single item must appear. Binary files included.]

## Architecture Overview
Answer each of these specifically for THIS codebase:
- **Overall pattern:** [MVC / component-based / microservices / monolithic / etc.]
- **Frontend structure:** [how pages/views are organized and rendered]
- **Routing:** [how routing is handled — file-based, config-based, etc.]
- **Backend/API:** [how the server-side works — API routes, controllers, etc.]
- **Authentication:** [where and how auth is implemented]
- **Data fetching:** [how the frontend gets data — REST, GraphQL, server components, etc.]
- **State management:** [global state approach — Context, Zustand, Redux, none, etc.]
- **External services:** [list every third-party service integrated]

## Data Flow Diagram
[ASCII diagram specific to THIS project showing the actual flow:]

User Action
    │
    ▼
[Component Name] ──→ [Hook/State] ──→ [API Route/Action]
                                              │
                                              ▼
                                       [Service/DB Call]
                                              │
                                              ▼
                                       [Supabase/DB]
                                              │
                          ◄────────────────────
                      [Response back to component]

## Critical Files
[List every file marked is_critical: true in MANIFEST, with:]
- `path/to/file` — [why it's critical] — imported by [N] files

## Key Patterns & Conventions Observed
- Naming conventions: [camelCase / kebab-case / PascalCase — where each is used]
- File naming: [pattern for components, pages, utils, etc.]
- Import style: [absolute paths / relative / path aliases like @/]
- Error handling: [try/catch patterns, error boundaries, etc.]
- Any other repeating patterns
```

---

## TASK 8 — Update .gitignore

Search for `.gitignore` in the project root.

If it exists: Check if `codebase-context/` is already listed. If not, append:
```
# CodeContext — auto-generated LLM documentation (do not commit)
codebase-context/
```

If it doesn't exist: Create `.gitignore` at the project root with that content.

Do NOT add `.codebase-context-system/` to gitignore — that folder should be version-controlled.

State the result: "`.gitignore` updated ✅" or "`.gitignore` already contained codebase-context/ ✅"

---

## TASK 9 — Create PROGRESS.json

Create `codebase-context/PROGRESS.json`:

```json
{
  "session_id": "[SESSION_ID]",
  "last_updated": "[ISO timestamp]",
  "steps": {
    "01_SCAN": {
      "status": "complete",
      "completed_at": "[ISO timestamp]",
      "total_files": 0,
      "critical_files": 0,
      "notes": ""
    },
    "02_INDEX": { "status": "pending", "completed_at": null, "files_documented": 0 },
    "03_DATABASE": { "status": "pending", "completed_at": null, "db_type": null, "tables_documented": 0 },
    "04_ENV": { "status": "pending", "completed_at": null, "variables_documented": 0 },
    "05_SUMMARY": { "status": "pending", "completed_at": null, "token_estimate": null, "split": false },
    "06_FULL": { "status": "pending", "completed_at": null, "layers_created": 0, "files_documented": 0 },
    "07_AUDIT": { "status": "pending", "completed_at": null, "verdict": null, "issues_found": 0 }
  }
}
```

Fill in the `01_SCAN` values with the actual counts from this run.

---

## TASK 10 — Completion Confirmation

After all tasks above are complete, reply with EXACTLY this format:

```
✅ STEP 1 COMPLETE — SCAN & MANIFEST
═══════════════════════════════════════
Session ID:          [SESSION_ID]
Total files found:   [X]
Code files:          [Y]
Binary files:        [Z]
Lock/gen excluded:   [N]
Critical files:      [M]
Monorepo detected:   Yes / No
.gitignore:          Updated / Already set / Created new

Files created:
  ✅ codebase-context/MANIFEST.json
  ✅ codebase-context/PROGRESS.json
  ✅ codebase-context/00_PROJECT_OVERVIEW.md
  ✅ .gitignore (updated/created)

➡️  Paste the STEP 2 kickoff prompt from ORCHESTRATOR.md to continue.
```

---

## ⛔ ANTI-SHORTCUT RULES — NON-NEGOTIABLE

1. NEVER write "and similar files" or group files into one manifest entry
2. NEVER assume what a file does — if you haven't read it, do not describe it
3. NEVER skip a directory because it "probably" only has generated files — check first
4. If you cannot access a folder, list it in the manifest as inaccessible with the reason — do not silently skip it
5. The MANIFEST `total_files` count must match the number of entries in the `files` array exactly
6. If you stop mid-scan for any reason, do not create a partial MANIFEST — complete it first
