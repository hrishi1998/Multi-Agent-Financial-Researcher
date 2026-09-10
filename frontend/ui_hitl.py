from __future__ import annotations

import httpx
import streamlit as st

from client import get_run_state, resume_run


def _evidence_lines(item: dict) -> str:
    parts = [
        f"- **Source:** {item.get('source') or '—'}",
        f"- **Type:** {item.get('source_type') or '—'}",
        f"- **Claim:** {item.get('claim') or '—'}",
        f"- **Metric:** {item.get('metric') or '—'} = {item.get('value') if item.get('value') is not None else '—'}",
        f"- **Period:** {item.get('reporting_period') or item.get('temporal_anchor') or '—'}",
        f"- **Confidence:** {item.get('confidence', '—')}",
    ]
    if item.get("raw_text"):
        parts.append(f"> {item['raw_text']}")
    return "\n".join(parts)


def render_hitl_tab() -> None:
    st.markdown("Look up a paused graph, inspect collected evidence, and resume synthesis.")
    default_run = st.session_state.get("hitl_run_id") or st.session_state.get("last_run_id") or ""
    run_id = st.text_input("Paused run ID", value=default_run)
    load = st.button("Load paused state")
    resume = st.button("Resume graph", type="primary")

    if load:
        if not run_id.strip():
            st.warning("Enter a run ID.")
            return
        try:
            state = get_run_state(run_id.strip())
        except httpx.HTTPError as exc:
            st.error(f"Could not load run state: {exc}")
            return
        st.session_state["hitl_state"] = state
        st.session_state["hitl_run_id"] = run_id.strip()

    state = st.session_state.get("hitl_state")
    if state:
        st.caption(f"Status: `{state.get('status')}` · next: {state.get('next_nodes') or []}")
        with st.expander("Collected evidence", expanded=True):
            evidence = state.get("evidence") or []
            if not evidence:
                st.markdown("_No evidence in checkpoint._")
            for index, item in enumerate(evidence, start=1):
                st.markdown(f"#### Evidence {index}")
                st.markdown(_evidence_lines(item) if isinstance(item, dict) else str(item))
        with st.expander("Validation result", expanded=True):
            validation = state.get("validation_result") or {}
            st.json(validation)
            warnings = state.get("warnings") or []
            if warnings:
                st.markdown("**Warnings**")
                st.json(warnings)

    if resume:
        target = (run_id or st.session_state.get("hitl_run_id") or "").strip()
        if not target:
            st.warning("Enter a run ID to resume.")
            return
        try:
            payload = resume_run(target)
        except httpx.HTTPError as exc:
            st.error(f"Resume failed: {exc}")
            return
        st.success(
            f"Graph `{payload.get('run_id', target)}` resumed. "
            "Return to **New Research** and start a new query, or look up this run ID "
            "after synthesis completes."
        )
        st.info("Switch to the New Research tab to watch or load the finished report.")
