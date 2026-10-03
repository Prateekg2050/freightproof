/* ============================================================
   FILE:      sql/tests/verify_setup.sql
   PURPOSE:   PASS/FAIL checks for row counts, integrity and the demo conflict
   RUN AFTER: sql/04_seed/demo_scenarios.sql
   RERUN:     SAFE (read-only)
   ============================================================ */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE SUPPLY_TRUST_WH;
USE DATABASE SUPPLY_TRUST_DB;

WITH checks AS (

    -- 1. Row counts: sample data loaded exactly once
    SELECT 'Count: source systems' AS check_name, COUNT(*) AS actual, 3 AS expected FROM RAW.SOURCE_SYSTEM
    UNION ALL SELECT 'Count: source records',       COUNT(*), 2 FROM RAW.SOURCE_RECORD
    UNION ALL SELECT 'Count: suppliers',            COUNT(*), 1 FROM CORE.SUPPLIER
    UNION ALL SELECT 'Count: parts',                COUNT(*), 1 FROM CORE.PART
    UNION ALL SELECT 'Count: plants',               COUNT(*), 1 FROM CORE.PLANT
    UNION ALL SELECT 'Count: supplier-part links',  COUNT(*), 1 FROM CORE.SUPPLIER_PART
    UNION ALL SELECT 'Count: entity mappings',      COUNT(*), 4 FROM CORE.ENTITY_MAPPING
    UNION ALL SELECT 'Count: inventory claims',     COUNT(*), 2 FROM CORE.INVENTORY_CLAIM
    UNION ALL SELECT 'Count: orders',               COUNT(*), 1 FROM CORE.CUSTOMER_ORDER
    UNION ALL SELECT 'Count: order lines',          COUNT(*), 1 FROM CORE.ORDER_LINE
    UNION ALL SELECT 'Count: business definitions', COUNT(*), 1 FROM TRUST.BUSINESS_DEFINITION
    UNION ALL SELECT 'Count: trust contracts',      COUNT(*), 1 FROM TRUST.TRUST_CONTRACT
    UNION ALL SELECT 'Count: trust evaluations',    COUNT(*), 1 FROM TRUST.TRUST_EVALUATION
    UNION ALL SELECT 'Count: evaluation evidence',  COUNT(*), 2 FROM TRUST.EVALUATION_EVIDENCE

    -- 2. Integrity: orphan records (Snowflake does not enforce FKs)
    UNION ALL
    SELECT 'Integrity: claims without source record', COUNT(*), 0
    FROM CORE.INVENTORY_CLAIM c
    LEFT JOIN RAW.SOURCE_RECORD r ON c.SOURCE_RECORD_ID = r.SOURCE_RECORD_ID
    WHERE r.SOURCE_RECORD_ID IS NULL
    UNION ALL
    SELECT 'Integrity: claims without part/plant', COUNT(*), 0
    FROM CORE.INVENTORY_CLAIM c
    LEFT JOIN CORE.PART p  ON c.PART_ID  = p.PART_ID
    LEFT JOIN CORE.PLANT l ON c.PLANT_ID = l.PLANT_ID
    WHERE p.PART_ID IS NULL OR l.PLANT_ID IS NULL
    UNION ALL
    SELECT 'Integrity: order lines without order', COUNT(*), 0
    FROM CORE.ORDER_LINE ol
    LEFT JOIN CORE.CUSTOMER_ORDER o ON ol.ORDER_ID = o.ORDER_ID
    WHERE o.ORDER_ID IS NULL
    UNION ALL
    SELECT 'Integrity: evidence without evaluation', COUNT(*), 0
    FROM TRUST.EVALUATION_EVIDENCE e
    LEFT JOIN TRUST.TRUST_EVALUATION t ON e.EVALUATION_ID = t.EVALUATION_ID
    WHERE t.EVALUATION_ID IS NULL
    UNION ALL
    SELECT 'Integrity: unconfirmed mappings', COUNT(*), 0
    FROM CORE.ENTITY_MAPPING WHERE MAPPING_STATUS <> 'CONFIRMED'

    -- 3. Business logic: the demo conflict is detected
    UNION ALL
    SELECT 'Logic: inventory variance = 76%', COUNT(*), 1
    FROM APP.V_INVENTORY_COMPARISON
    WHERE PART_ID = 'PART_BATTERY_001' AND VARIANCE_PERCENT = 76
    UNION ALL
    SELECT 'Logic: trust status CONFLICTED', COUNT(*), 1
    FROM APP.V_LATEST_TRUST_STATUS
    WHERE STATUS = 'CONFLICTED' AND ORDER_ID = 'ORD_001'
)
SELECT
    check_name,
    actual,
    expected,
    IFF(actual = expected, 'PASS', 'FAIL') AS result
FROM checks
ORDER BY result, check_name;

-- Evidence trail for the demo evaluation
SELECT
    E.EVALUATION_ID, E.STATUS, E.REASON, EE.EVIDENCE_ROLE,
    SS.SOURCE_SYSTEM_NAME, EE.EVIDENCE_VALUE, EE.UNIT,
    SR.EXTERNAL_RECORD_ID, SR.SOURCE_UPDATED_AT
FROM TRUST.TRUST_EVALUATION E
JOIN TRUST.EVALUATION_EVIDENCE EE ON E.EVALUATION_ID = EE.EVALUATION_ID
JOIN RAW.SOURCE_RECORD SR         ON EE.SOURCE_RECORD_ID = SR.SOURCE_RECORD_ID
JOIN RAW.SOURCE_SYSTEM SS         ON SR.SOURCE_SYSTEM_ID = SS.SOURCE_SYSTEM_ID
WHERE E.EVALUATION_ID = 'EVAL_INV_001'
ORDER BY SS.SOURCE_SYSTEM_NAME;

/* Stop compute */
ALTER WAREHOUSE SUPPLY_TRUST_WH SUSPEND;
