import json
import re
from datetime import datetime, timezone

from app.llm import complete
from app.tools.investigator_tools import (
    get_evidence,
    get_mapped_system_ids,
    get_order_lines,
    get_source_systems,
)

ORDER_ID_PATTERN = re.compile(r"\bORD_\d+\b", re.IGNORECASE)

INVESTIGATOR_PROMPT = """You are the Investigator agent of a supply-chain trust platform.
Explain to a supply planner why order {order_id} is blocked.

Rules:
- Use ONLY the facts in the JSON below. Do not invent numbers, records or causes.
- Cite source systems and record IDs exactly as given.
- Present possible_causes as possibilities, never as confirmed facts.
- If decision_sensitive is true, say clearly that the decision depends on which source is correct.
- Name the data owners who can resolve it.
- Do not propose fixes. Another agent handles that.
- Maximum 120 words. Plain text only: no markdown, no asterisks, no headings.

FACTS:
{facts}
"""


def _step(name: str, detail: str) -> dict:
    return {
        "agent": "investigator",
        "step": name,
        "detail": detail,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def _n(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def _src(e: dict) -> str:
    return f"{e['system_name']} (record {e['record_id']})"


def _owners(items: list) -> list:
    seen, result = set(), []
    for e in items:
        key = (e["system_name"], e["owner"])
        if key not in seen:
            seen.add(key)
            result.append({"system": e["system_name"], "owner": e["owner"]})
    return result


def pick_target(state: dict):
    """Named order in the request first, then the Monitor's top-ranked order."""
    if state.get("target_order_id"):
        return state["target_order_id"]
    match = ORDER_ID_PATTERN.search(state.get("request") or "")
    if match:
        return match.group(0).upper()
    risk = state.get("order_risk") or []
    return risk[0]["order_id"] if risk else None


def diagnose_line(line: dict, evidence: list, systems: list, mapped_system_ids: set) -> dict:
    """Deterministic root-cause facts for one order line. No LLM."""
    status = line["trust_status"]
    unit = line["unit"]
    req = line["required_quantity"]
    facts, causes, owners = [], [], []
    decision_sensitive = False

    if status == "CONFLICTED" and evidence:
        hi = max(evidence, key=lambda e: e["value"])
        lo = min(evidence, key=lambda e: e["value"])
        facts.append(
            f"{_src(hi)} reports {_n(hi['value'])} {unit}; "
            f"{_src(lo)} reports {_n(lo['value'])} {unit}."
        )
        facts.append(
            f"Gap of {_n(hi['value'] - lo['value'])} {unit} "
            f"({_n(line['max_variance_percent'])}% variance) exceeds the allowed "
            f"{_n(line['allowed_variance_percent'])}%."
        )
        newest = min(evidence, key=lambda e: e["age_minutes"])
        facts.append(
            f"Most recent update came from {newest['system_name']}, "
            f"{newest['age_minutes']} minute(s) ago."
        )
        if req is not None and lo["value"] < req <= hi["value"]:
            decision_sensitive = True
            facts.append(
                f"The order needs {_n(req)} {unit}: enough according to "
                f"{hi['system_name']}, not enough according to {lo['system_name']}."
            )
        if hi["system_type"] == "ERP" and lo["system_type"] == "WMS":
            causes = [
                "ERP stock not reduced after a goods issue, scrap or transfer",
                "Damaged or quarantined stock still counted as usable in ERP",
                "Delayed synchronization between the warehouse system and ERP",
            ]
        else:
            causes = [
                "Stock movement recorded in one system but not the other",
                "Different definitions of usable stock between systems",
            ]
        owners = _owners(evidence)

    elif status == "STALE":
        max_age = line["maximum_source_age_minutes"]
        stale = [e for e in evidence if max_age is not None and e["age_minutes"] > max_age]
        for e in stale or evidence:
            facts.append(
                f"{_src(e)} was last updated {e['age_minutes']} minute(s) ago; "
                f"the contract allows {max_age} minutes."
            )
        causes = [
            "Scheduled integration job delayed or failed",
            "No inventory update posted since the last count",
        ]
        owners = _owners(stale or evidence)

    elif status == "INSUFFICIENT_EVIDENCE":
        present = {e["system_type"] for e in evidence}
        required = set(line["required_source_types"] or [])
        missing = sorted(required - present)
        reported = ", ".join(f"{_src(e)} = {_n(e['value'])} {unit}" for e in evidence)
        facts.append(f"Only {len(evidence)} source(s) reported: {reported or 'none'}.")
        facts.append(
            f"The contract requires {line['minimum_source_count']} source(s) of types "
            f"{sorted(required)}; missing: {missing}."
        )
        missing_systems = [s for s in systems if s["system_type"] in missing]
        for s in missing_systems:
            if s["system_id"] not in mapped_system_ids:
                facts.append(
                    f"{s['system_name']} has no confirmed ID mapping for this part, "
                    f"so its records cannot be matched."
                )
        causes = [
            "Part not yet mapped in the missing system",
            "Missing or failed data feed from the missing system",
        ]
        owners = [{"system": s["system_name"], "owner": s["owner"]} for s in missing_systems]

    elif line["decision"] == "INSUFFICIENT_STOCK":
        verified = line["verified_quantity"] or 0
        facts.append(
            f"Inventory is verified at {_n(verified)} {unit}, but the order needs "
            f"{_n(req)} {unit}: short by {_n(req - verified)} {unit}."
        )
        causes = ["Demand exceeds verified usable stock"]

    elif status == "NOT_EVALUATED":
        facts.append("Inventory for this part has not been evaluated yet.")
        causes = ["Trust evaluation has not run for this part"]

    else:
        facts.append("Inventory is verified and covers the order.")

    return {
        "line_number": line["line_number"],
        "part_id": line["part_id"],
        "part_name": line["part_name"],
        "plant_id": line["plant_id"],
        "trust_status": status,
        "decision": line["decision"],
        "required_quantity": req,
        "unit": unit,
        "contract": line.get("contract"),
        "facts": facts,
        "possible_causes": causes,
        "data_owners": owners,
        "decision_sensitive": decision_sensitive,
        "evidence": evidence,
    }


def order_decision(findings: list) -> str:
    decisions = {f["decision"] for f in findings}
    if "REVIEW_REQUIRED" in decisions:
        return "REVIEW_REQUIRED"
    if "INSUFFICIENT_STOCK" in decisions:
        return "INSUFFICIENT_STOCK"
    return "CAN_FULFILL"


def fallback_explanation(facts: dict) -> str:
    parts = [f"Order {facts['order_id']} is {facts['order_decision']}."]
    for line in facts["lines"]:
        parts.append(f"{line['part_name']} ({line['trust_status']}): " + " ".join(line["facts"]))
        if line["possible_causes"]:
            parts.append("Possible causes: " + "; ".join(line["possible_causes"]) + ".")
        if line["data_owners"]:
            parts.append(
                "Data owners: "
                + ", ".join(f"{o['owner']} ({o['system']})" for o in line["data_owners"])
                + "."
            )
    return "\n".join(parts)


def investigator_node(state: dict) -> dict:
    trace = []
    order_id = pick_target(state)
    if not order_id:
        return {"trace": [_step("pick_target", "Nothing to investigate")]}

    trace.append(_step("pick_target", f"Investigating {order_id}"))
    lines = get_order_lines(order_id)
    if not lines:
        return {
            "target_order_id": order_id,
            "investigation": {
                "order_id": order_id,
                "found": False,
                "explanation": f"Order {order_id} was not found.",
            },
            "trace": trace + [_step("get_order_lines", "Order not found")],
        }
    trace.append(_step("get_order_lines", f"{len(lines)} line(s) loaded"))

    systems = get_source_systems()
    findings = []
    for line in lines:
        evidence = get_evidence(line["evaluation_id"]) if line["evaluation_id"] else []
        mapped = get_mapped_system_ids(line["part_id"])
        findings.append(diagnose_line(line, evidence, systems, mapped))

    blocked = [f for f in findings if f["decision"] != "CAN_FULFILL"]
    decision = order_decision(findings)
    trace.append(
        _step("diagnose", f"{len(blocked)} blocked line(s); order decision {decision}")
    )

    value = next(
        (o["order_value"] for o in state.get("order_risk") or [] if o["order_id"] == order_id),
        None,
    )
    facts = {
        "order_id": order_id,
        "order_decision": decision,
        "order_value": value,
        "lines": [
            {
                k: f[k]
                for k in (
                    "part_name", "trust_status", "decision", "facts",
                    "possible_causes", "data_owners", "decision_sensitive",
                )
            }
            for f in (blocked or findings)
        ],
    }

    try:
        explanation = complete(
            INVESTIGATOR_PROMPT.format(order_id=order_id, facts=json.dumps(facts, indent=2))
        )
        trace.append(_step("explain", "Explanation written by LLM"))
    except Exception as exc:  # demo must never break
        explanation = fallback_explanation(facts)
        trace.append(_step("explain", f"LLM unavailable, template used: {exc}"))

    return {
        "target_order_id": order_id,
        "investigation": {
            "order_id": order_id,
            "found": True,
            "order_decision": decision,
            "findings": findings,
            "explanation": explanation,
        },
        "trace": trace,
    }