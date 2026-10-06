/* ============================================================
   FILE:      sql/07_agentic/04_approval_and_execution.sql
   PURPOSE:   Human approval and governed execution of agent actions
   RUN AFTER: sql/07_agentic/03_action_requests.sql
   RERUN:     SAFE
   ============================================================ */

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE SUPPLY_TRUST_WH;
USE DATABASE SUPPLY_TRUST_DB;

/* ---------- Approve or reject a proposed action ---------- */
CREATE OR REPLACE PROCEDURE TRUST.DECIDE_ACTION(
    P_ACTION_ID VARCHAR,
    P_DECISION VARCHAR,
    P_DECIDED_BY VARCHAR,
    P_NOTE VARCHAR
)
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    V_COUNT  NUMBER DEFAULT 0;
    V_STATUS VARCHAR;
    V_RESULT VARIANT;
BEGIN
    IF (P_DECISION <> 'APPROVED' AND P_DECISION <> 'REJECTED') THEN
        V_RESULT := OBJECT_CONSTRUCT('ok', FALSE, 'error', 'Decision must be APPROVED or REJECTED');
        RETURN V_RESULT;
    END IF;

    IF (COALESCE(TRIM(P_DECIDED_BY), '') = '' OR CONTAINS(UPPER(P_DECIDED_BY), 'AGENT')) THEN
        V_RESULT := OBJECT_CONSTRUCT('ok', FALSE, 'error', 'Approver must be a named human, not an agent');
        RETURN V_RESULT;
    END IF;

    SELECT COUNT(1), MAX(STATUS) INTO :V_COUNT, :V_STATUS
    FROM TRUST.ACTION_REQUEST
    WHERE ACTION_ID = :P_ACTION_ID;

    IF (V_COUNT = 0) THEN
        V_RESULT := OBJECT_CONSTRUCT('ok', FALSE, 'error', 'Action not found');
        RETURN V_RESULT;
    END IF;

    IF (V_STATUS <> 'PROPOSED') THEN
        V_RESULT := OBJECT_CONSTRUCT('ok', FALSE, 'error', 'Only PROPOSED actions can be decided; current status ' || V_STATUS);
        RETURN V_RESULT;
    END IF;

    UPDATE TRUST.ACTION_REQUEST
    SET STATUS = :P_DECISION,
        DECIDED_BY = :P_DECIDED_BY,
        DECIDED_AT = CURRENT_TIMESTAMP(),
        DECISION_NOTE = :P_NOTE
    WHERE ACTION_ID = :P_ACTION_ID
      AND STATUS = 'PROPOSED';

    V_RESULT := OBJECT_CONSTRUCT('ok', TRUE, 'action_id', P_ACTION_ID, 'status', P_DECISION);
    RETURN V_RESULT;
END;
$$;

/* ---------- Execute an approved action ----------
   DEMO: the source system's response is simulated so the
   Verifier (Step 5) has new data to evaluate. */
CREATE OR REPLACE PROCEDURE TRUST.EXECUTE_ACTION(P_ACTION_ID VARCHAR)
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    V_COUNT      NUMBER DEFAULT 0;
    V_STATUS     VARCHAR;
    V_TYPE       VARCHAR;
    V_PART       VARCHAR;
    V_PLANT      VARCHAR;
    V_OWNER      VARCHAR;
    V_DECIDED_BY VARCHAR;
    V_UNIT       VARCHAR;
    V_QTY        FLOAT;
    V_POSTED     NUMBER DEFAULT 0;
    V_NOTE       VARCHAR;
    V_RUN        VARCHAR DEFAULT UPPER(LEFT(UUID_STRING(), 8));
    V_RESULT     VARIANT;
