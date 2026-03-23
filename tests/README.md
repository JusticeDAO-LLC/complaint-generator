# Testing Guide for Complaint Generator

This directory contains tests for the complaint-generator application following Test-Driven Development (TDD) principles.

## Test Structure

This overview is illustrative rather than exhaustive; prefer `pytest --collect-only` or targeted file discovery when you need the exact current suite shape.

```
tests/ (representative snapshot)
├── Complaint Processing Tests
│   ├── test_complaint_phases.py           # Three-phase system (7 classes, 27 tests)
│   ├── test_mediator_three_phase.py       # Three-phase integration (1 class, 6 tests)
│   └── test_enhanced_denoising.py         # Advanced denoising (4 classes)
├── Complaint Analysis Tests
│   ├── test_complaint_analysis.py         # Core analysis (5 classes)
│   ├── test_complaint_analysis_integration.py # Integration features (5 classes)
│   ├── test_complaint_taxonomies.py       # All 14 complaint types (10 classes)
│   ├── test_dei_analysis.py               # DEI analysis (5 classes, 19 tests)
│   └── test_hacc_integration.py           # DEI/HACC features (5 classes)
├── Adversarial Testing Tests
│   ├── test_adversarial_harness.py        # Adversarial framework (6 classes, 18 tests)
│   ├── test_sgd_cycle_integration.py      # SGD cycle integration
│   └── test_sweep_ranker.py               # Sweep ranking tests
├── Mediator & Hooks Tests
│   ├── test_mediator.py                   # Core orchestration (2 classes, 4 tests)
│   ├── test_legal_hooks.py                # Legal analysis pipeline (5 classes, 12 tests)
│   ├── test_legal_authority_hooks.py      # Legal research (4 classes, 11 tests)
│   ├── test_web_evidence_hooks.py         # Web evidence (3 classes, 12 tests)
│   ├── test_evidence_hooks.py             # Evidence management (4 classes, 12 tests)
│   └── test_search_hooks.py               # Search integration (5 classes)
├── Core Tests
│   ├── test_state.py                      # State management (1 class, 2 tests)
│   ├── test_llm_router_backend.py         # LLM routing (1 class, 7 tests)
│   ├── test_integration.py                # End-to-end (1 class, 2 tests)
│   └── test_log.py                        # Logging (6 tests)
└── __init__.py                            # Test package initialization
```

## Running Tests

### Install Test Dependencies

First, install the required testing packages:

```bash
pip install -r requirements.txt
```

### Run All Tests

```bash
pytest
```

### Run Specific Test Files

```bash
pytest tests/test_log.py
pytest tests/test_mediator.py
```

For the claim-support review workflow, the focused regression slice is:

```bash
.venv/bin/pytest -q \
  tests/test_complaint_generator_package.py \
    tests/test_claim_support_hooks.py \
    tests/test_review_api.py \
    tests/test_claim_support_review_dashboard_flow.py \
    tests/test_backfill_claim_testimony_links_cli.py \
  tests/test_claim_support_review_template.py \
  tests/test_claim_support_review_playwright_smoke.py \
  tests/test_complaint_generator_site_playwright.py
```

The equivalent repo-local helper auto-detects whether the browser smoke should be included:

```bash
.venv/bin/python scripts/run_claim_support_review_regression.py
```

In VS Code, the same runner is available from the workspace task list as `Claim Support Regression`, with explicit `No Browser` and `Require Browser` variants.

The Run and Debug panel exposes the same three variants through matching launch configurations.

GitHub Actions also runs this slice through `.github/workflows/claim-support-regression.yml`, splitting the enforcement into non-browser and browser-required lanes.

### Run Tests with Coverage

```bash
pytest --cov=. --cov-report=html
```

This will generate an HTML coverage report in the `htmlcov/` directory.

### Run Tests by Marker

Tests use markers to categorize different types of tests. Currently, most tests that require external dependencies or backend integrations are marked with `@pytest.mark.integration`.

Run only integration tests:
```bash
pytest -m integration
```

