/* ============================================================
   FILE:      scripts/demo_recount.sql
   PURPOSE:   Demo step 2 - a stock recount resolves the conflict
   RUN AFTER: sql/tests/verify_setup.sql (all PASS)
   RERUN:     NOT SAFE - run once per clean build
   ============================================================ */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE SUPPLY_TRUST_WH;
USE DATABASE SUPPLY_TRUST_DB;

/* Scenario:
   After the conflict was flagged, the warehouse team recounted stock.
   ERP is corrected from 500 to 125, and the warehouse confirms 120.
   New records are ADDED; the old ones are kept for the audit trail. */

-- 1. New source records (version 2)
INSERT INTO RAW.SOURCE_RECORD (
    SOURCE_RECORD_ID, SOURCE_SYSTEM_ID, EXTERNAL_RECORD_ID, RECORD_TYPE,
    RECORD_VERSION, PAYLOAD, SOURCE_UPDATED_AT, INGESTION_STATUS
)
SELECT 'REC_ERP_INV_002', 'SYS_ERP', 'ERP-INV-5001', 'INVENTORY', 2,
       PARSE_JSON('{"part_number":"ERP-BAT-01","plant_code":"BLR01","quantity":125,"unit":"PCS","quantity_type":"USABLE","note":"corrected after recount"}'),
       CURRENT_TIMESTAMP(), 'VALIDATED'
UNION ALL
SELECT 'REC_WMS_INV_002', 'SYS_WMS', 'WMS-STOCK-8801', 'INVENTORY', 2,
       PARSE_JSON('{"sku":"WH-BATTERY-A","warehouse":"BANGALORE-WH-1","quantity":120,"unit":"PCS","quantity_type":"USABLE"}'),
       CURRENT_TIMESTAMP(), 'VALIDATED';

-- 2. New inventory claims
INSERT INTO CORE.INVENTORY_CLAIM (
    CLAIM_ID, SOURCE_RECORD_ID, SOURCE_SYSTEM_ID, PART_ID, PLANT_ID,
    QUANTITY, UNIT, QUANTITY_TYPE, EFFECTIVE_AT
)
SELECT 'CLAIM_ERP_002', 'REC_ERP_INV_002', 'SYS_ERP', 'PART_BATTERY_001', 'PLANT_BLR_001',
       125, 'PCS', 'USABLE', CURRENT_TIMESTAMP()
UNION ALL
SELECT 'CLAIM_WMS_002', 'REC_WMS_INV_002', 'SYS_WMS', 'PART_BATTERY_001', 'PLANT_BLR_001',
       120, 'PCS', 'USABLE', CURRENT_TIMESTAMP();

-- 3. Re-run the trust engine
CALL TRUST.EVALUATE_INVENTORY_TRUST('TC_USABLE_INVENTORY', '1.0');

-- 4. Check the new decision
-- Expected: ORD_001 | 150 | VERIFIED | 120 | INSUFFICIENT_STOCK
SELECT ORDER_ID, REQUIRED_QUANTITY, TRUST_STATUS, VERIFIED_QUANTITY, DECISION, REASON
FROM APP.V_ORDER_DECISION;