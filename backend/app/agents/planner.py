import json
from datetime import datetime, timedelta, timezone

from app.llm import complete
from app.tools.investigator_tools import get_mapped_system_ids, get_source_systems
from app.tools.planner_tools import get_supplier_options, propose_action

PLANNER_PROMPT = """You are the Planner agent of a supply-chain trust platform.
Write the request message that will be sent to {owner} once a human approves it.

Rules:
- Use ONLY the facts in the JSON below. Do not invent numbers, records, people or dates.
- Say what is needed, why it blocks the order, and what done means (success criteria).
- Cite record IDs exactly as given.
- End with the hold instruction.
- Maximum 100 words. Plain text only: no markdown, no asterisks, no headings,
  no placeholders such as [Name].

FACTS:
{facts}
"""


def _step(name: str, detail: str) -> dict:
    return {
        "agent": "planner",
        "step": name,
        "detail": detail,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def _n(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def urgency(order_ctx: dict) -> str:
    value = order_ctx.get("order_value") or 0
    hours = order_ctx.get("hours_to_due")
    if value >= 100000 or (hours is not None and hours <= 24):
        return "HIGH"
    return "NORMAL"


def _owner_of(systems: list, system_type: str) -> dict:
    match = next((s for s in systems if s["system_type"] == system_type), None)
    return match or {"system_id": None, "system_name": "Unknown system", "owner": "Data Governance"}


def plan_line(finding, order_ctx, systems, suppliers, mapped_system_ids, now=None) -> dict:
    """Deterministic action for one blocked line. No LLM."""
    now = now or datetime.now(timezone.utc)
    order_id = order_ctx["order_id"]
    part = finding["part_name"]
    plant = finding["plant_id"]
    unit = finding["unit"]
    status = finding["trust_status"]
    evidence = finding.get("evidence") or []
    req = finding["required_quantity"]

    base = {
        "order_id": order_id,
        "part_id": finding["part_id"],
        "part_name": part,
        "plant_id": plant,
        "evaluation_id": finding.get("evaluation_id"),
        "trust_status": status,
        "urgency": urgency(order_ctx),
        "evidence_refs": [
            {"system": e["system_name"], "record_id": e["record_id"], "value": e["value"]}
            for e in evidence
        ],
        "cc": [],
    }
    hold = f"Do not confirm {order_id} to the customer until {part} inventory is VERIFIED."

    if status == "CONFLICTED" and evidence:
        counter = next((e for e in evidence if e["system_type"] == "WMS"), None)
        counter = counter or min(evidence, key=lambda e: e["value"])
        others = [e for e in evidence if e is not counter]
        return {
            **base,
            "action_type": "REQUEST_RECOUNT",
            "assigned_system": counter["system_name"],
            "assigned_owner": counter["owner"],
            "cc": sorted({e["owner"] for e in others}),
            "title": f"Recount usable {part} at {plant}",
            "steps": [
                f"Physically count usable {part} at {plant}, excluding damaged and quarantined stock.",
                f"Post the count to {counter['system_name']}.",
                *[
                    f"{e['owner']} reconciles {e['system_name']} record {e['record_id']} "
                    f"(currently {_n(e['value'])} {unit})."
                    for e in others
                ],
                "Re-run the trust evaluation.",
            ],
            "success_criteria": (
                f"All sources report usable {part} within "
                f"{_n(finding['allowed_variance_percent'])}% of each other."
            ),
            "hold": hold,
        }

    if status == "STALE":
        max_age = finding["maximum_source_age_minutes"]
        stale = [e for e in evidence if max_age is not None and e["age_minutes"] > max_age]
        stale = stale or evidence
        target = stale[0] if stale else {"system_name": "Unknown system", "owner": "Data Governance"}
        return {
            **base,
            "action_type": "REQUEST_DATA_REFRESH",
            "assigned_system": target["system_name"],
            "assigned_owner": target["owner"],
            "cc": sorted({e["owner"] for e in stale if e["owner"] != target["owner"]}),
            "title": f"Refresh {part} inventory data at {plant}",
            "steps": [
                *[
                    f"Send a current inventory extract for {part} from {e['system_name']} "
                    f"(record {e['record_id']}, last updated {e['age_minutes']} minutes ago)."
                    for e in stale
                ],
                "Check the scheduled integration job for failures.",
                "Re-run the trust evaluation.",
            ],
            "success_criteria": f"Every source updated within the last {max_age} minutes.",
            "hold": hold,
        }

    if status == "INSUFFICIENT_EVIDENCE":
        present = {e["system_type"] for e in evidence}
        required = finding.get("required_source_types") or []
        missing = [s for s in systems if s["system_type"] in set(required) - present]
        target = missing[0] if missing else _owner_of(systems, "WMS")
        steps = []
        for s in missing:
            if s["system_id"] not in mapped_system_ids:
                steps.append(
                    f"Confirm the {s['system_name']} item ID for {part} and submit the mapping for approval."
                )
            steps.append(f"Report current usable {part} at {plant} from {s['system_name']}.")
        steps.append("Re-run the trust evaluation.")
        return {
            **base,
            "action_type": "REQUEST_SOURCE_CONFIRMATION",
            "assigned_system": target["system_name"],
            "assigned_owner": target["owner"],
            "title": f"Confirm {part} inventory from {target['system_name']}",
            "steps": steps,
            "success_criteria": (
                f"At least {finding['minimum_source_count']} sources ({', '.join(required)}) "
                f"report usable {part} within {_n(finding['allowed_variance_percent'])}% of each other."
            ),
            "hold": hold,
        }

    if finding["decision"] == "INSUFFICIENT_STOCK":
        verified = finding.get("verified_quantity") or 0
        shortfall = req - verified
        procurement = _owner_of(systems, "SUPPLIER_PORTAL")
        supplier = suppliers[0] if suppliers else None
        hours = order_ctx.get("hours_to_due")
        days_to_due = hours / 24 if hours is not None else None
        common = {
            **base,
            "assigned_system": procurement["system_name"],
            "assigned_owner": procurement["owner"],
            "success_criteria": f"{order_id} fully covered by verified stock or an agreed revised date.",
            "hold": f"Do not promise the full {_n(req)} {unit} by the original date.",
        }
        if supplier and supplier["lead_time_days"] is not None and days_to_due is not None \
                and supplier["lead_time_days"] > days_to_due:
            earliest = (now + timedelta(days=supplier["lead_time_days"])).date().isoformat()
            return {
                **common,
                "action_type": "PARTIAL_SHIPMENT_AND_EXPEDITE",
                "title": f"Ship {_n(verified)} {unit} now, expedite {_n(shortfall)} {unit} of {part}",
                "steps": [
                    f"Ship the verified {_n(verified)} {unit} against {order_id} now.",
                    f"Request expedited delivery of {_n(shortfall)} {unit} from "
                    f"{supplier['supplier_name']} (standard lead time {supplier['lead_time_days']} days, "
                    f"risk score {_n(supplier['risk_score'])}).",
                    f"Agree a revised date for the remaining {_n(shortfall)} {unit}; "
                    f"earliest at standard lead time is {earliest}.",
                ],
            }
        return {
            **common,
            "action_type": "EXPEDITE_SUPPLY",
            "title": f"Expedite {_n(shortfall)} {unit} of {part}",
            "steps": [
                (
                    f"Order {_n(shortfall)} {unit} from {supplier['supplier_name']} "
                    f"(lead time {supplier['lead_time_days']} days)."
                    if supplier
                    else f"Identify an alternative supplier for {_n(shortfall)} {unit} of {part}."
                ),
                "Re-run the trust evaluation when stock is received.",
            ],
        }

    return {
        **base,
        "action_type": "RUN_TRUST_EVALUATION",
        "assigned_system": "Trust engine",
        "assigned_owner": "Data Governance",
        "title": f"Evaluate {part} inventory at {plant}",
        "steps": ["Run the trust evaluation for this part."],
        "success_criteria": "A current trust evaluation exists for this part.",
        "hold": hold,
    }


def fallback_message(action: dict) -> str:
    return (
        f"{action['assigned_owner']}: {action['title']}. "
        + " ".join(action["steps"])
        + f" Done when: {action['success_criteria']} {action['hold']}"
    )


def draft_message(action: dict):
    facts = {
        k: action[k]
        for k in (
            "order_id", "part_name", "plant_id", "action_type", "title", "assigned_owner",
            "cc", "steps", "success_criteria", "hold", "urgency", "evidence_refs",
        )
    }
    try:
        text = complete(
            PLANNER_PROMPT.format(owner=action["assigned_owner"], facts=json.dumps(facts, indent=2))
        )
        return text, "Message drafted by LLM"
    except Exception as exc:  # demo must never break
        return fallback_message(action), f"LLM unavailable, template used: {exc}"


def planner_node(state: dict) -> dict:
    inv = state.get("investigation") or {}
    if not inv.get("found"):
        return {"trace": [_step("skip", "No investigation to plan from")]}

    order_id = inv["order_id"]
    blocked = [f for f in inv.get("findings", []) if f["decision"] != "CAN_FULFILL"]
    if not blocked:
        return {
            "plan": {"order_id": order_id, "actions": [], "summary": f"{order_id} needs no action."},
            "trace": [_step("plan", "No action needed")],
        }

    ctx = next((o for o in state.get("order_risk") or [] if o["order_id"] == order_id), {})
    order_ctx = {**ctx, "order_id": order_id}
    systems = get_source_systems()
    trace = [_step("load_context", f"{len(blocked)} blocked line(s) for {order_id}")]

    actions = []
    for finding in blocked:
        suppliers = (
            get_supplier_options(finding["part_id"])
            if finding["decision"] == "INSUFFICIENT_STOCK" else []
        )
        mapped = (
            get_mapped_system_ids(finding["part_id"])
            if finding["trust_status"] == "INSUFFICIENT_EVIDENCE" else set()
        )
        action = plan_line(finding, order_ctx, systems, suppliers, mapped)
        trace.append(
            _step("choose_action",
                  f"{finding['part_name']}: {action['action_type']} -> {action['assigned_owner']}")
        )

        action["message"], note = draft_message(action)
        trace.append(_step("draft_message", note))

        if state.get("dry_run"):
            action.update({"action_id": None, "persisted": False})
            trace.append(_step("propose_action", "Dry run: not saved"))
        else:
            try:
                result = propose_action(action)
                action.update({
                    "action_id": result.get("action_id"),
                    "persisted": True,
                    "created": result.get("created"),
                })
                state_note = "created" if result.get("created") else "already open, reused"
                trace.append(
                    _step("propose_action", f"{action['action_id']} {state_note} (status PROPOSED)")
                )
            except Exception as exc:
                action.update({"action_id": None, "persisted": False})
                trace.append(_step("propose_action", f"Could not save proposal: {exc}"))
        actions.append(action)

    return {
        "plan": {
            "order_id": order_id,
            "actions": actions,
            "summary": f"{len(actions)} action(s) proposed for {order_id}; awaiting human approval.",
        },
        "trace": trace,
    }