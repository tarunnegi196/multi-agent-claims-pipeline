"""
LangGraph StateGraph — wires all agents into the claims processing pipeline.

Flow:
  intake → classify → verify ─[halt?]─► END
                              └─► extract ─[halt?]─► END
                                          └─► fraud → compose → END

Conditional routing after verify and extract: any node that sets
state["halt"]=True causes the pipeline to skip to END without calling
the remaining nodes. The FastAPI layer builds the final FinalOutput from
whatever state was accumulated.
"""
from langgraph.graph import StateGraph, END

from app.models.graph_state import GraphState
from app.agents.intake import intake_node
from app.agents.classifier import classify_node
from app.agents.verifier import verify_node
from app.agents.extractor import extract_node
from app.agents.fraud import fraud_node
from app.agents.composer import compose_node


def _route_after_intake(state: GraphState) -> str:
    return "end" if state.get("halt", False) else "classify"


def _route_after_verify(state: GraphState) -> str:
    return "end" if state.get("halt", False) else "extract"


def _route_after_extract(state: GraphState) -> str:
    return "end" if state.get("halt", False) else "fraud"


def build_graph() -> StateGraph:
    builder = StateGraph(GraphState)

    builder.add_node("intake", intake_node)
    builder.add_node("classify", classify_node)
    builder.add_node("verify", verify_node)
    builder.add_node("extract", extract_node)
    builder.add_node("fraud", fraud_node)
    builder.add_node("compose", compose_node)

    builder.set_entry_point("intake")

    builder.add_conditional_edges(
        "intake",
        _route_after_intake,
        {"end": END, "classify": "classify"},
    )
    builder.add_edge("classify", "verify")
    builder.add_conditional_edges(
        "verify",
        _route_after_verify,
        {"end": END, "extract": "extract"},
    )
    builder.add_conditional_edges(
        "extract",
        _route_after_extract,
        {"end": END, "fraud": "fraud"},
    )
    builder.add_edge("fraud", "compose")
    builder.add_edge("compose", END)

    return builder.compile()


# Module-level singleton — imported by main.py and tests
claims_graph = build_graph()
