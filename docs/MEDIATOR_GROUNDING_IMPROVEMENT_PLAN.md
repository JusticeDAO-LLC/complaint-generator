# Mediator-grounded complaint interview improvement program

This program extends the completed complaint-intake work. It connects the public terminal interview to the existing mediator hooks and the pinned submodule APIs. The earlier 58-task intake board and its evidence remain a separate completed program.

The executable specification is `docs/task_boards/complaint_mediator_grounding_spec.json`. Its native `FormalWorkPlan`, goals, subgoals, evidence requirements and task dependencies are emitted to `complaint_mediator_grounding_formal_work_plan.json`; the supervisor executes the matching `complaint_mediator_grounding_task_board.md` projection. Compiling or ingesting those contracts does not complete tasks or prove their goals satisfied.

## Start from the actual terminal journey

Use the canonical `python -m complaint_generator.cli chat --user-id SYNTHETIC_CASE` entrypoint with a temporary, synthetic case. Check narrative capture, question selection, answer transitions, `/why`, `/edit`, explicit jurisdiction and effective date, unresolved gaps, pause, encrypted persistence and a fresh-process resume. Existing synthetic acceptance tests already exercise much of this behavior. The new baseline must expose the missing mediator transitions instead of declaring a complete interview from a smoke-test pass.

The current audit identifies these integration seams:

- Shared pending inquiries can lose objective, graph-target, explanation and expected-update fields before `/why` or cold resume.
- Terminal `/edit` updates answers but does not yet use the mediator's existing supersession and graph-invalidation transition.
- Verified legal requirements are derived from locally admitted authorities, but the terminal lacks a complete public acquisition, source admission and dependency-refresh workflow.
- Legacy evidence and database hooks must use the private artifact boundary before they are activated for private cases.

## Keep factual and legal grounding distinct

The factual knowledge graph records what the user supplied: people, events, allegations, documents, corrections and contradictions. Every assertion needs the exact source statement or evidence revision. Generated suggestions remain hypotheses until the user or admissible evidence supports them. Corrections supersede prior assertions without erasing history and invalidate affected links and proof results.

The legal dependency graph records requirements supported by admitted legal sources. Its nodes carry authority identifiers, source passages, jurisdiction, effective date, applicability conditions, exceptions, burdens and version information. User allegations, search snippets, LLM responses and successful IR parsing do not by themselves establish a legal requirement. Missing authority or applicability context remains an explicit research gap.

Mediator hooks connect these graphs through inspectable support and contradiction links. An answer changes factual support for a requirement; it does not rewrite the source's legal rule. The interview asks about actionable factual uncertainties, evidence needs and contradictions, and hands research gaps to the appropriate legal workflow. It stops when no further actionable question is available, while reporting unresolved legal and evidentiary issues. Interview saturation is not a claim that a complaint is legally sufficient.

## Integrate existing submodule owners

Use `ipfs_datasets_py` through the first-party graph, legal-corpus and logic adapters. Reuse sourced requirements, applicable-context checks, canonical legal IR, bound proof obligations and typed proof routing. New bound-definition, interpretation, scope and source-sampling owners need explicit capability probes and bounded adapter contracts. Training, consistency checks and generated formal artifacts are separate from governing authority and successful proof execution.

Use `ipfs_accelerate_py.llm_router` with `grok-4.7`, provider `grok_cli`, and fallback disabled. All newly activated generation hooks need a purpose, bounded input, source references, case privacy decision and structured result. Case data reaches the remote model only after explicit authorization for that case. The development supervisor receives source code and synthetic fixtures; its private-path exclusions protect existing complaints, exports, evidence, keys and credentials.

Use the existing private repository and `ipfs_kit_py` adapters for durability. Encrypt before storage or replication, bind key ownership to the case, verify ciphertext readback and distinguish local commit, queued replication, pinning and verified replicas. Include graph revisions, inquiries, legal evaluations, proof traces, derived indexes and hook receipts. Migrate legacy plaintext resumably with encrypted readback before any cleanup; a missing key or unavailable backend must not create a fresh empty case or discard unresolved work.

## Execute bounded tasks with truthful health

Each task declares outputs, dependencies, a small implementation scope, behavioral acceptance criteria and a host validation command. Implementation remains Grok-only, with the existing 64-turn and 900-second limits, three paid attempts, one validation worker and a single worktree pool slot. Do not install or vendor dependencies inside a worker to hide an unavailable tool. Missing capabilities produce typed unavailable states; mandatory checks cannot silently skip or fabricate successful receipts.

Use a fresh campaign state directory, merge queue and private worktree root. The supervisor owns selection, claims, validation, retries and completion callbacks. Preserve deliberate holds and paid-attempt history. Distinguish a user-facing interview waiting for input from an implementation worker stalled without progress. Validation heartbeats describe actual bounded validation work and never extend its deadline. Recovery requires matching process birth, campaign identity, source and owned workspace; it cannot clear unrelated owners or reset budgets.

Startup acceptance requires more than a PID or a ready doctor result: verify native contract ingestion, the exact model route, a fresh owned heartbeat, canonical active task identity and real provider/tool or validation progress. Observe the first task through measured host validation and the ordinary completion callback. Record actual health and remaining work honestly.

## Operator commands

Run these commands from the selected checkout with its pinned submodules available. Choose a new private state directory and an existing UID-owned mode-0700 worktree root outside the checkout.

```bash
python scripts/run_complaint_improvement_supervisor.py prepare \
  --repo-root "$REPO_ROOT" \
  --spec "$REPO_ROOT/docs/task_boards/complaint_mediator_grounding_spec.json" \
  --state-dir "$CAMPAIGN_STATE"

python scripts/run_complaint_improvement_supervisor.py doctor \
  --repo-root "$REPO_ROOT" \
  --spec "$REPO_ROOT/docs/task_boards/complaint_mediator_grounding_spec.json" \
  --state-dir "$CAMPAIGN_STATE" --worktree-root "$WORKTREE_ROOT"

python scripts/run_complaint_improvement_supervisor.py start \
  --repo-root "$REPO_ROOT" \
  --spec "$REPO_ROOT/docs/task_boards/complaint_mediator_grounding_spec.json" \
  --state-dir "$CAMPAIGN_STATE" --worktree-root "$WORKTREE_ROOT" \
  --watch --monitor-seconds 21600

python scripts/run_complaint_improvement_supervisor.py status \
  --repo-root "$REPO_ROOT" \
  --spec "$REPO_ROOT/docs/task_boards/complaint_mediator_grounding_spec.json" \
  --state-dir "$CAMPAIGN_STATE"
```

Use the same explicit roots with `stop`. Resume uses `start` with the same state directory after verified closure. A not-ready report is a diagnosis, not execution evidence. Record local runtime and behavioral validation separately from hosted CI status.
