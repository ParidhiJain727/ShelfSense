"""
shelfsense/__init__.py
Main pipeline entry point called by the Streamlit UI and the Kaggle notebook.
"""

from shelfsense.gate import gate_route
from shelfsense.orchestrator import classify_intent, dispatch
from shelfsense.config import MAX_HISTORY_TURNS


def process_query(raw_input: str, history: list[dict]) -> tuple[str, list[dict], bool]:
    """
    Main pipeline. Returns (response_text, updated_history, gate_handled).
    gate_handled=True means the gate layer answered it with zero API calls.

    Pipeline:
      1. Gate layer — handles simple queries without any API call
      2. LLM classification (Flash-Lite) — for complex / ambiguous queries
      3. Dispatch to sub-agent — executes the action
      4. History update — trimmed to last MAX_HISTORY_TURNS turns

    history format:
      [{"role": "user"|"model", "parts": ["text"]}, ...]
    """
    # ── Step 1: Gate layer (zero API calls) ───────────────────────────────────
    gate_result = gate_route(raw_input)

    if gate_result["handled"]:
        response = gate_result["fast_answer"]
        history = history + [
            {"role": "user",  "parts": [raw_input]},
            {"role": "model", "parts": [response]},
        ]
        # Keep last MAX_HISTORY_TURNS turns (each turn = 2 entries)
        return response, history[-(MAX_HISTORY_TURNS * 2):], True

    # ── Step 2: LLM intent classification (Flash-Lite) ────────────────────────
    # If the gate already detected an intent, use it as fallback
    gate_intent = gate_result.get("intent")

    try:
        intent_result = classify_intent(raw_input, history)
    except RuntimeError as api_err:
        # API is down — try to fall back to gate-detected intent
        if gate_intent and gate_intent != "unknown":
            from shelfsense.models import IntentResult
            intent_result = IntentResult(
                intent=gate_intent,
                product_name=gate_result.get("product"),
                quantity=gate_result.get("quantity"),
                confidence=0.5,
            )
            response = dispatch(intent_result, gate_result)
            # Append API warning to the response
            response += (
                "\n\n---\n_⚠️ Note: AI model temporarily unavailable (503). "
                "Used keyword-based routing instead._"
            )
        else:
            # No gate intent either — return clear error message
            response = (
                "⚠️ **AI model is temporarily unavailable** (high demand, 503 error).\n\n"
                "Please try again in a few seconds, or use a simpler query that "
                "the gate layer can handle directly:\n"
                "- _'dahi kitna bacha?'_ — check stock\n"
                "- _'bread 5 bik gaye'_ — log a sale\n"
                "- _'kya koi alert hai?'_ — check alerts"
            )
        history = history + [
            {"role": "user",  "parts": [raw_input]},
            {"role": "model", "parts": [response]},
        ]
        return response, history[-(MAX_HISTORY_TURNS * 2):], False

    # ── Step 3: Dispatch to sub-agent ─────────────────────────────────────────
    response = dispatch(intent_result, gate_result)

    # ── Step 4: Update and trim history ───────────────────────────────────────
    history = history + [
        {"role": "user",  "parts": [raw_input]},
        {"role": "model", "parts": [response]},
    ]
    return response, history[-(MAX_HISTORY_TURNS * 2):], False
