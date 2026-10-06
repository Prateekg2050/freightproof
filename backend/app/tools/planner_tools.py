import json

from app.snowflake_client import parse_variant, query


def get_supplier_options(part_id: str) -> list:
    """Active suppliers for a part: primary first, then lowest risk, then fastest."""
    rows = query(
        """
        SELECT SP.SUPPLIER_ID, S.SUPPLIER_NAME, S.COUNTRY_CODE,
               SP.LEAD_TIME_DAYS, SP.RISK_SCORE, SP.IS_PRIMARY_SUPPLIER
        FROM CORE.SUPPLIER_PART SP
        JOIN CORE.SUPPLIER S ON S.SUPPLIER_ID = SP.SUPPLIER_ID
        WHERE SP.PART_ID = %s
          AND SP.STATUS = 'ACTIVE'
          AND S.STATUS = 'ACTIVE'
        ORDER BY SP.IS_PRIMARY_SUPPLIER DESC,
                 SP.RISK_SCORE ASC NULLS LAST,
                 SP.LEAD_TIME_DAYS ASC NULLS LAST
        """,
        (part_id,),
    )
    return [
        {
            "supplier_id": r["SUPPLIER_ID"],
            "supplier_name": r["SUPPLIER_NAME"],
            "country": r["COUNTRY_CODE"],
            "lead_time_days": int(r["LEAD_TIME_DAYS"]) if r["LEAD_TIME_DAYS"] is not None else None,
            "risk_score": float(r["RISK_SCORE"]) if r["RISK_SCORE"] is not None else None,
            "is_primary": bool(r["IS_PRIMARY_SUPPLIER"]),
        }
        for r in rows
    ]


def propose_action(action: dict) -> dict:
    """Save a proposal through the governed procedure. Returns action_id and created flag."""
    payload = {
        k: action[k]
        for k in ("steps", "success_criteria", "hold", "cc", "evidence_refs", "urgency")
    }
    rows = query(
        "CALL TRUST.PROPOSE_ACTION(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            action["order_id"],
            action["part_id"],
            action["plant_id"],
            action.get("evaluation_id"),
            action["trust_status"],
            action["action_type"],
            action["assigned_system"],
            action["assigned_owner"],
            action["title"],
            action.get("message"),
            json.dumps(payload),
        ),
    )
    return parse_variant(next(iter(rows[0].values()))) or {}