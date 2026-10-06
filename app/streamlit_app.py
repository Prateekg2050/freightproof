"""
FILE:    app/streamlit_app.py
PURPOSE: Supply Chain Trust Layer UI
MODES:   Inside Snowflake  -> dashboard (Snowpark session)
         Local / Community -> dashboard + LangGraph agent console
RUN:     streamlit run app/streamlit_app.py   (from repo root)
"""

import os
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Supply Chain Trust Layer", page_icon="🛡️", layout="wide")

DB = "SUPPLY_TRUST_DB"
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"


# ---------------- Mode detection ----------------
def load_secrets_into_env():
    try:
        for key, value in st.secrets.items():
            if isinstance(value, str):
                os.environ.setdefault(key, value)
    except Exception:
        pass


SNOWPARK = None
try:
    from snowflake.snowpark.context import get_active_session
    SNOWPARK = get_active_session()
except Exception:
    SNOWPARK = None

AGENTS_AVAILABLE = False
AGENT_IMPORT_ERROR = ""
if SNOWPARK is None:
    load_secrets_into_env()
    if BACKEND_DIR.exists() and str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    try:
        from langgraph.types import Command
        from app.graph import build_graph
        from app.snowflake_client import query as backend_query
        AGENTS_AVAILABLE = True
    except Exception as exc:
        AGENT_IMPORT_ERROR = str(exc)

if SNOWPARK is None and not AGENTS_AVAILABLE:
    st.error(f"No Snowflake session and backend not importable: {AGENT_IMPORT_ERROR}")
    st.stop()


# ---------------- Data access (works in both modes) ----------------
def run(sql: str, params=None) -> pd.DataFrame:
    """Use %s placeholders; converted to ? for Snowpark."""
    if SNOWPARK is not None:
        return SNOWPARK.sql(sql.replace("%s", "?"), params=params).to_pandas()
    return pd.DataFrame(backend_query(sql, tuple(params) if params else None))


@st.cache_data(ttl=30)
def load(sql: str) -> pd.DataFrame:
    return run(sql)


def money(value) -> str:
    return f"USD {float(value or 0):,.0f}"


DECISION_STYLE = {
    "REVIEW_REQUIRED": ("🔴", "error"),
    "INSUFFICIENT_STOCK": ("🟠", "warning"),
    "CAN_FULFILL": ("🟢", "success"),
}
AGENT_ICON = {
    "monitor": "🛰️", "investigator": "🔎", "planner": "🧭",
    "approval": "✋", "executor": "⚙️", "verifier": "✅",
}


# ---------------- Access gate (public deployments only) ----------------
if SNOWPARK is None and os.getenv("APP_PASSWORD") and not st.session_state.get("authenticated"):
    st.title("Supply Chain Trust Layer")
    code = st.text_input("Access code", type="password")
    if code == os.getenv("APP_PASSWORD"):
        st.session_state.authenticated = True
        st.rerun()
    elif code:
        st.error("Wrong access code")
    st.stop()


# ---------------- Header ----------------
st.title("🛡️ Supply Chain Trust Layer")
st.caption("Agents investigate and propose. Snowflake decides trust. Humans approve.")

col_a, col_b = st.columns([4, 1])
with col_b:
    if st.button("Re-run trust evaluation", use_container_width=True):
        msg = run(f"CALL {DB}.TRUST.RUN_TRUST_EVALUATION()").iloc[0, 0]
        st.toast(str(msg))
        st.cache_data.clear()
        st.rerun()

tab_tower, tab_agent, tab_actions, tab_audit = st.tabs(
    ["Control Tower", "Agent Workspace", "Action Queue", "Audit Trail"]
)

