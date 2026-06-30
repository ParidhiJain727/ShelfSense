"""
shelfsense/database.py
All SQLite read/write functions. Synchronous only. No ORM.
"""

import sqlite3
from datetime import date, timedelta
from typing import Optional
from rapidfuzz import process, fuzz

from shelfsense.config import DB_PATH, GATE_FUZZY_THRESHOLD


# ── Connection factory ─────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """Return a new SQLite connection with row_factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Schema initialisation ──────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables if they do not already exist."""
    conn = get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS inventory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sku         TEXT UNIQUE NOT NULL,
                name        TEXT NOT NULL,
                name_hindi  TEXT,
                category    TEXT NOT NULL,
                unit        TEXT NOT NULL,
                qty         REAL NOT NULL DEFAULT 0,
                min_qty     REAL NOT NULL DEFAULT 5,
                cost_price  REAL,
                sell_price  REAL,
                supplier_id INTEGER,
                expiry_date TEXT,
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sales_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sku         TEXT NOT NULL,
                qty_sold    REAL NOT NULL,
                sale_price  REAL,
                sold_at     TEXT DEFAULT (datetime('now')),
                notes       TEXT
            );

            CREATE TABLE IF NOT EXISTS suppliers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                phone       TEXT,
                category    TEXT,
                lead_days   INTEGER DEFAULT 2
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sku         TEXT NOT NULL,
                alert_type  TEXT NOT NULL,
                message     TEXT NOT NULL,
                resolved    INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ── Helper ─────────────────────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ── Stock queries ──────────────────────────────────────────────────────────────

def get_stock(sku: str) -> Optional[dict]:
    """Return a single inventory row by SKU, or None if not found."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM inventory WHERE sku = ?", (sku,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_stock_by_name(name: str) -> list[dict]:
    """
    Fuzzy-match product name or Hindi alias against inventory.
    Returns list of matching items (best match first).
    Uses rapidfuzz for matching.
    """
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM inventory").fetchall()
        if not rows:
            return []

        items = [_row_to_dict(r) for r in rows]
        # Build candidate list: (display_name, item_index)
        candidates = []
        for i, item in enumerate(items):
            candidates.append((item["name"].lower(), i))
            if item.get("name_hindi"):
                candidates.append((item["name_hindi"].lower(), i))

        name_lower = name.lower().strip()
        candidate_strings = [c[0] for c in candidates]

        result = process.extractOne(
            name_lower,
            candidate_strings,
            scorer=fuzz.partial_ratio
        )
        if result is None or result[1] < GATE_FUZZY_THRESHOLD:
            return []

        best_index = candidates[result[2]][1]
        # Return best match first; append others that also score well
        matched_indices = {best_index}
        other_results = process.extract(
            name_lower, candidate_strings, scorer=fuzz.partial_ratio, limit=5
        )
        for _, score, idx in other_results:
            if score >= GATE_FUZZY_THRESHOLD:
                matched_indices.add(candidates[idx][1])

        return [items[i] for i in sorted(matched_indices)]
    finally:
        conn.close()


def get_all_inventory() -> list[dict]:
    """Return all inventory rows ordered by category and name."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM inventory ORDER BY category, name"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_stock(sku: str, delta: float) -> dict:
    """
    Add delta to the current qty (negative delta = sale).
    Returns the updated inventory row.
    """
    conn = get_db()
    try:
        conn.execute(
            """UPDATE inventory
               SET qty = MAX(0, qty + ?), updated_at = datetime('now')
               WHERE sku = ?""",
            (delta, sku),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM inventory WHERE sku = ?", (sku,)).fetchone()
        return _row_to_dict(row) if row else {}
    finally:
        conn.close()


def get_low_stock_items(threshold_multiplier: float = 1.0) -> list[dict]:
    """
    Return items where qty <= min_qty * threshold_multiplier.
    Default: exact at or below min threshold.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM inventory WHERE qty <= min_qty * ? ORDER BY qty ASC",
            (threshold_multiplier,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_expiring_items(days_ahead: int = 7) -> list[dict]:
    """Return items whose expiry_date is within the next N days (and not already expired)."""
    conn = get_db()
    try:
        today = date.today().isoformat()
        cutoff = (date.today() + timedelta(days=days_ahead)).isoformat()
        rows = conn.execute(
            """SELECT * FROM inventory
               WHERE expiry_date IS NOT NULL
                 AND expiry_date >= ?
                 AND expiry_date <= ?
               ORDER BY expiry_date ASC""",
            (today, cutoff),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ── Sales log ──────────────────────────────────────────────────────────────────

def log_sale(sku: str, qty: float, price: Optional[float], notes: str) -> int:
    """Insert a sales record and return the new row id."""
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO sales_log (sku, qty_sold, sale_price, notes) VALUES (?, ?, ?, ?)",
            (sku, qty, price, notes),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_sales_summary(days: int = 7) -> list[dict]:
    """Return total qty_sold per sku for the last N days."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT sku, SUM(qty_sold) AS total_sold
               FROM sales_log
               WHERE sold_at >= datetime('now', ?)
               GROUP BY sku
               ORDER BY total_sold DESC""",
            (f"-{days} days",),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ── Alerts ─────────────────────────────────────────────────────────────────────

def write_alert(sku: str, alert_type: str, message: str) -> None:
    """Insert a new unresolved alert. Silently skip if an identical open alert exists."""
    conn = get_db()
    try:
        existing = conn.execute(
            """SELECT id FROM alerts
               WHERE sku = ? AND alert_type = ? AND resolved = 0""",
            (sku, alert_type),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO alerts (sku, alert_type, message) VALUES (?, ?, ?)",
                (sku, alert_type, message),
            )
            conn.commit()
    finally:
        conn.close()


def get_open_alerts() -> list[dict]:
    """Return all unresolved alerts, newest first."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE resolved = 0 ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def resolve_alert(alert_id: int) -> None:
    """Mark an alert as resolved."""
    conn = get_db()
    try:
        conn.execute("UPDATE alerts SET resolved = 1 WHERE id = ?", (alert_id,))
        conn.commit()
    finally:
        conn.close()