Run tests excluding integration tests (faster, unit-only tests):
```bash
pytest -m "not integration"
```

### Optional Browser Smoke

The claim-support dashboard includes an optional real-browser smoke test that validates the legacy testimony-link repair path end to end in Chromium.

```bash
.venv/bin/pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/pytest -q tests/test_claim_support_review_playwright_smoke.py
```

That smoke test starts a local FastAPI review surface, seeds one saved testimony row plus one proactively repaired legacy row in a temporary DuckDB, loads `/claim-support-review`, and verifies the rendered UI shows both testimony records under `Protected activity`.

If Playwright is not installed, the test skips cleanly at runtime.

Use `.venv/bin/python scripts/run_claim_support_review_regression.py --browser off` when you want the same focused slice without the browser-backed smoke, or `--browser on` when you want the command to require it.

### Verbose Output

For more detailed output:
```bash
pytest -v
```

## Test Organization

### Test Markers

Tests are organized using pytest markers (defined in `pytest.ini`):

- `@pytest.mark.integration` - Integration tests that require backends or external dependencies
- `@pytest.mark.slow` - Tests that take longer to run

Most tests use mocks to avoid external dependencies, but integration tests may require actual backend initialization or optional dependencies to be installed.

### Optional Test Dependencies

Some review, browser, and persistence suites rely on optional packages such as `duckdb`, `fastapi`, `uvicorn`, `requests`, `bs4`, or `playwright`.

- If a test module cannot provide useful coverage without one of those packages, prefer `pytest.importorskip(...)` at module import time instead of a hard import that fails collection.
- Use this pattern for environment-specific suites like browser smokes, dashboard flows, and DuckDB-backed persistence checks.
- Keep core backend and unit suites runnable without those optional packages whenever practical.
- When adding a new optional dependency, document the install command near the relevant suite in this file.

This keeps `pytest` behavior predictable in lean environments:

- core suites still run and fail normally when behavior regresses
- optional suites report as skipped rather than aborting collection
- CI lanes that install the full stack still exercise the richer coverage

#### Optional Dependency Matrix

| Suite / File | Purpose | Optional dependencies | Lean environment behavior |
| --- | --- | --- | --- |
| `tests/test_review_api.py` | Review API payload and route coverage | `duckdb`, `fastapi` | Skip if DuckDB is unavailable |
| `tests/test_claim_support_review_dashboard_flow.py` | Review dashboard HTML flow checks | `bs4`, `fastapi` | Skip if dashboard parsing or web stack is unavailable |
| `tests/test_claim_support_review_playwright_smoke.py` | Real-browser review smoke | `duckdb`, `fastapi`, `uvicorn`, `requests`, `playwright` | Skip if browser or web stack is unavailable |
| `tests/test_claim_support_hooks.py` | DuckDB-backed claim support persistence | `duckdb` | Skip if DuckDB is unavailable |
| `tests/test_backfill_claim_testimony_links_cli.py` | DuckDB-backed CLI backfill behavior | `duckdb` | Skip if DuckDB is unavailable |
| `tests/test_cli_commands.py` | CLI formatting and command routing | none beyond core test stack | Should run by default |
| `tests/test_intake_status.py` | Intake/review summary shaping | none beyond core test stack | Should run by default |
| `tests/test_mediator_three_phase.py` | Intake/evidence integration flow | none beyond core test stack | Should run by default |
| `tests/test_complaint_phases.py` | Phase manager and denoiser behavior | none beyond core test stack | Should run by default |
| `tests/test_mediator.py` | Core mediator behavior | none beyond core test stack | Should run by default |

Use this as a rule of thumb:

- If a suite verifies core logic, keep it runnable in a lean environment.
- If a suite verifies a browser, dashboard, or DuckDB-backed persistence path, make the dependency explicit and skip cleanly when it is absent.

#### Recommended Local Commands

Use these as the default entry points when choosing a regression slice:

