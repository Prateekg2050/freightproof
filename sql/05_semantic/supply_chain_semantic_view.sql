/* ============================================================
   FILE:      sql/05_semantic/supply_chain_semantic_view.sql
   PURPOSE:   Define governed supply-chain business semantics
   RUN AFTER: sql/02_views/order_decision_view.sql
   RERUN:     SAFE
   ============================================================ */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE SUPPLY_TRUST_WH;
USE DATABASE SUPPLY_TRUST_DB;
USE SCHEMA SEMANTIC;


/* ============================================================
   SUPPLY-CHAIN TRUST SEMANTIC VIEW

   Logical entities:
   - Supplier
   - Part
   - Plant
   - Supplier Part
   - Order Requirement
   - Inventory Comparison
   - Trust Status

   This view centralizes business meaning for analytics and
   future Cortex Agent integration.
   ============================================================ */

CREATE OR REPLACE SEMANTIC VIEW SEMANTIC.SUPPLY_CHAIN_TRUST_VIEW

TABLES (

    suppliers AS CORE.SUPPLIER
        PRIMARY KEY (SUPPLIER_ID)
        WITH SYNONYMS = ('vendors', 'providers')
        COMMENT = 'Canonical suppliers that provide parts',

    parts AS CORE.PART
        PRIMARY KEY (PART_ID)
        WITH SYNONYMS = ('components', 'materials', 'items')
        COMMENT = 'Canonical parts and components used for fulfillment',

    plants AS CORE.PLANT
        PRIMARY KEY (PLANT_ID)
        WITH SYNONYMS = ('factories', 'facilities', 'locations')
        COMMENT = 'Manufacturing or fulfillment plants',

    supplier_parts AS CORE.SUPPLIER_PART
        PRIMARY KEY (SUPPLIER_ID, PART_ID)
        COMMENT = 'Relationship between suppliers and the parts they provide',

    order_requirements AS APP.V_ORDER_REQUIREMENT
        PRIMARY KEY (ORDER_LINE_ID)
        COMMENT = 'Parts and quantities required by customer orders',

    inventory_comparison AS APP.V_INVENTORY_COMPARISON
        PRIMARY KEY (
            PART_ID,
            PLANT_ID,
            QUANTITY_TYPE,
            UNIT
        )
        COMMENT = 'Comparison of inventory claims across source systems',

    trust_status AS APP.V_LATEST_TRUST_STATUS
        PRIMARY KEY (EVALUATION_ID)
        COMMENT = 'Latest trust evaluation for a business entity'

)

RELATIONSHIPS (

    supplier_parts_to_supplier AS
        supplier_parts (SUPPLIER_ID)
        REFERENCES suppliers,

    supplier_parts_to_part AS
        supplier_parts (PART_ID)
        REFERENCES parts,

    order_requirements_to_part AS
        order_requirements (PART_ID)
        REFERENCES parts,

    order_requirements_to_plant AS
        order_requirements (PLANT_ID)
        REFERENCES plants,

    inventory_comparison_to_part AS
        inventory_comparison (PART_ID)
        REFERENCES parts,

    inventory_comparison_to_plant AS
        inventory_comparison (PLANT_ID)
        REFERENCES plants,

    trust_status_to_part AS
        trust_status (PART_ID)
        REFERENCES parts,

    trust_status_to_plant AS
        trust_status (PLANT_ID)
        REFERENCES plants

)

FACTS (

    supplier_parts.lead_time_days AS LEAD_TIME_DAYS
        COMMENT = 'Expected supplier lead time in days',

    supplier_parts.risk_score AS RISK_SCORE
        COMMENT = 'Supplier risk score from 0 to 100',

    order_requirements.required_quantity AS REQUIRED_QUANTITY
        COMMENT = 'Quantity required by an order line',

    order_requirements.order_value AS ORDER_VALUE
        COMMENT = 'Monetary value of an order',

    inventory_comparison.source_count AS SOURCE_COUNT
        COMMENT = 'Number of systems reporting the inventory value',

    inventory_comparison.minimum_reported_quantity
        AS MIN_REPORTED_QUANTITY
        COMMENT = 'Lowest quantity reported across source systems',

    inventory_comparison.maximum_reported_quantity
        AS MAX_REPORTED_QUANTITY
        COMMENT = 'Highest quantity reported across source systems',

    inventory_comparison.absolute_variance
        AS ABSOLUTE_VARIANCE
        COMMENT = 'Difference between the highest and lowest quantities',

    inventory_comparison.variance_percent
        AS VARIANCE_PERCENT
        COMMENT = 'Percentage disagreement between inventory sources',

    trust_status.evaluated_value AS EVALUATED_VALUE
        COMMENT = 'Verified conservative value when the trust contract passes',

    trust_status.maximum_variance_percent
        AS MAX_VARIANCE_PERCENT
        COMMENT = 'Maximum variance found during trust evaluation'

)

