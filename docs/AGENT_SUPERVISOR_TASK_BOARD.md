# Agent Supervisor Task Board

Date: 2026-07-20
Status: Active compatibility contract

## Purpose

`docs/task_boards/ipfs_supervisor_task_board.json` is the canonical machine-readable task board for the IPFS datasets, intake/evidence, claim-support review, payload-contract, and temporal-proof backlogs.

The markdown backlog files remain the human review surface. Supervisors and daemons should claim work from the JSON board, run the task's validation commands, and then update the board plus the corresponding markdown section.

## Compatible Supervisor Runtime

The board is designed for an `endomorphosis/ipfs_accelerate_py` supervisor or daemon using the MCP or P2P TaskQueue runtime.

Recommended entrypoints:

```bash
ipfs-accelerate mcp start
```

```bash
python -m ipfs_accelerate_py.mcp.cli \
  --host 0.0.0.0 \
  --port 9000 \
  --p2p-task-worker \
  --p2p-service \
  --p2p-queue ~/.cache/ipfs_datasets_py/task_queue.duckdb
```

## Task Lifecycle

1. Load `docs/task_boards/ipfs_supervisor_task_board.json`.
2. Select tasks with status `planned`, `in_progress`, or `validation_required`.
3. Claim a task before editing files.
4. Execute only within the task's `target_files` unless the implementation discovers a documented dependency.
5. Run every listed `validation_commands` entry that is practical in the local environment.
6. Mark the task `complete` only after validation passes or after recording a concrete degraded-mode rationale.
7. Keep `docs/PAYLOAD_CONTRACTS.md` valid whenever a payload surface changes.

## Status Semantics

- `complete`: implementation and validation are accepted as baseline.
- `validation_required`: checklist items appear implemented, but the supervisor should run validation before closure.
- `in_progress`: implementation remains active or incomplete.
- `planned`: designed work that has not started.
- `deferred`: useful work intentionally outside the current execution path.
- `blocked`: work cannot proceed without external input or capability changes.

## Guardrails

- Production code must continue to call `ipfs_datasets_py` through `integrations/ipfs_datasets/`.
- Long-running archive, parse, graph, retrieval, proof, and enrichment work should be queue-backed.
- Payload examples in `docs/PAYLOAD_CONTRACTS.md` must remain parseable JSON fixtures.
- Markdown section statuses should not say `Planned` when every checklist item is checked.
- Paths in the supervised docs should be repo-relative, not host-absolute.

## Validation

Run:

```bash
python scripts/validate_task_boards.py
```

The validator checks the canonical board, selected backlog docs, stale absolute links, planned-but-checked sections, target-file existence, dependency IDs, and every JSON fence in `docs/PAYLOAD_CONTRACTS.md`.
