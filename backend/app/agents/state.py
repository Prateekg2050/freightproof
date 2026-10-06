import operator
from typing import Annotated, TypedDict


class TrustAgentState(TypedDict, total=False):
    request: str
    # Monitor
    order_risk: list
    kpis: dict
    briefing: str
    # Investigator
    target_order_id: str
    investigation: dict
    # Each agent appends its steps here; the UI will display this
    trace: Annotated[list, operator.add]