# Evidence — M1 signature compare (PASS)

**Date:** 2026-10-07  
**Method:** static read

## control_plane/mint.py

- Canonical string built; expected HMAC-SHA256 hex
- Comparison uses `hmac.compare_digest` (observed ~L109–L111 and ~L126)
- Nonce + timestamp window enforced before accept; inserts into `used_nonces`

## tenant_portal_api/machine_auth.py

- Machine auth signature check uses `hmac.compare_digest` (~L160)

## Verdict

PASS — no naive `==` on signature digests in mint/machine auth paths reviewed.
