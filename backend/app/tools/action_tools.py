from app.snowflake_client import parse_variant, query


def _call(sql: str, params: tuple) -> dict:
    rows = query(sql, params)
    return parse_variant(next(iter(rows[0].values()))) or {}


def get_action_statuses(action_ids: list) -> dict:
    """Current status for each action ID."""
    if not action_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(action_ids))
    rows = query(
        f"SELECT ACTION_ID, STATUS FROM TRUST.ACTION_REQUEST WHERE ACTION_ID IN ({placeholders})",
        tuple(action_ids),
    )
    return {r["ACTION_ID"]: r["STATUS"] for r in rows}


def decide_action(action_id: str, decision: str, decided_by: str, note: str) -> dict:
    return _call(
        "CALL TRUST.DECIDE_ACTION(%s, %s, %s, %s)",
        (action_id, decision, decided_by, note),
    )


def execute_action(action_id: str) -> dict:
    return _call("CALL TRUST.EXECUTE_ACTION(%s)", (action_id,))