BEGIN
    SELECT COUNT(1), MAX(STATUS), MAX(ACTION_TYPE), MAX(PART_ID), MAX(PLANT_ID),
           MAX(ASSIGNED_OWNER), MAX(DECIDED_BY)
    INTO :V_COUNT, :V_STATUS, :V_TYPE, :V_PART, :V_PLANT, :V_OWNER, :V_DECIDED_BY
    FROM TRUST.ACTION_REQUEST
    WHERE ACTION_ID = :P_ACTION_ID;

    IF (V_COUNT = 0) THEN
        V_RESULT := OBJECT_CONSTRUCT('ok', FALSE, 'error', 'Action not found');
        RETURN V_RESULT;
    END IF;

    IF (V_STATUS <> 'APPROVED') THEN
        V_RESULT := OBJECT_CONSTRUCT('ok', FALSE, 'error', 'Action must be APPROVED before execution; current status ' || V_STATUS);
        RETURN V_RESULT;
    END IF;

    IF (V_TYPE = 'REQUEST_RECOUNT' OR V_TYPE = 'REQUEST_DATA_REFRESH') THEN

        IF (V_TYPE = 'REQUEST_RECOUNT') THEN
            -- Simulated physical count confirms the warehouse quantity
            SELECT MIN(QUANTITY) INTO :V_QTY
            FROM APP.V_LATEST_INVENTORY_CLAIMS
            WHERE PART_ID = :V_PART AND PLANT_ID = :V_PLANT
              AND QUANTITY_TYPE = 'USABLE' AND SOURCE_SYSTEM_ID = 'SYS_WMS';

            IF (V_QTY IS NULL) THEN
                V_RESULT := OBJECT_CONSTRUCT('ok', FALSE, 'error', 'No warehouse claim found to recount');
                RETURN V_RESULT;
            END IF;
            V_NOTE := 'Simulated physical count confirmed ' || V_QTY || '; all systems reconciled to the count';
        ELSE
            -- Simulated fresh extract: each source re-posts its current value
            V_QTY := NULL;
            V_NOTE := 'Simulated fresh extract posted by each source';
        END IF;

        INSERT INTO RAW.SOURCE_RECORD (
            SOURCE_RECORD_ID, SOURCE_SYSTEM_ID, EXTERNAL_RECORD_ID, RECORD_TYPE,
            RECORD_VERSION, PAYLOAD, SOURCE_UPDATED_AT, INGESTION_STATUS
        )
        SELECT 'REC_' || :V_RUN || '_' || C.SOURCE_SYSTEM_ID,
               C.SOURCE_SYSTEM_ID,
               SR.EXTERNAL_RECORD_ID,
               'INVENTORY',
               COALESCE(SR.RECORD_VERSION, 1) + 1,
               OBJECT_CONSTRUCT('quantity', COALESCE(:V_QTY, C.QUANTITY), 'unit', C.UNIT,
                                'quantity_type', 'USABLE', 'action_id', :P_ACTION_ID),
               CURRENT_TIMESTAMP(),
               'VALIDATED'
        FROM APP.V_LATEST_INVENTORY_CLAIMS C
        JOIN RAW.SOURCE_RECORD SR ON SR.SOURCE_RECORD_ID = C.SOURCE_RECORD_ID
        WHERE C.PART_ID = :V_PART AND C.PLANT_ID = :V_PLANT AND C.QUANTITY_TYPE = 'USABLE';

        V_POSTED := SQLROWCOUNT;

        INSERT INTO CORE.INVENTORY_CLAIM (
            CLAIM_ID, SOURCE_RECORD_ID, SOURCE_SYSTEM_ID, PART_ID, PLANT_ID,
            QUANTITY, UNIT, QUANTITY_TYPE, EFFECTIVE_AT
        )
        SELECT 'CLAIM_' || :V_RUN || '_' || C.SOURCE_SYSTEM_ID,
               'REC_' || :V_RUN || '_' || C.SOURCE_SYSTEM_ID,
               C.SOURCE_SYSTEM_ID, C.PART_ID, C.PLANT_ID,
               COALESCE(:V_QTY, C.QUANTITY), C.UNIT, 'USABLE', CURRENT_TIMESTAMP()
        FROM APP.V_LATEST_INVENTORY_CLAIMS C
        WHERE C.PART_ID = :V_PART AND C.PLANT_ID = :V_PLANT AND C.QUANTITY_TYPE = 'USABLE';

    ELSEIF (V_TYPE = 'REQUEST_SOURCE_CONFIRMATION') THEN
        -- Simulated: the warehouse confirms the item mapping and reports stock
        SELECT MIN(QUANTITY), MIN(UNIT) INTO :V_QTY, :V_UNIT
        FROM APP.V_LATEST_INVENTORY_CLAIMS
        WHERE PART_ID = :V_PART AND PLANT_ID = :V_PLANT AND QUANTITY_TYPE = 'USABLE';

        IF (V_QTY IS NULL) THEN
            V_RESULT := OBJECT_CONSTRUCT('ok', FALSE, 'error', 'No existing claim to confirm');
            RETURN V_RESULT;
        END IF;

        INSERT INTO CORE.ENTITY_MAPPING (
            ENTITY_MAPPING_ID, SOURCE_SYSTEM_ID, SOURCE_ENTITY_TYPE, SOURCE_ENTITY_ID,
            CANONICAL_ENTITY_TYPE, CANONICAL_ENTITY_ID, MAPPING_STATUS, MAPPING_METHOD,
            CONFIDENCE_SCORE, APPROVED_BY, APPROVED_AT
        )
        SELECT 'MAP_' || :V_RUN, 'SYS_WMS', 'PART', 'WH-' || :V_PART, 'PART', :V_PART,
               'CONFIRMED', 'MANUAL', 100, :V_DECIDED_BY, CURRENT_TIMESTAMP()
        WHERE NOT EXISTS (
            SELECT 1 FROM CORE.ENTITY_MAPPING
            WHERE SOURCE_SYSTEM_ID = 'SYS_WMS'
              AND CANONICAL_ENTITY_TYPE = 'PART'
              AND CANONICAL_ENTITY_ID = :V_PART
              AND MAPPING_STATUS = 'CONFIRMED'
        );

        INSERT INTO RAW.SOURCE_RECORD (
            SOURCE_RECORD_ID, SOURCE_SYSTEM_ID, EXTERNAL_RECORD_ID, RECORD_TYPE,
            RECORD_VERSION, PAYLOAD, SOURCE_UPDATED_AT, INGESTION_STATUS
        )
        SELECT 'REC_' || :V_RUN || '_SYS_WMS', 'SYS_WMS', 'WMS-CONFIRM-' || :V_RUN, 'INVENTORY', 1,
               OBJECT_CONSTRUCT('sku', 'WH-' || :V_PART, 'quantity', :V_QTY, 'unit', :V_UNIT,
                                'quantity_type', 'USABLE', 'action_id', :P_ACTION_ID),
               CURRENT_TIMESTAMP(), 'VALIDATED';

        INSERT INTO CORE.INVENTORY_CLAIM (
            CLAIM_ID, SOURCE_RECORD_ID, SOURCE_SYSTEM_ID, PART_ID, PLANT_ID,
            QUANTITY, UNIT, QUANTITY_TYPE, EFFECTIVE_AT
        )
        SELECT 'CLAIM_' || :V_RUN || '_SYS_WMS', 'REC_' || :V_RUN || '_SYS_WMS', 'SYS_WMS',
               :V_PART, :V_PLANT, :V_QTY