from datetime import datetime, timezone

from app.tools.action_tools import execute_action


def _step(name: str, detail: str) -> dict:
    return {
        "agent": "executor",
        "step": name,
        "detail": detail,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def executor_node(state: dict) -> dict:
    """Deterministic: runs approved actions through the governed procedure. No LLM."""
    approved = (state.get("approvals") or {}).get("approved_action_ids", [])
    trace, results = [], []

    for action_id in approved:
        try:
            result = execute_action(action_id)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}

        if result.get("ok"):
            trace.append(_step("execute_action", f"{action_id} EXECUTED: {result.get('note')}"))
        else:
            trace.append(_step("execute_action", f"{action_id} not executed: {result.get('error')}"))
        results.append({"action_id": action_id, **result})

    return {"execution": results, "trace": trace}