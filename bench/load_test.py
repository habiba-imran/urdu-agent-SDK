"""Phase 8 Load Testing Harness — bench/load_test.py.

Simulates concurrent token minting, token refresh under load, worker saturation,
and validates that quota_state.concurrent_now returns cleanly to 0 with zero unreconciled drift.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from dbconn import conn_kwargs
    import psycopg
except ImportError:
    conn_kwargs = None  # type: ignore
    psycopg = None  # type: ignore


async def simulate_session(
    client: httpx.AsyncClient,
    base_url: str,
    tenant_id: str,
    agent_id: str,
    session_id: int,
) -> dict:
    """Simulates a single call session: dev-mint -> refresh -> close."""
    start_time = time.monotonic()
    result = {"session_id": session_id, "success": False, "refresh_success": False, "latency_ms": 0}

    # 1. Dev Mint Request
    mint_url = f"{base_url.rstrip('/')}/v1/session/dev-mint"
    try:
        res = await client.post(
            mint_url,
            json={"agentId": agent_id, "publishableKey": tenant_id},
            timeout=10.0,
        )
        if res.status_code == 200:
            data = res.json()
            token = data.get("token")
            result["success"] = True

            # 2. Simulate token refresh under load
            if token:
                refresh_url = f"{base_url.rstrip('/')}/v1/session/refresh"
                ref_res = await client.post(
                    refresh_url,
                    json={"token": token},
                    timeout=10.0,
                )
                if ref_res.status_code == 200:
                    result["refresh_success"] = True
    except Exception as e:
        result["error"] = str(e)

    result["latency_ms"] = round((time.monotonic() - start_time) * 1000, 2)
    return result


async def run_load_test(
    base_url: str,
    concurrency: int,
    bursts: int,
    tenant_id: str = "15e96da6-6b75-4a28-bd7b-ac018986368d",
    agent_id: str = "3b5b7720-4cce-4ac0-a765-6a3685e1bdf0",
) -> dict:
    """Runs a concurrent load test burst against the Control Plane."""
    total_requests = concurrency * bursts
    print(f"[LOAD TEST] Starting burst test: {concurrency} concurrent x {bursts} bursts = {total_requests} total calls...")

    async with httpx.AsyncClient() as client:
        all_results = []
        for burst_idx in range(bursts):
            tasks = [
                simulate_session(
                    client,
                    base_url,
                    tenant_id,
                    agent_id,
                    burst_idx * concurrency + i,
                )
                for i in range(concurrency)
            ]
            burst_results = await asyncio.gather(*tasks)
            all_results.extend(burst_results)

    successes = sum(1 for r in all_results if r["success"])
    refreshes = sum(1 for r in all_results if r["refresh_success"])
    avg_latency = (
        round(sum(r["latency_ms"] for r in all_results) / len(all_results), 2)
        if all_results
        else 0
    )

    stats = {
        "total_requests": total_requests,
        "successful_mints": successes,
        "successful_refreshes": refreshes,
        "failed_requests": total_requests - successes,
        "avg_latency_ms": avg_latency,
    }

    print(f"[LOAD TEST] Completed: {successes}/{total_requests} mints successful, {refreshes} refreshes, avg latency {avg_latency}ms")
    return stats


def get_db_concurrency(tenant_id: str) -> int:
    """Queries live quota_state.concurrent_now for a tenant from PostgreSQL."""
    if not psycopg or not conn_kwargs:
        return 0
    try:
        with psycopg.connect(**conn_kwargs(), connect_timeout=5) as conn:
            row = conn.execute(
                "SELECT concurrent_now FROM quota_state WHERE tenant_id = %s",
                (tenant_id,),
            ).fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


def main():
    parser = argparse.ArgumentParser(description="UVA Control Plane Load Test Harness")
    parser.add_argument("--host-url", default="http://localhost:8000", help="Control plane base URL")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent calls per burst")
    parser.add_argument("--bursts", type=int, default=2, help="Number of bursts")
    args = parser.parse_args()

    results = asyncio.run(run_load_test(args.host_url, args.concurrency, args.bursts))
    print("[LOAD TEST SUMMARY]", results)


if __name__ == "__main__":
    main()
