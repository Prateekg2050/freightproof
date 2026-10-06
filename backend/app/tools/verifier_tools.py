import json

from app.snowflake_client import parse_variant, query


def run_trust_evaluation() -> str:
    rows = query("CALL TRUST.RUN_TRUST_EVALUATION()")
    return str(next(iter(rows[0].values())))


def record_verification(action_id: str, resolved: bool, verification: dict) -> dict:
    rows = query(
        "CALL TRUST.MARK_ACTION_VERIFIED(%s, %s, %s)",
        (action_id, resolved, json.dumps(verification, default=str)),
    )
    return parse_variant(next(iter(rows[0].values()))) or {}