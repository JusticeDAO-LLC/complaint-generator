# REF-007 Reconciliation Guardrail

Date: 2026-07-21
Fingerprint: a92a0e5a0feb048b0ef041cb44d09c0cc1976425
Kind: main_checkout_dirty
Reason: main_checkout_dirty
Candidate count: 1
Priority: P1
Track: ops

## Main Checkout Status

- ` M docs/ARCHITECTURE.md`
- ` M ipfs_datasets_py`
- `?? data/`
- `?? docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
- `?? scripts/refactor_agent_supervisor.py`

## Main Checkout Evidence

- Path categories: `modified=2, untracked=3`
- Status paths:
  - `docs/ARCHITECTURE.md`
  - `ipfs_datasets_py`
  - `data`
  - `docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
  - `scripts/refactor_agent_supervisor.py`
- Name status:
  - `M	docs/ARCHITECTURE.md`
  - `M	ipfs_datasets_py`
- Diff stat:
  - `docs/ARCHITECTURE.md | 68 ++++++++++++++++++++++++++++++++++++++++++++++++++++`
  - ` ipfs_datasets_py     |  2 +-`
  - ` 2 files changed, 69 insertions(+), 1 deletion(-)`
- Submodule summary:
  - `nal Vermont rule URLs and update tests for document discovery`
  - `  < test(scrapers): Add additional Rhode Island rule URL assertion in Michigan seeds test`
  - `  < feat(scrapers): Add Tennessee rule URL handling and enhance tests for document extraction`
  - `  < update state admin rules scraper and tests`
  - `  < feat(scrapers): Update Montana seed URLs and enhance tests for rule document discovery`
  - `  < feat(scrapers): Add sorting functions for Montana child sections and policies, and enhance document URL discovery tests`
  - `  < feat(scrapers): Enhance Montana rule document URL discovery with section child preference and add corresponding tests`
  - `  < feat(scrapers): Add Rhode Island and Montana rule URL handling and corresponding tests`
  - `  < feat(scrapers): Enhance Rhode Island and Montana rule URL handling in scraper logic and tests`
  - `  < feat(scrapers): Enhance Wyoming bootstrap logic to fetch additional document URLs and update tests`
  - `  < feat(scrapers): Add Wyoming rule document URL discovery and corresponding tests`
  - `  < update .gitignore to ignore artifacts and target directories`
  - `  < feat(scrapers): Implement Montana public API bootstrap for administrative rule discovery`
  - `  < chore: refresh ipfs_kit_py submodule`
  - `  < feat(scrapers): Add Indiana administrative code scraping functionality and corresponding tests`
  - `  < chore: refresh ipfs_kit_py submodule`
  - `  < feat(scrapers): Enhance New Hampshire archived rule scraping with diagnostics and additional URL handling`
  - `  < feat(scrapers): Add timestamp extraction for Wayback Machine URLs and enhance New Hampshire rule scraping tests`
  - `  < feat(optimizers): expand denoiser policy generation`
  - `  < update state admin rules scraper and tests`
