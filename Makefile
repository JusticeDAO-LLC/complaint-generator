.PHONY: canary-validate canary-smoke canary-sample regression regression-lean regression-review regression-full hacc-grounding hacc-grounding-no-smoke hacc-grounded-history hacc-unit

HACC_GROUNDED_RUN_DIR ?= output/hacc_grounded/latest

regression: regression-full

regression-lean:
	.venv/bin/python scripts/run_standard_regression.py --slice lean

regression-review:
	.venv/bin/python scripts/run_standard_regression.py --slice review

regression-full:
	.venv/bin/python scripts/run_standard_regression.py --slice full

hacc-grounding:
	.venv/bin/python scripts/run_hacc_grounding_regression.py

hacc-grounding-no-smoke:
	.venv/bin/python scripts/run_hacc_grounding_regression.py --skip-smoke

hacc-grounded-history:
	.venv/bin/python scripts/show_hacc_grounded_history.py --output-dir "$(HACC_GROUNDED_RUN_DIR)"

hacc-unit:
	.venv/bin/python scripts/run_hacc_unit_regression.py

canary-validate:
	.venv/bin/python scripts/validate_canary_ops.py
	.venv/bin/pytest tests/test_canary_ops_validation.py -q

canary-smoke: canary-validate
	.venv/bin/pytest tests/test_graph_phase2_integration.py -q --run-network --run-llm

canary-sample:
	ts=$$(date +%Y%m%d_%H%M%S); \
	metrics=statefiles/reranker_metrics_sample_$${ts}.json; \
	summary=statefiles/reranker_metrics_sample_$${ts}.summary.json; \
	METRICS_PATH="$$metrics" .venv/bin/python -c "import os; from mediator import Mediator; from unittest.mock import Mock; m=Mock(); m.id='sample-backend'; med=Mediator(backends=[m]); med.update_reranker_metrics(source='legal_authority', applied=True, metadata={'graph_run_avg_boost':0.05,'graph_run_elapsed_ms':2.0,'graph_latency_guard_applied':False}, canary_enabled=True); med.update_reranker_metrics(source='web_evidence', applied=False, metadata={}, canary_enabled=False); print(med.export_reranker_metrics_json(os.environ['METRICS_PATH']))"; \
	.venv/bin/python scripts/summarize_reranker_metrics.py --input "$$metrics" --summary-out "$$summary"; \
	echo "Sample metrics: $$metrics"; \
	echo "Sample summary: $$summary"
