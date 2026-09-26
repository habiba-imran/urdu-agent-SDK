#!/usr/bin/env python3
"""Encrypt existing plaintext tenant signing secrets (F-C6, phase 2 of the rollout).

Migration 0033 adds ``tenants.hmac_secret_enc``. This fills it from the plaintext
``hmac_secret`` column, and with ``--finalize`` clears the plaintext once every row has a
ciphertext.

Order matters, and the script enforces it:

    1. Apply 0033                          (python scripts/migrate.py)
    2. Set TENANT_SECRET_ENCRYPTION_KEY    on every service that reads tenant secrets:
                                           control plane AND tenant portal
    3. python scripts/encrypt_tenant_secrets.py --dry-run
    4. python scripts/encrypt_tenant_secrets.py
    5. Confirm minting still works, then:
       python scripts/encrypt_tenant_secrets.py --finalize

Between 4 and 5 both columns hold the secret, so a rollback is just "unset the key". After
--finalize the plaintext is gone and the key is required — which is why --finalize refuses
to run while any row still lacks a ciphertext.

Losing TENANT_SECRET_ENCRYPTION_KEY after finalizing means losing every tenant's signing
secret: each one would have to be rotated and redistributed. Store it where the other
service secrets live, not only in one person's shell.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from dbconn import conn_kwargs
except ImportError:  # pragma: no cover
    from scripts.dbconn import conn_kwargs  # type: ignore # noqa: E402

from control_plane.secret_crypto import (  # noqa: E402
    ENV_VAR,
    decrypt_tenant_secret,
    encrypt_tenant_secret,
    is_enabled,
    looks_encrypted,
)


def _counts(conn: psycopg.Connection) -> dict[str, int]:
    row = conn.execute(
        """
        select
          count(*) filter (where hmac_secret is not null and hmac_secret <> ''),
          count(*) filter (where hmac_secret_enc is not null and hmac_secret_enc <> ''),
          count(*)
        from tenants
        """
    ).fetchone()
    return {"plaintext": row[0], "encrypted": row[1], "total": row[2]}


def encrypt_all(*, dry_run: bool) -> int:
    with psycopg.connect(**conn_kwargs(), connect_timeout=15, autocommit=True) as conn:
        before = _counts(conn)
        print(
            f"[encrypt] tenants={before['total']} plaintext={before['plaintext']} "
            f"encrypted={before['encrypted']}"
        )
        rows = conn.execute(
            """
            select id, hmac_secret from tenants
            where hmac_secret is not null and hmac_secret <> ''
              and (hmac_secret_enc is null or hmac_secret_enc = '')
            """
        ).fetchall()
        done = 0
        for tenant_id, plaintext in rows:
            if looks_encrypted(plaintext):
                continue
            blob = encrypt_tenant_secret(plaintext)
            if blob is None:
                print(f"[encrypt] {ENV_VAR} is not set - nothing to do")
                return 1
            # Read it back before trusting it: a ciphertext that cannot be decrypted would
            # be an unrecoverable secret once the plaintext is cleared.
            if decrypt_tenant_secret(blob) != plaintext:
                print(f"[encrypt] REFUSING: round-trip check failed for tenant {tenant_id}")
                return 1
            if dry_run:
                print(f"[encrypt] would encrypt tenant {tenant_id}")
            else:
                conn.execute(
                    "update tenants set hmac_secret_enc = %s where id = %s",
                    (blob, tenant_id),
                )
                print(f"[encrypt] encrypted tenant {tenant_id}")
            done += 1
        after = _counts(conn)
        print(
            f"[encrypt] {'would encrypt' if dry_run else 'encrypted'} {done} tenant(s); "
            f"now plaintext={after['plaintext']} encrypted={after['encrypted']}"
        )
    return 0


def finalize(*, dry_run: bool) -> int:
    with psycopg.connect(**conn_kwargs(), connect_timeout=15, autocommit=True) as conn:
        missing = conn.execute(
            """
            select count(*) from tenants
            where hmac_secret is not null and hmac_secret <> ''
              and (hmac_secret_enc is null or hmac_secret_enc = '')
            """
        ).fetchone()[0]
        if missing:
            print(
                f"[encrypt] REFUSING to finalize: {missing} tenant(s) have no ciphertext. "
                "Run without --finalize first."
            )
            return 1
        # Verify every ciphertext opens with the current key before destroying the source.
        rows = conn.execute(
            "select id, hmac_secret_enc from tenants "
            "where hmac_secret_enc is not null and hmac_secret_enc <> ''"
        ).fetchall()
        for tenant_id, blob in rows:
            try:
                if not decrypt_tenant_secret(blob):
                    raise ValueError("empty plaintext")
            except Exception as exc:
                print(
                    f"[encrypt] REFUSING to finalize: tenant {tenant_id} ciphertext does not "
                    f"decrypt with the current {ENV_VAR} ({exc})"
                )
                return 1
        if dry_run:
            print(f"[encrypt] would clear plaintext hmac_secret for {len(rows)} tenant(s)")
            return 0
        conn.execute(
            "update tenants set hmac_secret = null "
            "where hmac_secret_enc is not null and hmac_secret_enc <> ''"
        )
        print(f"[encrypt] cleared plaintext hmac_secret for {len(rows)} tenant(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Clear the plaintext column (only once every row has a verified ciphertext)",
    )
    args = parser.parse_args(argv)

    if not is_enabled():
        print(
            f"[encrypt] {ENV_VAR} is not set. Set it on every service that reads tenant "
            "secrets (control plane and tenant portal) before running this."
        )
        return 1
    if args.finalize:
        return finalize(dry_run=args.dry_run)
    return encrypt_all(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
