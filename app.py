"""
app.py — ShelfSense Streamlit UI
Entry point. Run: streamlit run app.py
"""

import streamlit as st
from shelfsense import process_query
from shelfsense.database import init_db, get_open_alerts, resolve_alert, get_all_inventory
from data.seed_inventory import seed

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ShelfSense — Kirana AI Concierge",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://github.com/your-repo/shelfsense",
        "About": "ShelfSense — AI inventory concierge for kirana shops. Kaggle Capstone 2026.",
    },
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --primary:      #6c63ff;
    --primary-dark: #4a42cc;
    --success:      #22c55e;
    --warning:      #f59e0b;
    --danger:       #ef4444;
    --surface:      #1e1e2e;
    --surface2:     #2a2a3d;
    --text:         #e2e8f0;
    --muted:        #94a3b8;
    --border:       rgba(108,99,255,0.3);
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    border-right: 1px solid var(--border);
}

/* Main content */
.main .block-container {
    padding-top: 1.5rem;
    max-width: 860px;
}

/* Title banner */
.shelfsense-header {
    background: linear-gradient(135deg, #6c63ff 0%, #a855f7 50%, #ec4899 100%);
    border-radius: 16px;
    padding: 1.5rem 2rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 8px 32px rgba(108,99,255,0.35);
}
.shelfsense-header h1 {
    color: #fff;
    font-size: 2rem;
    font-weight: 700;
    margin: 0;
    letter-spacing: -0.5px;
}
.shelfsense-header p {
    color: rgba(255,255,255,0.85);
    font-size: 0.95rem;
    margin: 0.4rem 0 0;
}

/* Example chips */
.chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 1rem;
}

/* Chat bubbles */
[data-testid="stChatMessage"] {
    border-radius: 12px;
    margin-bottom: 0.5rem;
}

/* Alert badges in sidebar */
.alert-badge {
    padding: 0.4rem 0.7rem;
    border-radius: 8px;
    font-size: 0.82rem;
    margin-bottom: 0.4rem;
    background: rgba(239,68,68,0.15);
    border-left: 3px solid #ef4444;
    color: #fca5a5;
}
.alert-badge.warning {
    background: rgba(245,158,11,0.15);
    border-left: 3px solid #f59e0b;
    color: #fcd34d;
}
.alert-badge.expiry {
    background: rgba(168,85,247,0.15);
    border-left: 3px solid #a855f7;
    color: #d8b4fe;
}

/* Stat cards */
.stat-card {
    background: rgba(108,99,255,0.12);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 0.8rem 1rem;
    text-align: center;
}
.stat-card .stat-num { font-size: 1.6rem; font-weight: 700; color: #a5b4fc; }
.stat-card .stat-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }

