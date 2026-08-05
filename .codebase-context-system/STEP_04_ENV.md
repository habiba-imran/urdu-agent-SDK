# STEP 04 — ENVIRONMENT VARIABLES
CodeContext Generator | Step 4 of 7
Output: 03_ENV_KEYS.md

---

## TASK 1 — Prerequisite Check

1. Read `codebase-context/PROGRESS.json`
2. Verify `steps.01_SCAN.status`, `steps.02_INDEX.status`, and `steps.03_DATABASE.status` are all `"complete"`
3. Note the `session_id`

If any prerequisite is missing, stop:
"⛔ STEP 4 CANNOT START: Steps 1, 2, and 3 must be complete first."

---

## TASK 2 — Collect All Environment Variable Sources

### Source A — .env Files
Search for and read ALL of these files if they exist (do not skip any):
- `.env`
- `.env.local`
- `.env.development`
- `.env.development.local`
- `.env.production`
- `.env.production.local`
- `.env.staging`
- `.env.test`
- `.env.example`
- `.env.template`
- `.env.sample`

For each file found, list every key. Note which file each key appeared in.

### Source B — Code References
Search the ENTIRE codebase for every environment variable reference pattern:

For JavaScript / TypeScript projects:
- `process.env.`
- `import.meta.env.`
- `Deno.env.get(`

For Python projects:
- `os.environ[`
- `os.environ.get(`
- `os.getenv(`
- `settings.` (if using Django settings or pydantic-settings)

For other languages, adapt the search pattern accordingly.

For each reference found, extract the variable name and note which file references it.

### Deduplication
Merge sources A and B into a single list. Each unique variable name appears once.

State: "Found [X] unique environment variables across all sources."

---

## TASK 3 — Classify Each Variable

For every variable found, determine:

**Service/Category** — use the most specific match:
- `Supabase` — SUPABASE_URL, SUPABASE_KEY, etc.
- `Database` — DATABASE_URL, POSTGRES_*, REDIS_*, MONGODB_URI, etc.
- `Authentication` — NEXTAUTH_*, JWT_*, SESSION_*, CLERK_*, AUTH0_*, etc.
- `OpenAI / AI` — OPENAI_API_KEY, ANTHROPIC_*, REPLICATE_*, etc.
- `Stripe / Payments` — STRIPE_*, LEMON_SQUEEZY_*, PADDLE_*, etc.
- `Email` — RESEND_*, SENDGRID_*, MAILGUN_*, SMTP_*, etc.
- `Storage` — AWS_S3_*, CLOUDFLARE_*, UPLOADTHING_*, etc.
- `Analytics` — POSTHOG_*, MIXPANEL_*, SEGMENT_*, GA_*, etc.
- `Monitoring` — SENTRY_*, DATADOG_*, LOGTAIL_*, etc.
- `App Config` — NEXT_PUBLIC_APP_*, NODE_ENV, PORT, BASE_URL, etc.
- `Third Party API` — any other external service
- `Internal` — app-specific secrets not tied to a known service

**Required Level:**
- `Required — always` — app crashes or core feature breaks without it
- `Required — production only` — only needed in production environment
- `Optional` — app degrades gracefully without it
- `Development only` — only used locally
- `Unknown` — cannot determine from codebase inspection

**Value Format** (describe the format, NEVER the actual value):
- Examples: `UUID format`, `URL starting with https://`, `JWT secret string (any random string)`,
  `API key starting with sk-`, `Boolean: true | false`, `Integer port number`,
  `Base64-encoded string`, `Hex string`, `JSON string`

---

## TASK 4 — Generate 03_ENV_KEYS.md

Create `codebase-context/03_ENV_KEYS.md`:

```markdown
---
session_id: [SESSION_ID]
generated_at: [ISO timestamp]
step: 4 of 7
total_variables: [X]
---

# Environment Variables Documentation

⚠️ SECURITY NOTE: This document contains ONLY variable names and their purposes.
No real values are ever included. This file is safe to share and review.

---

## All Variables

[For EVERY variable, in alphabetical order by service category:]

---

### `VARIABLE_NAME`
- **Service / Category:** [from classification above]
- **Purpose:** [What does this variable enable? What breaks without it?
               Be specific — name the exact feature or service.]
- **Value Format:** [format description — NEVER the real value]
- **Required:** [Required — always | Required — production only | Optional | Dev only | Unknown]
- **Used In Files:**
  - `path/to/file1.ts` — [how it's used here]
  - `path/to/file2.ts` — [how it's used here]
- **Declared In:** `.env.local` | `.env.example` | [which file] | Not declared (code-only reference)
- **Exposed to Client:** Yes (NEXT_PUBLIC_ prefix) | No (server-only)

---

[Repeat for every variable]

---

## Summary Table

| Variable | Service | Required | Client-Exposed | Declared |
|----------|---------|----------|---------------|----------|
[one row per variable]

---

## ⚠️ Issues Found

### Undeclared Variables (in code but not in any .env file)
[Variables referenced in code that don't appear in any .env / .env.example file]

| Variable | Referenced In | Risk |
|----------|--------------|------|

[If none: "None — all referenced variables are declared ✅"]

### Unused Variables (declared in .env but not referenced in code)
[Variables in .env files that are never referenced in any code file]

| Variable | Declared In | Note |
|----------|------------|------|

[If none: "None — all declared variables are used ✅"]

### Client-Exposed Variables Review
[List any variables that are exposed to the client (NEXT_PUBLIC_ or equivalent).
For each, note whether this is intentional or a potential security concern.]

[If none: "No variables are exposed to the client ✅"]

---

## Service Map
[Group all variables by the external service they belong to:]

### [Service Name]
Variables: `VAR_1`, `VAR_2`, `VAR_3`
Purpose: [What does this service do in the app?]
Docs: [URL to the service's env variable documentation if known]

```

---

## TASK 5 — Update PROGRESS.json

Update `codebase-context/PROGRESS.json`:
- `steps.04_ENV.status` → `"complete"`
- `steps.04_ENV.completed_at` → current timestamp
- `steps.04_ENV.variables_documented` → total variable count

---

## TASK 6 — Completion Confirmation

Reply with EXACTLY this format:

```
✅ STEP 4 COMPLETE — ENVIRONMENT VARIABLES
═══════════════════════════════════════
Session ID:                  [SESSION_ID]
Total variables documented:  [X]
Undeclared (code-only):      [Y]
Unused (declared, not used): [Z]
Client-exposed variables:    [N]
External services mapped:    [M]

Files created:
  ✅ codebase-context/03_ENV_KEYS.md

➡️  Paste the STEP 5 kickoff prompt from ORCHESTRATOR.md to continue.
```

---

## ⛔ ANTI-SHORTCUT RULES

1. NEVER include a real value for any variable — not even a placeholder like "your-key-here"
2. NEVER skip a variable because it seems obvious
3. NEVER group multiple variables into one entry
4. NEVER write "see .env file for details"
5. If a variable appears in multiple .env files (e.g., both .env.example and .env.production), list all occurrences
6. Search the CODE, not just .env files — many projects reference variables without declaring them
