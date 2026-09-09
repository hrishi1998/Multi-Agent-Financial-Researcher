from __future__ import annotations

import httpx
import streamlit as st

from client import StreamEvent, get_run, iter_run_events, start_research

TERMINAL = {"run.completed", "run.failed", "run.cancelled"}
PROGRESS_HINTS = (
    ("run.started", 0.05),
    ("planner.", 0.15),
    ("research.", 0.40),
    ("validation.", 0.55),
    ("quant.", 0.70),
    ("synthesis.", 0.85),
    ("report.", 0.92),
    ("cache.hit", 0.95),
    ("hitl.paused", 0.75),
    ("run.completed", 1.0),
)


def _progress_for(event_type: str) -> float:
    score = 0.0
    for prefix, value in PROGRESS_HINTS:
        if event_type.startswith(prefix) or event_type == prefix:
            score = max(score, value)
    return score


def _render_event_log(events: list[StreamEvent]) -> str:
    lines = []
    for event in events[-40:]:
        lines.append(f"- `{event.event_type}` · **{event.agent}** — {event.message}")
    return "\n".join(lines) or "_Waiting for the first agent event…_"


def render_report(report: dict) -> None:
    st.subheader("Executive Summary")
    st.markdown(report.get("executive_conclusion") or "_No executive summary._")

    st.subheader("Key Findings")
    findings = report.get("key_findings") or []
    if findings:
        st.markdown("\n".join(f"- {item}" for item in findings))
    else:
        st.markdown("_No key findings._")

    cols = st.columns(2)
    with cols[0]:
        st.markdown("### Bull Case")
        st.markdown("\n".join(f"- {item}" for item in report.get("bull_case") or []) or "_None_")
    with cols[1]:
        st.markdown("### Bear Case")
        st.markdown("\n".join(f"- {item}" for item in report.get("bear_case") or []) or "_None_")

    st.subheader("Financial Metrics")
    metrics = report.get("financial_metrics") or {}
    if metrics:
        rows = ["| Metric | Value |", "|---|---|"]
        rows.extend(f"| {name} | {value} |" for name, value in metrics.items())
        st.markdown("\n".join(rows))
    derived = report.get("derived_metrics") or {}
    if derived:
        st.markdown("### Calculated Metrics")
        table = ["| Metric | Formula | Current | Unit |", "|---|---|---|---|"]
        for name, metric in derived.items():
            if isinstance(metric, dict):
                table.append(
                    f"| {metric.get('name') or name} | `{metric.get('formula', '')}` | "
                    f"{metric.get('current_value', '')} | {metric.get('unit', '')} |"
                )
        st.markdown("\n".join(table))


def render_research_tab() -> None:
    st.markdown("Start a live research run and watch LangGraph agents complete over SSE.")
    query = st.text_area(
        "Research query",
        value="Evaluate NVIDIA's profitability and revenue growth over the last 4 quarters",
        height=100,
    )
    submitted = st.button("Start research", type="primary")

    log_box = st.empty()
    progress = st.progress(0, text="Idle")
    status_box = st.empty()

    if submitted:
        if not query.strip():
            st.warning("Enter a research query first.")
            return
        try:
            run_id = start_research(query.strip())
        except httpx.HTTPError as exc:
            st.error(f"Could not start research: {exc}")
            return
        st.session_state["last_run_id"] = run_id
        events: list[StreamEvent] = []
        terminal = None
        try:
            for event in iter_run_events(run_id):
                events.append(event)
                progress.progress(_progress_for(event.event_type), text=event.event_type)
                log_box.markdown(_render_event_log(events))
                if event.event_type == "hitl.paused":
                    st.session_state["hitl_run_id"] = run_id
                    status_box.warning(
                        f"Run `{run_id}` paused for human approval. "
                        "Open the HITL tab to review evidence and resume."
                    )
                    return
                if event.event_type in TERMINAL:
                    terminal = event.event_type
                    break
        except httpx.HTTPError as exc:
            st.error(f"SSE stream failed: {exc}")
            return

        if terminal == "run.completed":
            payload = get_run(run_id)
            report = payload.get("final_report") or {}
            st.session_state["last_report"] = report
            status_box.success(f"Run `{run_id}` completed.")
            render_report(report)
        elif terminal == "run.failed":
            status_box.error(f"Run `{run_id}` failed.")
        elif terminal == "run.cancelled":
            status_box.warning(f"Run `{run_id}` was cancelled.")

    elif st.session_state.get("last_report"):
        st.caption(f"Last run: `{st.session_state.get('last_run_id', '')}`")
        render_report(st.session_state["last_report"])
