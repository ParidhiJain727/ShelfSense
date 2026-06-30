"""
shelfsense/agents/alert_watch.py
Sub-agent: pure-Python low-stock + expiry scanner.
No LLM call — DB scan + formatting only.
"""

from shelfsense.database import (
    get_low_stock_items,
    get_expiring_items,
    write_alert,
    get_open_alerts,
)
from shelfsense.config import LOW_STOCK_DAYS_AHEAD


def run() -> str:
    """
    Scan inventory for low-stock and near-expiry items.
    Write new alerts to DB and return a formatted summary.
    """
    low = get_low_stock_items()
    expiring = get_expiring_items(days_ahead=LOW_STOCK_DAYS_AHEAD)

    # Deduplicate against already-open alerts
    open_alerts = get_open_alerts()
    open_low_skus = {
        a["sku"] for a in open_alerts if a["alert_type"] in ("low_stock", "out_of_stock")
    }
    open_expiry_skus = {
        a["sku"] for a in open_alerts if a["alert_type"] == "expiry_warning"
    }

    # Write new low-stock alerts
    for item in low:
        if item["sku"] not in open_low_skus:
            alert_type = "out_of_stock" if item["qty"] == 0 else "low_stock"
            write_alert(
                item["sku"],
                alert_type,
                f"{item['name']}: only {item['qty']} {item['unit']} left "
                f"(min {item['min_qty']})",
            )

    # Write new expiry alerts
    for item in expiring:
        if item["sku"] not in open_expiry_skus:
            write_alert(
                item["sku"],
                "expiry_warning",
                f"{item['name']} expires on {item['expiry_date']}",
            )

    # Format response
    parts: list[str] = []

    if low:
        out_items = [i for i in low if i["qty"] == 0]
        low_items = [i for i in low if i["qty"] > 0]

        if out_items:
            lines = [
                f"  ❌ {i['name']}: **OUT OF STOCK** (min {i['min_qty']} {i['unit']})"
                for i in out_items
            ]
            parts.append("**🔴 OUT OF STOCK:**\n" + "\n".join(lines))

        if low_items:
            lines = [
                f"  🟡 {i['name']}: {i['qty']} {i['unit']} (min {i['min_qty']})"
                for i in low_items
            ]
            parts.append("**🟠 LOW STOCK:**\n" + "\n".join(lines))

    if expiring:
        lines = [
            f"  📅 {i['name']} — expires **{i['expiry_date']}**"
            for i in expiring
        ]
        parts.append("**⚠️ EXPIRING SOON (next 7 days):**\n" + "\n".join(lines))

    if not parts:
        return "✅ **All good!** No low-stock or expiry alerts at the moment."

    header = f"📋 **Alert Report** ({len(low)} low-stock, {len(expiring)} expiring soon)\n\n"
    return header + "\n\n".join(parts)
