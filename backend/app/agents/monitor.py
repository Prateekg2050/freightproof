import json
from datetime import datetime, timezone

from app.llm import complete
from app.tools.monitor_tools import get_order_risk

STATUS_MEANING = {
    "CONFLICTED": "source systems report different quantities",
    "STALE": "inventory data is older than the allowed age",
    "INSUFFICIENT_EVIDENCE": "not enough source systems reported inventory",
    "NOT_EVALUATED": "inventory has not been evaluated yet",
    "VERIFIED": "inventory is verified",
}

DECISION_MEANING = {
    "REVIEW_REQUIRED": "cannot be confirmed until the data is verified",
    "INSUFFICIENT_STOCK": "verified stock is below the required quantity",
}

PRIORITY_WEIGHT = {"CRITICAL": 4, "HIGH": 3, "NORMAL": 2, "LOW": 1}

MONITOR_PROMPT = """You are the Monitor agent of a supply-chain trust platform.
Write a short morning briefing for a supply planner.

Rules:
- Use ONLY the facts in the JSON below. Do not invent numbers, parts or causes.
- First sentence: how many orders are blocked and the total value at risk.
- Then one line per blocked order, in the given order: order id, value,
  part, trust status, and why it is blocked in plain words.
- Do not propose fixes. Another agent handles that.
- Maximum 120 words. Plain text, no headings.

FACTS:
{facts}
"""


def _step(name: str, detail: str) -> dict:
    return {
        "agent": "monitor",
        "step": name,
        "detail": detail,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def rank_orders(orders: list[dict]) -> list[dict]:
    """Highest value first, then priority, then soonest due date."""
    return sorted(
        orders,
        key=lambda o: (
            -o["order_value"],
            -PRIORITY_WEIGHT.get(o["priority"], 0),
            o["hours_to_due"] if o["hours_to_due"] is not None else float("inf"),
        ),
    )


def compute_kpis(orders: list[dict]) -> dict:
    by_decision: dict[str, int] = {}
    for o in orders:
        by_decision[o["order_decision"]] = by_decision.get(o["order_decision"], 0) + 1
    return {
        "blocked_orders": len(orders),
        "value_at_risk": sum(o["order_value"] for o in orders),
        "currency": orders[0]["currency"] if orders else "USD",
        "by_decision": by_decision,
    }


def build_facts(ranked: list[dict], kpis: dict) -> dict:
    cur = kpis["currency"]
    return {
        "blocked_orders": kpis["blocked_orders"],
        "value_at_risk": f"{cur} {kpis['value_at_risk']:,.0f}",
        "orders": [
            {
                "order_id": o["order_id"],
                "value": f"{cur} {o['order_value']:,.0f}",
                "priority": o["priority"],
                "decision": o["order_decision"],
                "decision_meaning": DECISION_MEANING.get(o["order_decision"], ""),
                "blocked_lines": [
                    {
                        "part": line["part_name"],
                        "trust_status": line["trust_status"],
                        "meaning": STATUS_MEANING.get(line["trust_status"], ""),
                    }
                    for line in o["lines"]
                    if line.get("decision") != "CAN_FULFILL"
                ],
            }
            for o in ranked
        ],
    }


def fallback_briefing(facts: dict) -> str:
    lines = [
        f"{facts['blocked_orders']} order(s) are blocked, "
        f"with {facts['value_at_risk']} at risk."
    ]
    for o in facts["orders"]:
        parts = "; ".join(
            f"{b['part']} is {b['trust_status']} ({b['meaning']})"
            for b in o["blocked_lines"]
        )
        lines.append(f"- {o['order_id']} ({o['value']}): {parts}.")
    return "\n".join(lines)


def monitor_node(state: dict) -> dict:
    trace = []

    orders = get_order_risk()
    trace.append(_step("get_order_risk", f"{len(orders)} blocked order(s) found"))

    if not orders:
        return {
            "order_risk": [],
            "kpis": compute_kpis([]),
            "briefing": "All open orders are verified and can be fulfilled.",
            "trace": trace,
        }

    ranked = rank_orders(orders)
    kpis = compute_kpis(ranked)
    facts = build_facts(ranked, kpis)
    trace.append(
        _step("rank_orders", f"Value at risk {facts['value_at_risk']}; top: {ranked[0]['order_id']}")
    )

    try:
        briefing = complete(MONITOR_PROMPT.format(facts=json.dumps(facts, indent=2)))
        trace.append(_step("write_briefing", "Briefing written by LLM"))
    except Exception as exc:  # demo must never break
        briefing = fallback_briefing(facts)
        trace.append(_step("write_briefing", f"LLM unavailable, template used: {exc}"))

    return {"order_risk": ranked, "kpis": kpis, "briefing": briefing, "trace": trace}