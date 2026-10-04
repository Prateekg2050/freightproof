/* ============================================================
   FILE:      sql/04_seed/demo_scenarios.sql
   PURPOSE:   Run the initial conflicting inventory scenario
   RUN AFTER: sql/03_procedures/evaluate_inventory_trust.sql
   RERUN:     NOT SAFE - creates another evaluation history row
   ============================================================ */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE SUPPLY_TRUST_WH;
USE DATABASE SUPPLY_TRUST_DB;

/*
Scenario:

Order ORD_001 requires 150 Battery Cells.

ERP reports:
500 usable units

Warehouse reports:
120 usable units

Variance:
76%

Trust contract allows:
5%

Expected result:
CONFLICTED
*/

CALL TRUST.EVALUATE_INVENTORY_TRUST(
    'TC_USABLE_INVENTORY',
    '1.0'
);