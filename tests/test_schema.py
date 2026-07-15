"""STEP 9.2 — Schema test: all tables exist with correct seed counts."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import Check

EXPECTED_TABLES = [
    "shop_info",
    "products",
    "customers",
    "reservations",
    "support_tickets",
    "callbacks",
    "conversations",
    "messages",
    "turn_metrics",
]


async def run() -> Check:
    import db

    check = Check("schema")
    client = await db.get_client()

    for table in EXPECTED_TABLES:
        try:
            await client.table(table).select("*").limit(1).execute()
            check.ok(f"table {table} exists", True)
        except Exception as e:
            check.ok(f"table {table} exists", False, str(e)[:100])

    res = await client.table("shop_info").select("*").execute()
    check.ok("shop_info seeded (1 row)", len(res.data) == 1, f"{len(res.data)} rows")
    if res.data:
        row = res.data[0]
        check.ok(
            "shop_info content",
            row["name"] == "TechZone Laptops" and row["city"] == "Islamabad",
            f"{row['name']}, {row['city']}",
        )

    res = await client.table("products").select("id, brand, condition, battery_health").execute()
    check.ok("products seeded (15 SKUs)", len(res.data) == 15, f"{len(res.data)} rows")
    brands = {r["brand"] for r in res.data}
    check.ok("non-Apple options present", {"Dell", "Lenovo"} <= brands, str(brands))
    used = [r for r in res.data if r["condition"] == "used"]
    check.ok(
        "used units with battery_health",
        len(used) >= 2 and all(r["battery_health"] for r in used),
        f"{len(used)} used units",
    )
    return check


if __name__ == "__main__":
    c = asyncio.run(run())
    sys.exit(0 if c.passed else 1)