/* Token efficiency pill */
.token-pill {
    display: inline-block;
    background: rgba(34,197,94,0.2);
    border: 1px solid rgba(34,197,94,0.4);
    color: #86efac;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-left: 8px;
}
</style>
""", unsafe_allow_html=True)


# ── Session state initialisation ──────────────────────────────────────────────
if "db_ready" not in st.session_state:
    init_db()
    seed()  # No-op if already seeded
    st.session_state.db_ready = True
    st.session_state.history = []          # Gemini chat history (trimmed)
    st.session_state.messages = []         # UI display messages
    st.session_state.api_calls = 0         # LLM call counter for display
    st.session_state.gate_hits = 0         # Gate-handled counter


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏪 ShelfSense")
    st.markdown("_AI Inventory Concierge_")
    st.divider()

    # ── Live Alert Panel ──────────────────────────────────────────────────────
    st.markdown("#### 🔔 Live Alerts")
    alerts = get_open_alerts()

    if alerts:
        for a in alerts[:12]:
            if a["alert_type"] == "out_of_stock":
                css_class = "alert-badge"
                icon = "🔴"
            elif a["alert_type"] == "low_stock":
                css_class = "alert-badge warning"
                icon = "🟡"
            else:
                css_class = "alert-badge expiry"
                icon = "🟣"
            st.markdown(
                f'<div class="{css_class}">{icon} {a["message"]}</div>',
                unsafe_allow_html=True,
            )
        if len(alerts) > 12:
            st.caption(f"...and {len(alerts)-12} more alerts")
    else:
        st.success("✅ No open alerts")

    if st.button("🔄 Refresh Alerts", use_container_width=True):
        st.rerun()

    st.divider()

    # ── Inventory Stats ───────────────────────────────────────────────────────
    st.markdown("#### 📊 Quick Stats")
    all_items = get_all_inventory()
    total_items = len(all_items)
    low_count = sum(1 for i in all_items if 0 < i["qty"] <= i["min_qty"])
    out_count = sum(1 for i in all_items if i["qty"] == 0)

    col1, col2 = st.columns(2)
    col1.metric("📦 Items", total_items)
    col2.metric("⚠️ Low Stock", low_count, delta_color="inverse")
    if out_count:
        st.error(f"❌ {out_count} items OUT OF STOCK")

    st.divider()

    # ── Token Efficiency Counter ──────────────────────────────────────────────
    st.markdown("#### ⚡ Token Efficiency")
    total_queries = st.session_state.api_calls + st.session_state.gate_hits
    if total_queries > 0:
        gate_pct = int(st.session_state.gate_hits / total_queries * 100)
        st.markdown(
            f"Gate handled: **{st.session_state.gate_hits}** queries "
            f"<span class='token-pill'>{gate_pct}% API-free</span>",
            unsafe_allow_html=True,
        )
        st.markdown(f"LLM calls made: **{st.session_state.api_calls}**")
    else:
        st.caption("Start chatting to see stats")

    st.divider()

    # ── Quick Actions ─────────────────────────────────────────────────────────
    st.markdown("#### 🛠️ Tools")
    if st.button("🌱 Re-seed Database", use_container_width=True):
        seed(force=True)
        st.success("Database re-seeded!")
        st.rerun()

    if st.button("📉 Simulate Low Stock (Demo)", use_container_width=True, help="Reduces several items below min threshold to trigger reorder alerts"):
        from shelfsense.database import get_db
        conn = get_db()
        try:
            # Set several items to critically low levels for demo
            demo_updates = [
                ("DAIRY001", 3),   # Curd: 3 (min 10)
                ("DAIRY002", 5),   # Milk: 5 (min 15)
                ("GRAIN001", 8),   # Rice: 8 (min 20)
                ("SNACK007", 2),   # Bread: 2 (min 8)
                ("BEV001", 4),     # Thums Up: 4 (min 20)
                ("HOUSE001", 1),   # Surf Excel: 1 (min 5)
            ]
            for sku, qty in demo_updates:
                conn.execute("UPDATE inventory SET qty=? WHERE sku=?", (qty, sku))
            conn.commit()
        finally:
            conn.close()
        st.warning("Low stock simulated! Now try asking 'is week kya reorder karna chahiye?'")
        st.rerun()

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.history = []
        st.rerun()


# ── Main Content ──────────────────────────────────────────────────────────────

# Header banner
st.markdown("""
<div class="shelfsense-header">
    <h1>🏪 ShelfSense</h1>
    <p>Your AI-powered kirana shop inventory concierge — ask in English, Hindi, or Hinglish</p>
</div>
""", unsafe_allow_html=True)

# ── Example query chips ───────────────────────────────────────────────────────
st.markdown("**💡 Try these queries:**")
examples = [
    ("📦", "dahi kitna bacha hai?"),
    ("💰", "bread ke 5 packet bik gaye"),
    ("⚠️", "kya koi item low stock hai?"),
    ("🔄", "is week kya reorder karna chahiye?"),
    ("📋", "show all stock"),
    ("🚨", "expiry alerts dikhao"),
]

# Render chips in 3 columns
chip_cols = st.columns(3)
for i, (icon, ex) in enumerate(examples):
    if chip_cols[i % 3].button(f"{icon} {ex}", key=f"chip_{i}", use_container_width=True):
        st.session_state.pending_input = ex

# ── Chat display ──────────────────────────────────────────────────────────────
st.divider()

for msg in st.session_state.messages:
    role = msg["role"]
    with st.chat_message(role, avatar="🧑‍💼" if role == "user" else "🤖"):
        st.markdown(msg["content"])

# ── Chat input ────────────────────────────────────────────────────────────────
user_input = st.chat_input("Type your query here — dahi kitna? bread bik gaya? reorder?")

# Handle chip click
if "pending_input" in st.session_state:
    user_input = st.session_state.pop("pending_input")

if user_input:
    # Display user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(user_input)

    # Process and display assistant response
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("ShelfSense is thinking..."):
            response, st.session_state.history, gate_handled = process_query(
                user_input, st.session_state.history
            )
            if gate_handled:
                st.session_state.gate_hits += 1
            else:
                st.session_state.api_calls += 1
        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
    st.rerun()

