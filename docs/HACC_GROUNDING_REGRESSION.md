# HACC Grounding Regression

Run the focused regression slice that covers:

- HACC seed-generation tests
- complaint-generator heavy-gated adversarial harness tests
- one live `core_hacc_policies` demo smoke with artifact validation

Command:

```bash
./.venv/bin/python scripts/run_hacc_grounding_regression.py
```

VS Code task:

```text
HACC Grounding Regression
```

Related smoke-matrix task:

```text
HACC Preset Matrix Smoke
```

Guarded smoke-matrix task:

```text
HACC Preset Matrix Smoke (Fail Fast)
```

Related comparison task:

```text
HACC Preset Matrix Compare
```

Guarded comparison task:

```text
HACC Preset Matrix Compare (Fail Fast)
```

Useful options:

```bash
./.venv/bin/python scripts/run_hacc_grounding_regression.py --list
./.venv/bin/python scripts/run_hacc_grounding_regression.py --skip-smoke
./.venv/bin/python scripts/run_hacc_grounding_regression.py --smoke-output-dir ../research_results/adversarial_runs/core_hacc_policies_regression_manual
```

Small preset matrix example:

```bash
./.venv/bin/python scripts/run_hacc_preset_matrix.py --presets core_hacc_policies,accommodation_focus --num-sessions 1 --hacc-count 1 --max-turns 2 --max-parallel 1 --output-dir ../research_results/adversarial_runs/hacc_preset_matrix_smoke --continue-on-error
```

Fail-fast matrix example:

```bash
./.venv/bin/python scripts/run_hacc_preset_matrix.py --presets core_hacc_policies,accommodation_focus --num-sessions 1 --hacc-count 1 --max-turns 2 --max-parallel 1 --output-dir ../research_results/adversarial_runs/hacc_preset_matrix_smoke_failfast --fail-on-degraded-runtime
```

In the current environment this guarded variant is expected to fail, because `llm-router` probes as available but falls back during live sessions and is now reported as degraded runtime.

Normal matrix runs preserve degraded runtime in the summary artifacts as `router_status: degraded` plus a `runtime_note` field when the selected backend probes cleanly but the live session falls back during execution.

Deeper preset comparison example:

```bash
./.venv/bin/python scripts/run_hacc_preset_matrix.py --presets core_hacc_policies,accommodation_focus,administrative_plan_retaliation --num-sessions 2 --hacc-count 2 --max-turns 4 --max-parallel 1 --output-dir ../research_results/adversarial_runs/hacc_preset_matrix_compare --continue-on-error
```

Guarded comparison example:

```bash
./.venv/bin/python scripts/run_hacc_preset_matrix.py --presets core_hacc_policies,accommodation_focus,administrative_plan_retaliation --num-sessions 2 --hacc-count 2 --max-turns 4 --max-parallel 1 --output-dir ../research_results/adversarial_runs/hacc_preset_matrix_compare_failfast --fail-on-degraded-runtime
```

If a stronger backend is available and properly provisioned, you can pin it explicitly with `--backend-id`. In the current environment, `llm-router-codex` is present but may be quota-limited, so the shared tasks intentionally leave backend selection automatic.

The script fails if the live smoke does not produce:

- `anchor_sections == ["grievance_hearing", "appeal_rights"]`
- `coverage_rate == 1.0` for both `grievance_hearing` and `appeal_rights`