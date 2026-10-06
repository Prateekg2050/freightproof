from datetime import datetime, timezone

from app.agents.planner import fallback_message, plan_line, urgency

SYSTEMS = [
    {"system_id": "SYS_ERP", "system_name": "ERP", "system_type": "ERP", "owner": "Finance"},
    {"system_id": "SYS_WMS", "system_name": "WMS", "system_type": "WMS", "owner": "Warehouse"},
    {"system_id": "SYS_SUP", "system_name": "Portal", "system_type": "SUPPLIER_PORTAL", "owner": "Procurement"},
]
ORDER = {"order_id": "ORD_001", "order_value": 250000, "hours_to_due": 48, "priority": "HIGH"}
NOW = datetime(2026, 10, 5, tzinfo=timezone.utc)


def _ev(system_type, value, age=2):
    s = next(x for x in SYSTEMS if x["system_type"] == system_type)
    return {**s, "record_id": f"R-{system_type}", "value": value, "unit": "PCS",
            "role": "x", "updated_at": "", "age_minutes": age}


def _finding(status, decision="REVIEW_REQUIRED", evidence=None, verified=None):
    return {
        "line_number": 1, "part_id": "P1", "part_name": "Battery Cell", "plant_id": "PLANT_BLR_001",
        "trust_status": status, "decision": decision, "required_quantity": 150,
        "verified_quantity": verified, "unit": "PCS", "evaluation_id": "E1",
        "allowed_variance_percent": 5.0, "maximum_source_age_minutes": 60,
        "minimum_source_count": 2, "required_source_types": ["ERP", "WMS"],
        "facts": [], "possible_causes": [], "data_owners": [],
        "decision_sensitive": False, "evidence": evidence or [],
    }


def test_conflict_requests_recount_from_warehouse():
    a = plan_line(_finding("CONFLICTED", evidence=[_ev("ERP", 500), _ev("WMS", 120)]),
                  ORDER, SYSTEMS, [], set(), NOW)
    assert a["action_type"] == "REQUEST_RECOUNT"
    assert a["assigned_owner"] == "Warehouse"
    assert a["cc"] == ["Finance"]
    assert any("R-ERP" in s for s in a["steps"])
    assert "ORD_001" in a["hold"]


def test_stale_requests_refresh():
    a = plan_line(_finding("STALE", evidence=[_ev("ERP", 400, 180), _ev("WMS", 400, 180)]),
                  ORDER, SYSTEMS, [], set(), NOW)
    assert a["action_type"] == "REQUEST_DATA_REFRESH"
    assert any("180 minutes" in s for s in a["steps"])


def test_insufficient_evidence_adds_mapping_step():
    a = plan_line(_finding("INSUFFICIENT_EVIDENCE", evidence=[_ev("ERP", 80)]),
                  ORDER, SYSTEMS, [], {"SYS_ERP"}, NOW)
    assert a["action_type"] == "REQUEST_SOURCE_CONFIRMATION"
    assert a["assigned_owner"] == "Warehouse"
    assert "mapping" in a["steps"][0]


def test_insufficient_stock_partial_when_lead_time_too_long():
    supplier = [{"supplier_id": "S1", "supplier_name": "ABC", "country": "IN",
                 "lead_time_days": 15, "risk_score": 62.5, "is_primary": True}]
    a = plan_line(_finding("VERIFIED", "INSUFFICIENT_STOCK", verified=120),
                  ORDER, SYSTEMS, supplier, set(), NOW)
    assert a["action_type"] == "PARTIAL_SHIPMENT_AND_EXPEDITE"
    assert a["assigned_owner"] == "Procurement"
    assert "120" in a["title"] and "30" in a["title"]
    assert any("2026-10-20" in s for s in a["steps"])


def test_urgency():
    assert urgency(ORDER) == "HIGH"
    assert urgency({"order_value": 20000, "hours_to_due": 72}) == "NORMAL"


def test_fallback_message_has_criteria_and_hold():
    a = plan_line(_finding("CONFLICTED", evidence=[_ev("ERP", 500), _ev("WMS", 120)]),
                  ORDER, SYSTEMS, [], set(), NOW)
    text = fallback_message(a)
    assert a["success_criteria"] in text
    assert "Do not confirm ORD_001" in text