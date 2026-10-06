/* ============================================================
   FILE:      sql/07_agentic/01_order_risk_view.sql
   PURPOSE:   One row per open order with its worst decision and value
   RUN AFTER: sql/02_views/order_decision_view.sql
   RERUN:     SAFE
   ============================================================ */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE SUPPLY_TRUST_WH;
USE DATABASE SUPPLY_TRUST_DB;

CREATE OR REPLACE VIEW APP.V_ORDER_RISK COPY GRANTS AS
SELECT
    O.ORDER_ID,
    O.PRIORITY,
    O.REQUIRED_BY,
    DATEDIFF('HOUR', CURRENT_TIMESTAMP(), O.REQUIRED_BY) AS HOURS_TO_DUE,
    O.ORDER_VALUE,
    O.CURRENCY_CODE,
    COUNT(1) AS LINE_COUNT,
    CASE
        WHEN COUNT_IF(D.DECISION = 'REVIEW_REQUIRED') > 0    THEN 'REVIEW_REQUIRED'
        WHEN COUNT_IF(D.DECISION = 'INSUFFICIENT_STOCK') > 0 THEN 'INSUFFICIENT_STOCK'
        ELSE 'CAN_FULFILL'
    END AS ORDER_DECISION,
    ARRAY_AGG(
        OBJECT_CONSTRUCT_KEEP_NULL(
            'line_number',       D.LINE_NUMBER,
            'part_id',           D.PART_ID,
            'part_name',         D.PART_NAME,
            'plant_id',          D.PLANT_ID,
            'required_quantity', D.REQUIRED_QUANTITY,
            'verified_quantity', D.VERIFIED_QUANTITY,
            'unit',              D.UNIT,
            'trust_status',      D.TRUST_STATUS,
            'decision',          D.DECISION,
            'reason',            D.REASON
        )
    ) WITHIN GROUP (ORDER BY D.LINE_NUMBER) AS LINES
FROM CORE.CUSTOMER_ORDER O
JOIN APP.V_ORDER_DECISION D
  ON D.ORDER_ID = O.ORDER_ID
WHERE O.ORDER_STATUS IN ('OPEN', 'PLANNED', 'IN_PROGRESS')
GROUP BY O.ORDER_ID, O.PRIORITY, O.REQUIRED_BY, O.ORDER_VALUE, O.CURRENCY_CODE;

SELECT ORDER_ID, ORDER_VALUE, ORDER_DECISION, HOURS_TO_DUE
FROM APP.V_ORDER_RISK
ORDER BY ORDER_VALUE DESC;