# Contributing to Complaint Generator

Thank you for your interest in contributing to the complaint generator! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Documentation](#documentation)
- [Pull Request Process](#pull-request-process)
- [Style Guide](#style-guide)
- [Areas for Contribution](#areas-for-contribution)

## Code of Conduct

### Our Standards

- Be respectful and inclusive
- Welcome newcomers and help them get started
- Accept constructive criticism gracefully
- Focus on what is best for the community
- Show empathy towards other community members

### Unacceptable Behavior

- Harassment, trolling, or discriminatory language
- Publishing others' private information
- Unethical or illegal behavior
- Other conduct which could reasonably be considered inappropriate

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Git
- GitHub account
- (Optional) IPFS node for testing storage features
- (Optional) API keys for LLM providers

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
```bash
git clone https://github.com/YOUR_USERNAME/complaint-generator.git
cd complaint-generator
```

3. Add upstream remote:
```bash
git remote add upstream https://github.com/endomorphosis/complaint-generator.git
```

### Set Up Development Environment

1. Initialize submodules:
```bash
git submodule update --init --recursive
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install development dependencies:
```bash
pip install pytest pytest-cov pytest-asyncio black flake8 mypy
```

4. Verify installation:
```bash
pytest tests/ -v
```

## Development Workflow

### 1. Create a Feature Branch

```bash
# Update your main branch
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/your-feature-name
```

### 2. Make Changes

Follow Test-Driven Development (TDD):

1. **Write a failing test** for the new feature
2. **Run tests** to verify it fails
3. **Implement** minimal code to pass the test
4. **Refactor** while keeping tests green
5. **Repeat** for next feature

### 3. Commit Changes

Write clear, descriptive commit messages:

```bash
git add .
git commit -m "Add feature: Brief description

Detailed explanation of what changed and why.
Addresses issue #123."
```

### 4. Keep Your Branch Updated

Regularly sync with upstream:

```bash
git fetch upstream
git rebase upstream/main
```

### 5. Push Changes

```bash
git push origin feature/your-feature-name
```

## Testing

### Run All Tests

```bash
pytest
```

### Run Claim-Support Regression

When you change the review surface, testimony-linking flow, or dashboard rendering, run the focused claim-support regression slice:

```bash
.venv/bin/python scripts/run_claim_support_review_regression.py
```

Use `--browser off` to force the non-browser slice or `--browser on` to require the Playwright smoke. The same regression is also available in VS Code through the `Claim Support Regression` task and launch configurations, and in GitHub Actions through `.github/workflows/claim-support-regression.yml`.

### Run Specific Test Files

```bash
pytest tests/test_mediator.py
pytest tests/test_complaint_analysis.py
```

### Run with Coverage

```bash
pytest --cov=. --cov-report=html
# View coverage report: open htmlcov/index.html
```

### Run Integration Tests Only

```bash
pytest -m integration
```

### Run Unit Tests Only (Faster)

```bash
pytest -m "not integration"
```

### Writing Tests

Follow existing test patterns:

```python
import pytest
from module import function_to_test

class TestFeature:
    """Test cases for a specific feature"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.test_data = "example"
    
    def test_basic_functionality(self):
        """Test basic functionality"""
        result = function_to_test(self.test_data)
        assert result == expected_value
    
    def test_edge_case(self):
        """Test edge case handling"""
        with pytest.raises(ValueError):
            function_to_test(invalid_data)
```

### Test Coverage Goals

- New features: 100% test coverage
- Bug fixes: Add test that reproduces the bug
- Refactoring: Maintain existing coverage
- Overall project: Aim for 80%+ coverage

## Documentation

### Update Documentation

When adding features or making changes:

1. **Update README.md** if adding major features
2. **Update module READMEs** for module-specific changes
3. **Create/update docs/** for detailed documentation
4. **Add docstrings** to all public functions and classes
5. **Update examples/** if demonstrating new features
6. **Update TESTING.md / tests/README.md / DOCUMENTATION_INDEX.md** when you add or change supported regression entry points

### Docstring Format

Use Google-style docstrings:

```python
def analyze_complaint(text: str, complaint_type: str = None) -> dict:
    """Analyze a legal complaint.
    
    Args:
        text: The complaint text to analyze
        complaint_type: Optional complaint type hint (e.g., 'employment')
    
    Returns:
        Dictionary containing:
            - risk_level: str, risk assessment
            - categories: list, identified categories
            - provisions: dict, extracted legal provisions
    
    Raises:
        ValueError: If text is empty
        AnalysisError: If analysis fails
    
    Example:
        >>> result = analyze_complaint("I was fired for...")
        >>> print(result['risk_level'])
        'high'
    """
    # Implementation
```

### Writing Good Documentation

- **Be Clear:** Use simple, precise language
- **Be Complete:** Cover all parameters, returns, exceptions
- **Be Concise:** Avoid unnecessary verbosity
- **Add Examples:** Show how to use the feature
- **Keep Updated:** Update docs when code changes

## Pull Request Process

### Before Submitting

- [ ] All tests pass (`pytest`)
- [ ] Code follows style guide (`black`, `flake8`)
- [ ] Added/updated tests for changes
- [ ] Updated documentation
- [ ] Rebased on latest upstream/main
- [ ] Commit messages are clear

### Submitting PR

1. Push your feature branch to your fork
2. Go to the original repository on GitHub
3. Click "New Pull Request"
4. Select your feature branch
5. Fill out the PR template:
   - **Title:** Brief, descriptive summary
   - **Description:** Detailed explanation of changes
   - **Related Issues:** Link to issues addressed
   - **Testing:** How you tested the changes
   - **Screenshots:** For UI changes

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Related Issues
Closes #123

## Testing
- [ ] Added new tests
- [ ] All tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guide
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] No breaking changes (or documented)
```

### Review Process

1. Maintainer reviews PR
2. Address feedback if requested
3. Once approved, maintainer merges
4. Your changes are in the main branch!

## Style Guide

### Python Style

Follow PEP 8 with these specifics:

- **Line Length:** 100 characters (not 79)
- **Indentation:** 4 spaces
- **Quotes:** Single quotes for strings (except docstrings)
- **Imports:** Organized by stdlib, third-party, local

### Code Formatting

Use `black` for automatic formatting:

```bash
black .
```

### Linting

Use `flake8` for linting:

```bash
flake8 .
```

### Type Hints

Use type hints for function signatures:

```python
from typing import List, Dict, Optional

def process_complaints(
    complaints: List[str],
    options: Optional[Dict[str, any]] = None
) -> Dict[str, any]:
    """Process multiple complaints."""
    # Implementation
```

### Naming Conventions

- **Functions/Methods:** `snake_case`
- **Classes:** `PascalCase`
- **Constants:** `UPPER_SNAKE_CASE`
- **Private:** `_leading_underscore`
- **Modules:** `lowercase` or `snake_case`

### Good Code Practices

- **DRY:** Don't Repeat Yourself
- **KISS:** Keep It Simple, Stupid
- **YAGNI:** You Aren't Gonna Need It
- **Single Responsibility:** One function, one purpose
- **Clear Variable Names:** Use descriptive names

## Areas for Contribution

### High Priority

1. **Web UI Development**
   - Create browser-based interface
   - Real-time complaint processing
   - Evidence upload interface

2. **API Development**
   - RESTful API endpoints
   - Authentication and authorization
   - API documentation (OpenAPI/Swagger)

3. **Additional Complaint Types**
   - Research new legal domains
   - Create keyword sets and decision trees
   - Add test coverage

4. **Performance Optimization**
   - Improve LLM caching
   - Optimize graph algorithms
   - Database query optimization

### Medium Priority

5. **Enhanced Testing**
   - More edge case coverage
   - Performance benchmarks
   - Load testing

6. **Legal Research Improvements**
   - Additional data sources
   - Better relevance scoring
   - Citation formatting

7. **Documentation**
   - More examples
   - Video tutorials
   - API reference improvements

8. **Internationalization**
   - Multi-language support
   - Localized legal patterns
   - Translation infrastructure

### Low Priority (Nice to Have)

9. **Mobile Application**
   - iOS/Android apps
   - Offline capability
   - Push notifications

10. **Advanced Features**
    - Case outcome prediction
    - Automated brief generation
    - Collaborative editing

11. **Integration**
    - Document management systems
    - Case management software
    - Legal research platforms

## Getting Help

### Resources

- **Documentation:** See docs/ directory
- **Examples:** See examples/ directory
- **Tests:** See tests/ directory for usage patterns
- **Issues:** Check existing issues for similar problems

### Communication

- **GitHub Issues:** For bug reports and feature requests
- **GitHub Discussions:** For questions and general discussion
- **Pull Requests:** For code contributions

### Asking Good Questions

1. **Search First:** Check docs, issues, discussions
2. **Be Specific:** Provide details, error messages, code snippets
3. **Be Clear:** Explain what you tried and what you expected
4. **Be Respectful:** Remember that maintainers are volunteers

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in documentation (if significant contribution)

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (see LICENSE file).

## Thank You!

Every contribution, no matter how small, helps make this project better. We appreciate your time and effort!

---

**Questions?** Open an issue or start a discussion on GitHub.

**Ready to contribute?** Fork the repo and start coding!
