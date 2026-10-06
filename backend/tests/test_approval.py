from langgraph.graph import END

from app.agents.approval import build_approval_request, normalize_decisions
from app.graph import route_after_approval, route_after_planner


def test_only_proposed_actions_need_approval():
    actions = [{"action_id": "A1"}, {"action_id": "A2"}, {"action_id": "A3"}]
    statuses = {"A1": "PROPOSED", "A2": "APPROVED", "A3": "EXECUTED"}
    request = build_approval_request(actions, statuses)
    assert [a["action_id"] for a in request["actions"]] == ["A1"]


def test_valid_approval():
    out = normalize_decisions(
        {"decisions": [{"action_id": "A1", "decision": "approved", "decided_by": "Prateek"}]},
        ["A1"],
    )
    assert out[0]["valid"] is True
    assert out[0]["decision"] == "APPROVED"


def test_agent_cannot_approve():
    out = normalize_decisions(
        {"decisions": [{"action_id": "A1", "decision": "APPROVED", "decided_by": "PLANNER_AGENT"}]},
        ["A1"],
    )
    assert out[0]["valid"] is False


def test_missing_decision_stays_pending():
    out = normalize_decisions({"decisions": []}, ["A1"])
    assert out[0]["valid"] is False
    assert "decision" not in out[0]


def test_dry_run_stops_after_planner():
    state = {"dry_run": True, "plan": {"actions": [{"action_id": "A1"}]}}
    assert route_after_planner(state) == END


def test_executor_runs_only_with_approvals():
    assert route_after_approval({"approvals": {"approved_action_ids": []}}) == END
    assert route_after_approval({"approvals": {"approved_action_ids": ["A1"]}}) == "executor"