import operator
from typing import Annotated, TypedDict


class TrustAgentState(TypedDict, total=False):
    request: str
    dry_run: bool
    # Monitor
    order_risk: list
    kpis: dict
    briefing: str
    # Investigator
    target_order_id: str
    investigation: dict
    # Planner
    plan: dict
    # Approval and Executor
    approvals: dict
    execution: list
    # Each agent appends its steps here; the UI will display this
    trace: Annotated[list, operator.add]