# ---------------- Control Tower ----------------
with tab_tower:
    risk = load(f"""
        SELECT ORDER_ID, PRIORITY, REQUIRED_BY, ORDER_VALUE, ORDER_DECISION
        FROM {DB}.APP.V_ORDER_RISK ORDER BY ORDER_VALUE DESC
    """)
    variance = load(f"""
        SELECT PART_ID, PLANT_ID, SOURCE_COUNT, MIN_REPORTED_QUANTITY,
               MAX_REPORTED_QUANTITY, VARIANCE_PERCENT, LATEST_EFFECTIVE_AT
        FROM {DB}.APP.V_INVENTORY_COMPARISON ORDER BY VARIANCE_PERCENT DESC
    """)

    blocked = risk[risk["ORDER_DECISION"] != "CAN_FULFILL"] if not risk.empty else risk
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Open orders", len(risk))
    k2.metric("Blocked orders", len(blocked))
    k3.metric("Value at risk", money(blocked["ORDER_VALUE"].sum() if not blocked.empty else 0))
    k4.metric("Max inventory variance",
              f"{float(variance['VARIANCE_PERCENT'].max()):.0f}%" if not variance.empty else "n/a")

    st.subheader("Orders")
    for _, o in risk.iterrows():
        icon, _ = DECISION_STYLE.get(o["ORDER_DECISION"], ("⚪", "info"))
        st.markdown(f"{icon} **{o['ORDER_ID']}** · {money(o['ORDER_VALUE'])} · "
                    f"{o['PRIORITY']} · **{o['ORDER_DECISION']}**")

    if not risk.empty:
        st.subheader("Order detail")
        order_id = st.selectbox("Order", risk["ORDER_ID"].tolist())
        lines = run(f"""
            SELECT LINE_NUMBER, PART_NAME, PLANT_ID, REQUIRED_QUANTITY, VERIFIED_QUANTITY,
                   UNIT, TRUST_STATUS, DECISION, REASON, EVALUATION_ID
            FROM {DB}.APP.V_ORDER_DECISION
            WHERE ORDER_ID = %s ORDER BY LINE_NUMBER
        """, [order_id])

        for _, line in lines.iterrows():
            _, style = DECISION_STYLE.get(line["DECISION"], ("⚪", "info"))
            verified = line["VERIFIED_QUANTITY"]
            qty = f" · verified {float(verified):,.0f} vs required " \
                  f"{float(line['REQUIRED_QUANTITY']):,.0f} {line['UNIT']}" if pd.notna(verified) else ""
            getattr(st, style)(
                f"**{line['DECISION']}** · {line['PART_NAME']} at {line['PLANT_ID']} · "
                f"trust **{line['TRUST_STATUS']}**{qty}\n\n{line['REASON'] or ''}"
            )
            if line["EVALUATION_ID"]:
                evidence = run(f"""
                    SELECT SS.SOURCE_SYSTEM_NAME AS SOURCE_SYSTEM, SR.EXTERNAL_RECORD_ID AS RECORD_ID,
                           EE.EVIDENCE_VALUE AS REPORTED_QUANTITY, EE.UNIT, EE.EVIDENCE_ROLE,
                           SR.SOURCE_UPDATED_AT, SS.SYSTEM_OWNER AS OWNER
                    FROM {DB}.TRUST.EVALUATION_EVIDENCE EE
                    JOIN {DB}.RAW.SOURCE_RECORD SR ON SR.SOURCE_RECORD_ID = EE.SOURCE_RECORD_ID
                    JOIN {DB}.RAW.SOURCE_SYSTEM SS ON SS.SOURCE_SYSTEM_ID = SR.SOURCE_SYSTEM_ID
                    WHERE EE.EVALUATION_ID = %s ORDER BY SS.SOURCE_SYSTEM_NAME
                """, [line["EVALUATION_ID"]])
                st.write("**Evidence**")
                st.dataframe(evidence, hide_index=True, use_container_width=True)

    st.subheader("Inventory across source systems")
    st.dataframe(variance, hide_index=True, use_container_width=True)

