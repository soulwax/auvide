"""Tests for the versioned engine progress reporter."""
from __future__ import annotations

import io
import json

import pytest

from auvide.progress import PROTOCOL, VERSION, Reporter


def test_json_event_is_one_parseable_ndjson_line():
    stdout, stderr = io.StringIO(), io.StringIO()
    reporter = Reporter(True, run_id="render-42", stdout=stdout, stderr=stderr)

    reporter.event(
        "plan", input="in.mp4", output="out.mp4", total_frames=24,
        total_chunks=1, stages=["extract", "upscale", "encode", "concat_mux"],
    )

    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event == {
        "input": "in.mp4",
        "output": "out.mp4",
        "protocol": PROTOCOL,
        "run_id": "render-42",
        "stages": ["extract", "upscale", "encode", "concat_mux"],
        "total_chunks": 1,
        "total_frames": 24,
        "type": "plan",
        "version": VERSION,
    }
    assert stderr.getvalue() == ""


def test_json_mode_sends_human_logs_to_stderr():
    stdout, stderr = io.StringIO(), io.StringIO()
    reporter = Reporter(True, run_id="render-42", stdout=stdout, stderr=stderr)

    reporter.log("[1/3] extracting", flush=True)

    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "[1/3] extracting\n"


def test_normal_mode_keeps_human_logs_and_suppresses_events():
    stdout, stderr = io.StringIO(), io.StringIO()
    reporter = Reporter(False, run_id="render-42", stdout=stdout, stderr=stderr)

    reporter.log("ready")
    reporter.event("completed", output="out.mp4")

    assert stdout.getvalue() == "ready\n"
    assert stderr.getvalue() == ""


@pytest.mark.parametrize(
    ("event_type", "payload", "message"),
    [
        ("unknown", {}, "unknown progress event type"),
        ("completed", {}, "missing field"),
        ("completed", {"output": "out.mp4", "run_id": "override"}, "must not replace"),
    ],
)
def test_event_contract_rejects_invalid_payloads(event_type, payload, message):
    reporter = Reporter(True, run_id="render-42", stdout=io.StringIO(), stderr=io.StringIO())

    with pytest.raises(ValueError, match=message):
        reporter.event(event_type, **payload)
