# Complaint Generator - Modernization Summary

## Changes Made

### 1. Git Submodule Added ✅
- **Repository**: `endomorphosis/ipfs_datasets_py@main`
- **Location**: `./ipfs_datasets_py/`
- **Configuration**: Configured in `.gitmodules`

To initialize the submodule when cloning:
```bash
git submodule init
git submodule update
```

Or clone with submodules:
```bash
git clone --recurse-submodules <repo-url>
```

### 2. Test-Driven Development (TDD) Framework ✅

#### Testing Framework Setup
- **Framework**: pytest 7.4.0+
- **Additional Tools**: 
  - pytest-cov (code coverage)
  - pytest-asyncio (async test support)

#### Directory Structure
```
tests/
├── __init__.py
├── README.md              # Comprehensive testing guide
├── test_log.py           # Tests for logging module (6 tests)
├── test_mediator.py      # Tests for mediator module (4 tests)
├── test_state.py         # Tests for state module (2 tests)
└── test_integration.py   # Integration tests (2 tests)
```

#### Configuration Files
- `pytest.ini` - Pytest configuration
- `.coveragerc` - Coverage configuration
- `.gitignore` - Updated to exclude test artifacts

## Running Tests

### Quick Start
```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage report
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_log.py

# Run tests by marker
pytest -m unit
pytest -m integration
```

### Optional Browser Smoke
The claim-support dashboard now includes an optional real-browser smoke test for the legacy testimony-link repair path:

```bash
# Install Playwright into the project venv
.venv/bin/pip install playwright

# Install a browser runtime once per machine
.venv/bin/python -m playwright install chromium

# Run the dashboard smoke test
.venv/bin/pytest -q tests/test_claim_support_review_playwright_smoke.py
```

The smoke test starts a local FastAPI review surface, seeds one saved testimony row plus one proactively repaired legacy row in a temporary DuckDB, opens the real `/claim-support-review` page in Chromium, clicks `Load Review`, and verifies the rendered testimony summary and cards show both rows linked to `Protected activity`.

If Playwright is not installed, the test is collected and skipped cleanly.

For the full focused claim-support regression slice, use the repo-local runner:

```bash
.venv/bin/python scripts/run_claim_support_review_regression.py
```

That command auto-includes the Playwright smoke when both the Playwright package and Chromium runtime are installed. Use `--browser off` to force the non-browser slice or `--browser on` to require the browser smoke explicitly.

VS Code also exposes this runner through the workspace tasks `Claim Support Regression`, `Claim Support Regression (No Browser)`, and `Claim Support Regression (Require Browser)`.

The Run and Debug panel now mirrors those entry points with `Claim Support Regression`, `Claim Support Regression (No Browser)`, and `Claim Support Regression (Require Browser)` launch configurations.

GitHub Actions now enforces the same focused slice in `.github/workflows/claim-support-regression.yml` with separate non-browser and browser-required lanes.

### Standard Regression Gate

The default repo-level regression entrypoint is now:

```bash
.venv/bin/python scripts/run_standard_regression.py
```

That helper defaults to the browser-inclusive `full` slice and covers the review API, dashboard flow, hooks, template rendering, document pipeline, formal document pipeline, and Playwright smoke.

Equivalent entry points:

- `make regression`
- VS Code tasks `Standard Regression (Lean)`, `Standard Regression (Review)`, and `Standard Regression (Full)`
- GitHub Actions workflow `.github/workflows/standard-regression.yml`

Maintenance rule:

- When you add or remove tests from `scripts/run_standard_regression.py`, update `.github/workflows/standard-regression.yml` path filters in the same change so CI triggers still match the executed slice.
- When you add or remove tests from `scripts/run_claim_support_review_regression.py`, update `.github/workflows/claim-support-regression.yml` path filters in the same change.
- Prefer high-confidence direct source files, runner scripts, and test files over speculative transitive dependencies when expanding workflow trigger paths.

### Current Validation Guidance
- Use `scripts/run_standard_regression.py` as the default gate for review-surface, workflow-guidance, and document-pipeline changes.
- Use `scripts/run_claim_support_review_regression.py` when you need the narrower claim-support-focused slice.
- Use `pytest -m "not integration"` for faster local feedback when you do not need external integrations.
- Treat the browser smoke as optional for local setup and required in the browser CI lane.

### Canary Ops Smoke Checks

For reranker rollout tooling, run these lightweight checks before opening a PR:

```bash
# CI-safe canary wiring validation
python scripts/validate_canary_ops.py

# Focused validator test
pytest tests/test_canary_ops_validation.py -q

# Focused reranker integration regression
pytest tests/test_graph_phase2_integration.py -q --run-network --run-llm
```

In VS Code, equivalent one-click tasks are available in `.vscode/tasks.json`:
- `Canary: Validate Ops Wiring (CI-safe)`
- `Canary: Run + Export + Summarize Reranker Metrics`

For terminal-first workflows, use the top-level `Makefile` aliases:

```bash
make canary-validate
make canary-smoke
make canary-sample
```

## TDD Workflow

The project now follows Test-Driven Development principles:

1. **Write a failing test** - Define expected behavior
2. **Run the test** - Verify it fails (Red)
3. **Write minimal code** - Make the test pass
4. **Run the test** - Verify it passes (Green)
5. **Refactor** - Clean up while keeping tests green
6. **Repeat** - Continue for next feature

## Example: Adding a New Feature

```python
# 1. Write the test first (tests/test_new_feature.py)
def test_new_feature_behavior():
    """Test that new feature works as expected"""
    result = new_feature("input")
    assert result == "expected output"

# 2. Run tests (should fail)
pytest tests/test_new_feature.py

# 3. Implement the feature
def new_feature(input):
    return "expected output"

# 4. Run tests again (should pass)
pytest tests/test_new_feature.py
```

## Benefits of TDD

1. **Confidence**: Tests verify your code works as expected
2. **Documentation**: Tests serve as usage examples
3. **Refactoring**: Tests catch regressions when changing code
4. **Design**: Writing tests first leads to better API design
5. **Coverage**: Ensures all code paths are tested

## Next Steps

1. **Add More Tests**: Expand test coverage for uncovered modules
2. **Gate Selection**: Prefer the standard regression gate for review/document workflow changes before falling back to narrower slices
3. **Backend Dependencies**: Install full backend dependencies to run all tests
4. **Custom Fixtures**: Create reusable test fixtures in `conftest.py`
5. **Test Data**: Add test data fixtures for complex scenarios

## Resources

- [Testing Guide](tests/README.md) - Detailed testing documentation
- [Pytest Documentation](https://docs.pytest.org/)
- [TDD Best Practices](https://testdriven.io/)

## Questions?

For more information on running tests, see `tests/README.md`.