```bash
# Lean regression: core backend, phase flow, CLI, and intake status
pytest -q \
    tests/test_cli_commands.py \
    tests/test_intake_status.py \
    tests/test_mediator_three_phase.py \
    tests/test_complaint_phases.py \
    tests/test_mediator.py

# Review regression without browser: review and persistence suites that may skip
pytest -q \
    tests/test_review_api.py \
    tests/test_claim_support_review_dashboard_flow.py \
    tests/test_claim_support_hooks.py \
  tests/test_backfill_claim_testimony_links_cli.py \
  tests/test_claim_support_review_template.py \
  tests/test_document_pipeline.py \
  tests/test_formal_document_pipeline.py

# Full review/browser regression: requires the optional browser/web stack
pytest -q \
    tests/test_complaint_generator_package.py \
    tests/test_complaint_generator_package_surface.py \
    tests/test_review_api.py \
    tests/test_claim_support_review_dashboard_flow.py \
    tests/test_claim_support_hooks.py \
    tests/test_backfill_claim_testimony_links_cli.py \
    tests/test_claim_support_review_template.py \
    tests/test_document_pipeline.py \
    tests/test_formal_document_pipeline.py \
    tests/test_claim_support_review_playwright_smoke.py \
    tests/test_complaint_generator_site_playwright.py
```

The repo-local helper exposes the same slices without copy-pasting long commands:

```bash
python scripts/run_standard_regression.py
python scripts/run_standard_regression.py --slice review
python scripts/run_standard_regression.py --slice full
```

The same slices are also available through editor and shell tooling:

- VS Code tasks:
  - `Standard Regression (Lean)`
  - `Standard Regression (Review)`
  - `Standard Regression (Full)`
- Run and Debug:
  - `Standard Regression (Lean)`
  - `Standard Regression (Review)`
  - `Standard Regression (Full)`
- Make targets:
  - `make regression`
  - `make regression-lean`
  - `make regression-review`
  - `make regression-full`
- GitHub Actions workflow:
  - `.github/workflows/standard-regression.yml`

The default helper invocation now resolves to the `full` slice so browser smoke and document workflow coverage stay in the standard gate.

For the HACC grounding workflow, use the focused helper:

```bash
python scripts/run_hacc_grounding_regression.py --list
python scripts/run_hacc_grounding_regression.py --skip-smoke
make hacc-adversarial-runner HACC_REPO_DIR=../HACC
```

For an existing grounded run directory, you can inspect the current workflow state without rerunning the full pipeline:

```bash
python scripts/show_hacc_grounded_history.py
python scripts/show_hacc_grounded_history.py --list-runs
python scripts/show_hacc_grounded_history.py --json
python scripts/show_hacc_grounded_history.py --output-dir output/hacc_grounded/<run_id>
python scripts/show_hacc_grounded_history.py --output-dir previous
python scripts/show_hacc_grounded_history.py --output-dir last-successful
```

That read-only inspection summarizes:

- `grounded_workflow_status.json`
- `grounded_workflow_history.json`
- `completed_grounded_intake_follow_up_worksheet.json`
- `refreshed_grounding_state.json`
- `grounded_follow_up_answer_summary.json`

Use it when you want to list the available grounded runs, current alias targets, the best candidate to resume, and ready-to-run inspection and operational commands first, then confirm whether a grounded worksheet has already been completed, whether refreshed grounding exists yet, and what the last few workflow transitions were. The helper accepts `latest`, `previous`, and `last-successful` aliases in addition to an explicit run directory, and its recommended operational command suggests a grounded pipeline rerun for pre-follow-up runs before switching to synthesis once a worksheet-backed resume is ready. When the run summary is present, that rerun command preserves the original query, claim type, preset, and search-mode flags, and when a persisted grounded worksheet exists the helper can also emit a rerun-plus-synthesis command with `--synthesize-complaint` and `--completed-grounded-intake-worksheet`.

Example output:

```text
Output directory: output/hacc_grounded/20260322_120000
Workflow stage: post_grounded_follow_up
Recorded transitions: 2
Next action: continue_drafting (document_generation)
Completed grounded worksheet items: 3
Refreshed grounding status: chronology_supported
Grounded follow-up answers: 3
```

