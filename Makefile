.PHONY: canary-validate canary-smoke canary-sample package-install-smoke regression regression-lean regression-review regression-full hacc-grounding hacc-grounding-no-smoke hacc-grounded-history hacc-master-email hacc-master-email-rebuild hacc-unit hacc-adversarial-runner complaint-workspace-cli complaint-mcp-server
.PHONY: test-collect test-smoke test-adapter test-mediator test-document test-ui test-ui-browser test-refactor
.PHONY: validate-w1-adapters validate-w2-acquisition validate-w3-documents validate-w4-graphs validate-w9-legal validate-w10-drafting validate-p0

PYTHON ?= python
PYTEST_ARGS ?= -q --maxfail=1

# Focused architectural test lanes. Keep these lists explicit: marker coverage is
# intentionally incremental, while these commands must remain deterministic for
# refactor agents and CI. See docs/VERIFICATION_SUMMARY.md for ownership rules.
SMOKE_TESTS := \
	tests/test_package_imports.py \
	tests/test_state.py \
	tests/test_main_chat_payload.py \
	tests/test_mike_status_contract.py

ADAPTER_TESTS := \
	tests/test_package_imports.py \
	tests/test_ipfs_adapter_import_boundary.py \
	tests/test_ipfs_adapter_types.py \
	tests/test_ipfs_adapter_layer.py \
	tests/test_ipfs_logic_adapter.py \
	tests/test_ipfs_provenance.py

MEDIATOR_TESTS := \
	tests/test_mediator.py \
	tests/test_mediator_three_phase.py \
	tests/test_mediator_legal_support_context.py \
	tests/test_claim_support_hooks.py \
	tests/test_evidence_hooks.py \
	tests/test_legal_authority_hooks.py \
	tests/test_web_evidence_hooks.py

DOCUMENT_TESTS := \
	tests/test_document_pipeline.py \
	tests/test_document_pipeline_fallbacks.py \
	tests/test_formal_document_pipeline.py \
	tests/test_legal_document_parsing.py \
	tests/test_document_workflow_targeting_summary.py

UI_TESTS := \
	tests/test_application_launcher.py \
	tests/test_review_api.py \
	tests/test_claim_support_review_dashboard_flow.py \
	tests/test_claim_support_review_template.py \
	tests/test_review_surface_config.py \
	tests/test_workspace_template_contract.py

UI_BROWSER_TESTS := \
	tests/test_claim_support_review_playwright_smoke.py \
	tests/test_review_surface_site_playwright.py \
	tests/test_complaint_generator_site_playwright.py \
	tests/test_website_cohesion_playwright.py

HACC_GROUNDED_RUN_DIR ?= output/hacc_grounded/latest
HACC_REPO_DIR ?= ../HACC
HACC_MASTER_EMAIL_QUERY ?= hcv orientation living room

regression: regression-full

# Collection is the repository-wide structural gate used by the refactor
# supervisor. It imports every configured test module without executing tests.
test-collect:
	$(PYTHON) -m pytest --collect-only -q

test-smoke:
	$(PYTHON) -m pytest $(PYTEST_ARGS) $(SMOKE_TESTS)

test-adapter:
	$(PYTHON) -m pytest $(PYTEST_ARGS) $(ADAPTER_TESTS)

test-mediator:
	$(PYTHON) -m pytest $(PYTEST_ARGS) $(MEDIATOR_TESTS)

test-document:
	$(PYTHON) -m pytest $(PYTEST_ARGS) $(DOCUMENT_TESTS)

# Fast UI contracts only. Real browser execution is intentionally separate so
# this lane remains useful in lean worktrees and headless refactor workers.
test-ui:
	$(PYTHON) -m pytest $(PYTEST_ARGS) $(UI_TESTS)

test-ui-browser:
	$(PYTHON) -m pytest $(PYTEST_ARGS) $(UI_BROWSER_TESTS)

test-refactor: test-smoke test-adapter test-mediator test-document test-ui

# Named P0 roadmap validations. These aliases encode each workstream's owned
# architectural seams and make the coverage map executable, not just narrative.
validate-w1-adapters: test-adapter

validate-w2-acquisition: test-adapter test-mediator

validate-w3-documents: test-adapter test-mediator test-document

validate-w4-graphs: test-adapter test-mediator

validate-w9-legal: test-adapter test-mediator

validate-w10-drafting: test-document test-ui

validate-p0: test-adapter test-mediator test-document test-ui

package-install-smoke:
	.venv/bin/python -m pip install -e . --no-deps
	.venv/bin/python scripts/run_package_install_smoke.py --json

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

hacc-master-email:
	PYTHONPATH="$(CURDIR)" .venv/bin/python scripts/master_case_email.py --search-query "$(HACC_MASTER_EMAIL_QUERY)" --search-limit 5

hacc-master-email-rebuild:
	PYTHONPATH="$(CURDIR)" .venv/bin/python scripts/master_case_email.py --rebuild

hacc-unit:
	.venv/bin/python scripts/run_hacc_unit_regression.py

hacc-adversarial-runner:
	python3 -m pytest "$(HACC_REPO_DIR)/tests/test_hacc_adversarial_runner.py" -q

complaint-workspace-cli:
	.venv/bin/python -m complaint_generator.cli --help

complaint-mcp-server:
	.venv/bin/python -m complaint_generator.mcp_server

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
