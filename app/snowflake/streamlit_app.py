"""
Supply Chain Trust Layer - Snowflake dashboard
The agent console runs outside Snowflake (repo: app/streamlit_app.py).
"""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Supply Chain Trust Layer", page_icon="🛡️", layout="wide")

DB = "SUPPLY_TRUST_DB"

try:
    from snowflake.snowpark.context import get_active_session
    session = get_active_session()
except Exception:
    session = st.connection("snowflake").session()


def run(sql, params=None):
    return session.sql(sql, params=params).to_pandas()


@st.cache_data(ttl=30)
def load(sql):
    return run(sql)


def money(value):
    return "USD {:,.0f}".format(float(value or 0))


ICON = {"REVIEW_REQUIRED": "🔴", "INSUFFICIENT_STOCK": "🟠", "CAN_FULFILL": "🟢"}

st.title("🛡️ Supply Chain Trust Layer")
st.caption("Agents investigate and propose. Snowflake decides trust. Humans approve.")

if st.button("Re-run trust evaluation"):
    msg = run("CALL " + DB + ".TRUST.RUN_TRUST_EVALUATION()").iloc[0, 0]
    st.toast(str(msg))
    st.cache_data.clear()
    st.rerun()

tab_tower, tab_agent, tab_actions, tab_audit = st.tabs(
    ["Control Tower", "Agent Workspace", "Action Queue", "Audit Trail"]
)

risk = load(
    "SELECT ORDER_ID, PRIORITY, REQUIRED_BY, ORDER_VALUE, ORDER_DECISION "
    "FROM " + DB + ".APP.V_ORDER_RISK ORDER BY ORDER_VALUE DESC"
)
variance = load(
    "SELECT PART_ID, PLANT_ID, SOURCE_COUNT, MIN_REPORTED_QUANTITY, "
    "MAX_REPORTED_QUANTITY, VARIANCE_PERCENT, LATEST_EFFECTIVE_AT "
    "FROM " + DB + ".APP.V_INVENTORY_COMPARISON ORDER BY VARIANCE_PERCENT DESC"
)

with tab_tower:
    blocked = risk[risk["ORDER_DECISION"] != "CAN_FULFILL"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Open orders", len(risk))
    k2.metric("Blocked orders", len(blocked))
    k3.metric("Value at risk", money(blocked["ORDER_VALUE"].sum()))
    max_var = variance["VARIANCE_PERCENT"].max() if len(variance) else 0
    k4.metric("Max inventory variance", "{:.0f}%".format(float(max_var or 0)))

    st.subheader("Orders")
    for _, o in risk.iterrows():
        st.markdown(
            ICON.get(o["ORDER_DECISION"], "⚪") + " **" + o["ORDER_ID"] + "** · "
            + money(o["ORDER_VALUE"]) + " · " + str(o["PRIORITY"])
            + " · **" + o["ORDER_DECISION"] + "**"
        )

    if len(risk):
        st.subheader("Order detail")
        order_id = st.selectbox("Order", risk["ORDER_ID"].tolist())
        lines = run(
            "SELECT LINE_NUMBER, PART_NAME, PLANT_ID, REQUIRED_QUANTITY, VERIFIED_QUANTITY, "
            "UNIT, TRUST_STATUS, DECISION, REASON, EVALUATION_ID "
            "FROM " + DB + ".APP.V_ORDER_DECISION WHERE ORDER_ID = ? ORDER BY LINE_NUMBER",
            [order_id],
        )
        for _, line in lines.iterrows():
            text = (
                "**" + line["DECISION"] + "** · " + line["PART_NAME"]
                + " · trust **" + line["TRUST_STATUS"] + "**\n\n" + str(line["REASON"] or "")
            )
            if line["DECISION"] == "REVIEW_REQUIRED":
                st.error(text)
            elif line["DECISION"] == "INSUFFICIENT_STOCK":
                st.warning(text)
            else:
                st.success(text)

            if line["EVALUATION_ID"]:
                evidence = run(
                    "SELECT SS.SOURCE_SYSTEM_NAME AS SOURCE_SYSTEM, "
                    "SR.EXTERNAL_RECORD_ID AS RECORD_ID, EE.EVIDENCE_VALUE AS REPORTED_QUANTITY, "
                    "EE.UNIT, EE.EVIDENCE_ROLE, SR.SOURCE_UPDATED_AT, SS.SYSTEM_OWNER AS OWNER "
                    "FROM " + DB + ".TRUST.EVALUATION_EVIDENCE EE "
                    "JOIN " + DB + ".RAW.SOURCE_RECORD SR ON SR.SOURCE_RECORD_ID = EE.SOURCE_RECORD_ID "
                    "JOIN " + DB + ".RAW.SOURCE_SYSTEM SS ON SS.SOURCE_SYSTEM_ID = SR.SOURCE_SYSTEM_ID "
                    "WHERE EE.EVALUATION_ID = ? ORDER BY SS.SOURCE_SYSTEM_NAME",
                    [line["EVALUATION_ID"]],
                )
                st.write("**Evidence**")
                st.dataframe(evidence, hide_index=True, use_container_width=True)

    st.subheader("Inventory across source systems")
    st.dataframe(variance, hide_index=True, use_container_width=True)

with tab_agent:
    st.info(
        "The agent console (Monitor, Investigator, Planner, approval, Executor, Verifier) "
        "runs in the external deployment of this app. Inside Snowflake, ask questions in "
        "AI & ML > Agents > SUPPLY_TRUST_AGENT."
    )

with tab_actions:
    actions = load(
        "SELECT ACTION_ID, ORDER_ID, ACTION_TYPE, STATUS, ASSIGNED_OWNER, TITLE, "
        "DECIDED_BY, PROPOSED_AT, DECIDED_AT, EXECUTED_AT, VERIFIED_AT "
        "FROM " + DB + ".APP.V_ACTION_QUEUE"
    )
    if len(actions) == 0:
        st.info("No actions yet.")
    else:
        st.dataframe(actions, hide_index=True, use_container_width=True)

with tab_audit:
    history = load(
        "SELECT EVALUATED_AT, ENTITY_ID, STATUS, REASON_CODE, MAX_VARIANCE_PERCENT, "
        "EVALUATED_VALUE, CONTRACT_ID, CONTRACT_VERSION "
        "FROM " + DB + ".TRUST.TRUST_EVALUATION ORDER BY EVALUATED_AT DESC LIMIT 100"
    )
    st.dataframe(history, hide_index=True, use_container_width=True)