#!/usr/bin/env python3
"""Provision the first super-admin portal account (NON-LIVE: dev DB write only).

Generates a random password + a fresh RFC 6238 TOTP secret, inserts one admin_users row, and
writes the credentials to state/admin_bootstrap.local.md (gitignored — see .gitignore) — NEVER to
stdout, NEVER to any tracked file. This deliberately avoids repeating the demo-gate3 lesson
(state/BLOCKERS.md): a secret pasted into chat/tool output or a committed file is compromised the
moment it lands there. Read the credentials from that file, then delete it or rotate the password
via a fresh run of this script.

    python scripts/provision_admin.py --email you@example.com          # dry-run: prints the plan
    python scripts/provision_admin.py --email you@example.com --commit # writes the dev DB row +
                                                                        # state/admin_bootstrap.local.md
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from admin.auth import provision_admin  # noqa: E402
from admin.security import random_base32_secret  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402

CREDS_PATH = ROOT / "state" / "admin_bootstrap.local.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument(
        "--commit", action="store_true", help="actually write to the dev DB"
    )
    args = ap.parse_args()

    password = secrets.token_urlsafe(18)
    totp_secret = random_base32_secret()
    otpauth = (
        f"otpauth://totp/UVA%20Admin:{args.email}?secret={totp_secret}"
        f"&issuer=UVA%20Admin&algorithm=SHA1&digits=6&period=30"
    )

    print(f"email: {args.email}")
    print(
        "password/TOTP secret: will be written to state/admin_bootstrap.local.md, not printed here"
    )

    if not args.commit:
        print(
            "\nDRY RUN — pass --commit to seed the dev DB and write the credentials file."
        )
        return 0

    with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
        admin_id = provision_admin(
            conn, email=args.email, password=password, totp_secret=totp_secret
        )

    CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDS_PATH.write_text(
        "# Admin bootstrap credentials — gitignored, read once then rotate/delete.\n"
        f"admin_id: {admin_id}\n"
        f"email: {args.email}\n"
        f"password: {password}\n"
        f"totp_secret (base32): {totp_secret}\n"
        f"otpauth_uri (scan into an authenticator app): {otpauth}\n",
        encoding="utf-8",
    )
    print(f"\nSEEDED to dev DB. Credentials written to {CREDS_PATH}")
    print(f"Delete later with: delete from admin_users where id = '{admin_id}';")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
