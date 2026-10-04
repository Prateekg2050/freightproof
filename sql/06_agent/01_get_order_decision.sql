/* ============================================================
   FILE:      sql/06_agent/01_get_order_decision.sql
   PURPOSE:   Read-only agent tool: order decision + evidence as JSON
   RUN AFTER: sql/05_semantic/supply_chain_semantic_view.sql
   RERUN:     SAFE
   ============================================================ */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE SUPPLY_TRUST_WH;
USE DATABASE SUPPLY_TRUST_DB;

CREATE OR REPLACE PROCEDURE APP.GET_ORDER_DECISION(ORDER_ID VARCHAR)
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    V_RESULT VARIANT;
BEGIN
    SELECT OBJECT_CONSTRUCT_KEEP_NULL(
        'order_id',   :ORDER_ID,
        'line_count', COUNT(1),
        'lines', ARRAY_AGG(
            OBJECT_CONSTRUCT_KEEP_NULL(
                'line_number',       D.LINE_NUMBER,
                'part_name',         D.PART_NAME,
                'plant_id',          D.PLANT_ID,
                'required_quantity', D.REQUIRED_QUANTITY,
                'unit',              D.UNIT,
                'trust_status',      D.TRUST_STATUS,
                'verified_quantity', D.VERIFIED_QUANTITY,
                'decision',          D.DECISION,
                'reason',            D.REASON,
                'evidence',          EV.EVIDENCE
            )
        )
    )
    INTO :V_RESULT
    FROM APP.V_ORDER_DECISION D
    LEFT JOIN (
        SELECT
            EE.EVALUATION_ID,
            ARRAY_AGG(
                OBJECT_CONSTRUCT_KEEP_NULL(
                    'source_system',      SS.SOURCE_SYSTEM_NAME,
                    'external_record_id', SR.EXTERNAL_RECORD_ID,
                    'reported_quantity',  EE.EVIDENCE_VALUE,
                    'evidence_role',      EE.EVIDENCE_ROLE,
                    'source_updated_at',  SR.SOURCE_UPDATED_AT
                )
            ) AS EVIDENCE
        FROM TRUST.EVALUATION_EVIDENCE EE
        JOIN RAW.SOURCE_RECORD SR ON SR.SOURCE_RECORD_ID = EE.SOURCE_RECORD_ID
        JOIN RAW.SOURCE_SYSTEM SS ON SS.SOURCE_SYSTEM_ID = SR.SOURCE_SYSTEM_ID
        GROUP BY EE.EVALUATION_ID
    ) EV
      ON EV.EVALUATION_ID = D.EVALUATION_ID
    WHERE D.ORDER_ID = :ORDER_ID;

    RETURN V_RESULT;
END;
$$;