from app.agents.investigator import diagnose_line, order_decision, pick_target

SYSTEMS = [
    {"system_id": "SYS_ERP", "system_name": "ERP", "system_type": "ERP", "owner": "Finance"},
    {"system_id": "SYS_WMS", "system_name": "WMS", "system_type": "WMS", "owner": "Warehouse"},
]


def _line(status, decision="REVIEW_REQUIRED", req=150, verified=None):
    return {
        "line_number": 1, "part_id": "P1", "part_name": "Part", "plant_id": "PL1",
        "required_quantity": req, "verified_quantity": verified, "unit": "PCS",
        "trust_status": status, "decision": decision, "contract": "TC v1.0",
        "max_variance_percent": 76.0, "allowed_variance_percent": 5.0,
        "maximum_source_age_minutes": 60, "minimum_source_count": 2,
        "required_source_types": ["ERP", "WMS"],
    }


def _ev(system_type, value, age=2):
    sys = next(s for s in SYSTEMS if s["system_type"] == system_type)
    return {**sys, "record_id": f"R-{system_type}", "value": value,
            "unit": "PCS", "role": "x", "updated_at": "", "age_minutes": age}


def test_conflict_is_decision_sensitive():
    f = diagnose_line(_line("CONFLICTED"), [_ev("ERP", 500), _ev("WMS", 120)], SYSTEMS, set())
    assert f["decision_sensitive"] is True
    assert any("500" in x and "120" in x for x in f["facts"])
    assert "ERP" in f["possible_causes"][0]
    assert len(f["data_owners"]) == 2


def test_stale_flags_old_source():
    f = diagnose_line(_line("STALE"), [_ev("ERP", 400, 180), _ev("WMS", 400, 180)], SYSTEMS, set())
    assert any("180 minute" in x for x in f["facts"])


def test_insufficient_evidence_names_missing_system():
    f = diagnose_line(_line("INSUFFICIENT_EVIDENCE"), [_ev("ERP", 80)], SYSTEMS, {"SYS_ERP"})
    assert any("missing: ['WMS']" in x for x in f["facts"])
    assert any("no confirmed ID mapping" in x for x in f["facts"])
    assert f["data_owners"] == [{"system": "WMS", "owner": "Warehouse"}]


def test_insufficient_stock_shortfall():
    f = diagnose_line(_line("VERIFIED", "INSUFFICIENT_STOCK", 150, 120), [], SYSTEMS, set())
    assert any("short by 30" in x for x in f["facts"])


def test_pick_target_prefers_request():
    state = {"request": "check ord_003", "order_risk": [{"order_id": "ORD_001"}]}
    assert pick_target(state) == "ORD_003"
    assert pick_target({"request": "scan", "order_risk": [{"order_id": "ORD_001"}]}) == "ORD_001"


def test_order_decision_worst_wins():
    assert order_decision([{"decision": "CAN_FULFILL"}, {"decision": "REVIEW_REQUIRED"}]) == "REVIEW_REQUIRED"