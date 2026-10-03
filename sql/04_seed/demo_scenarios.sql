/* ============================================================
   FILE:      sql/04_seed/demo_scenarios.sql
   PURPOSE:   Scenario 1: ERP vs WMS inventory conflict (manual evaluation + evidence)
   RUN AFTER: sql/04_seed/demo_base_data.sql
   RERUN:     NOT SAFE - inserts data. To start over, run scripts/reset_database.sql
   ============================================================ */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE SUPPLY_TRUST_WH;
USE DATABASE SUPPLY_TRUST_DB;

/* ERP reports 500 and WMS reports 120.
   Variance = (500 - 120) / 500 * 100 = 76%. Allowed variance = 5%.
   Therefore the result is CONFLICTED.

   NOTE: This evaluation is inserted manually for the MVP.
   It will be replaced by a call to the trust-evaluation stored
   procedure once sql/03_procedures is added. */

INSERT INTO TRUST.TRUST_EVALUATION (
    EVALUATION_ID, CONTRACT_ID, CONTRACT_VERSION, ENTITY_TYPE, ENTITY_ID,
    PART_ID, PLANT_ID, ORDER_ID, METRIC_NAME, EVALUATED_VALUE, UNIT, STATUS,
    REASON_CODE, REASON, SOURCE_COUNT, MAX_VARIANCE_PERCENT, EVALUATED_AT, EXPIRES_AT
)
SELECT
    'EVAL_INV_001', 'TC_USABLE_INVENTORY', '1.0', 'PART_AT_PLANT', 'PART_BATTERY_001@PLANT_BLR_001',
    'PART_BATTERY_001', 'PLANT_BLR_001', 'ORD_001', 'USABLE_INVENTORY', NULL, 'PCS', 'CONFLICTED',
    'VARIANCE_EXCEEDED',
    'ERP reports 500 usable units while WMS reports 120 usable units. The 76% variance exceeds the allowed 5% threshold.',
    2, 76.00, CURRENT_TIMESTAMP(), DATEADD('MINUTE', 60, CURRENT_TIMESTAMP());

/* Evidence for the evaluation */
INSERT INTO TRUST.EVALUATION_EVIDENCE (
    EVALUATION_EVIDENCE_ID, EVALUATION_ID, SOURCE_RECORD_ID, CLAIM_ID,
    EVIDENCE_ROLE, EVIDENCE_VALUE, UNIT, EVIDENCE_NOTE
)
SELECT 'EVIDENCE_EVAL_001_ERP', 'EVAL_INV_001', 'REC_ERP_INV_001', 'CLAIM_ERP_001', 'CONFLICTING', 500, 'PCS', 'ERP inventory claim'
UNION ALL
SELECT 'EVIDENCE_EVAL_001_WMS', 'EVAL_INV_001', 'REC_WMS_INV_001', 'CLAIM_WMS_001', 'CONFLICTING', 120, 'PCS', 'Warehouse inventory claim';
