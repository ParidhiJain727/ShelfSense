"""
data/seed_inventory.py
Seeds inventory.db with 30 sample products, 2 suppliers, and initial alerts.
Run: python data/seed_inventory.py
"""

import os
import sys
from datetime import date, timedelta

# Ensure the project root is on sys.path so shelfsense imports work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shelfsense.database import init_db, get_db

# Expiry dates relative to today for demo purposes
def _exp(days_from_now: int) -> str:
    return (date.today() + timedelta(days=days_from_now)).isoformat()


# 30 products — 8 have expiry dates within 30 days for immediate alert demo
PRODUCTS = [
    # ── DAIRY ─────────────────────────────────────────────────────────────────
    ("DAIRY001", "Curd 500g",        "dahi",        "dairy",     "packet",  24, 10,  14,  18, 1, _exp(5)),
    ("DAIRY002", "Milk 1L",          "doodh",       "dairy",     "litre",   40, 15,  50,  60, 1, _exp(3)),
    ("DAIRY003", "Paneer 200g",      "paneer",      "dairy",     "packet",   8,  5,  55,  70, 1, _exp(7)),
    ("DAIRY004", "Butter 100g",      "makhan",      "dairy",     "packet",  18,  8,  40,  55, 1, _exp(12)),
    ("DAIRY005", "Ghee 500ml",       "ghee",        "dairy",     "bottle",  10,  4, 250, 310, 1, None),
    ("DAIRY006", "Lassi 200ml",      "lassi",       "dairy",     "packet",  30, 12,  10,  15, 1, _exp(4)),

    # ── GRAIN ─────────────────────────────────────────────────────────────────
    ("GRAIN001", "Basmati Rice 1kg", "chawal",      "grain",     "kg",      60, 20,  65,  85, 1, None),
    ("GRAIN002", "Atta 5kg",         "atta",        "grain",     "packet",  12,  5, 200, 250, 1, None),
    ("GRAIN003", "Toor Dal 1kg",     "arhar dal",   "grain",     "kg",      25, 10, 110, 140, 1, None),
    ("GRAIN004", "Moong Dal 500g",   "moong",       "grain",     "packet",  20,  8,  60,  80, 1, None),
    ("GRAIN005", "Maida 1kg",        "maida",       "grain",     "kg",      15,  6,  40,  55, 1, None),
    ("GRAIN006", "Poha 500g",        "poha",        "grain",     "packet",  18,  7,  35,  48, 1, None),

    # ── SNACK ─────────────────────────────────────────────────────────────────
    ("SNACK001", "Haldirams Bhujia 200g", "bhujia", "snack",     "packet",  30, 10,  42,  60, 2, _exp(25)),
    ("SNACK002", "Lays Classic 50g", "chips",       "snack",     "packet",  50, 20,  12,  20, 2, _exp(60)),
    ("SNACK003", "Parle-G 100g",     "parle g",     "snack",     "packet",  40, 15,  10,  15, 2, None),
    ("SNACK004", "Monaco Biscuit",   "biscuit",     "snack",     "packet",  35, 12,  22,  32, 2, None),
    ("SNACK005", "Kurkure 50g",      "kurkure",     "snack",     "packet",  45, 20,  18,  25, 2, _exp(20)),
    ("SNACK006", "Maggi 2-min 70g",  "maggi",       "snack",     "packet",  60, 25,  14,  18, 2, None),
    ("SNACK007", "Bread Loaf 400g",  "bread",       "snack",     "packet",  20,  8,  25,  35, 2, _exp(8)),

    # ── BEVERAGE ──────────────────────────────────────────────────────────────
    ("BEV001",   "Thums Up 600ml",   "thums up",    "beverage",  "bottle",  48, 20,  30,  40, 2, _exp(180)),
    ("BEV002",   "Sprite 600ml",     "sprite",      "beverage",  "bottle",  36, 15,  30,  40, 2, None),
    ("BEV003",   "Maaza 200ml",      "maaza",       "beverage",  "tetra",   24, 10,  18,  25, 2, _exp(15)),
    ("BEV004",   "Frooti 200ml",     "frooti",      "beverage",  "tetra",   30, 12,  18,  25, 2, _exp(18)),
    ("BEV005",   "Tea Dust 250g",    "chai patti",  "beverage",  "packet",  20,  8,  80, 110, 2, None),
    ("BEV006",   "Nescafe Classic",  "coffee",      "beverage",  "jar",        5,  2, 400, 520, 2, None),

    # ── HOUSEHOLD ─────────────────────────────────────────────────────────────
    ("HOUSE001", "Surf Excel 500g",  "surf",        "household", "packet",  15,  5,  85, 120, 2, None),
    ("HOUSE002", "Lifebuoy Soap",    "sabun",       "household", "piece",   25, 10,  22,  35, 2, None),
    ("HOUSE003", "Colgate 200g",     "toothpaste",  "household", "tube",    12,  5,  85, 115, 2, None),
    ("HOUSE004", "Dettol 250ml",     "dettol",      "household", "bottle",   8,  3, 130, 165, 2, None),
    ("HOUSE005", "Vim Bar 200g",     "vim",         "household", "piece",   20,  8,  22,  30, 2, None),
    ("HOUSE006", "Wheel Detergent",  "kapde dhone", "household", "kg",      10,  4,  75, 100, 2, None),
]

SUPPLIERS = [
    (1, "Ramesh Distributors", "9812345678", "dairy,grain", 2),
    (2, "City Wholesale",      "9723456789", "snack,beverage,household", 1),
]


def seed(force: bool = False) -> None:
    """
    Seed the database.
    If force=False (default) skip seeding if products already exist.
    """
    init_db()
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
        if count > 0 and not force:
            return  # Already seeded

        # Clear existing data for clean re-seed
        conn.execute("DELETE FROM inventory")
        conn.execute("DELETE FROM suppliers")
        conn.execute("DELETE FROM sales_log")
        conn.execute("DELETE FROM alerts")

        # Insert suppliers
        conn.executemany(
            "INSERT OR REPLACE INTO suppliers (id, name, phone, category, lead_days) VALUES (?,?,?,?,?)",
            SUPPLIERS,
        )

        # Insert products
        conn.executemany(
            """INSERT OR REPLACE INTO inventory
               (sku, name, name_hindi, category, unit, qty, min_qty,
                cost_price, sell_price, supplier_id, expiry_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            PRODUCTS,
        )
        conn.commit()
        print(f"[OK] Seeded {len(PRODUCTS)} products and {len(SUPPLIERS)} suppliers.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed(force=True)
    print("Database seeding complete. Run: python -m streamlit run app.py")
