"""
FILE:    app/streamlit_app.py
PURPOSE: Supply Chain Trust Layer dashboard (Streamlit in Snowflake)
"""

import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="Supply Chain Trust Layer", layout="wide")
session = get_active_session()

DB = "SUPPLY_TRUST_DB"


def run(sql, params=None):
    return session.sql(sql, params=params).to_pandas()


# ---------------- Header ----------------
st.title("Supply Chain Trust Layer")
st.caption("Every decision is checked against a trust contract before it is shown.")

col_a, col_b = st.columns([3, 1])
with col_b:
    if st.button("Re-run trust evaluation", use_container_width=True):
        msg = session.sql(
            f"CALL {DB}.TRUST.EVALUATE_INVENTORY_TRUST('TC_USABLE_INVENTORY', '1.0')"
        ).collect()[0][0]
        st.toast(msg)
        st.rerun()

# ---------------- KPIs ----------------
decisions = run(f"""
    SELECT ORDER_ID, LINE_NUMBER, PART_NAME, PLANT_ID, REQUIRED_QUANTITY, UNIT,
           TRUST_STATUS, VERIFIED_QUANTITY, DECISION, REASON, EVALUATION_ID
    FROM {DB}.APP.V_ORDER_DECISION
    ORDER BY ORDER_ID, LINE_NUMBER
""")

variance = run(f"""
    SELECT PART_ID, PLANT_ID, QUANTITY_TYPE, UNIT, SOURCE_COUNT,
           MIN_REPORTED_QUANTITY, MAX_REPORTED_QUANTITY, VARIANCE_PERCENT,
           LATEST_EFFECTIVE_AT
    FROM {DB}.APP.V_INVENTORY_COMPARISON
""")

k1, k2, k3 = st.columns(3)
k1.metric("Order lines", len(decisions))
k2.metric("Need review", int((decisions["DECISION"] == "REVIEW_REQUIRED").sum()))
k3.metric(
    "Max inventory variance",
    f"{variance['VARIANCE_PERCENT'].max():.0f}%" if not variance.empty else "n/a",
)

st.divider()

# ---------------- Order decision ----------------
st.subheader("Order decisions")

if decisions.empty:
    st.info("No orders found.")
else:
    order_ids = decisions["ORDER_ID"].unique().tolist()
    selected = st.selectbox("Order", order_ids)

    for _, row in decisions[decisions["ORDER_ID"] == selected].iterrows():
        headline = (
            f"**{row['PART_NAME']}** at {row['PLANT_ID']} | "
            f"required {row['REQUIRED_QUANTITY']:.0f} {row['UNIT']} | "
            f"trust status: **{row['TRUST_STATUS']}**"
        )
        decision = row["DECISION"]

        if decision == "REVIEW_REQUIRED":
            st.error(f"REVIEW REQUIRED: the order cannot be confirmed.\n\n{headline}")
        elif decision == "INSUFFICIENT_STOCK":
            st.warning(
                f"INSUFFICIENT STOCK: verified {row['VERIFIED_QUANTITY']:.0f} "
                f"vs required {row['REQUIRED_QUANTITY']:.0f}.\n\n{headline}"
            )
        else:
            st.success(
                f"CAN FULFILL: verified {row['VERIFIED_QUANTITY']:.0f} "
                f"vs required {row['REQUIRED_QUANTITY']:.0f}.\n\n{headline}"
            )

        st.write(f"**Reason:** {row['REASON']}")

        if row["EVALUATION_ID"]:
            evidence = run(
                f"""
                SELECT SS.SOURCE_SYSTEM_NAME AS SOURCE_SYSTEM,
                       SR.EXTERNAL_RECORD_ID AS RECORD_ID,
                       EE.EVIDENCE_VALUE     AS REPORTED_QUANTITY,
                       EE.UNIT,
                       EE.EVIDENCE_ROLE,
                       SR.SOURCE_UPDATED_AT
                FROM {DB}.TRUST.EVALUATION_EVIDENCE EE
                JOIN {DB}.RAW.SOURCE_RECORD SR ON SR.SOURCE_RECORD_ID = EE.SOURCE_RECORD_ID
                JOIN {DB}.RAW.SOURCE_SYSTEM SS ON SS.SOURCE_SYSTEM_ID = SR.SOURCE_SYSTEM_ID
                WHERE EE.EVALUATION_ID = ?
                ORDER BY SS.SOURCE_SYSTEM_NAME
                """,
                params=[row["EVALUATION_ID"]],
            )
            st.write("**Evidence**")
            st.dataframe(evidence, use_container_width=True, hide_index=True)

st.divider()

# ---------------- Inventory comparison ----------------
st.subheader("Inventory across source systems")
st.dataframe(variance, use_container_width=True, hide_index=True)

# ---------------- Audit trail ----------------
with st.expander("Audit trail: all trust evaluations"):
    history = run(f"""
        SELECT EVALUATED_AT, ENTITY_ID, STATUS, REASON_CODE,
               MAX_VARIANCE_PERCENT, EVALUATED_VALUE, CONTRACT_ID, CONTRACT_VERSION
        FROM {DB}.TRUST.TRUST_EVALUATION
        ORDER BY EVALUATED_AT DESC
    """)
    st.dataframe(history, use_container_width=True, hide_index=True)

st.caption("Ask questions in natural language: AI & ML → Agents → SUPPLY_TRUST_AGENT")