from typing import Any, Dict, Optional

from app.api.schemas.events import AgentEvent, EventType

NODE_COMPLETED_EVENTS: Dict[str, EventType] = {
    "planner": EventType.PLANNER_COMPLETED,
    "financial_researcher": EventType.RESEARCH_FINANCIAL_COMPLETED,
    "market_researcher": EventType.RESEARCH_MARKET_COMPLETED,
    "web_researcher": EventType.RESEARCH_WEB_COMPLETED,
    "rag_researcher": EventType.RESEARCH_RAG_COMPLETED,
    "quant_analysis": EventType.QUANT_ANALYSIS_COMPLETED,
    "synthesizer": EventType.SYNTHESIS_COMPLETED,
    "formatter": EventType.REPORT_COMPLETED,
}


def map_node_update(
    run_id: str,
    node_name: str,
    update: Any,
    sequence_number: int,
) -> AgentEvent:
    """Convert a LangGraph node update into a typed AgentEvent (no raw state leak)."""
    payload_keys = list(update.keys()) if isinstance(update, dict) else []
    event_type = NODE_COMPLETED_EVENTS.get(node_name)
    status = "COMPLETED"
    message = f"{node_name} completed."

    if node_name == "validator":
        is_validated = bool(update.get("is_validated")) if isinstance(update, dict) else False
        event_type = EventType.VALIDATION_PASSED if is_validated else EventType.VALIDATION_WARNING
        status = "COMPLETED" if is_validated else "WARNING"
        message = "Validation passed." if is_validated else "Validation requires another research pass."

    if event_type is None:
        event_type = EventType.SYNTHESIS_COMPLETED
        message = f"{node_name} produced an update."

    return AgentEvent(
        run_id=run_id,
        agent=node_name,
        event_type=event_type,
        status=status,
        message=message,
        payload={"node": node_name, "updated_keys": payload_keys},
        sequence_number=sequence_number,
    )


def lifecycle_event(
    run_id: str,
    event_type: EventType,
    message: str,
    status: str,
    sequence_number: int = 0,
    payload: Optional[Dict[str, Any]] = None,
) -> AgentEvent:
    return AgentEvent(
        run_id=run_id,
        agent="run_manager",
        event_type=event_type,
        status=status,
        message=message,
        payload=payload or {},
        sequence_number=sequence_number,
    )
