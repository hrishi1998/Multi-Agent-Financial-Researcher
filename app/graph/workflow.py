from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes.financial_researcher import financial_researcher_node
from app.graph.nodes.market_researcher import market_researcher_node
from app.graph.nodes.planner import planner_node
from app.graph.nodes.rag_researcher import rag_researcher_node
from app.graph.nodes.synthesizer import synthesizer_node
from app.graph.nodes.web_researcher import web_researcher_node
from app.graph.state import ResearchState

RESEARCHER_NODES = (
    "financial_researcher",
    "market_researcher",
    "web_researcher",
    "rag_researcher",
)


def build_research_graph() -> CompiledStateGraph:
    """Compile planner → parallel researchers → synthesizer → END."""
    workflow = StateGraph(ResearchState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("financial_researcher", financial_researcher_node)
    workflow.add_node("market_researcher", market_researcher_node)
    workflow.add_node("web_researcher", web_researcher_node)
    workflow.add_node("rag_researcher", rag_researcher_node)
    workflow.add_node("synthesizer", synthesizer_node)

    workflow.set_entry_point("planner")
    for researcher in RESEARCHER_NODES:
        workflow.add_edge("planner", researcher)
    workflow.add_edge(list(RESEARCHER_NODES), "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile()


graph = build_research_graph()
