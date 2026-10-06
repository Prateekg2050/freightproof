import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph import build_graph  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    request = " ".join(a for a in args if a != "--dry-run") or "morning scan"

    result = build_graph().invoke({"request": request, "dry_run": dry_run, "trace": []})

    print(f"\n=== REQUEST: {request}{' (dry run)' if dry_run else ''} ===")
    print("\n=== TRACE ===")
    for step in result["trace"]:
        print(f"[{step['agent']}] {step['step']}: {step['detail']}")

    inv = result.get("investigation")
    if inv:
        print(f"\n=== INVESTIGATION: {inv['order_id']} ===")
        print(inv["explanation"])

    plan = result.get("plan")
    if plan:
        print(f"\n=== PLAN: {plan['summary']} ===")
        for a in plan["actions"]:
            print(f"\n{a.get('action_id') or '(not saved)'} | {a['action_type']} | urgency {a['urgency']}")
            print(f"  title:    {a['title']}")
            print(f"  assigned: {a['assigned_owner']} ({a['assigned_system']}); cc {a['cc']}")
            for s in a["steps"]:
                print(f"  step:     {s}")
            print(f"  done when: {a['success_criteria']}")
            print(f"  hold:     {a['hold']}")
            print(f"  evidence: {json.dumps(a['evidence_refs'])}")
            print(f"\n  --- Message ---\n  {a['message']}")


if __name__ == "__main__":
    main()