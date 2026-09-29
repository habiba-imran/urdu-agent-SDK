<!-- F-M28. Keep this short; it exists so the risky paths get a deliberate answer, not to add ceremony. -->

## What this changes

<!-- One or two sentences. If it closes an audit finding, name the ID (e.g. F-C3). -->

## Why

<!-- The problem, not the patch. What breaks today, or what could? -->

## How it was verified

<!-- What you actually ran, and what it said. "CI is green" counts; "should work" does not. -->

- [ ] Tests added or updated for the behaviour that changed
- [ ] Full test suite run, with any pre-existing failures named

## Risk

- [ ] Touches authentication, signing, encryption, quota, or billing
- [ ] Changes a database schema (migration is additive and re-runnable)
- [ ] Changes deploy, release, or scheduled jobs
- [ ] Needs a configuration change before or after merge — **list it here, or say "none"**:

<!--
Configuration a reviewer should check for, when relevant:
  UVA_ENV / CP_ALLOWED_ORIGINS / TENANT_PORTAL_JWT_SECRET / ADMIN_JWT_SECRET  (fail at startup)
  CP_ENABLE_DEV_MINT / CP_ENABLE_DOCS / CP_DEV_MINT_RESET_QUOTA               (off by default)
  RECONCILE_APPLY / PURGE_APPLY                                               (dry-run by default)
-->