That helper now covers both:

- the HACC seed-generation regression
- the HACC evidence loader regression in `tests/test_hacc_evidence_loader.py`

The same HACC slice is also available through editor and shell tooling:

- VS Code task:
  - `HACC Grounding Regression`
  - `HACC Grounded History`
  - `HACC Adversarial Runner Tests`
- Run and Debug:
  - `HACC Grounding Regression`
  - `HACC Grounding Regression (No Smoke)`
  - `HACC Grounded History`
  - `HACC Adversarial Runner Tests`
- Make targets:
  - `make hacc-grounding`
  - `make hacc-grounding-no-smoke`
  - `make hacc-grounded-history HACC_GROUNDED_RUN_DIR=output/hacc_grounded/<run_id>`
  - `make hacc-adversarial-runner HACC_REPO_DIR=../HACC`
- GitHub Actions:
  - `.github/workflows/hacc-grounding-regression.yml` as a manual workflow, defaulting to `--skip-smoke`

Use the sibling-repo adversarial runner test when you want to validate the HACC-side CLI surface itself: parser defaults, JSON mode, stdout summaries, and workflow-phase autopatch flag handling in `../HACC/tests/test_hacc_adversarial_runner.py`.

For a faster HACC-only unit slice, use:

```bash
python scripts/run_hacc_unit_regression.py
```

That lightweight slice covers:

- `tests/test_hacc_evidence_loader.py`
- `tests/test_synthesize_hacc_complaint.py`
- `tests/test_run_hacc_adversarial_report.py`

The same unit slice is also available through:

- VS Code task:
  - `HACC Unit Regression`
- Run and Debug:
  - `HACC Unit Regression`
- Make target:
  - `make hacc-unit`
- GitHub Actions:
  - `.github/workflows/hacc-unit-regression.yml`

### Test Naming Convention

- Test files: `test_*.py` or `*_test.py`
- Test classes: `Test*`
- Test functions: `test_*`

## Writing New Tests

### Basic Test Structure

```python
import pytest
from module_to_test import function_to_test

class TestFeature:
    """Test cases for a specific feature"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.test_data = "example"
    
    def test_specific_behavior(self):
        """Test a specific behavior"""
        result = function_to_test(self.test_data)
        assert result == expected_value
```

### Using Mocks

For testing code that depends on external services or complex dependencies:

```python
from unittest.mock import Mock, patch

def test_with_mock():
    mock_backend = Mock()
    mock_backend.return_value = "mocked response"
    
    result = function_using_backend(mock_backend)
    
    mock_backend.assert_called_once()
    assert result == "expected result"
```

## Test-Driven Development (TDD) Workflow

1. **Write a failing test** - Write a test for the new feature/behavior
2. **Run the test** - Verify it fails (Red)
3. **Write minimal code** - Write just enough code to pass the test
4. **Run the test** - Verify it passes (Green)
5. **Refactor** - Clean up the code while keeping tests passing
6. **Repeat** - Continue the cycle for the next feature

## Continuous Integration

Tests should be run automatically in CI/CD pipelines before merging changes.

## Coverage Goals

- Aim for at least 80% code coverage
- Critical paths should have 100% coverage
- Focus on testing behavior, not implementation details

## Best Practices

1. **Keep tests independent** - Tests should not depend on each other
2. **Use descriptive names** - Test names should describe what they test
3. **One assertion per test** - When possible, test one thing at a time
4. **Use fixtures** - Share common setup code using pytest fixtures
5. **Mock external dependencies** - Don't rely on external services in tests
6. **Test edge cases** - Include tests for boundary conditions and error cases

## Troubleshooting

### Import Errors

If you encounter import errors, ensure you're running tests from the project root:

```bash
cd /path/to/complaint-generator
pytest tests/
```

### Slow Tests

Mark slow tests and exclude them during rapid development:

```bash
pytest -m "not slow"
```

## Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Test-Driven Development Guide](https://testdriven.io/)
- [Python Testing Best Practices](https://docs.python-guide.org/writing/tests/)
