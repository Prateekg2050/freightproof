from langgraph.graph import END, START, StateGraph

from app.agents.investigator import investigator_node, pick_target
from app.agents.monitor import monitor_node
from app.agents.planner import planner_node
from app.agents.state import TrustAgentState


def route_after_monitor(state: dict) -> str:
    return "investigator" if pick_target(state) else END


def route_after_investigator(state: dict) -> str:
    inv = state.get("investigation") or {}
    if inv.get("found") and inv.get("order_decision") != "CAN_FULFILL":
        return "planner"
    return END


def build_graph():
    graph = StateGraph(TrustAgentState)
    graph.add_node("monitor", monitor_node)
    graph.add_node("investigator", investigator_node)
    graph.add_node("planner", planner_node)

    graph.add_edge(START, "monitor")
    graph.add_conditional_edges(
        "monitor", route_after_monitor, {"investigator": "investigator", END: END}
    )
    graph.add_conditional_edges(
        "investigator", route_after_investigator, {"planner": "planner", END: END}
    )
    graph.add_edge("planner", END)
    return graph.compile()