# freightproof
Proof before every supply-chain decision
Run in Snowsight with ACCOUNTADMIN and COMPUTE_WH:
1. sql/00_setup → 01_tables → 02_views → 03_procedures
2. sql/04_seed  (only once; use scripts/reset_database.sql to start over)
3. sql/tests/verify_setup.sql  → all checks should PASS
4. CALL TRUST.EVALUATE_INVENTORY_TRUST('TC_USABLE_INVENTORY', '1.0');