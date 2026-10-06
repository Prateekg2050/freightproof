from langgraph.graph import END

from app.agents.verifier import assess_action, compare_lines, next_step
from app.graph import route_after_verifier

BEFORE = [{
    "part_id": "P1", "part_name": "Battery Cell", "plant_id": "PL1", "unit": "PCS",
    "required_quantity": 150, "trust_status": "CONFLICTED", "decision": "REVIEW_REQUIRED",
}]


def _after(status, decision, qty=None):
    return [{"part_id": "P1", "plant_id": "PL1", "trust_status": status,
             "decision": decision, "verified_quantity": qty, "reason": "x"}]


def test_compare_lines():
    c = compare_lines(BEFORE, _after("VERIFIED", "INSUFFICIENT_STOCK", 120))[0]
    assert c["status_before"] == "CONFLICTED"
    assert c["status_after"] == "VERIFIED"
    assert c["verified_quantity_after"] == 120


def test_recount_resolved():
    changes = compare_lines(BEFORE, _after("VERIFIED", "INSUFFICIENT_STOCK", 120))
    a = assess_action({"part_id": "P1", "action_type": "REQUEST_RECOUNT"}, {"ok": True}, changes)
    assert a["resolved"] is True


def test_recount_not_resolved():
    changes = compare_lines(BEFORE, _after("CONFLICTED", "REVIEW_REQUIRED"))
    a = assess_action({"part_id": "P1", "action_type": "REQUEST_RECOUNT"}, {"ok": True}, changes)
    assert a["outcome"] == "NOT_RESOLVED"


def test_dispatch_is_not_marked_resolved():
    changes = compare_lines(BEFORE, _after("VERIFIED", "INSUFFICIENT_STOCK", 120))
    a = assess_action({"part_id": "P1", "action_type": "PARTIAL_SHIPMENT_AND_EXPEDITE"},
                      {"ok": True, "note": "dispatched"}, changes)
    assert a["outcome"] == "DISPATCHED"
    assert a["resolved"] is False


def test_failed_execution():
    a = assess_action({"part_id": "P1", "action_type": "REQUEST_RECOUNT"},
                      {"ok": False, "error": "x"}, [])
    assert a["outcome"] == "NOT_EXECUTED"


def test_replan_when_decision_changes():
    assert next_step("REVIEW_REQUIRED", "INSUFFICIENT_STOCK", 1)["replan"] is True


def test_no_replan_at_max_cycles():
    assert next_step("REVIEW_REQUIRED", "INSUFFICIENT_STOCK", 2)["replan"] is False


def test_can_fulfill_stops():
    assert next_step("REVIEW_REQUIRED", "CAN_FULFILL", 1)["replan"] is False


def test_route_after_verifier():
    assert route_after_verifier({"verifications": [{"replan": True}]}) == "investigator"
    assert route_after_verifier({"verifications": []}) == END