# HACC Grounding Regression

Run the focused regression slice that covers:

- HACC seed-generation tests
- complaint-generator heavy-gated adversarial harness tests
- one live `core_hacc_policies` demo smoke with artifact validation

Command:

```bash
./.venv/bin/python scripts/run_hacc_grounding_regression.py
```

Useful options:

```bash
./.venv/bin/python scripts/run_hacc_grounding_regression.py --list
./.venv/bin/python scripts/run_hacc_grounding_regression.py --skip-smoke
./.venv/bin/python scripts/run_hacc_grounding_regression.py --smoke-output-dir ../research_results/adversarial_runs/core_hacc_policies_regression_manual
```

The script fails if the live smoke does not produce:

- `anchor_sections == ["grievance_hearing", "appeal_rights"]`
- `coverage_rate == 1.0` for both `grievance_hearing` and `appeal_rights`