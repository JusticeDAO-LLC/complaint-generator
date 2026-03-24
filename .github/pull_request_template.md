## Summary

Describe the user-visible or developer-visible change.

## Change Type

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor
- [ ] Documentation update
- [ ] CI or tooling update

## Validation

- [ ] Ran `.venv/bin/python scripts/run_standard_regression.py`
- [ ] Ran `.venv/bin/python scripts/run_claim_support_review_regression.py` for review/dashboard/testimony-link changes
- [ ] Ran `.venv/bin/python scripts/run_claim_support_review_regression.py --browser on --network on` when browser surfaces or network-gated package review/export paths changed
- [ ] Ran `make canary-validate` for canary/reranker/metrics changes
- [ ] Added or updated focused tests for the modified behavior
- [ ] Skipped one or more checks intentionally and explained why below

## Documentation

- [ ] Updated `README.md`, `TESTING.md`, `tests/README.md`, or other relevant docs
- [ ] No documentation changes were needed

## Notes

List anything reviewers should know about scope, follow-ups, skipped validation, or rollout risk.