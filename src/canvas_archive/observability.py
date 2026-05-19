"""Structured JSON logs for pipeline and extract steps (Prometheus / Grafana later).

Emit one JSON object per line to stderr when CANVAS_ARCHIVE_LOG_JSON is truthy.
Fields align with common observability vocabulary so you can ship the same stream to
Promtail, Loki, or an OTLP collector later without changing call sites.

Vocabulary (pick what you need for dashboards later):

- **Four golden signals** (Google SRE): latency, traffic, errors, saturation
- **RED** (microservices health): rate, errors, duration
- **USE** (capacity): utilization, saturation, errors
- **Three pillars**: metrics, logs, traces (this module is logs-first; duration_ms is a metric primitive)

This package does not start Prometheus or Grafana. Add those after the pipeline is stable;
point a log collector at stderr or tee JSON lines to a file.

When ``CANVAS_ARCHIVE_LOG_JSON`` is set, ``extract_complete`` events include at least:
``assignments_written``, ``canvas_files_downloaded``, ``external_starters_downloaded``,
``external_spec_follow_downloaded`` (bundles discovered inside downloaded ``.htm`` / ``.html`` starters),
``canvas_file_bytes_total``, ``canvas_file_errors``, ``extract_duration_ms``, plus stage counters
``stage_home_table_canvas_assignments``, ``stage_home_table_external_assignments``,
``stage_assignments_with_canvas_downloads``, and ``stage_assignments_with_external_downloads``.
Pipeline ``run_complete`` repeats the extract counters it knows for dashboards. Those fields are
enough to derive RED-style counters or histograms in Loki or to forward to an OTLP metrics bridge.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any


def log_json_enabled() -> bool:
    v = (os.environ.get("CANVAS_ARCHIVE_LOG_JSON") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def log_event(component: str, event: str, **fields: Any) -> None:
    """Write a single JSON log record to stderr (no secrets)."""
    if not log_json_enabled():
        return
    rec: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "component": component,
        "event": event,
    }
    for k, v in fields.items():
        if v is not None:
            rec[k] = v
    sys.stderr.write(json.dumps(rec, default=str) + "\n")
    sys.stderr.flush()


class StepTimer:
    """Wall-clock timer for latency_ms on a block."""

    __slots__ = ("_t0",)

    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    def latency_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)
