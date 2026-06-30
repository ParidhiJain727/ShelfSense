"""
shelfsense/gate.py
Gate layer: language detection + Hinglish normaliser + keyword matcher.

This is the most important file. It MUST handle ≥60 % of common queries
without touching any Gemini API. Zero external network calls allowed here.
"""

import re
from rapidfuzz import process, fuzz
from shelfsense.config import GATE_FUZZY_THRESHOLD


# ── Hinglish → English product alias map ──────────────────────────────────────
# Covers all 30 seed products plus common misspellings / phonetic variants.
HINGLISH_MAP: dict[str, str] = {
    # dairy
    "dahi":        "curd",
    "doodh":       "milk",
    "paneer":      "paneer",
    "makhan":      "butter",
    "ghee":        "ghee",
    "lassi":       "lassi",
    # grain
    "chawal":      "rice",
    "atta":        "flour",
    "maida":       "maida",
    "arhar":       "toor dal",
    "arhar dal":   "toor dal",
    "moong":       "moong dal",
    "poha":        "poha",
    # snack
    "bhujia":      "bhujia",
    "chips":       "lays",
    "parle g":     "parle-g",
    "parleg":      "parle-g",
    "biscuit":     "biscuit",
    "kurkure":     "kurkure",
    "maggi":       "maggi",
    "noodles":     "maggi",
    "bread":       "bread",
    # beverage
    "thums up":    "thums up",
    "thumsup":     "thums up",
    "sprite":      "sprite",
    "maaza":       "maaza",
    "frooti":      "frooti",
    "chai patti":  "tea dust",
    "chai":        "tea dust",
    "coffee":      "nescafe",
    # household
    "surf":        "surf excel",
    "sabun":       "lifebuoy soap",
    "soap":        "lifebuoy soap",
    "toothpaste":  "colgate",
    "paste":       "colgate",
    "dettol":      "dettol",
    "vim":         "vim bar",
    "kapde dhone": "wheel detergent",
    # generic
    "namak":       "salt",
    "cheeni":      "sugar",
    "tel":         "oil",
    "dal":         "toor dal",
    "aloo":        "potato",
}

# ── Intent keyword rules (order matters — first match wins) ───────────────────
INTENT_RULES: list[tuple[str, list[str]]] = [
    # alert_watch must come BEFORE stock_check to catch "low stock" phrases
    ("alert_watch", [
        "alert", "khatam", "finish", "expir", "warning",
        "band", "out of", "problem", "issue", "khatam ho",
        "danger", "low stock", "koi khatam", "koi alert",
        "koi item low", "khatam ho raha",
    ]),
    ("stock_check", [
        "kitna", "how much", "stock", "bacha", "left", "available",
        "hai kitna", "remaining", "check", "show", "list", "total",
        "inventory", "kitne", "bachha",
    ]),
    ("sales_log", [
        "bika", "sold", "bik gaye", "bik gaya", "sale", "bikri",
        "sell", "diya", "gaya", "sell kiya", "becha", "de diya",
        "gram bika", "packet bika",
    ]),
    ("reorder", [
        "reorder", "order", "mangao", "mangana", "purchase",
        "buy more", "stock karo", "supplier", "order karo",
        "order dena", "kitna order", "kya order",
    ]),
]


# ── Text normalisation ─────────────────────────────────────────────────────────

