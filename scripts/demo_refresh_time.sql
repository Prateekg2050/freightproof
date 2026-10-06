/* ============================================================
   FILE:      scripts/demo_refresh_time.sql
   PURPOSE:   DEMO ONLY - re-age synthetic data relative to now
   RERUN:     SAFE
   NOTE:      Real source data is never updated. This exists only
              because demo timestamps age after seeding.
   ============================================================ */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE SUPPLY_TRUST_WH;
USE DATABASE SUPPLY_TRUST_DB;

-- Cooling Fan stays 3 hours old (the STALE scenario); everything else is fresh
UPDATE CORE.INVENTORY_CLAIM
SET EFFECTIVE_AT = DATEADD('MINUTE', IFF(PART_ID = 'PART_FAN_001', -180, -2), CURRENT_TIMESTAMP());

UPDATE RAW.SOURCE_RECORD
SET SOURCE_UPDATED_AT = DATEADD('MINUTE', IFF(SOURCE_RECORD_ID ILIKE '%FAN%', -180, -2), CURRENT_TIMESTAMP());

UPDATE CORE.CUSTOMER_ORDER
SET REQUIRED_BY = DATEADD('DAY', 2, CURRENT_TIMESTAMP());

CALL TRUST.EVALUATE_INVENTORY_TRUST('TC_USABLE_INVENTORY', '1.0');

SELECT ORDER_ID, PART_NAME, TRUST_STATUS, DECISION
FROM APP.V_ORDER_DECISION
ORDER BY ORDER_ID;