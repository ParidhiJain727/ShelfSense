"""
shelfsense/agents/sales_log.py
Sub-agent: record a sale, decrement stock.
No LLM call — pure DB write + formatting.
"""

from shelfsense.database import (
    get_stock_by_name,
    update_stock,
    log_sale,
    write_alert,
)


def run(product_name: str | None, quantity: float | None, unit: str | None) -> str:
    """
    Log a sale and update inventory.
    Returns a human-readable confirmation or error message.
    """
    if not product_name:
        return (
            "🤔 Which product was sold? Please mention the product name.\n"
            "Example: _'bread ke 5 packet bik gaye'_"
        )

    if not quantity or quantity <= 0:
        return (
            f"🤔 How many units of **{product_name}** were sold? "
            f"Please include the quantity.\nExample: _'{product_name} 5 bik gaye'_"
        )

    rows = get_stock_by_name(product_name)
    if not rows:
        return (
            f"🔍 Product **'{product_name}'** not found in inventory. "
            f"Please check the product name."
        )

    item = rows[0]

    # Sanity check: can't sell more than in stock
    if quantity > item["qty"]:
        return (
            f"❌ Cannot log **{quantity} {item['unit']}** sold — "
            f"only **{item['qty']} {item['unit']}** of {item['name']} in stock.\n"
            f"Please verify the quantity and try again."
        )

    # Write to DB
    updated = update_stock(item["sku"], -quantity)
    log_sale(item["sku"], quantity, item.get("sell_price"), "agent")
    new_qty = updated.get("qty", item["qty"] - quantity)

    # Revenue calculation
    revenue_str = ""
    if item.get("sell_price"):
        revenue = item["sell_price"] * quantity
        revenue_str = f"\n💰 Revenue: ₹{revenue:.0f}"

    response = (
        f"✅ **Sale recorded:** {quantity} {item['unit']} of **{item['name']}**\n"
        f"📦 Remaining stock: {new_qty} {item['unit']}{revenue_str}"
    )

    # Auto-alert if stock drops below minimum
    if new_qty <= item["min_qty"]:
        write_alert(
            item["sku"],
            "low_stock" if new_qty > 0 else "out_of_stock",
            f"{item['name']}: only {new_qty} {item['unit']} left (min {item['min_qty']})",
        )
        if new_qty == 0:
            response += f"\n\n⚠️ **ALERT:** {item['name']} is now **OUT OF STOCK!**"
        else:
            response += (
                f"\n\n⚠️ **Warning:** {item['name']} is now below minimum stock level "
                f"({new_qty}/{item['min_qty']} {item['unit']})."
            )

    return response