# ---------------- Agent Workspace ----------------
with tab_agent:
    if not AGENTS_AVAILABLE:
        st.info("The agent console runs in the external deployment of this app "
                "(LangGraph backend). Inside Snowflake, ask questions in "
                "AI & ML > Agents > SUPPLY_TRUST_AGENT.")
    else:
        @st.cache_resource
        def get_graph():
            return build_graph()

        graph = get_graph()
        if "thread_id" not in st.session_state:
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.log = []

        def cfg():
            return {"configurable": {"thread_id": st.session_state.thread_id}}

        def render_step(step):
            icon = AGENT_ICON.get(step["agent"], "•")
            st.markdown(f"{icon} **{step['agent'].title()}** · `{step['step']}` — {step['detail']}")

        def stream_run(payload):
            with st.status("Agents working...", expanded=True) as status:
                for chunk in graph.stream(payload, cfg(), stream_mode="updates"):
                    for node, update in chunk.items():
                        if node.startswith("__") or not update:
                            continue
                        for step in update.get("trace", []):
                            st.session_state.log.append(step)
                            render_step(step)
                status.update(label="Stage complete", state="complete")
            st.cache_data.clear()
            st.rerun()

        snapshot = graph.get_state(cfg())
        pending = [i for t in snapshot.tasks for i in (t.interrupts or [])]

        if not pending:
            c1, c2 = st.columns([3, 1])
            preset = c2.selectbox("Quick pick", ["morning scan", "check ORD_001",
                                                 "check ORD_003", "check ORD_004"])
            request = c1.text_input("Request", value=preset)
            dry_run = st.checkbox("Dry run (plan only, nothing saved)")
            b1, b2 = st.columns([1, 5])
            if b1.button("Run agents", type="primary"):
                st.session_state.thread_id = str(uuid.uuid4())
                st.session_state.log = []
                stream_run({"request": request, "dry_run": dry_run, "trace": []})
            if b2.button("Clear"):
                st.session_state.thread_id = str(uuid.uuid4())
                st.session_state.log = []
                st.rerun()

        if st.session_state.log:
            st.subheader("Agent steps")
            for step in st.session_state.log:
                render_step(step)

        if pending:
            payload = pending[0].value
            st.subheader("✋ Approval needed")
            st.info("The graph is paused. Nothing runs until a named person decides.")
            with st.form("approval_form"):
                name = st.text_input("Your name (approver)")
                choices, notes = {}, {}
                for a in payload["actions"]:
                    st.markdown(f"**{a['title']}** · `{a['action_type']}` · urgency {a['urgency']}")
                    st.caption(f"Assigned to {a['assigned_owner']} ({a['assigned_system']}); cc {a['cc']}")
                    for s in a["steps"]:
                        st.markdown(f"- {s}")
                    st.markdown(f"**Done when:** {a['success_criteria']}  \n**Hold:** {a['hold']}")
                    with st.expander("Message to owner"):
                        st.write(a.get("message") or "")
                    choices[a["action_id"]] = st.radio(
                        "Decision", ["Approve", "Reject", "Leave pending"],
                        key=f"d_{a['action_id']}", horizontal=True)
                    notes[a["action_id"]] = st.text_input("Note", key=f"n_{a['action_id']}")
                    st.divider()
                submitted = st.form_submit_button("Submit decisions", type="primary")
            if submitted:
                decisions = [
                    {"action_id": aid,
                     "decision": "APPROVED" if c == "Approve" else "REJECTED",
                     "decided_by": name, "note": notes[aid]}
                    for aid, c in choices.items() if c != "Leave pending"
                ]
                stream_run(Command(resume={"decisions": decisions}))

        values = snapshot.values or {}
        if values.get("briefing"):
            st.subheader("🛰️ Briefing")
            st.write(values["briefing"])
        if values.get("investigation"):
            inv = values["investigation"]
            st.subheader(f"🔎 Investigation · {inv['order_id']}")
            st.write(inv.get("explanation", ""))
        for v in values.get("verifications") or []:
            st.subheader(f"✅ Verification · cycle {v.get('cycle')}")
            st.markdown(f"**{v.get('decision_before')} → {v.get('decision_after')}**")
            st.write(v.get("summary", ""))
            st.caption(f"Next: {v.get('next')}")

# ---------------- Action Queue ----------------
with tab_actions:
    actions = load(f"""
        SELECT ACTION_ID, ORDER_ID, ACTION_TYPE, STATUS, ASSIGNED_OWNER, TITLE,
               DECIDED_BY, PROPOSED_AT, DECIDED_AT, EXECUTED_AT, VERIFIED_AT
        FROM {DB}.APP.V_ACTION_QUEUE
    """)
    if actions.empty:
        st.info("No actions yet. Run the agents in the Agent Workspace.")
    else:
        counts = actions["STATUS"].value_counts()
        for col, (status, n) in zip(st.columns(len(counts)), counts.items()):
            col.metric(status, int(n))
        st.dataframe(actions, hide_index=True, use_container_width=True)

# ---------------- Audit Trail ----------------
with tab_audit:
    history = load(f"""
        SELECT EVALUATED_AT, ENTITY_ID, STATUS, REASON_CODE, MAX_VARIANCE_PERCENT,
               EVALUATED_VALUE, CONTRACT_ID, CONTRACT_VERSION
        FROM {DB}.TRUST.TRUST_EVALUATION
        ORDER BY EVALUATED_AT DESC LIMIT 100
    """)
    st.dataframe(history, hide_index=True, use_container_width=True)