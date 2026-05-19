# Observability (logs first, dashboards later)

This repo emits **optional JSON logs** on stderr for pipeline and extract steps. That gives you a durable stream to train parsers, correlate runs, and later wire **Prometheus** (metrics), **Grafana** (dashboards), and **Loki** or **Promtail** (log ingestion) without changing call sites first.

## Enable JSON logs

Set in `.env` (loaded by the CLI) or the shell:

```bash
export CANVAS_ARCHIVE_LOG_JSON=1
```

Each line is one JSON object. Fields vary by `event`; common keys include `ts`, `component`, `event`, `canvas_id`, `latency_ms`, `canvas_file_bytes_total`, `canvas_file_errors`, `assignments_written`, `extract_duration_ms`.

## Vocabulary cheat sheet

You mentioned **latency**, **size**, and **errors**. Here is the fuller set teams usually mean when they say “observability keywords”:

| Area | Keywords |
| :-- | :-- |
| **Four golden signals** (SRE) | latency, traffic, errors, saturation |
| **RED** (request-oriented) | rate, errors, duration |
| **USE** (resources) | utilization, saturation, errors |
| **Three pillars** | metrics, logs, traces |

Today’s implementation is **logs-first** with numeric fields that double as light **metrics** (counts, bytes, durations). **Traces** are not emitted yet; add OpenTelemetry later if you need span IDs across subprocesses.

## Prometheus and Grafana (after the pipeline is stable)

1. Keep `CANVAS_ARCHIVE_LOG_JSON=1` and tee stderr to a file, or run under systemd / launchd with `StandardError=append:/path/run.log`.
2. Ship JSON lines with **Promtail** or **Vector** into **Loki**, then build **Grafana** panels on `canvas_file_errors`, `extract_duration_ms`, `canvas_file_bytes_total`, and `assignments_written`.
3. For **Prometheus** counters and histograms, either add a small `/metrics` exporter later or use the **textfile collector** pattern from batch jobs (write `.prom` snippets at end of run).

Dashboards are intentionally **out of scope** until you are happy with the extract; the log schema is the contract.

## Related code

| Path | Role |
| :-- | :-- |
| [src/canvas_archive/observability.py](../src/canvas_archive/observability.py) | `log_event`, `StepTimer`, `log_json_enabled` |
| [src/canvas_archive/extractors/canvas_only.py](../src/canvas_archive/extractors/canvas_only.py) | `extract_complete` event, per-run extract timing |
| [src/canvas_archive/pipeline.py](../src/canvas_archive/pipeline.py) | `run_start`, `run_complete`, `run_failed` |
