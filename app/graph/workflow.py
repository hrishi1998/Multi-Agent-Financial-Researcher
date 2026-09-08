import os

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.financial_researcher import financial_researcher_node
from app.graph.nodes.formatter import formatter_node
from app.graph.nodes.market_researcher import market_researcher_node
from app.graph.nodes.planner import planner_node
from app.graph.nodes.quant_analysis import quant_analysis_node
from app.graph.nodes.rag_researcher import rag_researcher_node
from app.graph.nodes.synthesizer import synthesizer_node
from app.graph.nodes.validator import validator_node
from app.graph.nodes.web_researcher import web_researcher_node
from app.graph.routing import route_after_validation
from app.graph.state import ResearchState
from app.memory.short_term import get_checkpointer

RESEARCHER_NODES = (
    "financial_researcher",
    "market_researcher",
    "web_researcher",
    "rag_researcher",
)


def build_research_graph() -> CompiledStateGraph:
    """Compile planner → researchers → validator ↺ planner → quant → synth → formatter."""
    workflow = StateGraph(ResearchState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("financial_researcher", financial_researcher_node)
    workflow.add_node("market_researcher", market_researcher_node)
    workflow.add_node("web_researcher", web_researcher_node)
    workflow.add_node("rag_researcher", rag_researcher_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("quant_analysis", quant_analysis_node)
    workflow.add_node("synthesizer", synthesizer_node)
    workflow.add_node("formatter", formatter_node)

    workflow.set_entry_point("planner")
    for researcher in RESEARCHER_NODES:
        workflow.add_edge("planner", researcher)
    workflow.add_edge(list(RESEARCHER_NODES), "validator")
    workflow.add_conditional_edges(
        "validator",
        route_after_validation,
        {
            "quant_analysis": "quant_analysis",
            "planner": "planner",
        },
    )
    workflow.add_edge("quant_analysis", "synthesizer")
    workflow.add_edge("synthesizer", "formatter")
    workflow.add_edge("formatter", END)

    interrupt_before = ["synthesizer"] if os.getenv("ENABLE_HITL") == "1" else []
    return workflow.compile(
        checkpointer=get_checkpointer(),
        interrupt_before=interrupt_before,
    )


_compiled_graph: CompiledStateGraph | None = None


def get_compiled_graph() -> CompiledStateGraph:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_research_graph()
    return _compiled_graph


def rebuild_graph() -> CompiledStateGraph:
    global _compiled_graph, graph
    _compiled_graph = build_research_graph()
    graph = _compiled_graph
    return _compiled_graph


graph = get_compiled_graph()
