#!/usr/bin/env python3
# path: scripts/create_new_client.py
"""Provision a new Client Tenant for Finova Solutions Urdu Voice Agent Platform.

Usage:
    python scripts/create_new_client.py "Client Business Name"
    python scripts/create_new_client.py "Finova Client Alpha" --max-concurrent 10 --max-minutes 5000
"""

from __future__ import annotations

import argparse
import secrets
import sys
import uuid
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from control_plane.secrets import secret_hash  # noqa: E402
from dbconn import conn_kwargs  # noqa: E402


def create_tenant(
    name: str, max_concurrent: int = 20, max_minutes_month: int = 10000
) -> dict:
    tid = str(uuid.uuid4())
    raw_secret = secrets.token_urlsafe(32)
    hashed_secret = secret_hash(raw_secret)

    with psycopg.connect(**conn_kwargs(), autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO tenants (id, name, hmac_secret, hmac_secret_hash, status, max_concurrent, max_minutes_month, allowed_origins)
            VALUES (%s, %s, %s, %s, 'active', %s, %s, ARRAY['http://localhost:5173', 'http://localhost:5174', 'http://localhost:3000'])
            """,
            (tid, name, raw_secret, hashed_secret, max_concurrent, max_minutes_month),
        )
        conn.execute(
            """
            INSERT INTO quota_state (tenant_id, concurrent_now, minutes_this_month)
            VALUES (%s, 0, 0)
            ON CONFLICT (tenant_id) DO NOTHING
            """,
            (tid,),
        )

    return {
        "tenant_id": tid,
        "tenant_secret": raw_secret,
        "publishable_key": tid,
        "name": name,
        "max_concurrent": max_concurrent,
        "max_minutes_month": max_minutes_month,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision a new client tenant in Finova platform."
    )
    parser.add_argument("name", help="Name of the client tenant business")
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=20,
        help="Max concurrent sessions allowed (default: 20)",
    )
    parser.add_argument(
        "--max-minutes",
        type=int,
        default=10000,
        help="Max monthly minutes allowed (default: 10000)",
    )

    args = parser.parse_args()

    cred = create_tenant(args.name, args.max_concurrent, args.max_minutes)

    print("==================================================================")
    print("           FINOVA SOLUTIONS — NEW CLIENT PROVISIONED              ")
    print("==================================================================")
    print(f"  Client Name      : {cred['name']}")
    print(f"  Tenant ID        : {cred['tenant_id']}")
    print(f"  Publishable Key  : {cred['publishable_key']}")
    print(f"  Tenant Secret    : {cred['tenant_secret']}")
    print(f"  Max Concurrent   : {cred['max_concurrent']}")
    print(f"  Max Minutes/Mo   : {cred['max_minutes_month']}")
    print("==================================================================")
    print("\nProvide these credentials to the client for their test-app/backend/.env:")
    print(f"  UVA_TENANT_ID={cred['tenant_id']}")
    print(f"  UVA_HMAC_SECRET={cred['tenant_secret']}")
    print(f"  UVA_PUBLISHABLE_KEY={cred['publishable_key']}")
    print("==================================================================")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
