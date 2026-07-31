#!/usr/bin/env python3
"""CLI script for running telephony state reconciliation.

Usage:
  python scripts/reconcile_telephony.py [--apply]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tenant_portal_api.telephony_reconcile import reconcile_telephony_state


def main():
    parser = argparse.ArgumentParser(description="Telephony background reconciler CLI")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply repair changes to database (default is dry-run mode)",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    print(f"Running Telephony Reconciler (dry_run={dry_run})...")

    results = reconcile_telephony_state(db_conn=None, dry_run=dry_run)
    print("Reconciliation Complete:")
    print(f"  Stale Orders Found:    {results['stale_orders_found']}")
    print(f"  Stale Calls Repaired:  {results['stale_calls_cleaned']}")
    print(f"  Quota Leaks Repaired:  {results['quota_leaks_repaired']}")
    print(f"  Mode:                  {'Dry Run' if dry_run else 'Applied'}")


if __name__ == "__main__":
    main()
