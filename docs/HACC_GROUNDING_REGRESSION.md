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

Related comparison task:

```text
HACC Preset Matrix Compare
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

Deeper preset comparison example:

```bash
./.venv/bin/python scripts/run_hacc_preset_matrix.py --presets core_hacc_policies,accommodation_focus,administrative_plan_retaliation --num-sessions 2 --hacc-count 2 --max-turns 4 --max-parallel 1 --output-dir ../research_results/adversarial_runs/hacc_preset_matrix_compare --continue-on-error
```

The script fails if the live smoke does not produce:

- `anchor_sections == ["grievance_hearing", "appeal_rights"]`
- `coverage_rate == 1.0` for both `grievance_hearing` and `appeal_rights`