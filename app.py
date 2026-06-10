"""
app.py
------
AI Refund Agent Quality Dashboard
Built as a portfolio artifact to demonstrate AI PM evaluation thinking.

Key decisions I made in this build:
  - Dark theme with color-coded labels (green/red/amber/indigo) for instant pattern recognition
  - Quality score displayed prominently — the single number that tells hiring managers
    whether this agent is safe to put in production
  - Separate "Trace Explorer" tab so I can show LangSmith-style step-by-step logging
  - Insights auto-generated from metrics — shows product recommendation thinking
"""

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# ── Load LangSmith secrets from Streamlit Cloud ────────────────────────────────
# In Streamlit Cloud: Settings → Secrets → add LANGCHAIN_API_KEY etc.
# Locally: add them to .env
# When key is present, agent.py's @traceable functions send traces to LangSmith.
# When key is absent, everything still works — tracing is just skipped.
if hasattr(st, "secrets"):
    for key in ["LANGCHAIN_API_KEY", "LANGCHAIN_TRACING_V2", "LANGCHAIN_PROJECT"]:
        if key in st.secrets:
            os.environ[key] = st.secrets[key]

LANGSMITH_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "refund-agent-eval")
LANGSMITH_ENABLED = bool(os.environ.get("LANGCHAIN_API_KEY"))

# Auto-generate sample data if CSV doesn't exist.
# This runs on first boot on Streamlit Cloud (no pre-generated CSV there).
if not os.path.exists("sample_outputs.csv"):
    from generate_sample_data import generate
    generate()

# ── Page config (must be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="AI Refund Agent — Quality Dashboard",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Colour system ──────────────────────────────────────────────────────────────
LABEL_COLOURS = {
    "Grounded":     {"fg": "#22C55E", "bg": "#052e16", "border": "#166534"},
    "Hallucinated": {"fg": "#EF4444", "bg": "#450a0a", "border": "#7f1d1d"},
    "Incomplete":   {"fg": "#F59E0B", "bg": "#451a03", "border": "#92400e"},
    "Uncertain":    {"fg": "#818CF8", "bg": "#1e1b4b", "border": "#3730a3"},
}

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* Base typography */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
code, .mono { font-family: 'JetBrains Mono', monospace; font-size: 12px; }

/* Metric card */
.kpi-card {
    background: #111827;
    border-radius: 10px;
    padding: 18px 20px;
    border-left: 3px solid;
    height: 100%;
}
.kpi-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #6B7280;
    margin-bottom: 6px;
}
.kpi-value {
    font-size: 36px;
    font-weight: 800;
    line-height: 1;
    margin-bottom: 4px;
}
.kpi-sub {
    font-size: 12px;
    color: #6B7280;
}

/* Section label */
.section-tag {
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: #6B7280;
    border-bottom: 1px solid #1F2937;
    padding-bottom: 6px;
    margin-bottom: 16px;
    width: 100%;
}

/* Label pill */
.pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
}

