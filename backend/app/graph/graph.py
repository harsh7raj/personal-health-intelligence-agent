from langgraph.graph import END, START, StateGraph

from app.graph.nodes.intake import intake_node
from app.graph.nodes.memory import memory_node
from app.graph.nodes.reasoning import reasoning_node
from app.graph.nodes.response import response_node
from app.graph.state import GraphState


def _route_after_intake(state: GraphState) -> str:
    return "clarify" if state.needs_clarification else "memory"


def _clarify_node(state: GraphState) -> dict:
    # Terminal node for the clarify branch; pending_question is already set by intake.
    return {}


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("intake", intake_node)
    g.add_node("clarify", _clarify_node)
    g.add_node("memory", memory_node)
    g.add_node("reasoning", reasoning_node)
    g.add_node("response", response_node)

    g.add_edge(START, "intake")
    g.add_conditional_edges(
        "intake", _route_after_intake, {"clarify": "clarify", "memory": "memory"}
    )
    g.add_edge("clarify", END)
    g.add_edge("memory", "reasoning")
    g.add_edge("reasoning", "response")
    g.add_edge("response", END)
    return g.compile()


graph = build_graph()
