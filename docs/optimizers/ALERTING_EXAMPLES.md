# Alerting Examples for Optimizer Regressions

This guide provides baseline alert rules for quality and reliability regressions.

## Objectives

Detect these failure modes early:
- sustained score degradation,
- validation/error spikes,
- stage latency regressions,
- sudden throughput drops.

## Prometheus Rule Examples

```yaml
groups:
- name: optimizer-regression-alerts
  interval: 30s
  rules:
  - alert: OptimizerValidationErrorsHigh
    expr: sum(rate(optimizer_errors_total{error_type="validation_failed"}[5m])) > 0.05
    for: 10m
    labels:
      severity: warning
      service: optimizers
    annotations:
      summary: "Validation errors are elevated"
      description: "Validation failure rate exceeded 0.05/s for 10m."

  - alert: OptimizerScoreDeltaNegative
    expr: avg_over_time(optimizer_score_delta[30m]) < -0.03
    for: 20m
    labels:
      severity: warning
      service: optimizers
    annotations:
      summary: "Quality drift detected"
      description: "Average score delta over 30m is below -0.03."

  - alert: OptimizerStageLatencyP95High
    expr: histogram_quantile(0.95, sum(rate(optimizer_stage_duration_seconds_bucket[10m])) by (le, stage)) > 2.5
    for: 15m
    labels:
      severity: warning
      service: optimizers
    annotations:
      summary: "Stage latency P95 regression"
      description: "One or more stages exceed 2.5s p95 for 15m."

  - alert: OptimizerThroughputDrop
    expr: sum(rate(optimizer_rounds_completed_total[10m])) < 0.1
    for: 20m
    labels:
      severity: warning
      service: optimizers
    annotations:
      summary: "Optimizer throughput dropped"
      description: "Round completion throughput is below expected baseline."
```

## Recommended Severity Levels

- `warning`: quality drift, moderate latency increase, low-level error increase.
- `critical`: hard outage, sustained high error rate, zero throughput.

## Tuning Guidance

- Start with conservative thresholds for 1 week.
- Tune by domain: legal/medical often have different baseline latencies.
- Keep score-drift thresholds relative to recent baseline, not static forever.

## Alert Response Checklist

1. Check score delta + validation errors together.
2. Inspect stage-level latency panels.
3. Correlate with deploy/config changes.
4. Roll back config if regression started after rollout.
5. Capture failing examples for regression tests.
