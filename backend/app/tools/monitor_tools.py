from app.snowflake_client import parse_variant, query


def get_order_risk(include_fulfillable: bool = False) -> list[dict]:
    """Return open orders with their worst decision, value and lines."""
    sql = """
        SELECT ORDER_ID, PRIORITY, REQUIRED_BY, HOURS_TO_DUE, ORDER_VALUE,
               CURRENCY_CODE, ORDER_DECISION, LINE_COUNT, LINES
        FROM APP.V_ORDER_RISK
    """
    if not include_fulfillable:
        sql += " WHERE ORDER_DECISION <> 'CAN_FULFILL'"

    orders = []
    for row in query(sql):
        orders.append(
            {
                "order_id": row["ORDER_ID"],
                "priority": row["PRIORITY"],
                "required_by": str(row["REQUIRED_BY"]),
                "hours_to_due": row["HOURS_TO_DUE"],
                "order_value": float(row["ORDER_VALUE"] or 0),
                "currency": row["CURRENCY_CODE"] or "USD",
                "order_decision": row["ORDER_DECISION"],
                "lines": parse_variant(row["LINES"]) or [],
            }
        )
    return orders