# REF-014 Validation Retry-Budget Finding: REF-012

Date: 2026-07-22
Source task: REF-012
Follow-up task: REF-014
Retry budget: 3
Observed consecutive validation failures: 3

## Evidence

- Failed command: `python -m pytest tests/test_symbolicai_logic_dependency.py tests/test_ipld_logic_storage_dependency.py -q`
- Attempts: 1, 2, 3
- Logs: /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g3-g3-s2/state/implementation_logs/ref-012-attempt-1.log, /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g3-g3-s2/state/implementation_logs/ref-012-attempt-2.log, /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g3-g3-s2/state/implementation_logs/ref-012-attempt-3.log



## Guardrail Result

The accelerator backlog refinery classified this as backlog work instead of
allowing another implementation attempt to loop on the same failure. The source
task is added to the strategy `blocked_tasks` list and the follow-up task below
is appended for normal daemon parsing.

## Resolution

Resolved on 2026-07-22. The repeated failures were caused by dependency drift,
not by the REF-012 capability contract: the validation environment resolved an
older shared `ipfs_datasets_py` checkout that lacked
`ensure_symai_config_for_import`, and importing SymbolicAI consequently tried
to create `/usr/.symai`. The repository now pins dependency revision
`7b39c55930e54c696bba48039dfffd0244ec2ab3`, which selects a writable
SymbolicAI configuration root before import and hardens the IPLD logic-storage
imports so they use the installed IPLD implementation.

The REF-012 implementation preserved on rescue commit
`99e1c244c199263c65a4ef1194a9a38898e325f0` was recovered into this repair. It
adds typed `unavailable`, `degraded`, and `implemented` capability states,
operation-specific gates, deterministic exceptions, serialized capability
metadata, and centralized normalization for legacy payloads. Review callers
now branch on the typed contract instead of fragile provider status strings.

Validation passes against the repaired dependency:

```text
python -m pytest tests/test_symbolicai_logic_dependency.py tests/test_ipld_logic_storage_dependency.py -q
2 passed in 11.26s
```

The restored capability contract and its claim-support consumers also pass the
focused regression lane (`58 passed`), and all changed Python modules compile.

REF-014 is marked completed in the bundle todo. Under the production guardrail
release contract, that completion makes REF-012 eligible for removal from the
lane strategy's `blocked_tasks` list on the next supervisor maintenance pass.
A non-mutating simulation using a temporary copy of the live strategy returned
the release below and an empty `blocked_tasks` list:

```json
{
  "source_task_id": "REF-012",
  "follow_up_task_id": "REF-014",
  "guardrail_kind": "retry_budget"
}
```
