import operator
from typing import Annotated, TypedDict


class TrustAgentState(TypedDict, total=False):
    request: str
    # Monitor
    order_risk: list[dict]
    kpis: dict
    briefing: str
    # Each agent appends its steps here; the UI will display this
    trace: Annotated[list[dict], operator.add]