# How To Add a New Optimizer

This guide is the implementation checklist for adding a new optimizer module to the codebase with consistent architecture, tests, and docs.

## Goal

Ship a new optimizer that:
- follows shared optimizer contracts,
- has deterministic baseline tests,
- is observable (logs + metrics),
- is documented and runnable from examples/CLI.

## 1) Choose the Shape

Decide whether the optimizer is:
- `single-pass` (generate + evaluate once),
- `iterative` (round-based refine loop), or
- `batch` (analyze multiple artifacts and summarize).

For iterative or batch workflows, prefer extending shared abstractions in `ipfs_datasets_py/optimizers/common/`.

## 2) Create Module Skeleton

Recommended files:
- `ipfs_datasets_py/optimizers/<domain>/<new_optimizer>.py`
- `ipfs_datasets_py/optimizers/<domain>/cli_wrapper.py` (if user-facing CLI required)
- `ipfs_datasets_py/optimizers/tests/unit/<domain>/test_<new_optimizer>.py`

Minimal class template:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from ipfs_datasets_py.optimizers.common.base_optimizer import BaseOptimizer, OptimizationContext


@dataclass
class NewOptimizerConfig:
    max_rounds: int = 3
    threshold: float = 0.7
    extra: Dict[str, Any] = field(default_factory=dict)


class NewOptimizer(BaseOptimizer):
    def __init__(self, config: NewOptimizerConfig | None = None, **kwargs: Any) -> None:
        super().__init__(config=config or NewOptimizerConfig(), **kwargs)

    def generate(self, input_data: Any, context: OptimizationContext) -> Any:
        """Generate initial artifact from input data."""
        return {"artifact": input_data}

    def critique(self, artifact: Any, context: OptimizationContext) -> Tuple[float, List[str]]:
        """Evaluate artifact quality.
        
        Returns:
            Tuple of (score, feedback_list) where score is 0-1 and feedback is list of suggestions.
        """
        return (1.0, [])

    def optimize(self, artifact: Any, score: float, feedback: List[str], context: OptimizationContext) -> Any:
        """Improve artifact based on critique feedback."""
        return artifact

    def validate(self, artifact: Any, context: OptimizationContext) -> bool:
        """Validate that artifact meets requirements."""
        return True
```

## 3) Wire Exports

Update package exports so imports are stable:
- `<domain>/__init__.py`
- (if public API) `ipfs_datasets_py/optimizers/__init__.py`

Ensure `from ipfs_datasets_py.optimizers.<domain> import NewOptimizer` works.

## 4) Add Tests First-Class

Required test layers:
- unit tests for each method (`generate/critique/optimize/validate`),
- at least one session/pipeline flow test,
- edge-case tests (empty input, invalid config, malformed artifacts).

Minimum unit checklist:
- constructor/default config,
- deterministic behavior with fixed inputs,
- validation failures are explicit (typed exception or clear result),
- score/result bounds (if scoring is used).

## 5) Observability Contract

For any new optimizer, include:
- structured logs with stable keys,
- duration tracking (`execution_time_ms` or equivalent),
- failure logging without leaking secrets.

Suggested log fields:
- `optimizer`, `session_id`, `round`, `domain`, `score`, `duration_ms`, `status`.

## 6) CLI Integration (Optional but Common)

If user-facing:
- add argparse commands in `<domain>/cli_wrapper.py`,
- support `--input`, `--output`, `--config`,
- return non-zero exit code on failures,
- add CLI tests for success and invalid-input paths.

## 7) Documentation Requirements

Update docs in same PR:
- this guide (if new pattern learned),
- API reference for new class/config,
- one integration snippet in `docs/optimizers/INTEGRATION_EXAMPLES.md`,
- add links in `DOCUMENTATION_INDEX.md`.

## 8) Performance + Safety Gates

Before merge, run:
- focused unit tests for new optimizer,
- existing optimizer suite smoke test,
- optional micro-benchmark if optimizer adds heavy loops.

Safety checks:
- no broad silent `except Exception` in core path,
- no logging of tokens/keys/raw secrets,
- file paths validated for CLI inputs.

## 9) Pull Request Checklist

- [ ] Optimizer class + typed config added
- [ ] Package exports updated
- [ ] Unit tests added and passing
- [ ] CLI behavior tested (if applicable)
- [ ] Structured logs/metrics included
- [ ] Docs and examples updated
- [ ] TODO item updated with completion note

## 10) Example Done Entry (TODO)

```md
- [x] (P2) [docs] Write "How to add a new optimizer" guide
  - Done 2026-02-24: added docs/optimizers/HOW_TO_ADD_NEW_OPTIMIZER.md; linked in DOCUMENTATION_INDEX.md.
```
