from langgraph.graph import END, START, StateGraph

try:
    from langgraph.checkpoint.memory import InMemorySaver as _Saver
except ImportError:  # older langgraph
    from langgraph.checkpoint.memory import MemorySaver as _Saver

from app.agents.approval import approval_node
from app.agents.executor import executor_node
from app.agents.investigator import investigator_node, pick_target
from app.agents.monitor import monitor_node
from app.agents.planner import planner_node
from app.agents.state import TrustAgentState
from app.agents.verifier import verifier_node


def route_after_monitor(state: dict) -> str:
    return "investigator" if pick_target(state) else END


def route_after_investigator(state: dict) -> str:
    inv = state.get("investigation") or {}
    if inv.get("found") and inv.get("order_decision") != "CAN_FULFILL":
        return "planner"
    return END


def route_after_planner(state: dict) -> str:
    if state.get("dry_run"):
        return END
    actions = (state.get("plan") or {}).get("actions", [])
    return "approval" if any(a.get("action_id") for a in actions) else END


def route_after_approval(state: dict) -> str:
    approved = (state.get("approvals") or {}).get("approved_action_ids", [])
    return "executor" if approved else END


def route_after_verifier(state: dict) -> str:
    verifications = state.get("verifications") or []
    if verifications and verifications[-1].get("replan"):
        return "investigator"
    return END


def build_graph(checkpointer=None):
    graph = StateGraph(TrustAgentState)
    graph.add_node("monitor", monitor_node)
    graph.add_node("investigator", investigator_node)
    graph.add_node("planner", planner_node)
    graph.add_node("approval", approval_node)
    graph.add_node("executor", executor_node)
    graph.add_node("verifier", verifier_node)

    graph.add_edge(START, "monitor")
    graph.add_conditional_edges("monitor", route_after_monitor,
                                {"investigator": "investigator", END: END})
    graph.add_conditional_edges("investigator", route_after_investigator,
                                {"planner": "planner", END: END})
    graph.add_conditional_edges("planner", route_after_planner,
                                {"approval": "approval", END: END})
    graph.add_conditional_edges("approval", route_after_approval,
                                {"executor": "executor", END: END})
    graph.add_edge("executor", "verifier")
    graph.add_conditional_edges("verifier", route_after_verifier,
                                {"investigator": "investigator", END: END})

    # A checkpointer is required for interrupt/resume
    return graph.compile(checkpointer=checkpointer or _Saver())