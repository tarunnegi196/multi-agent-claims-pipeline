"""
LangGraph StateGraph — wires all agents into the claims processing pipeline.

Flow:
  intake → classify → verify ─[halt?]─► report → END
                              └─► extract ─[halt?]─► report → END
                                          └─► consistency → fraud → compose → report → END

Conditional routing after intake, verify, and extract: any node that sets
state["halt"]=True jumps to the report node (which still generates a
narrative for halted claims) then to END.
"""
from langgraph.graph import StateGraph, END

from app.models.graph_state import GraphState
from app.agents.intake import intake_node
from app.agents.classifier import classify_node
from app.agents.verifier import verify_node
from app.agents.extractor import extract_node
from app.agents.consistency import consistency_node
from app.agents.fraud import fraud_node
from app.agents.composer import compose_node
from app.agents.reporter import report_node


def _route_after_intake(state: GraphState) -> str:
    return "report" if state.get("halt", False) else "classify"


def _route_after_verify(state: GraphState) -> str:
    return "report" if state.get("halt", False) else "extract"


def _route_after_extract(state: GraphState) -> str:
    return "report" if state.get("halt", False) else "consistency"


def build_graph() -> StateGraph:
    builder = StateGraph(GraphState)

    builder.add_node("intake", intake_node)
    builder.add_node("classify", classify_node)
    builder.add_node("verify", verify_node)
    builder.add_node("extract", extract_node)
    builder.add_node("consistency", consistency_node)
    builder.add_node("fraud", fraud_node)
    builder.add_node("compose", compose_node)
    builder.add_node("report", report_node)

    builder.set_entry_point("intake")

    builder.add_conditional_edges(
        "intake",
        _route_after_intake,
        {"report": "report", "classify": "classify"},
    )
    builder.add_edge("classify", "verify")
    builder.add_conditional_edges(
        "verify",
        _route_after_verify,
        {"report": "report", "extract": "extract"},
    )
    builder.add_conditional_edges(
        "extract",
        _route_after_extract,
        {"report": "report", "consistency": "consistency"},
    )
    builder.add_edge("consistency", "fraud")
    builder.add_edge("fraud", "compose")
    builder.add_edge("compose", "report")
    builder.add_edge("report", END)

    return builder.compile()


# Module-level singleton — imported by main.py and tests
claims_graph = build_graph()
