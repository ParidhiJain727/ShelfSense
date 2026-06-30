"""
shelfsense/orchestrator.py
Intent classifier + dispatcher.
Uses MODEL_LITE (gemini-2.5-flash-lite) ONLY. Never calls MODEL_FULL.
Uses google.genai SDK (v2+).
Includes retry logic with exponential backoff for transient 503 errors.
"""

import json
import time
import google.genai as genai
import google.genai.types as types

from shelfsense.config import GEMINI_API_KEY, MODEL_LITE, MAX_OUTPUT_TOKENS, MAX_HISTORY_TURNS
from shelfsense.models import IntentResult

# ── System prompt — ≤150 tokens (verified: ~35 words / ~47 tokens) ────────────
SYSTEM_PROMPT = (
    "You are ShelfSense, an inventory assistant for a kirana shop. "
    "Classify the user's message into exactly one intent and extract entities. "
    "Return ONLY valid JSON matching the IntentResult schema. No explanation."
)

# JSON schema mirroring IntentResult
INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["stock_check", "sales_log", "alert_watch", "reorder", "unknown"],
        },
        "product_name":    {"type": "string",  "nullable": True},
        "quantity":        {"type": "number",  "nullable": True},
        "unit":            {"type": "string",  "nullable": True},
        "timeframe_days":  {"type": "integer", "nullable": True},
        "confidence":      {"type": "number"},
    },
    "required": ["intent"],
}

# Retry settings for transient 503/429 errors
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2.0


def _make_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)


def classify_intent(user_message: str, history: list[dict]) -> IntentResult:
    """
    Call Gemini Flash-Lite to classify user intent when the gate layer
    could not handle the query.

    Includes retry with exponential backoff for transient API errors.
    Falls back to gate-based intent if all retries fail.

    history: last MAX_HISTORY_TURNS turns as
             [{"role": "user"|"model", "parts": ["text"]}, ...]
    """
    client = _make_client()

    # Build contents list from history + current message
    trimmed_history = history[-(MAX_HISTORY_TURNS * 2):]
    contents = []
    for turn in trimmed_history:
        role = turn.get("role", "user")
        text = turn["parts"][0] if turn.get("parts") else ""
        contents.append(
            types.Content(role=role, parts=[types.Part(text=text)])
        )
    contents.append(
        types.Content(role="user", parts=[types.Part(text=user_message)])
    )

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL_LITE,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=INTENT_SCHEMA,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    temperature=0.1,
                ),
            )
            data = json.loads(response.text)
            return IntentResult(**data)

        except Exception as e:
            last_error = e
            error_str = str(e)
            # Retry on transient server errors
            if any(code in error_str for code in ["503", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED"]):
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_DELAY_SECONDS * (2 ** attempt)
                    time.sleep(wait)
                    continue
            # Non-retryable error — break immediately
            break

    # All retries exhausted — raise to let caller show user-friendly error
    raise RuntimeError(
        f"Gemini API unavailable after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )


def dispatch(intent_result: IntentResult, gate_result: dict) -> str:
    """
    Route the classified intent to the correct sub-agent.
    Merges entity info from both the LLM result and gate result.
    Returns a human-readable markdown response string.
    """
    from shelfsense.agents.stock_check import run as stock_check_run
    from shelfsense.agents.sales_log import run as sales_log_run
    from shelfsense.agents.alert_watch import run as alert_watch_run
    from shelfsense.agents.reorder import run as reorder_run

    intent = intent_result.intent
    # Prefer LLM-extracted entities; fall back to gate-extracted ones
    product = intent_result.product_name or gate_result.get("product")
    qty = intent_result.quantity or gate_result.get("quantity")

    if intent == "stock_check":
        return stock_check_run(product)
    elif intent == "sales_log":
        return sales_log_run(product, qty, intent_result.unit)
    elif intent == "alert_watch":
        return alert_watch_run()
    elif intent == "reorder":
        return reorder_run()
    else:
        return (
            "🤔 Sorry, I didn't understand that. Try:\n"
            "- _'dahi kitna bacha?'_ — check stock\n"
            "- _'bread 5 bik gaye'_ — log a sale\n"
            "- _'kya koi alert hai?'_ — check alerts\n"
            "- _'reorder plan banao'_ — get reorder suggestions"
        )
