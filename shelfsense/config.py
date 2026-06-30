"""
shelfsense/config.py
Central configuration. All constants are defined here.
No API keys are hard-coded — they are loaded from .env only.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Gemini API ─────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ── Model names ────────────────────────────────────────────────────────────────
# Primary: used for ALL intent classification and response formatting
MODEL_LITE = "gemini-2.5-flash-lite"
# Secondary: called ONLY inside the Reorder sub-agent
MODEL_FULL = "gemini-2.5-flash"

# ── Database ───────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "inventory.db")

# ── Alert / scan windows ───────────────────────────────────────────────────────
LOW_STOCK_DAYS_AHEAD = 7        # expiry warning window in days

# ── LLM call constraints ───────────────────────────────────────────────────────
MAX_HISTORY_TURNS = 2           # never send more than 2 turns to Gemini
MAX_OUTPUT_TOKENS = 512         # cap on Gemini output tokens per call

# ── Gate layer ─────────────────────────────────────────────────────────────────
GATE_FUZZY_THRESHOLD = 70       # rapidfuzz score cutoff for product matching
