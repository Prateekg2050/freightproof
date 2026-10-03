/* ============================================================
   FILE:      sql/03_procedures/evaluate_inventory_trust.sql
   PURPOSE:   Automatically evaluate inventory trust contracts
   RUN AFTER: sql/02_views/app_views.sql
   RERUN:     SAFE
   ============================================================ */

USE ROLE ACCOUNTADMIN;
USE WARE*OUSE SUPPLY_TRUST_WH;
USE DATABASE*SUPPLY_TRUST_DB;

CREATE OR REPLAC* PROCEDURE TRUST.EVALUATE_INVENTOR*_TRUST(
    P_CONTRACT_ID VARCHAR,*    P_CONTRACT_VERSION VARCHAR
)
R*TURNS VARCHAR
LANGUAGE SQL
EXECUTE*AS CALLER
AS
$$
DECLARE
    V_METR*C              VARCHAR;
    V_MIN_*OURCES         NUMBER;
    V_MAX_A*E_MINUTES     NUMBER;
    V_ALLOWE*_VARIANCE    FLOAT;
    V_RUN_ID              VARCHAR DEFAULT UUID_STRING();
    V_NOW                 TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP();
    V_CONTRACT_COUNT      NUMBER DEFAULT 0;
    V_EVALUATION_COUNT    NUMBER DEFAULT 0;
    V_EVIDENCE_COUNT      NUMBER DEFAULT 0;

    CONTRACT_NOT_FOUND EXCEPTION (
        -20001,
        'Active trust contract not found'
    );

