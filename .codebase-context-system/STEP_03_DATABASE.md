# STEP 03 — DATABASE SCHEMA
CodeContext Generator | Step 3 of 7
Output: 02_DB_SCHEMA.md

---

## TASK 1 — Prerequisite Check

1. Read `codebase-context/PROGRESS.json`
2. Verify `steps.01_SCAN.status` and `steps.02_INDEX.status` are both `"complete"`
3. Note the `session_id`

If either prerequisite is missing, stop and respond:
"⛔ STEP 3 CANNOT START: Steps 1 and 2 must be complete first. Check PROGRESS.json."

---

## TASK 2 — Detect Database Type

Search the project for the following indicators IN THIS ORDER. Stop at the first match.

### Detection Rules:

**1. Prisma ORM**
- Look for: `prisma/schema.prisma`
- Confirm: `@prisma/client` in package.json dependencies
- Action: Go to TASK 3A

**2. Drizzle ORM**
- Look for: `drizzle.config.ts` or `drizzle.config.js`
- Look for: files containing `import { pgTable` or `import { mysqlTable` or `import { sqliteTable`
- Confirm: `drizzle-orm` in package.json dependencies
- Action: Go to TASK 3B

**3. Supabase (Direct SQL / no ORM)**
- Look for: `@supabase/supabase-js` in package.json
- Look for: `createClient` from `@supabase/supabase-js` in any file
- Look for: `supabase/` folder at project root
- Action: Go to TASK 3C

**4. SQLAlchemy (Python)**
- Look for: `sqlalchemy` in requirements.txt or pyproject.toml
- Look for: files with `from sqlalchemy` imports and class definitions inheriting `Base`
- Action: Go to TASK 3D

**5. Django ORM**
- Look for: `django` in requirements.txt
- Look for: `models.py` files with classes inheriting `models.Model`
- Action: Go to TASK 3E

**6. Mongoose (MongoDB)**
- Look for: `mongoose` in package.json
- Look for: files with `mongoose.Schema` or `new Schema(`
- Action: Go to TASK 3F

**7. Firebase Firestore**
- Look for: `firebase` or `firebase-admin` in package.json
- Look for: `getFirestore` or `collection(` calls in files
- Action: Go to TASK 3G

**8. Raw SQL Migrations**
- Look for: `migrations/` or `db/migrations/` folder with `.sql` files
- Look for: `schema.sql` or `database.sql` at root or in `db/` folder
- Action: Go to TASK 3H

**9. No Database Detected**
- None of the above found
- Action: Go to TASK 3I

State your finding:
"Database type detected: [TYPE]. Proceeding to TASK 3[letter]."

If you find MULTIPLE database systems (e.g., Prisma + Firebase), document ALL of them.
Create a section in the output for each.

---

## TASK 3A — Prisma Schema

Read `prisma/schema.prisma` completely.

Also check for any additional Prisma files:
- `prisma/seed.ts` or `prisma/seed.js`
- Any files in `prisma/migrations/`

Proceed to TASK 4 with this data.

---

## TASK 3B — Drizzle ORM Schema

Find all schema definition files. They typically are named:
- `db/schema.ts` / `src/db/schema.ts`
- `lib/db/schema.ts`
- Any file containing `pgTable(` or `mysqlTable(` or `sqliteTable(`

Read all of them completely.

Also read `drizzle.config.ts` for connection and database type info.

Proceed to TASK 4 with this data.

---

## TASK 3C — Supabase (SQL Schema Required)

You need the actual SQL schema from the user.

State the following to the user and WAIT for their response before continuing:

```
⚠️ SUPABASE DETECTED — I need your database schema.

Please do ONE of the following:

Option A (Recommended): Go to your Supabase dashboard → SQL Editor → New query → paste and run this SQL, then copy the entire output and paste it here:

SELECT 
  'CREATE TABLE ' || tablename AS table_info,
  schemaname
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY tablename;

Option B: If you have a schema.sql or supabase/migrations/ folder, paste the contents here.

Option C: Go to Supabase → Table Editor → for each table, click the table name, then click "Definition" and paste those SQL statements here.

I will wait for you to paste the schema before proceeding.
```

Once the user pastes schema SQL, proceed to TASK 4 with that data.

---

## TASK 3D — SQLAlchemy Models

Find all model files. Look for:
- `models/` directory with Python files
- Files containing `class [Name](Base):`
- Files with `Column(`, `relationship(`, `ForeignKey(` patterns

Read all model files completely.

Also look for Alembic migration files in `alembic/versions/` for migration history.

Proceed to TASK 4 with this data.

---

## TASK 3E — Django Models

Find all `models.py` files across all Django apps.

Read each one completely. Note the app each model belongs to.

Also check for `migrations/` folders for migration history.

Proceed to TASK 4 with this data.

---

## TASK 3F — Mongoose Schemas

Find all files containing `mongoose.Schema` or `new Schema(`.
These are typically in `models/` or `src/models/`.

Read all model files completely.

Proceed to TASK 4 with this data.

---

## TASK 3G — Firebase Firestore

Firebase doesn't have a schema file — document it from usage patterns.

Search the codebase for:
- `collection(db, '[name]')` → identify collection names
- `.add(`, `.set(`, `.doc(` → understand document structure
- Any TypeScript interfaces/types that correspond to Firestore documents

Also read any `firestore.rules` file if present.

Proceed to TASK 4 with the collection names and inferred structures.

---

## TASK 3H — Raw SQL Migrations

