import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph import build_graph  # noqa: E402


def main() -> None:
    request = " ".join(sys.argv[1:]) or "morning scan"
    result = build_graph().invoke({"request": request, "trace": []})

    print(f"\n=== REQUEST: {request} ===")
    print("\n=== TRACE ===")
    for step in result["trace"]:
        print(f"[{step['agent']}] {step['step']}: {step['detail']}")

    print("\n=== BRIEFING ===")
    print(result.get("briefing", ""))

    inv = result.get("investigation")
    if inv:
        print(f"\n=== INVESTIGATION: {inv['order_id']} ===")
        for f in inv.get("findings", []):
            if f["decision"] == "CAN_FULFILL":
                continue
            print(f"\n{f['part_name']} | {f['trust_status']} | {f['decision']}")
            for fact in f["facts"]:
                print(f"  fact:  {fact}")
            for cause in f["possible_causes"]:
                print(f"  cause: {cause}")
            print(f"  owners: {json.dumps(f['data_owners'])}")
        print("\n--- Explanation ---")
        print(inv["explanation"])


if __name__ == "__main__":
    main()