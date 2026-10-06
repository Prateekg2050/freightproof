from app.snowflake_client import parse_variant, query


def _num(value):
    return float(value) if value is not None else None


def _int(value):
    return int(value) if value is not None else None


def get_order_lines(order_id: str) -> list:
    """Order lines with decision, latest evaluation and the contract rules used."""
    rows = query(
        """
        SELECT D.LINE_NUMBER, D.PART_ID, D.PART_NAME, D.PLANT_ID,
               D.REQUIRED_QUANTITY, D.VERIFIED_QUANTITY, D.UNIT,
               D.TRUST_STATUS, D.DECISION, D.REASON, D.EVALUATION_ID,
               E.CONTRACT_ID, E.CONTRACT_VERSION, E.MAX_VARIANCE_PERCENT,
               C.ALLOWED_VARIANCE_PERCENT, C.MAXIMUM_SOURCE_AGE_MINUTES,
               C.MINIMUM_SOURCE_COUNT, C.REQUIRED_SOURCE_TYPES
        FROM APP.V_ORDER_DECISION D
        LEFT JOIN TRUST.TRUST_EVALUATION E
               ON E.EVALUATION_ID = D.EVALUATION_ID
        LEFT JOIN TRUST.TRUST_CONTRACT C
               ON C.CONTRACT_ID = E.CONTRACT_ID
              AND C.CONTRACT_VERSION = E.CONTRACT_VERSION
        WHERE D.ORDER_ID = %s
        ORDER BY D.LINE_NUMBER
        """,
        (order_id,),
    )
    return [
        {
            "line_number": r["LINE_NUMBER"],
            "part_id": r["PART_ID"],
            "part_name": r["PART_NAME"],
            "plant_id": r["PLANT_ID"],
            "required_quantity": _num(r["REQUIRED_QUANTITY"]),
            "verified_quantity": _num(r["VERIFIED_QUANTITY"]),
            "unit": r["UNIT"],
            "trust_status": r["TRUST_STATUS"],
            "decision": r["DECISION"],
            "reason": r["REASON"],
            "evaluation_id": r["EVALUATION_ID"],
            "contract": (
                f"{r['CONTRACT_ID']} v{r['CONTRACT_VERSION']}" if r["CONTRACT_ID"] else None
            ),
            "max_variance_percent": _num(r["MAX_VARIANCE_PERCENT"]),
            "allowed_variance_percent": _num(r["ALLOWED_VARIANCE_PERCENT"]),
            "maximum_source_age_minutes": _int(r["MAXIMUM_SOURCE_AGE_MINUTES"]),
            "minimum_source_count": _int(r["MINIMUM_SOURCE_COUNT"]),
            "required_source_types": parse_variant(r["REQUIRED_SOURCE_TYPES"]) or [],
        }
        for r in rows
    ]


def get_evidence(evaluation_id: str) -> list:
    """Source records behind one trust evaluation."""
    rows = query(
        """
        SELECT SS.SOURCE_SYSTEM_ID, SS.SOURCE_SYSTEM_NAME, SS.SYSTEM_TYPE,
               SS.SYSTEM_OWNER, SR.EXTERNAL_RECORD_ID, EE.EVIDENCE_VALUE,
               EE.UNIT, EE.EVIDENCE_ROLE, SR.SOURCE_UPDATED_AT,
               DATEDIFF('MINUTE', SR.SOURCE_UPDATED_AT, CURRENT_TIMESTAMP()) AS AGE_MINUTES
        FROM TRUST.EVALUATION_EVIDENCE EE
        JOIN RAW.SOURCE_RECORD SR ON SR.SOURCE_RECORD_ID = EE.SOURCE_RECORD_ID
        JOIN RAW.SOURCE_SYSTEM SS ON SS.SOURCE_SYSTEM_ID = SR.SOURCE_SYSTEM_ID
        WHERE EE.EVALUATION_ID = %s
        ORDER BY EE.EVIDENCE_VALUE DESC
        """,
        (evaluation_id,),
    )
    return [
        {
            "system_id": r["SOURCE_SYSTEM_ID"],
            "system_name": r["SOURCE_SYSTEM_NAME"],
            "system_type": r["SYSTEM_TYPE"],
            "owner": r["SYSTEM_OWNER"],
            "record_id": r["EXTERNAL_RECORD_ID"],
            "value": _num(r["EVIDENCE_VALUE"]),
            "unit": r["UNIT"],
            "role": r["EVIDENCE_ROLE"],
            "updated_at": str(r["SOURCE_UPDATED_AT"]),
            "age_minutes": _int(r["AGE_MINUTES"]),
        }
        for r in rows
    ]


def get_source_systems() -> list:
    rows = query(
        """
        SELECT SOURCE_SYSTEM_ID, SOURCE_SYSTEM_NAME, SYSTEM_TYPE, SYSTEM_OWNER
        FROM RAW.SOURCE_SYSTEM
        WHERE IS_ACTIVE
        """
    )
    return [
        {
            "system_id": r["SOURCE_SYSTEM_ID"],
            "system_name": r["SOURCE_SYSTEM_NAME"],
            "system_type": r["SYSTEM_TYPE"],
            "owner": r["SYSTEM_OWNER"],
        }
        for r in rows
    ]


def get_mapped_system_ids(part_id: str) -> set:
    """Source systems that have a confirmed ID mapping for this part."""
    rows = query(
        """
        SELECT DISTINCT SOURCE_SYSTEM_ID
        FROM CORE.ENTITY_MAPPING
        WHERE CANONICAL_ENTITY_TYPE = 'PART'
          AND CANONICAL_ENTITY_ID = %s
          AND MAPPING_STATUS = 'CONFIRMED'
        """,
        (part_id,),
    )
    return {r["SOURCE_SYSTEM_ID"] for r in rows}