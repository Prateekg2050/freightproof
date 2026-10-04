# freightproof
Proof before every supply-chain decision
Run in Snowsight with ACCOUNTADMIN and COMPUTE_WH:
1. sql/00_setup/01_*atabase_schemas.sql
2. sql/01_tabl*s/raw_tables.sql
3. sql/01_tables/*ore_tables.sql
4. sql/01_tables/tr*st_tables.sql
5. sql/02_views/app_views.sql
6. sql/02_views/order_decision_view.sql
7. sql/03_procedures/evaluate_inventory_trust.sql
8. sql/04_seed/demo_base_data.sql
9. sql/04_seed/demo_scenarios.sql
10. sql/tests/verify_setup.sql