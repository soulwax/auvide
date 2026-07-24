"""Versioned NDJSON progress protocol for GUI and automation clients."""
from __future__ import annotations

import json
import sys
import uuid
from typing import Any, TextIO

PROTOCOL = "auvide.progress"
VERSION = 1

EVENT_FIELDS = {
    "plan": {"input", "output", "total_frames", "total_chunks", "stages"},
    "stage_started": {"stage", "ordinal", "stage_count"},
    "progress": {"stage", "current", "total", "unit"},
    "stage_completed": {"stage"},
    "warning": {"code", "message"},
    "completed": {"output"},
    "cancelled": {"resumable", "work_dir"},
    "failed": {"code", "message"},
}

COMMON_FIELDS = {"protocol", "version", "run_id", "type"}


class Reporter:
    """Keep human logs and machine progress on separate streams.

    In progress mode stdout is reserved for one JSON object per line. Human
    diagnostics move to stderr so a consumer can parse stdout without regexes.
    In normal CLI mode events are suppressed and log output stays on stdout.
    """

    def __init__(self, progress_json: bool = False, run_id: str | None = None,
                 stdout: TextIO | None = None, stderr: TextIO | None = None) -> None:
        self.progress_json = progress_json
        self.run_id = run_id or uuid.uuid4().hex
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr

    def log(self, message: str = "", *, error: bool = False, flush: bool = False) -> None:
        """Write a human-readable line without contaminating NDJSON stdout."""
        stream = self.stderr if self.progress_json or error else self.stdout
        print(message, file=stream, flush=flush)

    def event(self, event_type: str, **payload: Any) -> None:
        """Emit one validated NDJSON event when the protocol is enabled."""
        if event_type not in EVENT_FIELDS:
            raise ValueError(f"unknown progress event type: {event_type}")
        overlap = COMMON_FIELDS.intersection(payload)
        if overlap:
            raise ValueError(
                f"progress payload must not replace common field(s): {sorted(overlap)}")
        missing = EVENT_FIELDS[event_type] - payload.keys()
        if missing:
            raise ValueError(f"{event_type} event missing field(s): {sorted(missing)}")
        if not self.progress_json:
            return

        event = {
            "protocol": PROTOCOL,
            "version": VERSION,
            "run_id": self.run_id,
            "type": event_type,
            **payload,
        }
        print(
            json.dumps(event, separators=(",", ":"), sort_keys=True),
            file=self.stdout,
            flush=True,
        )
