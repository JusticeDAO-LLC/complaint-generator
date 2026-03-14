# Testing Guide for Complaint Generator

This directory contains tests for the complaint-generator application following Test-Driven Development (TDD) principles.

## Test Structure

```
tests/ (22 files, 60+ test classes, 150+ tests)
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
    tests/test_claim_support_hooks.py \
    tests/test_review_api.py \
    tests/test_claim_support_review_dashboard_flow.py \
    tests/test_backfill_claim_testimony_links_cli.py \
    tests/test_claim_support_review_playwright_smoke.py
```

The equivalent repo-local helper auto-detects whether the browser smoke should be included:

```bash
.venv/bin/python scripts/run_claim_support_review_regression.py
```

In VS Code, the same runner is available from the workspace task list as `Claim Support Regression`, with explicit `No Browser` and `Require Browser` variants.

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
