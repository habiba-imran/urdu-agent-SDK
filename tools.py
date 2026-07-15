"""Function-calling tools for Mahnoor (STEP 5).

Every fact the agent speaks (price, stock, spec, policy) must come from these tools.
Tool-layer validation (STEP 7):
- phone numbers validated against a Pakistani mobile regex before any write
- product_id must exist (and have stock) before a reservation
- writes are rejected when the name is missing
"""

import asyncio
import re
import time
from typing import Any

from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams

import db
from db import DBTimeout
from session_state import SessionState

# --- Validation ----------------------------------------------------------------

# Pakistani mobile: 03XXXXXXXXX (also accepts +92 / 92 / 0092 prefixes and separators)
_PK_MOBILE_RE = re.compile(r"^03\d{9}$")

DB_ERROR_RESULT = {
    "error": "database_unavailable",
    "instruction": "Apologize in Urdu that you cannot confirm right now and offer a callback. Do not guess.",
}


def normalize_pk_phone(raw: str) -> str | None:
    """Normalize a Pakistani mobile number to 03XXXXXXXXX, or None if invalid."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if digits.startswith("0092"):
        digits = "0" + digits[4:]
    elif digits.startswith("92"):
        digits = "0" + digits[2:]
    if _PK_MOBILE_RE.match(digits):
        return digits
    return None


def _clean_name(raw: Any) -> str | None:
    name = str(raw or "").strip()
    return name if len(name) >= 2 else None


# --- Product cache + fuzzy search ------------------------------------------------

_products_cache: list[dict] = []
_products_cache_at: float = 0.0
_PRODUCTS_TTL = 60.0


async def _get_products() -> list[dict]:
    global _products_cache, _products_cache_at
    if _products_cache and time.monotonic() - _products_cache_at < _PRODUCTS_TTL:
        return _products_cache
    client = await db.get_client()
    res = await db.timed_read(client.table("products").select("*").execute(), "products")
    _products_cache = res.data or []
    _products_cache_at = time.monotonic()
    return _products_cache


_SYNONYMS = {
    "mac": "macbook",
    "makbook": "macbook",
    "airbook": "air",
    "pro": "pro",
    "used": "used",
    "purana": "used",
    "second": "used",
    "new": "new",
    "naya": "new",
}


def _fuzzy_score(product: dict, tokens: list[str]) -> float:
    haystack = " ".join(
        str(product.get(k) or "").lower()
        for k in ("brand", "model", "chip", "condition", "notes")
    )
    haystack += f" {product.get('ram_gb')}gb {product.get('storage_gb')}gb {product.get('screen_size')}"
    score = 0.0
    for tok in tokens:
        tok = _SYNONYMS.get(tok, tok)
        if not tok:
            continue
        if tok in haystack:
            score += 2.0
        elif len(tok) >= 4 and any(tok[:4] in word for word in haystack.split()):
            score += 0.5
    return score


def _product_public(p: dict) -> dict:
    # v2 token diet: tool results replay in every later LLM call — keep them lean
    out = {
        "product_id": p["id"],
        "brand": p["brand"],
        "model": p["model"],
        "chip": p.get("chip"),
        "ram_gb": p["ram_gb"],
        "storage_gb": p["storage_gb"],
        "screen_size": float(p["screen_size"]),
        "condition": p["condition"],
        "price_pkr": p["price_pkr"],
        "stock_qty": p["stock_qty"],
    }
    if p.get("battery_health") is not None:
        out["battery_health_percent"] = p["battery_health"]
    return out


# --- Tool handlers ---------------------------------------------------------------


async def search_products(params: FunctionCallParams):
    args = params.arguments
    query = str(args.get("query") or "").lower()
    condition = args.get("condition")
    max_price = args.get("max_price_pkr")
    if isinstance(max_price, str):
        digits = re.sub(r"\D", "", max_price)
        max_price = int(digits) if digits else None
    try:
        products = await _get_products()
    except (DBTimeout, Exception) as e:
        logger.error(f"search_products failed: {e}")
        await params.result_callback(DB_ERROR_RESULT)
        return

    tokens = re.findall(r"[a-z0-9]+", query)
    results = list(products)
    if condition in ("new", "used", "open_box"):
        results = [p for p in results if p["condition"] == condition]
    if isinstance(max_price, (int, float)) and max_price > 0:
        results = [p for p in results if p["price_pkr"] <= max_price]

    if tokens:
        scored = [(_fuzzy_score(p, tokens), p) for p in results]
        scored = [(s, p) for s, p in scored if s > 0]
        scored.sort(key=lambda sp: (-sp[0], sp[1]["price_pkr"]))
        results = [p for _, p in scored]
    else:
        results.sort(key=lambda p: p["price_pkr"])

    top = [_product_public(p) for p in results[:3]]
    await params.result_callback({"matches": top, "match_count": len(top)})


async def get_product_details(params: FunctionCallParams):
    pid = params.arguments.get("product_id")
    try:
        products = await _get_products()
    except Exception as e:
        logger.error(f"get_product_details failed: {e}")
        await params.result_callback(DB_ERROR_RESULT)
        return
    product = next((p for p in products if str(p["id"]) == str(pid)), None)
    if not product:
        await params.result_callback({"error": "product_not_found"})
        return
    await params.result_callback(_product_public(product))


async def get_shop_info(params: FunctionCallParams):
    try:
        client = await db.get_client()
        res = await db.timed_read(
            client.table("shop_info").select("*").eq("id", 1).single().execute(), "shop_info"
        )
    except Exception as e:
        logger.error(f"get_shop_info failed: {e}")
        await params.result_callback(DB_ERROR_RESULT)
        return
    info = dict(res.data)
    info.pop("id", None)
    await params.result_callback(info)


async def _find_or_create_customer(name: str, phone: str) -> int:
    client = await db.get_client()
    res = await db.timed_read(
        client.table("customers").select("id").eq("phone", phone).execute(), "customer-lookup"
    )
    if res.data:
        return res.data[0]["id"]
    created = await asyncio.wait_for(
        client.table("customers").insert({"name": name, "phone": phone}).execute(), timeout=4
    )
    return created.data[0]["id"]


def _validated_contact(params: FunctionCallParams) -> tuple[str, str] | dict:
    name = _clean_name(params.arguments.get("name"))
    phone = normalize_pk_phone(params.arguments.get("phone"))
    if not name:
        return {
            "error": "missing_name",
            "instruction": "Ask the customer for their name before saving.",
        }
    if not phone:
        return {
            "error": "invalid_phone",
            "instruction": (
                "The phone number is not a valid Pakistani mobile number (03XXXXXXXXX). "
                "Ask the customer to repeat it, then read it back digit by digit for confirmation."
            ),
        }
    return name, phone


async def create_reservation(params: FunctionCallParams):
    check = _validated_contact(params)
    if isinstance(check, dict):
        await params.result_callback(check)
        return
    name, phone = check
    pid = params.arguments.get("product_id")
    mode = str(params.arguments.get("pickup_or_delivery") or "pickup").lower()
    if mode not in ("pickup", "delivery"):
        mode = "pickup"
    notes = str(params.arguments.get("notes") or "") or None

    try:
        products = await _get_products()
        product = next((p for p in products if str(p["id"]) == str(pid)), None)
        if not product:
            await params.result_callback({"error": "product_not_found"})
            return
        if product["stock_qty"] <= 0:
            await params.result_callback({"error": "out_of_stock"})
            return
        customer_id = await _find_or_create_customer(name, phone)
        client = await db.get_client()
        created = await asyncio.wait_for(
            client.table("reservations")
            .insert(
                {
                    "customer_id": customer_id,
                    "product_id": product["id"],
                    "pickup_or_delivery": mode,
                    "notes": notes,
                }
            )
            .execute(),
            timeout=4,
        )
        reservation_id = created.data[0]["id"]
        await params.result_callback(
            {
                "reservation_id": reservation_id,
                "status": "pending",
                "product": f"{product['brand']} {product['model']}",
                "price_pkr": product["price_pkr"],
                "pickup_or_delivery": mode,
                "customer_phone": phone,
            }
        )
    except Exception as e:
        logger.error(f"create_reservation failed: {e}")
        await params.result_callback(DB_ERROR_RESULT)


async def create_support_ticket(params: FunctionCallParams):
    check = _validated_contact(params)
    if isinstance(check, dict):
        await params.result_callback(check)
        return
    name, phone = check
    category = str(params.arguments.get("category") or "query").lower()
    if category not in ("repair", "warranty", "complaint", "query"):
        category = "query"
    description = str(params.arguments.get("description") or "").strip()
    if not description:
        await params.result_callback(
            {"error": "missing_description", "instruction": "Ask what the issue is."}
        )
        return
    try:
        customer_id = await _find_or_create_customer(name, phone)
        client = await db.get_client()
        created = await asyncio.wait_for(
            client.table("support_tickets")
            .insert(
                {"customer_id": customer_id, "category": category, "description": description}
            )
            .execute(),
            timeout=4,
        )
        await params.result_callback(
            {"ticket_id": created.data[0]["id"], "category": category, "status": "open"}
        )
    except Exception as e:
        logger.error(f"create_support_ticket failed: {e}")
        await params.result_callback(DB_ERROR_RESULT)


async def schedule_callback(params: FunctionCallParams):
    check = _validated_contact(params)
    if isinstance(check, dict):
        await params.result_callback(check)
        return
    name, phone = check
    preferred_time = str(params.arguments.get("preferred_time") or "").strip() or None
    reason = str(params.arguments.get("reason") or "").strip() or None
    try:
        customer_id = await _find_or_create_customer(name, phone)
        client = await db.get_client()
        created = await asyncio.wait_for(
            client.table("callbacks")
            .insert(
                {
                    "customer_id": customer_id,
                    "phone": phone,
                    "preferred_time": preferred_time,
                    "reason": reason,
                }
            )
            .execute(),
            timeout=4,
        )
        await params.result_callback(
            {"callback_id": created.data[0]["id"], "status": "pending", "phone": phone}
        )
    except Exception as e:
        logger.error(f"schedule_callback failed: {e}")
        await params.result_callback(DB_ERROR_RESULT)


def make_end_conversation_summary(session: SessionState):
    async def end_conversation_summary(params: FunctionCallParams):
        summary = str(params.arguments.get("summary") or "").strip()
        db.record_conversation_end(session.conversation_id, summary or None)
        session.summary_written = True
        session.end_requested = True
        await params.result_callback({"status": "saved", "instruction": "Close the call warmly."})

    return end_conversation_summary


# --- Schemas ---------------------------------------------------------------------


def build_tools_schema() -> ToolsSchema:
    # v2 token diet: one tight sentence per tool and per parameter (PROMPT2 CHANGE 3)
    return ToolsSchema(
        standard_tools=[
            FunctionSchema(
                name="search_products",
                description="Search inventory; returns up to 3 products with exact PKR price and stock. Call before quoting any price or availability.",
                properties={
                    "query": {"type": "string"},
                    "condition": {"type": "string", "enum": ["new", "used", "open_box"]},
                    # string: llama-3.3 sometimes quotes numbers and Groq hard-rejects
                    # integer-typed params on mismatch; the handler parses digits
                    "max_price_pkr": {"type": "string", "description": "Max budget in PKR digits."},
                },
                required=["query"],
            ),
            FunctionSchema(
                name="get_product_details",
                description="Full details for one product_id.",
                properties={"product_id": {"type": "integer"}},
                required=["product_id"],
            ),
            FunctionSchema(
                name="get_shop_info",
                description="Hours, address, phone and warranty/return/delivery policies.",
                properties={},
                required=[],
            ),
            FunctionSchema(
                name="create_reservation",
                description="Reserve a laptop after the phone was confirmed digit-by-digit (phone format 03XXXXXXXXX).",
                properties={
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "product_id": {"type": "integer"},
                    "pickup_or_delivery": {"type": "string", "enum": ["pickup", "delivery"]},
                    "notes": {"type": "string"},
                },
                required=["name", "phone", "product_id", "pickup_or_delivery"],
            ),
            FunctionSchema(
                name="create_support_ticket",
                description="Open a support ticket (phone confirmed digit-by-digit first).",
                properties={
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "category": {"type": "string", "enum": ["repair", "warranty", "complaint", "query"]},
                    "description": {"type": "string"},
                },
                required=["name", "phone", "category", "description"],
            ),
            FunctionSchema(
                name="schedule_callback",
                description="Schedule a senior-rep callback (phone confirmed digit-by-digit first).",
                properties={
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "preferred_time": {"type": "string"},
                    "reason": {"type": "string"},
                },
                required=["name", "phone"],
            ),
            FunctionSchema(
                name="end_conversation_summary",
                description="Call at conversation end with a one-sentence summary, then say the closing line.",
                properties={"summary": {"type": "string"}},
                required=["summary"],
            ),
        ]
    )


def register_tools(llm, session: SessionState):
    """Register all tool handlers on an LLM service instance."""
    llm.register_function("search_products", search_products)
    llm.register_function("get_product_details", get_product_details)
    llm.register_function("get_shop_info", get_shop_info)
    llm.register_function("create_reservation", create_reservation)
    llm.register_function("create_support_ticket", create_support_ticket)
    llm.register_function("schedule_callback", schedule_callback)
    llm.register_function("end_conversation_summary", make_end_conversation_summary(session))
