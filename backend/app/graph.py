from langgraph.graph import END, START, StateGraph

from app.agents.monitor import monitor_node
from app.agents.state import TrustAgentState


def build_graph():
    graph = StateGraph(TrustAgentState)
    graph.add_node("monitor", monitor_node)
    graph.add_edge(START, "monitor")
    graph.add_edge("monitor", END)
    return graph.compile()