Read all `.sql` files in `migrations/`, `db/migrations/`, or root-level schema files.

Read them in chronological order if numbered (001_, 002_, etc.).

Build a complete picture of the final schema state.

Proceed to TASK 4 with this data.

---

## TASK 3I — No Database

Document as:
```markdown
## Database
No database detected in this project.

The project does not appear to use a database. It may use:
- Local storage / browser APIs
- External APIs only (no local data persistence)
- File system storage

[Document any data persistence patterns found in the codebase]
```

Write this to `codebase-context/02_DB_SCHEMA.md` and skip to TASK 5.

---

## TASK 4 — Generate 02_DB_SCHEMA.md

Create `codebase-context/02_DB_SCHEMA.md` using this structure.
Adapt the terminology to the database type detected (tables/collections/models/etc.).

```markdown
---
session_id: [SESSION_ID]
generated_at: [ISO timestamp]
step: 3 of 7
db_type: [Prisma / Drizzle / Supabase PostgreSQL / SQLAlchemy / Django / Mongoose / Firebase / Raw SQL]
total_tables: [X]
---

# Database Schema Documentation

## Overview
[What does this database store? What are the main entities?
How many tables/collections? What is the overall data model?]

## Entity Relationship Map (ASCII)
[Show ALL tables and their relationships in one diagram.
Use this format:]

users ─────────< posts          (one user has many posts)
posts ─────────< comments       (one post has many comments)
users ─────────< comments       (one user has many comments)
posts >─────────  categories    (many posts belong to one category)

[Every foreign key relationship must appear here.]
[If using MongoDB/Firebase, show document nesting and references instead.]

---

## Tables / Collections / Models

[For EVERY table, document using the appropriate format below:]

---

### [Table/Collection/Model Name]

**Purpose:** [What real-world concept does this represent?
             What data does it store? How is it used in the app?]

**Row Level Security:** Enabled | Disabled | N/A (non-Postgres)

#### Columns / Fields

| Column/Field | Type | Required | Default | Description |
|-------------|------|----------|---------|-------------|
[Every single column — do not skip any]

**Primary Key:** [column name(s)]

**Foreign Keys:**
- `[column]` → `[referenced_table].[referenced_column]`
  Plain English: [What relationship does this represent?
                 e.g., "Each post belongs to one user"]

**Indexes:**
[List all non-primary indexes with their purpose]

**Unique Constraints:**
[List all unique constraints]

**Check Constraints:**
[List all CHECK constraints with their conditions]

**RLS Policies:** (Supabase / PostgreSQL only)
[If none: "No RLS policies defined"]
[For each policy:]
- **Policy:** `[policy_name]`
  - Command: SELECT | INSERT | UPDATE | DELETE | ALL
  - Role: authenticated | anon | [specific role]
  - Rule: [What does this policy allow or deny? In plain English.]

**Timestamps:**
[Does this table have created_at / updated_at? Are they auto-managed?]

---

[Repeat for every table]

---

## Database Functions

[For every database function / stored procedure:]

### Function: `[function_name]`
- **Returns:** [return type]
- **Parameters:** [list parameters with types]
- **Purpose:** [what does this function do? why does it exist?]
- **Called by:** [which application code calls this, if known]

[If none: "No custom database functions defined."]

## Triggers

### Trigger: `[trigger_name]`
- **Table:** [which table]
- **Event:** BEFORE | AFTER — INSERT | UPDATE | DELETE
- **Executes:** [function name]
- **Purpose:** [what does this trigger do in plain English?]

[If none: "No triggers defined."]

## Custom Types & Enums

### Enum / Type: `[name]`
- **Values:** [list all values]
- **Used in:** [which columns reference this type]

[If none: "No custom types or enums defined."]

## Database Migrations
[If migrations folder exists:]
- Total migrations: [X]
- Date range: [earliest] to [latest]
- Major schema changes: [brief summary of significant migrations]

## Application ↔ Database Mapping
[For each table, note where in the codebase it is queried/mutated:]

| Table | Read in | Written in | Notes |
|-------|---------|-----------|-------|
[Fill this from your knowledge of the codebase from Steps 1-2]

```

---

## TASK 5 — Update PROGRESS.json

Update `codebase-context/PROGRESS.json`:
- `steps.03_DATABASE.status` → `"complete"`
- `steps.03_DATABASE.completed_at` → current timestamp
- `steps.03_DATABASE.db_type` → detected database type
- `steps.03_DATABASE.tables_documented` → count of tables/collections documented

---

## TASK 6 — Completion Confirmation

Reply with EXACTLY this format:

```
✅ STEP 3 COMPLETE — DATABASE SCHEMA
═══════════════════════════════════════
Session ID:          [SESSION_ID]
DB type detected:    [TYPE]
Tables documented:   [X]
Functions:           [Y]
Triggers:            [Z]
Custom types/enums:  [N]
RLS policies:        [M]

Files created:
  ✅ codebase-context/02_DB_SCHEMA.md

➡️  Paste the STEP 4 kickoff prompt from ORCHESTRATOR.md to continue.
```

---

## ⛔ ANTI-SHORTCUT RULES

1. NEVER skip a column — every column in every table must be documented
2. NEVER write "standard columns" or "usual fields" — list them explicitly
3. NEVER skip RLS policies — they are critical for understanding data security
4. NEVER assume foreign key relationships — only document ones explicitly defined
5. NEVER combine multiple tables into one entry
6. If the user's SQL has tables you don't understand, document them anyway and note they need clarification