def normalise(text: str) -> str:
    """
    Lowercase, strip punctuation, replace Hinglish words with English equivalents.
    Multi-word aliases must be processed before single-word ones to avoid partial replacements.
    """
    text = text.lower().strip()
    # Strip common punctuation (including Hindi danda)
    text = re.sub(r"[?!।,।।\.\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Sort by length desc so multi-word phrases match before their component words
    sorted_aliases = sorted(HINGLISH_MAP.items(), key=lambda x: -len(x[0]))
    for hindi, english in sorted_aliases:
        # Word-boundary aware replacement
        text = re.sub(rf"(?<!\w){re.escape(hindi)}(?!\w)", english, text)

    return text.strip()


# ── Entity extraction ──────────────────────────────────────────────────────────

# Common Hindi/English stop words to exclude from word-by-word matching
STOP_WORDS = {
    "hai", "kya", "ka", "ki", "ke", "ko", "me", "se", "ho", "ek",
    "the", "a", "an", "is", "of", "in", "it", "be", "do", "to",
    "for", "on", "at", "as", "by", "up", "so", "or", "and", "any",
    "all", "not", "no", "that", "this", "with", "are", "was", "had",
    "has", "have", "you", "we", "he", "she", "they", "its", "from",
    "kitna", "kitne", "bacha", "bachha", "available", "left", "stock",
    "bik", "bika", "gaye", "gaya", "packet", "litre", "kilo", "piece",
    "show", "check", "how", "much", "remaining", "current", "total",
    "sold", "sale", "units", "unit", "list", "karo", "dikhao",
}


def extract_product(text: str, threshold: int = GATE_FUZZY_THRESHOLD) -> str | None:
    """
    Fuzzy-match a product name from the text against the live inventory.
    Strategy:
      1. Full-text partial_ratio match
      2. Word-by-word match (excluding stop words)
    Returns the inventory item name string or None if no confident match.
    """
    from shelfsense.database import get_all_inventory

    all_items = get_all_inventory()
    if not all_items:
        return None

    candidates: list[str] = []
    for item in all_items:
        candidates.append(item["name"].lower())
        if item.get("name_hindi"):
            candidates.append(item["name_hindi"].lower())

    # Strategy 1: full text match
    result = process.extractOne(text, candidates, scorer=fuzz.partial_ratio)
    if result and result[1] >= threshold:
        return result[0]

    # Strategy 2: word-by-word, skip stop words and very short words
    best_score = 0
    best_match = None
    words = [w for w in text.split() if len(w) > 2 and w not in STOP_WORDS]
    for word in words:
        res = process.extractOne(word, candidates, scorer=fuzz.partial_ratio)
        if res and res[1] > best_score:
            best_score = res[1]
            best_match = res[0]

    return best_match if best_score >= threshold else None


def extract_quantity(text: str) -> float | None:
    """
    Extract a numeric quantity from text like '5 packet', '2 kg', or 'teen'.
    Handles Hindi number words as well.
    """
    WORD_NUMS: dict[str, int] = {
        "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5,
        "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
        "gyara": 11, "bara": 12, "tera": 13, "choda": 14, "pandara": 15,
        "bees": 20, "pachees": 25, "tees": 30,
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    for word, val in WORD_NUMS.items():
        if re.search(rf"\b{re.escape(word)}\b", text):
            return float(val)
    nums = re.findall(r"\d+\.?\d*", text)
    return float(nums[0]) if nums else None


# ── Main gate router ───────────────────────────────────────────────────────────

def gate_route(raw_input: str) -> dict:
    """
    Evaluate the input query without calling any LLM.

    Returns a gate result dict:
    {
      "handled":    bool,        # True = gate answered it, skip LLM
      "intent":     str | None,
      "product":    str | None,
      "quantity":   float | None,
      "fast_answer": str | None, # Pre-built response if handled=True
    }
    """
    norm = normalise(raw_input)

    # ── Intent detection ───────────────────────────────────────────────────────
    intent: str | None = None
    for candidate_intent, keywords in INTENT_RULES:
        if any(kw in norm for kw in keywords):
            intent = candidate_intent
            break

    product = extract_product(norm)
    quantity = extract_quantity(norm)

    # ── Fast-path 1: stock check with known product ────────────────────────────
    if intent == "stock_check" and product:
        from shelfsense.database import get_stock_by_name
        rows = get_stock_by_name(product)
        if rows:
            item = rows[0]
            if item["qty"] == 0:
                status_str = "⚠️ OUT OF STOCK"
            elif item["qty"] <= item["min_qty"]:
                status_str = "🟡 Low stock"
            else:
                status_str = "✅ In stock"
            fast_answer = (
                f"{item['name']}: **{item['qty']} {item['unit']}** — {status_str}\n"
                f"_(Min threshold: {item['min_qty']} {item['unit']})_"
            )
            return {
                "handled": True, "intent": intent,
                "product": product, "quantity": None,
                "fast_answer": fast_answer,
            }

    # ── Fast-path 2: sale log with known product + quantity ────────────────────
    if intent == "sales_log" and product and quantity:
        from shelfsense.database import get_stock_by_name, update_stock, log_sale
        rows = get_stock_by_name(product)
        if rows:
            item = rows[0]
            if quantity > item["qty"]:
                fast_answer = (
                    f"❌ Cannot log {quantity} {item['unit']} sold — "
                    f"only {item['qty']} in stock. Please verify the quantity."
                )
                return {
                    "handled": True, "intent": intent,
                    "product": product, "quantity": quantity,
                    "fast_answer": fast_answer,
                }
            updated = update_stock(item["sku"], -quantity)
            log_sale(item["sku"], quantity, item.get("sell_price"), "gate layer")
            new_qty = updated.get("qty", item["qty"] - quantity)
            warn = ""
            if new_qty <= item["min_qty"]:
                from shelfsense.database import write_alert
                write_alert(
                    item["sku"], "low_stock",
                    f"{item['name']}: only {new_qty} {item['unit']} left (min {item['min_qty']})"
                )
                warn = f"\n⚠️ **{item['name']}** is now below minimum stock level!"
            fast_answer = (
                f"✅ Recorded: **{quantity} {item['unit']}** of {item['name']} sold. "
                f"Remaining stock: {new_qty} {item['unit']}.{warn}"
            )
            return {
                "handled": True, "intent": intent,
                "product": product, "quantity": quantity,
                "fast_answer": fast_answer,
            }

    # ── Not handled — pass to LLM ──────────────────────────────────────────────
    return {
        "handled": False, "intent": intent,
        "product": product, "quantity": quantity,
        "fast_answer": None,
    }
