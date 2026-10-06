from datetime import datetime, timezone

from langgraph.types import interrupt

from app.tools.action_tools import decide_action, get_action_statuses

APPROVAL_FIELDS = (
    "action_id", "order_id", "part_name", "action_type", "title", "assigned_owner",
    "assigned_system", "cc", "steps", "success_criteria", "hold", "urgency",
    "message", "evidence_refs",
)


def _step(name: str, detail: str) -> dict:
    return {
        "agent": "approval",
        "step": name,
        "detail": detail,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def build_approval_request(actions: list, statuses: dict) -> dict:
    """Only PROPOSED actions need a human decision."""
    pending = [
        {k: a.get(k) for k in APPROVAL_FIELDS}
        for a in actions
        if statuses.get(a.get("action_id")) == "PROPOSED"
    ]
    return {"type": "approval_request", "actions": pending}


def normalize_decisions(response: dict, pending_ids: list) -> list:
    """
    Validate the human response. Invalid or missing decisions are NOT
    turned into rejections; the action simply stays PROPOSED.
    """
    by_id = {d.get("action_id"): d for d in (response or {}).get("decisions", [])}
    result = []
    for action_id in pending_ids:
        d = by_id.get(action_id) or {}
        decision = str(d.get("decision") or "").strip().upper()
        decided_by = str(d.get("decided_by") or "").strip()
        note = str(d.get("note") or "").strip()

        if decision not in ("APPROVED", "REJECTED"):
            result.append({"action_id": action_id, "valid": False, "reason": "No valid decision given"})
        elif not decided_by or "AGENT" in decided_by.upper():
            result.append({"action_id": action_id, "valid": False,
                           "reason": "Approver must be a named human, not an agent"})
        else:
            result.append({"action_id": action_id, "valid": True, "decision": decision,
                           "decided_by": decided_by, "note": note})
    return result


def approval_node(state: dict) -> dict:
    # Note: on resume, LangGraph re-runs this node from the start.
    # Everything before interrupt() must be read-only.
    plan = state.get("plan") or {}
    actions = [a for a in plan.get("actions", []) if a.get("action_id")]
    statuses = get_action_statuses([a["action_id"] for a in actions])

    request = build_approval_request(actions, statuses)
    pending_ids = [a["action_id"] for a in request["actions"]]
    already_approved = [aid for aid, s in statuses.items() if s == "APPROVED"]

    trace = [_step(
        "request_approval",
        f"{len(pending_ids)} action(s) awaiting human decision; "
        f"{len(already_approved)} already approved",
    )]

    decisions = []
    approved_ids = list(already_approved)

    if pending_ids:
        response = interrupt(request)  # graph pauses here until a human responds
        for d in normalize_decisions(response, pending_ids):
            if not d["valid"]:
                trace.append(_step("decide", f"{d['action_id']} left PROPOSED: {d['reason']}"))
                decisions.append(d)
                continue
            try:
                result = decide_action(d["action_id"], d["decision"], d["decided_by"], d["note"])
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            if result.get("ok"):
                trace.append(_step("decide", f"{d['action_id']} {d['decision']} by {d['decided_by']}"))
                if d["decision"] == "APPROVED":
                    approved_ids.append(d["action_id"])
            else:
                trace.append(_step("decide", f"{d['action_id']} refused by Snowflake: {result.get('error')}"))
            decisions.append({**d, "result": result})

    return {
        "approvals": {"decisions": decisions, "approved_action_ids": approved_ids},
        "trace": trace,
    }