- Untracked paths:
  - `data`
  - `docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
  - `scripts/refactor_agent_supervisor.py`

## Sample Branches Or Worktrees

- `implementation/ref-005-attempt-1-1784663197` at `/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g2-g2-s1/ref-005-attempt-1-1784663197`

## Why This Blocks Progress

The implementation supervisor can only merge clean inactive implementation
worktrees when the main checkout is safe to mutate. Dirty main checkouts and
dirty backlogged worktrees are preserved until a deliberate reconciliation task
decides whether to commit, merge, discard generated duplicates, or split
unresolved work into follow-up tasks.

## Suggested Repair

Inspect the dirty paths and sampled worktrees, resolve any real work into
reviewable commits or follow-up tasks, rerun the supervisor reconciliation pass,
and verify that either the candidate merge count decreases or the dirty
worktree cleanup skip count decreases.

## Reconciliation Plan

Work surface: `1` candidates, `1` sampled records.

### Suggested Actions

- `classify_main_checkout_changes`: inspect git status, diff stats, submodule status, and generated artifacts before merges
- `preserve_or_split_main_checkout_work`: commit intentional changes or convert unresolved changes into follow-up tasks; never discard unknown work
- `rerun_worktree_reconciliation`: rerun reconcile_backlogged_worktrees once the main checkout is clean enough to mutate

### Safety Constraints

- Do not discard dirty or untracked content unless it is proven redundant with the target ref.
- Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.
- Keep todo, objective, discovery, and strategy files parseable after reconciliation.

### Success Signals

- `candidate_count_decreases`
- `dirty_worktree_group_count_decreases`
- `main_checkout_dirty_becomes_false`
- `cleanup_or_reconciliation_pass_processes_candidates`

## Machine Readable Manifest

```json
{
  "actions": [
    {
      "action": "classify_main_checkout_changes",
      "automation": "inspect git status, diff stats, submodule status, and generated artifacts before merges",
      "scope": "repo_root"
    },
    {
      "action": "preserve_or_split_main_checkout_work",
      "automation": "commit intentional changes or convert unresolved changes into follow-up tasks; never discard unknown work",
      "scope": "repo_root"
    },
    {
      "action": "rerun_worktree_reconciliation",
      "automation": "rerun reconcile_backlogged_worktrees once the main checkout is clean enough to mutate",
      "scope": "backlogged_worktrees"
    }
  ],
  "candidate_count": 1,
  "conflict_path_counts": {},
  "dedupe_key": "reconciliation_guardrail:main_checkout_dirty",
  "fingerprint": "a92a0e5a0feb048b0ef041cb44d09c0cc1976425",
  "kind": "main_checkout_dirty",
  "main_dirty_evidence": {
    "diff_stat": "docs/ARCHITECTURE.md | 68 ++++++++++++++++++++++++++++++++++++++++++++++++++++\n ipfs_datasets_py     |  2 +-\n 2 files changed, 69 insertions(+), 1 deletion(-)",
    "name_status": "M\tdocs/ARCHITECTURE.md\nM\tipfs_datasets_py",
    "path_categories": {
      "modified": 2,
      "untracked": 3
    },
    "status_paths": [
      "docs/ARCHITECTURE.md",
      "ipfs_datasets_py",
      "data",
      "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
      "scripts/refactor_agent_supervisor.py"
    ],
    "status_short": [
      " M docs/ARCHITECTURE.md",
      " M ipfs_datasets_py",
      "?? data/",
      "?? docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
      "?? scripts/refactor_agent_supervisor.py"
    ],
    "submodule_summary": "nal Vermont rule URLs and update tests for document discovery\n  < test(scrapers): Add additional Rhode Island rule URL assertion in Michigan seeds test\n  < feat(scrapers): Add Tennessee rule URL handling and enhance tests for document extraction\n  < update state admin rules scraper and tests\n  < feat(scrapers): Update Montana seed URLs and enhance tests for rule document discovery\n  < feat(scrapers): Add sorting functions for Montana child sections and policies, and enhance document URL discovery tests\n  < feat(scrapers): Enhance Montana rule document URL discovery with section child preference and add corresponding tests\n  < feat(scrapers): Add Rhode Island and Montana rule URL handling and corresponding tests\n  < feat(scrapers): Enhance Rhode Island and Montana rule URL handling in scraper logic and tests\n  < feat(scrapers): Enhance Wyoming bootstrap logic to fetch additional document URLs and update tests\n  < feat(scrapers): Add Wyoming rule document URL discovery and corresponding tests\n  < update .gitignore to ignore artifacts and target directories\n  < feat(scrapers): Implement Montana public API bootstrap for administrative rule discovery\n  < chore: refresh ipfs_kit_py submodule\n  < feat(scrapers): Add Indiana administrative code scraping functionality and corresponding tests\n  < chore: refresh ipfs_kit_py submodule\n  < feat(scrapers): Enhance New Hampshire archived rule scraping with diagnostics and additional URL handling\n  < feat(scrapers): Add timestamp extraction for Wayback Machine URLs and enhance New Hampshire rule scraping tests\n  < feat(optimizers): expand denoiser policy generation\n  < update state admin rules scraper and tests\n  < fix(scrapers): Update Wyoming rule discovery to prevent inspecting certain program URLs\n  < feat(scrapers): Enhance New Hampshire archived rule scraping with new functions and tests\n  < feat(scrapers): Update state admin rules scraper to include additional RTF sources and enhance PDF text extraction\n  < feat(scrapers): Enhance Oklahoma rule scraping with caching and improved document handling\n  < feat(optimizers): Implement action policy mode in TestDrivenOptimizer and enhance intake action rendering\n  < Enhance anyio compatibility and add new scraper tests\n  < feat(.gitignore): Add artifacts directory to ignore list\n  < feat(optimizers): Enhance TestDrivenOptimizer with generation diagnostics and symbol-level optimization handling\n  < Update dependencies and add new requirements for scraping and vectorization\n  < feat(scrapers): Enhance Michigan and Alaska rule detection with new URL patterns and scoring logic\n  < Enhance tests for legal scrapers: - Added assertions for Tennessee and Massachusetts curated seed URLs. - Updated Alabama and Arkansas rule detail recognition logic. - Introduced new tests for Arkansas section rule pages and Montana rule document URLs. - Improved handling of Alabama and Montana rule detail scraping via API. - Added checks for New Hampshire archived rule chapters and Tennessee inventory pages.\n  < feat(scrapers): Enhance Tennessee rule detection with additional URL patterns and inventory page recognition\n  < feat(tests): Add tests for Indiana and Tennessee curated seed URLs\n  < feat(scrapers): Enhance Georgia and New Mexico rule detection and scoring\n  < Align package metadata with search and vector dependencies\n  < Enhance state laws scraper with legal metadata detection and improve quality metrics\n  < Add Montana policy URL handling and Rhode Island document trimming functions\n  < Add egg-info files for package dependencies and top-level modules\n  < Add Tennessee regex patterns and tests for administrative rules scraping\n  < Add Arkansas-specific regex patterns and tests for administrative rules scraping\n  < Add Kansas and New Hampshire regex patterns and tests for administrative rules scraping\n  < Add Wyoming-specific regex patterns and tests to filter non-substantive rule pages\n  < Refactor code structure for improved readability and maintainability",
    "untracked_paths": [
      "data",
      "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
      "scripts/refactor_agent_supervisor.py"
    ]
  },
  "reason": "main_checkout_dirty",
  "safety_constraints": [
    "Do not discard dirty or untracked content unless it is proven redundant with the target ref.",
    "Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "implementation/ref-005-attempt-1-1784663197"
  ],
  "sample_count": 1,
  "sample_status_paths": [
    "docs/ARCHITECTURE.md",
    "ipfs_datasets_py",
    "data",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "scripts/refactor_agent_supervisor.py"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g2-g2-s1/ref-005-attempt-1-1784663197"
  ],
  "success_signals": [
    "candidate_count_decreases",
    "dirty_worktree_group_count_decreases",
    "main_checkout_dirty_becomes_false",
    "cleanup_or_reconciliation_pass_processes_candidates"
  ],
  "top_conflict_paths": []
}
```

## Reconciliation Result

Resolved: 2026-07-21T20:06Z

- Classified the original dirty main checkout evidence and found the work had
  already been narrowed from five paths to one local supervisor wrapper change.
- Preserved that remaining main checkout change with commit
  `f20703f1bb2a732fa78daf8c031fb315232baa1e`
  (`chore(refactor): preserve merge watchdog pacing`) instead of discarding it.
- Reran the `refactor/g2/g2-s1` supervisor reconciliation path. The lane event
  log records `main_checkout_dirty: false`, empty `main_status_short`, and empty
  `main_dirty_evidence` for the post-repair pass at
  `2026-07-21T20:06:01Z`.
- The dirty-main blocked candidate count for this guardrail decreased from
  `1` to `0`. The remaining candidates moved to the separate
  `preflight_merge_conflict` guardrail surface, so REF-007 no longer owns those
  merge blockers.
- A failed background merge attempt was aborted after the preserved branch
  commits remained available on their implementation refs; the main checkout was
  returned to a non-merge state before handing this task back to the supervisor.

Post-repair evidence source:
`data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/state/agent_refactor_g2_g2_s1_supervisor_events.jsonl`
contains the rerun pass with `target_signature`
`f20703f1bb2a732fa78daf8c031fb315232baa1e`,
`main_checkout_dirty: false`, `candidate_count: 2`,
`processed_count: 2`, and `preflight_blocked_count: 2`.
