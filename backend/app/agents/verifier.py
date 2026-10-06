import json
from datetime import datetime, timezone

from app.agents.investigator import order_decision
from app.llm import complete
from app.tools.investigator_tools import get_order_lines
from app.tools.verifier_tools import record_verification, run_trust_evaluation

MAX_CYCLES = 2

DATA_ACTIONS = {
    "REQUEST_RECOUNT",
    "REQUEST_DATA_REFRESH",
    "REQUEST_SOURCE_CONFIRMATION",
    "RUN_TRUST_EVALUATION",
}

VERIFIER_PROMPT = """You are the Verifier agent of a supply-chain trust platform.
Summarize for a supply planner what changed after the approved actions ran.

Rules:
- Use ONLY the facts in the JSON below. Do not invent numbers or outcomes.
- State the trust status and decision before and after, with quantities.
- Say whether each action resolved its problem.
- End with the next step exactly as given.
- Maximum 80 words. Plain text only: no markdown, no asterisks, no headings.

FACTS:
{facts}
"""


def _step(name: str, detail: str) -> dict:
    return {
        "agent": "verifier",
        "step": name,
        "detail": detail,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def compare_lines(before_findings: list, after_lines: list) -> list:
    """Before and after trust status and decision for each order line."""
    after = {(a["part_id"], a["plant_id"]): a for a in after_lines}
    changes = []
    for b in before_findings:
        a = after.get((b["part_id"], b["plant_id"]), {})
        changes.append({
            "part_id": b["part_id"],
            "part_name": b["part_name"],
            "plant_id": b["plant_id"],
            "unit": b["unit"],
            "required_quantity": b["required_quantity"],
            "status_before": b["trust_status"],
            "status_after": a.get("trust_status"),
            "decision_before": b["decision"],
            "decision_after": a.get("decision"),
            "verified_quantity_after": a.get("verified_quantity"),
            "reason_after": a.get("reason"),
        })
    return changes


def assess_action(action: dict, result: dict, changes: list) -> dict:
    """Did the action fix the problem it targeted?"""
    if not result.get("ok"):
        return {"resolved": False, "outcome": "NOT_EXECUTED", "detail": result.get("error")}

    change = next((c for c in changes if c["part_id"] == action.get("part_id")), None)

    if action.get("action_type") in DATA_ACTIONS:
        if change and change["status_after"] == "VERIFIED":
            return {"resolved": True, "outcome": "RESOLVED",
                    "detail": f"{change['part_name']} is now VERIFIED"}
        status = change["status_after"] if change else "unknown"
        return {"resolved": False, "outcome": "NOT_RESOLVED",
                "detail": f"Trust status is still {status}"}

    # Expedite and partial shipment: dispatched, but stock has not arrived yet
    return {"resolved": False, "outcome": "DISPATCHED",
            "detail": result.get("note") or "Request dispatched"}


def next_step(before_decision: str, after_decision: str, cycle: int) -> dict:
    if after_decision == "CAN_FULFILL":
        return {"replan": False, "next": "Order can be confirmed to the customer."}
    if after_decision != before_decision and cycle < MAX_CYCLES:
        return {"replan": True, "next": f"Decision changed to {after_decision}, re-planning."}
    if after_decision == "REVIEW_REQUIRED":
        return {"replan": False, "next": "Data is still not verified, escalate to the data owners."}
    return {"replan": False, "next": "Waiting for the dispatched request to complete."}


def fallback_summary(facts: dict) -> str:
    parts = [f"{facts['order_id']}: {facts['decision_before']} -> {facts['decision_after']}."]
    for c in facts["changes"]:
        qty = c["verified_quantity_after"]
        qty_text = f" (verified {qty:,.0f} {c['unit']})" if qty is not None else ""
        parts.append(f"{c['part_name']}: {c['status_before']} -> {c['status_after']}{qty_text}.")
    for o in facts["outcomes"]:
        parts.append(f"{o['action_type']}: {o['outcome']}.")
    parts.append(facts["next"])
    return " ".join(parts)


def verifier_node(state: dict) -> dict:
    inv = state.get("investigation") or {}
    order_id = inv.get("order_id")
    execution = state.get("execution") or []
    cycle = (state.get("cycle") or 0) + 1

    if not order_id or not execution:
        return {"cycle": cycle, "trace": [_step("skip", "Nothing executed to verify")]}

    trace = []
    try:
        trace.append(_step("run_trust_evaluation", run_trust_evaluation()))
    except Exception as exc:
        trace.append(_step("run_trust_evaluation", f"Failed: {exc}"))
        return {
            "cycle": cycle,
            "verifications": [{"order_id": order_id, "error": str(exc), "replan": False}],
            "trace": trace,
        }

    after_lines = get_order_lines(order_id)
    changes = compare_lines(inv.get("findings", []), after_lines)
    before_decision = inv.get("order_decision")
    after_decision = order_decision(after_lines) if after_lines else before_decision

    for c in changes:
        trace.append(_step(
            "compare",
            f"{c['part_name']}: {c['status_before']} -> {c['status_after']}; "
            f"decision {c['decision_before']} -> {c['decision_after']}",
        ))

    actions = {a.get("action_id"): a for a in (state.get("plan") or {}).get("actions", [])}
    outcomes = []
    for r in execution:
        action = actions.get(r["action_id"], {"action_id": r["action_id"]})
        assessment = assess_action(action, r, changes)

        if r.get("ok"):
            try:
                rec = record_verification(
                    r["action_id"],
                    assessment["resolved"],
                    {**assessment, "decision_after": after_decision},
                )
                action_status = rec.get("status") or rec.get("error")
            except Exception as exc:
                action_status = f"not recorded: {exc}"
        else:
            action_status = "skipped"

        trace.append(_step("record", f"{r['action_id']} {assessment['outcome']}, status {action_status}"))
        outcomes.append({
            "action_id": r["action_id"],
            "action_type": action.get("action_type"),
            **assessment,
            "action_status": action_status,
        })

    nxt = next_step(before_decision, after_decision, cycle)
    cycle_note = f" (cycle {cycle} of {MAX_CYCLES})" if nxt["replan"] else ""
    trace.append(_step("next", nxt["next"] + cycle_note))

    facts = {
        "order_id": order_id,
        "decision_before": before_decision,
        "decision_after": after_decision,
        "changes": changes,
        "outcomes": [
            {k: o[k] for k in ("action_type", "outcome", "detail")} for o in outcomes
        ],
        "next": nxt["next"],
    }

    try:
        summary = complete(VERIFIER_PROMPT.format(facts=json.dumps(facts, indent=2, default=str)))
        trace.append(_step("summarize", "Summary written by LLM"))
    except Exception as exc:  # demo must never break
        summary = fallback_summary(facts)
        trace.append(_step("summarize", f"LLM unavailable, template used: {exc}"))

    return {
        "cycle": cycle,
        "verifications": [{
            "order_id": order_id,
            "cycle": cycle,
            "decision_before": before_decision,
            "decision_after": after_decision,
            "changes": changes,
            "outcomes": outcomes,
            "replan": nxt["replan"],
            "next": nxt["next"],
            "summary": summary,
        }],
        "trace": trace,
    }