/* Score ring */
.score-ring {
    text-align: center;
    padding: 16px 0;
}
.score-number { font-size: 72px; font-weight: 900; line-height: 1; }
.score-denom  { font-size: 14px; color: #6B7280; }
.score-label  { font-size: 10px; font-weight: 700; text-transform: uppercase;
                letter-spacing: 0.14em; color: #6B7280; margin-top: 6px; }

/* Insight card */
.insight-card {
    background: #111827;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 6px 0;
    font-size: 13px;
    color: #D1D5DB;
    border-left: 3px solid #3B82F6;
}

/* Hide Streamlit chrome */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }

/* Tabs */
.stTabs [data-baseweb="tab"] { font-size: 13px; font-weight: 500; }
.stTabs [aria-selected="true"] { color: #3B82F6 !important; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def kpi(label: str, value: str, sub: str, color: str, border: str):
    st.markdown(f"""
    <div class="kpi-card" style="border-color:{border}">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value" style="color:{color}">{value}</div>
        <div class="kpi-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)


def pill(label: str) -> str:
    c = LABEL_COLOURS.get(label, {"fg": "#9CA3AF", "bg": "#1F2937"})
    return f'<span class="pill" style="color:{c["fg"]};background:{c["bg"]}">{label}</span>'


@st.cache_data
def load_data():
    if os.path.exists("sample_outputs.csv"):
        return pd.read_csv("sample_outputs.csv")
    st.error("⚠️ sample_outputs.csv not found. Run: python generate_sample_data.py")
    return pd.DataFrame()


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔍 Refund Agent")
    st.markdown("**AI Quality Dashboard**")
    st.caption("PM Portfolio — Priyanshu G.")
    st.divider()

    st.markdown("**Filter by Label**")
    show = {
        "Grounded":     st.checkbox("✅ Grounded",     value=True),
        "Hallucinated": st.checkbox("❌ Hallucinated", value=True),
        "Incomplete":   st.checkbox("⚠️ Incomplete",   value=True),
        "Uncertain":    st.checkbox("❓ Uncertain",    value=True),
    }
    st.divider()

    st.markdown("**Filter by Order**")
    order_filter = st.text_input("", placeholder="e.g. ORD-4582", label_visibility="collapsed")

    st.divider()
    st.markdown("**What this project shows**")
    st.caption(
        "How a PM traces an AI agent, labels failure modes, "
        "calculates quality metrics, and recommends product fixes. "
        "No LLM key required to run."
    )
    st.divider()
    st.markdown("**LangSmith**")
    if LANGSMITH_ENABLED:
        st.success("Connected")
        st.caption(f"Project: `{LANGSMITH_PROJECT}`")
        st.markdown("[Open LangSmith ↗](https://smith.langchain.com)")
    else:
        st.warning("Not connected")
        st.caption("Add `LANGCHAIN_API_KEY` in Streamlit → Settings → Secrets to enable real tracing.")
    st.divider()
    st.caption("github.com/Priyanshug09/PM-Portfolio")


# ── Load + filter ──────────────────────────────────────────────────────────────
df = load_data()
if df.empty:
    st.stop()

active_labels = [lbl for lbl, v in show.items() if v]
fdf = df[df["label"].isin(active_labels)]
if order_filter.strip():
    fdf = fdf[fdf["order_id"].str.contains(order_filter.strip(), case=False, na=False)]

from metrics import calculate_metrics, quality_score, insights
m     = calculate_metrics(df)       # always over full dataset
score = quality_score(m)
tips  = insights(m)


# ── Main layout ────────────────────────────────────────────────────────────────
st.markdown("## AI Refund Agent — Quality Dashboard")
st.caption(
    f"Evaluating AI-generated refund answers against ground-truth mock data  •  "
    f"{m['total']} conversations reviewed  •  "
    f"Updated {datetime.now().strftime('%d %b %Y')}"
)
st.divider()

# ── KPI row ────────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    kpi("Total Reviews", str(m["total"]), "conversations", "#3B82F6", "#1D4ED8")
with c2:
    kpi("Grounded", f"{m['grounded_rate']}%", f"{m['grounded_count']} answers",
        LABEL_COLOURS["Grounded"]["fg"], LABEL_COLOURS["Grounded"]["border"])
with c3:
    kpi("Hallucinated", f"{m['hallucination_rate']}%", f"{m['hallucinated_count']} answers",
        LABEL_COLOURS["Hallucinated"]["fg"], LABEL_COLOURS["Hallucinated"]["border"])
with c4:
    kpi("Incomplete", f"{m['incomplete_rate']}%", f"{m['incomplete_count']} answers",
        LABEL_COLOURS["Incomplete"]["fg"], LABEL_COLOURS["Incomplete"]["border"])
with c5:
    kpi("Uncertain", f"{m['uncertain_rate']}%", f"{m['uncertain_count']} answers",
        LABEL_COLOURS["Uncertain"]["fg"], LABEL_COLOURS["Uncertain"]["border"])

st.markdown("<br>", unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📊  Dashboard", "🔎  Conversation Review", "📁  Trace Explorer"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Dashboard
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown('<div class="section-tag">Label Distribution</div>', unsafe_allow_html=True)
        chart_df = pd.DataFrame({
            "Label": ["Grounded", "Hallucinated", "Incomplete", "Uncertain"],
            "Count": [m["grounded_count"], m["hallucinated_count"],
                      m["incomplete_count"], m["uncertain_count"]],
        }).set_index("Label")
        st.bar_chart(chart_df, color="#3B82F6", height=260)

        st.markdown('<div class="section-tag">Hallucination Rate Over Time</div>', unsafe_allow_html=True)
        if "timestamp" in df.columns:
            ts_df = df.copy()
            ts_df["ts"] = pd.to_datetime(ts_df["timestamp"])
            ts_df["is_hallucinated"] = (ts_df["label"] == "Hallucinated").astype(int)
            ts_df["cumulative_hr"] = (
                ts_df["is_hallucinated"].cumsum() / (ts_df.index + 1) * 100
            ).round(1)
            ts_df["conversation_n"] = range(1, len(ts_df) + 1)
            st.line_chart(ts_df.set_index("conversation_n")["cumulative_hr"],
                          color="#EF4444", height=180)
            st.caption("Cumulative hallucination rate as conversations accumulate")

    with col_right:
        st.markdown('<div class="section-tag">Quality Score</div>', unsafe_allow_html=True)
        score_color = (
            "#22C55E" if score >= 70
            else "#F59E0B" if score >= 40
            else "#EF4444"
        )
        score_verdict = (
            "Production-ready" if score >= 70
            else "Needs improvement" if score >= 40
            else "Not production-ready"
        )
        st.markdown(f"""
        <div class="score-ring">
            <div class="score-number" style="color:{score_color}">{score}</div>
            <div class="score-denom">/ 100</div>
            <div class="score-label">{score_verdict}</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.markdown('<div class="section-tag">Performance Metrics</div>', unsafe_allow_html=True)

        col_a, col_b = st.columns(2)
        with col_a:
            if m.get("avg_latency_ms"):
                st.metric("Avg Latency", f"{m['avg_latency_ms']} ms")
        with col_b:
            if m.get("avg_cost_usd"):
                st.metric("Avg Cost / Query", f"${m['avg_cost_usd']:.6f}")
        if m.get("total_cost_usd"):
            st.metric("Total Eval Cost", f"${m['total_cost_usd']:.5f}")

        st.divider()
        st.markdown('<div class="section-tag">Score Formula</div>', unsafe_allow_html=True)
        st.code(
            "score = grounded_rate\n"
            "      - hallucination_rate × 1.5\n"
            "      - incomplete_rate    × 0.5\n"
            "      - uncertain_rate     × 0.25",
            language="text"
        )
        st.caption("Hallucinations penalised 1.5× — they cause direct customer harm.")

    st.divider()
    st.markdown('<div class="section-tag">Product Insights</div>', unsafe_allow_html=True)
    for tip in tips:
        st.markdown(f'<div class="insight-card">{tip}</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Conversation Review
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown(f'<div class="section-tag">Conversation Review — {len(fdf)} shown</div>',
                unsafe_allow_html=True)

    # Individual conversation cards
    for _, row in fdf.iterrows():
        lc = LABEL_COLOURS.get(row["label"], {"fg": "#9CA3AF", "bg": "#1F2937", "border": "#374151"})

        with st.expander(
            f"{pill(row['label'])} &nbsp; **{row['order_id']}** — {row['user_query']}",
            expanded=False
        ):
            col1, col2 = st.columns([1, 1])

            with col1:
                st.markdown("**User Query**")
                st.info(row["user_query"])

                st.markdown("**Expected Answer**")
                st.success(str(row.get("expected_answer", "—")))

            with col2:
                st.markdown("**AI Answer**")
                answer_color = "error" if row["label"] == "Hallucinated" else "warning" if row["label"] in ("Incomplete", "Uncertain") else "success"
                if answer_color == "error":
                    st.error(row["ai_answer"])
                elif answer_color == "warning":
                    st.warning(row["ai_answer"])
                else:
                    st.success(row["ai_answer"])

            st.markdown("**Evaluation**")
            col_a, col_b, col_c = st.columns([1, 2, 2])
            with col_a:
                st.markdown(f'**Label:** {pill(row["label"])}', unsafe_allow_html=True)
                st.caption(f"Intent: `{row.get('intent', '—')}`")
                st.caption(f"Latency: `{row.get('latency_ms', '—')} ms`")
            with col_b:
                st.markdown("**Failure Reason**")
                st.caption(str(row.get("failure_reason", "—")))
            with col_c:
                st.markdown("**Recommended Fix**")
                st.caption(str(row.get("recommended_fix", "—")))

    st.divider()
    st.markdown('<div class="section-tag">Raw Data Table</div>', unsafe_allow_html=True)

    display_cols = [c for c in
        ["order_id", "user_query", "label", "latency_ms", "failure_reason", "recommended_fix"]
        if c in fdf.columns]

    def _style_label(val):
        c = LABEL_COLOURS.get(val, {})
        return f"background-color:{c.get('bg','#1F2937')};color:{c.get('fg','#9CA3AF')};font-weight:700"

    styled = fdf[display_cols].style.map(_style_label, subset=["label"])
    st.dataframe(styled, use_container_width=True, height=350)

    st.divider()
    export_col, _ = st.columns([1, 4])
    with export_col:
        st.download_button(
            label="⬇️  Export CSV",
            data=fdf.to_csv(index=False).encode("utf-8"),
            file_name=f"refund_eval_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Trace Explorer  (simulated LangSmith-style view)
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-tag">Trace Explorer — Simulated LangSmith View</div>',
                unsafe_allow_html=True)
    st.caption(
        "Each trace shows the full agent pipeline: intent detection → data fetch → "
        "answer generation → evaluation label. In production this would live inside LangSmith."
    )

    # Let user pick a conversation to inspect
    query_options = fdf["user_query"].tolist() if not fdf.empty else df["user_query"].tolist()
    order_options = fdf["order_id"].tolist() if not fdf.empty else df["order_id"].tolist()

    combined = [f"{o} | {q}" for o, q in zip(order_options, query_options)]
    if not combined:
        st.info("No conversations match current filter.")
    else:
        selected = st.selectbox("Select a conversation to inspect", combined)
        idx = combined.index(selected)
        row = (fdf if not fdf.empty else df).iloc[idx]

        # Build a fake trace object
        from agent import run_agent, detect_intent
        from mock_data import get_order, get_return_by_order, get_refund_by_order

        order_id = row["order_id"]
        order  = get_order(order_id)
        ret    = get_return_by_order(order_id)
        refund = get_refund_by_order(order_id)

        # ── Trace steps ──
        st.markdown("---")
        st.markdown("#### 🔗 Trace")
        st.caption(f"Run ID: `trace-{abs(hash(row['user_query']))%100000:05d}`  |  "
                   f"Latency: `{row.get('latency_ms', '—')} ms`  |  "
                   f"Tokens: `~{row.get('est_tokens', '—')}`")

        # Step 1
        with st.expander("**Step 1 — User Input**", expanded=True):
            st.code(row["user_query"], language="text")

        # Step 2
        with st.expander("**Step 2 — Intent Detection**", expanded=True):
            intent = detect_intent(row["user_query"])
            st.code(f"intent: {intent}", language="yaml")

        # Step 3
        with st.expander("**Step 3 — Mock API Calls**", expanded=True):
            ctx = {
                "get_order":             {"order_id": order_id, "result": order},
                "get_return_by_order":   {"order_id": order_id, "result": ret},
                "get_refund_by_order":   {"order_id": order_id, "result": refund},
                "get_policy":            {"result": "loaded"}
            }
            st.code(json.dumps(ctx, indent=2, default=str), language="json")

        # Step 4
        with st.expander("**Step 4 — Final AI Answer**", expanded=True):
            lc = LABEL_COLOURS.get(row["label"], {"fg": "#9CA3AF"})
            st.markdown(f"> {row['ai_answer']}")
            st.markdown(
                f"**Label:** <span style='color:{lc['fg']};font-weight:700'>{row['label']}</span>  |  "
                f"**Reason:** {row.get('failure_reason','—')}",
                unsafe_allow_html=True
            )

        # Step 5 — Recommended fix
        with st.expander("**Step 5 — Product Recommendation**", expanded=True):
            fix = row.get("recommended_fix", "—")
            if row["label"] == "Grounded":
                st.success(f"✅ {fix}")
            else:
                st.warning(f"🛠️ {fix}")

        # LangSmith callout
        st.divider()
        st.markdown("#### 🔌 LangSmith Integration")
        st.info(
            "To enable real LangSmith tracing, set `LANGCHAIN_API_KEY` in `.env` and "
            "wrap `run_agent()` with `@traceable` from `langsmith.run_helpers`. "
            "Each run will then appear in your LangSmith project dashboard with full "
            "latency, token counts, and eval scores."
        )
        st.code(
            'from langsmith.run_helpers import traceable\n\n'
            '@traceable(name="refund-agent")\n'
            'def run_agent(question, order_id):\n'
            '    ...  # your existing agent code',
            language="python"
        )

st.divider()
st.caption(
    "AI Refund Agent Quality Dashboard  •  Built by Priyanshu G.  •  "
    "github.com/Priyanshug09/PM-Portfolio  •  "
    "Demonstrates: trace → label → metric → product fix"
)
