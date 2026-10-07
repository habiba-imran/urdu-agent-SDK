# Habiba evidence folder

Store **redacted** proof here. Never commit secrets, tokens, raw `.env`, or full customer PII.

## Naming

```
YYYY-MM-DD_<phase>_<short-name>.txt|png|md
```

Examples:

- `2026-10-08_0_rls_check.txt`
- `2026-10-09_1A_mint_compare.md`
- `2026-10-12_B_M1-F03_retest.txt`

## What belongs here

- Script stdout (`rls_check`, `verify_rate_limit_live`, `verify_admin_boundary_live`)
- SQL policy extracts (no row data with phones if avoidable)
- Route matrices / diagrams (text or png)
- Retest logs for fixed findings

## What does not

- HMAC secrets, Telnyx keys, JWTs, connection strings
- Unredacted production transcripts
