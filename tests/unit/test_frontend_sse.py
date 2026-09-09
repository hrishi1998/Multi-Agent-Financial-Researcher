import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
sys.path.insert(0, str(FRONTEND))

from client import parse_sse_frame  # noqa: E402


def test_parse_sse_frame_reads_agent_event_json():
    frame = (
        "event: planner.completed\n"
        'data: {"event_type":"planner.completed","message":"Planner done.",'
        '"agent":"planner","status":"COMPLETED","run_id":"abc","payload":{"node":"planner"},'
        '"sequence_number":2}'
    )
    event = parse_sse_frame(frame)
    assert event is not None
    assert event.event_type == "planner.completed"
    assert event.agent == "planner"
    assert event.run_id == "abc"
    assert event.payload["node"] == "planner"


def test_parse_sse_frame_accepts_crlf_separators():
    frame = (
        "event: run.completed\r\n"
        'data: {"event_type":"run.completed","message":"done","agent":"run_manager",'
        '"status":"COMPLETED","run_id":"xyz","payload":{},"sequence_number":9}\r\n'
    )
    event = parse_sse_frame(frame)
    assert event is not None
    assert event.event_type == "run.completed"
    assert event.run_id == "xyz"
