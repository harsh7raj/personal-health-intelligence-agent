from langgraph.graph import END, START, StateGraph

from app.graph.nodes.intake import intake_node
from app.graph.nodes.memory import memory_node
from app.graph.nodes.reasoning import reasoning_node
from app.graph.nodes.response import response_node
from app.graph.nodes.router import question_node, router_node
from app.graph.state import GraphState


def _route_after_router(state: GraphState) -> str:
    # Questions are not saved (memory.md D21); logs and "both" go through intake.
    # In chat, a question goes to memory -> response for an answer (D31).
    if state.message_kind == "question":
        return "memory" if state.chat else "question"
    return "intake"


def _route_after_memory(state: GraphState) -> str:
    return "reasoning" if state.new_entry else "response"


def _route_after_intake(state: GraphState) -> str:
    return "clarify" if state.needs_clarification else "memory"


def _clarify_node(state: GraphState) -> dict:
    # Terminal node for the clarify branch; pending_question is already set by intake.
    return {}


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("router", router_node)
    g.add_node("question", question_node)
    g.add_node("intake", intake_node)
    g.add_node("clarify", _clarify_node)
    g.add_node("memory", memory_node)
    g.add_node("reasoning", reasoning_node)
    g.add_node("response", response_node)

    g.add_edge(START, "router")
    g.add_conditional_edges(
        "router",
        _route_after_router,
        {"question": "question", "intake": "intake", "memory": "memory"},
    )
    g.add_edge("question", END)
    g.add_conditional_edges(
        "intake", _route_after_intake, {"clarify": "clarify", "memory": "memory"}
    )
    g.add_edge("clarify", END)
    g.add_conditional_edges(
        "memory", _route_after_memory, {"reasoning": "reasoning", "response": "response"}
    )
    g.add_edge("reasoning", "response")
    g.add_edge("response", END)
    return g.compile()


graph = build_graph()
