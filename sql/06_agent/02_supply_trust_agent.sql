/* ============================================================
   FILE:      sql/06_agent/02_supply_trust_agent.sql
   PURPOSE:   Cortex Agent over the semantic view + order-decision tool
   RUN AFTER: sql/06_agent/01_get_order_decision.sql
   RERUN:     SAFE
   ============================================================ */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE SUPPLY_TRUST_WH;
USE DATABASE SUPPLY_TRUST_DB;

CREATE OR REPLACE AGENT SUPPLY_TRUST_DB.APP.SUPPLY_TRUST_AGENT
COMMENT = 'Supply-chain copilot that answers only from verified, evidence-backed data'
FROM SPECIFICATION
$$
models:
  orchestration: claude-opus-4-6

instructions:
  orchestration: >
    For any question about whether an order can be fulfilled, shipped, or
    committed, ALWAYS call get_order_decision. Never calculate fulfillment
    from raw inventory numbers yourself.
    Use supply_chain_analyst for analytical questions about suppliers, parts,
    plants, orders, inventory variance, and trust status.
  response: >
    Lead with the decision. Rules:
    1. If decision is REVIEW_REQUIRED, say clearly that the order cannot be
       confirmed because the data is not verified. Never say the order can or
       cannot be fulfilled in that case.
    2. Always show the trust status, the reason, and every evidence row
       (source system, record ID, reported quantity).
    3. If decision is CAN_FULFILL or INSUFFICIENT_STOCK, state the verified
       quantity versus the required quantity.
    4. If line_count is 0, say the order was not found.
    Keep answers short and factual. Do not invent numbers.
  sample_questions:
    - question: "Can we fulfill order ORD_001?"
    - question: "Why is ORD_001 blocked?"
    - question: "Which part has the highest inventory variance?"
    - question: "Which suppliers provide critical parts?"

tools:
  - tool_spec:
      type: cortex_analyst_text_to_sql
      name: supply_chain_analyst
      description: >
        Answers analytical questions about suppliers, parts, plants, order
        requirements, cross-system inventory variance, and trust status.
  - tool_spec:
      type: generic
      name: get_order_decision
      description: >
        Returns the governed fulfillment decision for one order, including
        trust status, reason, and source evidence. Decisions:
        CAN_FULFILL, INSUFFICIENT_STOCK, REVIEW_REQUIRED.
      input_schema:
        type: object
        properties:
          order_id:
            type: string
            description: "Order identifier, for example ORD_001"
        required:
          - order_id

tool_resources:
  supply_chain_analyst:
    semantic_view: SUPPLY_TRUST_DB.SEMANTIC.SUPPLY_CHAIN_TRUST_VIEW
    execution_environment:
      type: warehouse
      warehouse: SUPPLY_TRUST_WH
  get_order_decision:
    type: procedure
    identifier: SUPPLY_TRUST_DB.APP.GET_ORDER_DECISION
    execution_environment:
      type: warehouse
      warehouse: SUPPLY_TRUST_WH
      query_timeout: 60
$$;

-- Confirm the agent was created
SHOW AGENTS IN SCHEMA SUPPLY_TRUST_DB.APP;