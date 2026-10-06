import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langgraph.types import Command  # noqa: E402

from app.graph import build_graph  # noqa: E402


def parse_args(args: list) -> dict:
    opts = {"dry_run": False, "approve_as": None, "reject_as": None, "words": []}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--dry-run":
            opts["dry_run"] = True
        elif a in ("--approve-as", "--reject-as") and i + 1 < len(args):
            opts[a[2:].replace("-", "_")] = args[i + 1]
            i += 1
        else:
            opts["words"].append(a)
        i += 1
    return opts


def pending_interrupts(graph, config) -> list:
    snapshot = graph.get_state(config)
    return [i for task in snapshot.tasks for i in (task.interrupts or [])]


def collect_decisions(payload: dict, opts: dict) -> dict:
    decisions = []
    for a in payload["actions"]:
        print(f"\n>>> APPROVAL NEEDED: {a['action_id']} | {a['action_type']} | urgency {a['urgency']}")
        print(f"    {a['title']}")
        print(f"    assigned to {a['assigned_owner']} ({a['assigned_system']}); cc {a['cc']}")
        for s in a["steps"]:
            print(f"    - {s}")
        print(f"    done when: {a['success_criteria']}")
        print(f"    hold: {a['hold']}")

        if opts["approve_as"]:
            decisions.append({"action_id": a["action_id"], "decision": "APPROVED",
                              "decided_by": opts["approve_as"], "note": "Approved via CLI"})
        elif opts["reject_as"]:
            decisions.append({"action_id": a["action_id"], "decision": "REJECTED",
                              "decided_by": opts["reject_as"], "note": "Rejected via CLI"})
        else:
            answer = input("    Approve? [y/n]: ").strip().lower()
            name = input("    Your name: ").strip()
            note = input("    Note (optional): ").strip()
            decisions.append({"action_id": a["action_id"],
                              "decision": "APPROVED" if answer == "y" else "REJECTED",
                              "decided_by": name, "note": note})
    return {"decisions": decisions}


def print_report(request: str, opts: dict, state: dict) -> None:
    print(f"\n=== REQUEST: {request}{' (dry run)' if opts['dry_run'] else ''} ===")
    print("\n=== TRACE ===")
    for step in state.get("trace", []):
        print(f"[{step['agent']}] {step['step']}: {step['detail']}")

    inv = state.get("investigation")
    if inv:
        print(f"\n=== INVESTIGATION: {inv['order_id']} ===")
        print(inv["explanation"])

    plan = state.get("plan")
    if plan:
        print(f"\n=== PLAN: {plan['summary']} ===")
        for a in plan["actions"]:
            print(f"- {a.get('action_id') or '(not saved)'} | {a['action_type']} | {a['title']}")

    approvals = state.get("approvals")
    if approvals:
        print("\n=== APPROVALS ===")
        for d in approvals["decisions"]:
            print(json.dumps(d, default=str))

    execution = state.get("execution")
    if execution:
        print("\n=== EXECUTION ===")
        for r in execution:
            print(json.dumps(r, default=str))
    verifications = state.get("verifications")
    if verifications:
        print("\n=== VERIFICATION ===")
        for v in verifications:
            print(f"\nCycle {v.get('cycle')}: {v.get('decision_before')} -> {v.get('decision_after')}")
            for o in v.get("outcomes", []):
                print(f"  {o['action_id']} | {o['action_type']} | {o['outcome']} | status {o['action_status']}")
            print(f"  next: {v.get('next')}")
            print(f"  summary: {v.get('summary')}")


def main() -> None:
    opts = parse_args(sys.argv[1:])
    request = " ".join(opts["words"]) or "morning scan"

    graph = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    graph.invoke({"request": request, "dry_run": opts["dry_run"], "trace": []}, config)

    interrupts = pending_interrupts(graph, config)
    while interrupts:
        response = collect_decisions(interrupts[0].value, opts)
        graph.invoke(Command(resume=response), config)
        interrupts = pending_interrupts(graph, config)

    print_report(request, opts, graph.get_state(config).values)

    


if __name__ == "__main__":
    main()