DIMENSIONS (

    suppliers.supplier_id AS SUPPLIER_ID
        WITH SYNONYMS = ('vendor id')
        COMMENT = 'Canonical supplier identifier',

    suppliers.supplier_name AS SUPPLIER_NAME
        WITH SYNONYMS = ('vendor name')
        COMMENT = 'Supplier business name',

    suppliers.country_code AS SUPPLIER_COUNTRY_CODE
        COMMENT = 'Country in which the supplier operates',

    suppliers.supplier_status AS STATUS
        COMMENT = 'Current supplier status',

    parts.part_id AS PART_ID
        WITH SYNONYMS = ('component id', 'material id', 'item id')
        COMMENT = 'Canonical part identifier',

    parts.part_name AS PART_NAME
        WITH SYNONYMS = ('component name', 'material name', 'item name')
        COMMENT = 'Business name of the part',

    parts.part_criticality AS CRITICALITY
        COMMENT = 'Supply-chain criticality of the part',

    parts.base_unit AS BASE_UNIT
        COMMENT = 'Standard measurement unit for the part',

    plants.plant_id AS PLANT_ID
        WITH SYNONYMS = ('factory id', 'facility id')
        COMMENT = 'Canonical plant identifier',

    plants.plant_name AS PLANT_NAME
        WITH SYNONYMS = ('factory name', 'facility name')
        COMMENT = 'Plant or facility name',

    plants.city AS PLANT_CITY
        COMMENT = 'City where the plant is located',

    order_requirements.order_id AS ORDER_ID
        WITH SYNONYMS = ('customer order', 'sales order')
        COMMENT = 'Canonical customer order identifier',

    order_requirements.order_status AS ORDER_STATUS
        COMMENT = 'Current operational state of the order',

    order_requirements.priority AS ORDER_PRIORITY
        COMMENT = 'Priority assigned to the order',

    order_requirements.required_by AS REQUIRED_BY
        COMMENT = 'Date and time by which the order is required',

    order_requirements.currency_code AS CURRENCY_CODE
        COMMENT = 'Currency used for the order value',

    inventory_comparison.quantity_type AS QUANTITY_TYPE
        COMMENT = 'Meaning of the inventory quantity, such as usable or on hand',

    inventory_comparison.inventory_unit AS UNIT
        COMMENT = 'Measurement unit used by inventory claims',

    trust_status.trust_status AS STATUS
        WITH SYNONYMS = ('verification status', 'data trust status')
        COMMENT = 'Trust result such as VERIFIED, CONFLICTED or STALE',

    trust_status.reason_code AS REASON_CODE
        COMMENT = 'Machine-readable reason for the trust result',

    trust_status.reason AS REASON
        COMMENT = 'Human-readable explanation for the trust result',

    trust_status.metric_name AS METRIC_NAME
        COMMENT = 'Governed business metric evaluated by the trust contract',

    trust_status.evaluated_at AS EVALUATED_AT
        COMMENT = 'Time at which the trust contract was evaluated'

)

METRICS (

    suppliers.supplier_count AS COUNT(SUPPLIER_ID)
        COMMENT = 'Number of suppliers',

    parts.part_count AS COUNT(PART_ID)
        COMMENT = 'Number of parts',

    plants.plant_count AS COUNT(PLANT_ID)
        COMMENT = 'Number of plants',

    order_requirements.order_count AS COUNT(DISTINCT ORDER_ID)
        COMMENT = 'Number of distinct customer orders',

    order_requirements.total_required_quantity
        AS SUM(REQUIRED_QUANTITY)
        COMMENT = 'Total quantity required across order lines',

    order_requirements.total_order_value
        AS SUM(ORDER_VALUE)
        COMMENT = 'Total monetary value of orders',

    inventory_comparison.average_inventory_variance
        AS AVG(VARIANCE_PERCENT)
        COMMENT = 'Average inventory variance across business entities',

    inventory_comparison.maximum_inventory_variance
        AS MAX(VARIANCE_PERCENT)
        COMMENT = 'Largest inventory variance detected',

    trust_status.trust_evaluation_count
        AS COUNT(EVALUATION_ID)
        COMMENT = 'Number of latest trust evaluations'

)

COMMENT = 'Governed semantic layer for supply-chain entities, inventory comparisons, orders and trust evaluations';