BEGIN

    /* --------------------------------------------------------
       1. Verify that the requested contract exists
       -------------------------------------------------------- */

    SELECT COUNT(*)
    INTO :V_CONTRACT_COUNT
    FROM TRUST.TRUST_CONTRACT
    WHERE CONTRACT_ID = :P_CONTRACT_ID
      AND CONTRACT_VERSION = :P_CONTRACT_VERSION
      AND IS_ACTIVE = TRUE;

    IF (V_CONTRACT_COUNT = 0) THEN
        RAISE CONTRACT_NOT_FOUND;
    END IF;


    /* --------------------------------------------------------
       2. Load contract rules
       -------------------------------------------------------- */

    SELECT
        METRIC_NAME,
        MINIMUM_SOURCE_COUNT,
        COALESCE(MAXIMUM_SOURCE_AGE_MINUTES, 525600),
        COALESCE(ALLOWED_VARIANCE_PERCENT, 0)
    INTO
        :V_METRIC,
        :V_MIN_SOURCES,
        :V_MAX_AGE_MINUTES,
        :V_ALLOWED_VARIANCE
    FROM TRUST.TRUST_CONTRACT
    WHERE CONTRACT_ID = :P_CONTRACT_ID
      AND CONTRACT_VERSION = :P_CONTRACT_VERSION
      AND IS_ACTIVE = TRUE;


    /* --------------------------------------------------------
       3. Evaluate the latest inventory claims
       -------------------------------------------------------- */

    INSERT INTO TRUST.TRUST_EVALUATION (
        EVALUATION_ID,
        CONTRACT_ID,
        CONTRACT_VERSION,
        ENTITY_TYPE,
        ENTITY_ID,
        PART_ID,
        PLANT_ID,
        ORDER_ID,
        METRIC_NAME,
        EVALUATED_VALUE,
        UNIT,
        STATUS,
        REASON_CODE,
        REASON,
        SOURCE_COUNT,
        MAX_VARIANCE_PERCENT,
        EVALUATED_AT,
        EXPIRES_AT
    )

    WITH INVENTORY_SUMMARY AS (
        SELECT
            PART_ID,
            PLANT_ID,
            UNIT,

            COUNT(DISTINCT SOURCE_SYSTEM_ID)
                AS SOURCE_COUNT,

            MIN(QUANTITY)
                AS MIN_QUANTITY,

            MAX(QUANTITY)
                AS MAX_QUANTITY,

            MIN(EFFECTIVE_AT)
                AS OLDEST_EFFECTIVE_AT,

            CASE
                WHEN MAX(QUANTITY) = 0 THEN 0
                ELSE ROUND(
                    (
                        MAX(QUANTITY) - MIN(QUANTITY)
                    ) / MAX(QUANTITY) * 100,
                    2
                )
            END AS VARIANCE_PERCENT

        FROM APP.V_LATEST_INVENTORY_CLAIMS

        WHERE QUANTITY_TYPE = 'USABLE'

        GROUP BY
            PART_ID,
            PLANT_ID,
            UNIT
    ),

    CLASSIFIED AS (
        SELECT
            *,

            CASE
                WHEN SOURCE_COUNT < :V_MIN_SOURCES
                    THEN 'INSUFFICIENT_EVIDENCE'

                WHEN VARIANCE_PERCENT > :V_ALLOWED_VARIANCE
                    THEN 'CONFLICTED'

                WHEN DATEDIFF(
                    'MINUTE',
                    OLDEST_EFFECTIVE_AT,
                    :V_NOW
                ) > :V_MAX_AGE_MINUTES
                    THEN 'STALE'

                ELSE 'VERIFIED'
            END AS TRUST_STATUS

        FROM INVENTORY_SUMMARY
    )

    SELECT
        :V_RUN_ID || ':' || PART_ID || '@' || PLANT_ID,

        :P_CONTRACT_ID,
        :P_CONTRACT_VERSION,

        'PART_AT_PLANT',
        PART_ID || '@' || PLANT_ID,

        PART_ID,
        PLANT_ID,
        NULL,

        :V_METRIC,

        CASE
            WHEN TRUST_STATUS = 'VERIFIED'
                THEN MIN_QUANTITY
            ELSE NULL
        END,

        UNIT,
        TRUST_STATUS,

        CASE TRUST_STATUS
            WHEN 'INSUFFICIENT_EVIDENCE'
                THEN 'BELOW_MIN_SOURCES'

            WHEN 'CONFLICTED'
                THEN 'VARIANCE_EXCEEDED'

            WHEN 'STALE'
                THEN 'SOURCE_TOO_OLD'

            ELSE 'ALL_CHECKS_PASSED'
        END,

        CASE TRUST_STATUS
            WHEN 'INSUFFICIENT_EVIDENCE' THEN
                'Only ' || SOURCE_COUNT ||
                ' source(s) reported. Contract requires ' ||
                :V_MIN_SOURCES || '.'

            WHEN 'CONFLICTED' THEN
                'Sources disagree. Reported usable quantity ranges from ' ||
                MIN_QUANTITY || ' to ' ||
                MAX_QUANTITY || ' ' ||
                UNIT || '. Variance is ' ||
                VARIANCE_PERCENT || '%. Allowed variance is ' ||
                :V_ALLOWED_VARIANCE || '%.'

            WHEN 'STALE' THEN
                'At least one source is older than the allowed ' ||
                :V_MAX_AGE_MINUTES || ' minutes.'

            ELSE
                'Sources agree within the allowed variance. ' ||
                'Conservative verified quantity is ' ||
                MIN_QUANTITY || ' ' || UNIT || '.'
        END,

        SOURCE_COUNT,
        VARIANCE_PERCENT,
        :V_NOW,

        DATEADD(
            'MINUTE',
            :V_MAX_AGE_MINUTES,
            :V_NOW
        )

    FROM CLASSIFIED;

    V_EVALUATION_COUNT := SQLROWCOUNT;


    /* --------------------------------------------------------
       4. Attach the source evidence
       -------------------------------------------------------- */

    INSERT INTO TRUST.EVALUATION_EVIDENCE (
        EVALUATION_EVIDENCE_ID,
        EVALUATION_ID,
        SOURCE_RECORD_ID,
        CLAIM_ID,
        EVIDENCE_ROLE,
        EVIDENCE_VALUE,
        UNIT,
        EVIDENCE_NOTE
    )

    SELECT
        E.EVALUATION_ID || ':' || C.CLAIM_ID,
        E.EVALUATION_ID,
        C.SOURCE_RECORD_ID,
        C.CLAIM_ID,

        CASE
            WHEN E.STATUS = 'VERIFIED'
                THEN 'SUPPORTING'

            WHEN E.STATUS = 'CONFLICTED'
                THEN 'CONFLICTING'

            WHEN E.STATUS = 'STALE'
                AND DATEDIFF(
                    'MINUTE',
                    C.EFFECTIVE_AT,
                    :V_NOW
                ) > :V_MAX_AGE_MINUTES
                THEN 'STALE'

            ELSE 'INFORMATIONAL'
        END,

        C.QUANTITY,
        C.UNIT,

        'Latest ' ||
        C.QUANTITY_TYPE ||
        ' claim from ' ||
        C.SOURCE_SYSTEM_ID

    FROM TRUST.TRUST_EVALUATION E

    JOIN APP.V_LATEST_INVENTORY_CLAIMS C
      ON C.PART_ID = E.PART_ID
     AND C.PLANT_ID = E.PLANT_ID
     AND C.UNIT = E.UNIT
     AND C.QUANTITY_TYPE = 'USABLE'

    WHERE STARTSWITH(
        E.EVALUATION_ID,
        :V_RUN_ID
    );

    V_EVIDENCE_COUNT := SQLROWCOUNT;


    /* --------------------------------------------------------
       5. Return execution summary
       -------------------------------------------------------- */

    RETURN
        'Run ' || V_RUN_ID ||
        ': ' || V_EVALUATION_COUNT ||
        ' evaluation(s), ' ||
        V_EVIDENCE_COUNT ||
        ' evidence row(s).';

END;
$$;