"""STEP 9.3 — Tool unit tests against the live Supabase project.

Covers each tool, plus timeout and invalid-input paths.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import Check, FakeFunctionCallParams

import config


async def call(handler, **arguments):
    params = FakeFunctionCallParams(handler.__name__, arguments)
    await handler(params)
    return params.result


async def run() -> Check:
    import db
    import tools as tz
    from session_state import SessionState

    check = Check("tools")

    # --- validation helpers ---
    check.ok("phone: valid 0300...", tz.normalize_pk_phone("0300 1234567") == "03001234567")
    check.ok("phone: +92 normalized", tz.normalize_pk_phone("+92 300 1234567") == "03001234567")
    check.ok("phone: landline rejected", tz.normalize_pk_phone("051 2345678") is None)
    check.ok("phone: short rejected", tz.normalize_pk_phone("0300123") is None)

    # --- search_products ---
    res = await call(tz.search_products, query="MacBook Air M2")
    ok = res and res.get("matches") and any("M2" in m["model"] for m in res["matches"])
    check.ok("search_products: fuzzy match M2", bool(ok), str(res)[:120])
    check.ok("search_products: <=3 results", res and len(res["matches"]) <= 3)

    res = await call(tz.search_products, query="macbook", condition="used")
    ok = res and res["matches"] and all(m["condition"] == "used" for m in res["matches"])
    check.ok("search_products: condition filter", bool(ok))
    check.ok(
        "search_products: used units expose battery health",
        res and all("battery_health_percent" in m for m in res["matches"]),
    )

    res = await call(tz.search_products, query="laptop", max_price_pkr=300000)
    ok = res and all(m["price_pkr"] <= 300000 for m in res.get("matches", []))
    check.ok("search_products: max_price filter", bool(ok))

    res = await call(tz.search_products, query="thinkpad")
    ok = res and res["matches"] and res["matches"][0]["brand"] == "Lenovo"
    check.ok("search_products: non-Apple query", bool(ok), str(res)[:100])

    # --- get_product_details ---
    first = (await call(tz.search_products, query="MacBook Air M1"))["matches"][0]
    res = await call(tz.get_product_details, product_id=first["product_id"])
    check.ok("get_product_details: found", res.get("product_id") == first["product_id"])
    res = await call(tz.get_product_details, product_id=999999)
    check.ok("get_product_details: invalid id", res.get("error") == "product_not_found")

    # --- get_shop_info ---
    res = await call(tz.get_shop_info)
    check.ok(
        "get_shop_info: policies present",
        res.get("name") == "TechZone Laptops" and "warranty_policy_urdu" in res,
    )

    # --- create_reservation ---
    res = await call(
        tz.create_reservation,
        name="Test Khareedar",
        phone="0301 7654321",
        product_id=first["product_id"],
        pickup_or_delivery="pickup",
    )
    reservation_id = res.get("reservation_id")
    check.ok("create_reservation: happy path", bool(reservation_id), str(res)[:120])

    client = await db.get_client()
    if reservation_id:
        row = (
            await client.table("reservations")
            .select("*, customers(name, phone)")
            .eq("id", reservation_id)
            .execute()
        ).data
        check.ok(
            "create_reservation: row in Supabase w/ normalized phone",
            row and row[0]["customers"]["phone"] == "03017654321",
            str(row)[:140],
        )

    res = await call(
        tz.create_reservation,
        name="X",  # too short
        phone="03017654321",
        product_id=first["product_id"],
        pickup_or_delivery="pickup",
    )
    check.ok("create_reservation: missing name rejected", res.get("error") == "missing_name")

    res = await call(
        tz.create_reservation,
        name="Test Khareedar",
        phone="12345",
        product_id=first["product_id"],
        pickup_or_delivery="pickup",
    )
    check.ok("create_reservation: invalid phone rejected", res.get("error") == "invalid_phone")

    res = await call(
        tz.create_reservation,
        name="Test Khareedar",
        phone="03017654321",
        product_id=999999,
        pickup_or_delivery="delivery",
    )
    check.ok("create_reservation: bad product rejected", res.get("error") == "product_not_found")

    # --- create_support_ticket ---
    res = await call(
        tz.create_support_ticket,
        name="Test Khareedar",
        phone="03017654321",
        category="repair",
        description="Screen flickering on MacBook Air",
    )
    check.ok("create_support_ticket: happy path", bool(res.get("ticket_id")), str(res)[:100])
    res = await call(
        tz.create_support_ticket,
        name="Test Khareedar",
        phone="03017654321",
        category="repair",
        description="",
    )
    check.ok("create_support_ticket: empty description", res.get("error") == "missing_description")

    # --- schedule_callback ---
    res = await call(
        tz.schedule_callback,
        name="Test Khareedar",
        phone="03017654321",
        preferred_time="kal shaam 5 baje",
        reason="price negotiation with manager",
    )
    check.ok("schedule_callback: happy path", bool(res.get("callback_id")), str(res)[:100])

    # --- end_conversation_summary ---
    session = SessionState()
    import db as db_mod

    db_mod.record_conversation_start(session.conversation_id)
    await asyncio.sleep(1.0)  # let fire-and-forget insert land
    handler = tz.make_end_conversation_summary(session)
    res = await call(handler, summary="Customer reserved a MacBook Air M1.")
    check.ok("end_conversation_summary: saved + end requested", res.get("status") == "saved" and session.end_requested)
    await asyncio.sleep(1.5)
    conv = (
        await client.table("conversations")
        .select("summary, ended_at")
        .eq("id", session.conversation_id)
        .execute()
    ).data
    check.ok(
        "end_conversation_summary: summary row in Supabase",
        conv and conv[0]["summary"] and conv[0]["ended_at"],
        str(conv)[:120],
    )

    # --- timeout path: reads that exceed the 2.5s budget fall back gracefully ---
    original = db.timed_read

    async def slow_read(coro, what="read"):
        coro.close()

        async def _never():
            await asyncio.sleep(10)

        return await original(_never(), what)

    db.timed_read = slow_read
    tz._products_cache = []  # force a DB hit
    tz._products_cache_at = 0.0
    t0 = asyncio.get_event_loop().time()
    res = await call(tz.search_products, query="macbook")
    elapsed = asyncio.get_event_loop().time() - t0
    db.timed_read = original
    tz._products_cache = []
    tz._products_cache_at = 0.0
    check.ok(
        "timeout path: DB_ERROR_RESULT within ~2.5s",
        res.get("error") == "database_unavailable" and elapsed < 4.0,
        f"{elapsed:.2f}s → {str(res)[:80]}",
    )

    return check


if __name__ == "__main__":
    c = asyncio.run(run())
    sys.exit(0 if c.passed else 1)
