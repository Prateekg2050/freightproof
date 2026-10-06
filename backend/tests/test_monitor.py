from app.agents.monitor import build_facts, compute_kpis, fallback_briefing, rank_orders


def _order(order_id, value, priority="NORMAL", hours=48, status="CONFLICTED"):
    return {
        "order_id": order_id,
        "priority": priority,
        "required_by": "",
        "hours_to_due": hours,
        "order_value": value,
        "currency": "USD",
        "order_decision": "REVIEW_REQUIRED",
        "lines": [
            {"part_name": "Part", "trust_status": status, "decision": "REVIEW_REQUIRED"}
        ],
    }


def test_rank_by_value_first():
    ranked = rank_orders([_order("A", 20000), _order("B", 250000), _order("C", 60000)])
    assert [o["order_id"] for o in ranked] == ["B", "C", "A"]


def test_priority_breaks_value_ties():
    ranked = rank_orders([_order("A", 1000, "LOW"), _order("B", 1000, "HIGH")])
    assert ranked[0]["order_id"] == "B"


def test_kpis():
    kpis = compute_kpis([_order("A", 250000), _order("B", 80000)])
    assert kpis["blocked_orders"] == 2
    assert kpis["value_at_risk"] == 330000
    assert kpis["by_decision"] == {"REVIEW_REQUIRED": 2}


def test_fallback_briefing_uses_only_facts():
    orders = rank_orders([_order("ORD_001", 250000)])
    text = fallback_briefing(build_facts(orders, compute_kpis(orders)))
    assert "USD 250,000" in text
    assert "ORD_001" in text