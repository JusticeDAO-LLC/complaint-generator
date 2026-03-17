# Troubleshooting Dashboards (Performance and Quality Drift)

This guide provides practical dashboard panels to diagnose optimizer regressions.

## Scope

Covers GraphRAG, logic, and base optimizer signals emitted by:
- Prometheus metrics (`optimizer_*`)
- Structured run logs (`ontology_pipeline_run`, `logic_optimizer_analyze_batch`)

## Dashboard 1: Run Health Overview

Purpose: detect immediate failures, latency spikes, and score collapse.

Panels:
- `Run Duration P95 (5m)`
  - PromQL: `histogram_quantile(0.95, sum(rate(optimizer_stage_duration_seconds_bucket[5m])) by (le, stage))`
- `Validation Failure Rate (5m)`
  - PromQL: `sum(rate(optimizer_errors_total{error_type="validation_failed"}[5m]))`
- `Current Round Throughput`
  - PromQL: `sum(rate(optimizer_rounds_completed_total[5m]))`
- `Latest Score by Domain`
  - PromQL: `max by (domain) (optimizer_score)`

## Dashboard 2: Quality Drift

Purpose: identify slow quality degradation before hard failures.

Panels:
- `Score Delta Trend (30m)`
  - PromQL: `avg_over_time(optimizer_score_delta[30m])`
- `Negative Delta Ratio`
  - PromQL: `sum(rate(optimizer_score_delta[15m] < 0))`
  - Note: if your Prometheus does not support this style, derive from logs.
- `Domain Comparison`
  - PromQL: `avg by (domain) (optimizer_score)`

Alert suggestion:
- Trigger warning when `avg_over_time(optimizer_score_delta[30m]) < -0.03` for 20 minutes.

## Dashboard 3: Pipeline Stage Bottlenecks

Purpose: locate where latency moved after code/config changes.

Panels:
- `Stage Duration Heatmap`
  - PromQL: `sum(rate(optimizer_stage_duration_seconds_bucket[10m])) by (stage, le)`
- `Stage Mean Duration`
  - PromQL: `sum(rate(optimizer_stage_duration_seconds_sum[10m])) by (stage) / sum(rate(optimizer_stage_duration_seconds_count[10m])) by (stage)`
- `Stage Outlier Detector`
  - Compare current 15m mean vs previous 24h baseline.

## Log-Based Panels (Loki/ELK)

Use structured log fields from `PIPELINE_RUN`/`PIPELINE_BATCH`:
- `domain`
- `score`
- `duration_ms`
- `stage_durations_ms`
- `actions_count`

Suggested queries:
- Top slow runs by `duration_ms`
- Lowest score runs by `domain`
- Correlation between `actions_count` and quality score

## Query Metrics Persistence Error Codes

When query metrics persistence falls back or fails, monitor these structured codes:
- `QMETRICS_SERIALIZATION_ERROR`: primary metrics payload could not be serialized; fallback file payload was written.
- `QMETRICS_FALLBACK_WRITE_ERROR`: both primary and fallback metric writes failed; only logger output is available.

Operational guidance:
1. If `QMETRICS_SERIALIZATION_ERROR` appears repeatedly, inspect recent schema/type changes in emitted metrics payloads.
2. If `QMETRICS_FALLBACK_WRITE_ERROR` appears, prioritize filesystem/permissions/disk-health checks for the metrics directory.

Example log filters:
- Loki: `{app="optimizers"} |= "QMETRICS_SERIALIZATION_ERROR"`
- Loki: `{app="optimizers"} |= "QMETRICS_FALLBACK_WRITE_ERROR"`
- ELK/KQL: `message : "QMETRICS_SERIALIZATION_ERROR" OR message : "QMETRICS_FALLBACK_WRITE_ERROR"`

Prometheus alert rule snippets (when mirrored into a counter metric):
```yaml
- alert: QueryMetricsFallbackWriteErrorBurst
  expr: sum(rate(optimizer_errors_total{error_code="QMETRICS_FALLBACK_WRITE_ERROR"}[5m])) > 0
  for: 10m
  labels:
    severity: critical
  annotations:
    summary: "Query metrics fallback writes are failing"
    description: "Fallback metrics writes have been failing for at least 10m."

- alert: QueryMetricsSerializationErrorSustained
  expr: sum(rate(optimizer_errors_total{error_code="QMETRICS_SERIALIZATION_ERROR"}[15m])) > 0.05
  for: 20m
  labels:
    severity: warning
  annotations:
    summary: "Sustained query metrics serialization failures"
    description: "Investigate metrics payload schema/type drift."
```

## Triage Playbook

When alerts fire:
1. Confirm whether regression is global or domain-specific.
2. Check stage-level latency to isolate extraction/evaluation/refinement bottleneck.
3. Inspect score delta and validation failures together (quality + correctness).
4. Correlate with recent deploy/config changes.
5. Roll back risky config first; then profile specific slow stage.

## Minimum Operational Set

If starting from scratch, build these first:
1. Run Duration P95
2. Validation Failure Rate
3. Latest Score by Domain
4. Score Delta Trend
