"""
shelfsense/agents/stock_check.py
Sub-agent: query current stock levels.
No LLM call — pure DB query + formatting.
"""

from shelfsense.database import get_stock_by_name, get_all_inventory


def run(product_name: str | None) -> str:
    """
    Return formatted stock information.
    If product_name is None, return a summary of the full inventory.
    """
    if not product_name:
        # Full inventory summary (first 20 items)
        items = get_all_inventory()
        if not items:
            return "📦 Inventory is empty. Run the seed script to populate data."

        lines: list[str] = []
        current_cat = ""
        for item in items[:20]:
            if item["category"] != current_cat:
                current_cat = item["category"]
                lines.append(f"\n**{current_cat.upper()}**")
            status = ""
            if item["qty"] == 0:
                status = " ⚠️ OUT"
            elif item["qty"] <= item["min_qty"]:
                status = " 🟡 LOW"
            lines.append(
                f"  • {item['name']}: {item['qty']} {item['unit']}{status}"
            )

        remaining = len(items) - 20
        footer = f"\n\n_...and {remaining} more items_" if remaining > 0 else ""
        return "📦 **Current Inventory:**" + "\n".join(lines) + footer

    # Specific product lookup
    rows = get_stock_by_name(product_name)
    if not rows:
        return (
            f"🔍 Product **'{product_name}'** not found in inventory. "
            f"Check spelling or add it to the inventory."
        )

    item = rows[0]
    if item["qty"] == 0:
        status = "⚠️ **OUT OF STOCK**"
    elif item["qty"] <= item["min_qty"]:
        status = "🟡 **LOW STOCK**"
    else:
        status = "✅ **In stock**"

    expiry_str = ""
    if item.get("expiry_date"):
        expiry_str = f"\n📅 Expiry: {item['expiry_date']}"

    price_str = ""
    if item.get("sell_price"):
        price_str = f"\n💰 Sell price: ₹{item['sell_price']:.0f}/{item['unit']}"

    return (
        f"**{item['name']}** [{item['sku']}]\n"
        f"Stock: {item['qty']} {item['unit']} — {status}\n"
        f"Min threshold: {item['min_qty']} {item['unit']}"
        f"{expiry_str}{price_str}"
    )
