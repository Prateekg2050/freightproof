import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph import build_graph  # noqa: E402


def main() -> None:
    result = build_graph().invoke({"request": "morning scan", "trace": []})

    print("\n=== TRACE ===")
    for step in result["trace"]:
        print(f"[{step['agent']}] {step['step']}: {step['detail']}")

    print("\n=== KPIs ===")
    print(json.dumps(result["kpis"], indent=2))

    print("\n=== BRIEFING ===")
    print(result["briefing"])


if __name__ == "__main__":
    main()