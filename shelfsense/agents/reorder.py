"""
shelfsense/agents/reorder.py
Sub-agent: smart reorder plan generator.
THE ONLY agent that calls MODEL_FULL (gemini-2.5-flash). Used sparingly.
Uses google.genai SDK (v2+).
"""

import json
import time
import google.genai as genai
import google.genai.types as types

from shelfsense.config import GEMINI_API_KEY, MODEL_FULL, MAX_OUTPUT_TOKENS
from shelfsense.database import get_low_stock_items, get_sales_summary, get_db

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2.0

# System prompt — kept ≤150 tokens as per constraint
REORDER_SYSTEM_PROMPT = (
    "You are a procurement assistant for a kirana shop. "
    "Given low-stock items and recent sales velocity, generate: "
    "1) Suggested reorder quantities (enough for 2 weeks based on sales rate). "
    "2) A short WhatsApp-ready purchase order message in simple English. "
    "Return ONLY valid JSON. No markdown."
)

REORDER_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name":                {"type": "string"},
                    "sku":                 {"type": "string"},
                    "current_qty":         {"type": "number"},
                    "suggested_order_qty": {"type": "number"},
                    "reason":              {"type": "string"},
                },
                "required": ["name", "sku", "current_qty", "suggested_order_qty", "reason"],
            },
        },
        "purchase_order_text": {"type": "string"},
    },
    "required": ["items", "purchase_order_text"],
}


def _get_supplier_map() -> dict[str, str]:
    """Return a mapping of category -> supplier name for context."""
    conn = get_db()
    try:
        rows = conn.execute("SELECT name, category FROM suppliers").fetchall()
        mapping: dict[str, str] = {}
        for row in rows:
            for cat in row["category"].split(","):
                mapping[cat.strip()] = row["name"]
        return mapping
    finally:
        conn.close()


def run() -> str:
    """
    Generate a reorder plan using Gemini Flash.
    Returns formatted markdown with the plan and WhatsApp PO text.
    """
    low_items = get_low_stock_items()
    if not low_items:
        return "✅ **No items need reordering right now.** Stock levels look good!"

    sales_data = get_sales_summary(days=7)
    sales_map = {s["sku"]: s["total_sold"] for s in sales_data}
    supplier_map = _get_supplier_map()

    prompt_data = [
        {
            "name":         item["name"],
            "sku":          item["sku"],
            "category":     item["category"],
            "current_qty":  item["qty"],
            "unit":         item["unit"],
            "min_qty":      item["min_qty"],
            "cost_price":   item.get("cost_price"),
            "weekly_sales": sales_map.get(item["sku"], 0),
            "supplier":     supplier_map.get(item["category"], "Unknown"),
        }
        for item in low_items
    ]

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt_text = (
        f"Low stock items with recent sales data:\n{json.dumps(prompt_data, indent=2)}"
    )

    last_error = None
    data = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL_FULL,
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    system_instruction=REORDER_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=REORDER_SCHEMA,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    temperature=0.2,
                ),
            )
            data = json.loads(response.text)
            break  # success
        except json.JSONDecodeError:
            return "⚠️ Could not parse reorder plan from AI. Please try again."
        except Exception as e:
            last_error = e
            error_str = str(e)
            if any(code in error_str for code in ["503", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED"]):
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY_SECONDS * (2 ** attempt)
                    time.sleep(wait)
                    continue
            break

    if data is None:
        return (
            f"⚠️ **Reorder agent unavailable** — Gemini API is currently overloaded.\n\n"
            f"Please try again in a few seconds. Error: `{last_error}`"
        )

    items_text = "\n".join(
        f"  • **{i['name']}**: order {i['suggested_order_qty']} units "
        f"_(currently {i['current_qty']}, {i['reason']})_"
        for i in data.get("items", [])
    )

    po_text = data.get("purchase_order_text", "No PO text generated.")

    # Calculate estimated total cost if cost_price available
    total_cost = 0.0
    cost_available = False
    for item_plan in data.get("items", []):
        sku = item_plan.get("sku", "")
        orig = next((x for x in low_items if x["sku"] == sku), None)
        if orig and orig.get("cost_price"):
            total_cost += orig["cost_price"] * item_plan["suggested_order_qty"]
            cost_available = True

    cost_str = f"\n\n💰 **Estimated Total Cost:** ₹{total_cost:.0f}" if cost_available else ""

    return (
        f"📋 **Reorder Plan** ({len(data.get('items', []))} items)\n\n"
        f"{items_text}"
        f"{cost_str}\n\n"
        f"---\n📱 **WhatsApp Purchase Order:**\n```\n{po_text}\n```"
    )
