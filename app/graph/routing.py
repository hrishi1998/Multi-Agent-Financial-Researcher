from app.graph.state import ResearchState


def route_after_validation(state: ResearchState) -> str:
    """Retry planner while invalid; otherwise advance to quant_analysis."""
    if state.get("is_validated"):
        return "quant_analysis"
    if state.get("iteration_count", 0) < state.get("max_iterations", 2):
        return "planner"
    return "quant_analysis"
