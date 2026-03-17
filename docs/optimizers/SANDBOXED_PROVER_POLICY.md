# Sandboxed Prover Policy

This document defines the security policy for running untrusted or semi-trusted
external theorem provers from the optimizer stack.

## Scope

Applies to subprocess-backed prover integrations in:
- `ipfs_datasets_py/ipfs_datasets_py/optimizers/logic_theorem_optimizer/additional_provers.py`
- `ipfs_datasets_py/ipfs_datasets_py/optimizers/logic_theorem_optimizer/prover_integration.py`
- Future external prover adapters.

Does not apply to in-process provers that do not spawn executables.

## Threat Model

Primary risks:
- Arbitrary code execution via malicious prover binaries or payloads.
- Host file exfiltration through unrestricted filesystem access.
- Network exfiltration/beaconing from prover child processes.
- Resource exhaustion (CPU, memory, process forks, disk writes).
- Hang/stall behavior that blocks optimizer sessions.

## Required Runtime Controls

Every subprocess prover invocation must enforce all controls below.

1. Timeout controls
- Hard timeout per prover call (default `10s`, upper bound `60s`).
- Kill process group on timeout.
- Mark result as timeout; do not retry immediately more than once.

2. Resource controls
- CPU: bounded via cgroup/cpulimit (`<= 1 core` by default).
- Memory: hard cap (`<= 512MB` default; configurable per prover profile).
- Process count: `nproc` cap (`<= 32`).
- File size/output cap: stdout+stderr truncated (`<= 1MB`).

3. Filesystem controls
- Run from isolated temp working directory.
- Mount/read access limited to prover input + required runtime libs.
- No write access outside isolated temp dir.
- Always use absolute executable path from allowlist.

4. Network controls
- Default deny all outbound/inbound networking for prover subprocesses.
- If network is required for a specific prover, it must be explicitly allowlisted.

5. Execution controls
- Run under non-privileged user.
- `no_new_privs` enabled.
- Disallow shell execution (`shell=False`) and avoid string commands.
- Use argument vectors only, with strict input normalization.

6. Observability and audit
- Structured log per prover call with: prover name, timeout, duration, exit code,
  bytes output, and whether policy controls were active.
- Emit security-classified error codes for policy violations.

## Prover Allowlist

Only explicitly approved executables are permitted.

Example policy entry:

```yaml
provers:
  z3:
    executable: /usr/bin/z3
    max_timeout_s: 20
    max_memory_mb: 512
  cvc5:
    executable: /usr/bin/cvc5
    max_timeout_s: 30
    max_memory_mb: 768
  vampire:
    executable: /usr/bin/vampire
    max_timeout_s: 15
    max_memory_mb: 512
```

Validation requirements:
- Reject unknown prover names.
- Reject executables not matching allowlist exact path.
- Reject non-file or symlink-resolved paths outside approved locations.

## Failure Handling Policy

When sandbox policy fails to initialize or enforce:
- Do not run subprocess prover in unrestricted mode.
- Return typed policy error (`ProverError` with `policy_violation` dimension).
- Continue session with remaining safe provers when possible.

## Recommended Implementation Pattern

1. Introduce `SandboxedProverRunner` abstraction:
- `run(argv: list[str], timeout_s: float, limits: ProverLimits) -> ProverExecResult`

2. Centralize policy config:
- single config object loaded at startup,
- immutable view passed to adapters.

3. Migrate each external prover adapter to call runner instead of direct
   `subprocess.run(...)`.

4. Add policy tests:
- timeout kill behavior,
- memory/process caps enforced,
- allowlist rejection,
- no-network mode,
- log/audit event emission.

## Rollout Plan

1. Phase 1: Add runner + policy config with feature flag (`PROVER_SANDBOX_ENABLED`).
2. Phase 2: Migrate Z3/CVC5 adapters and keep legacy path behind kill-switch.
3. Phase 3: Migrate remaining external provers; remove legacy unrestricted path.
4. Phase 4: Enforce sandbox-by-default in production profiles.

## Operational Defaults

- `PROVER_SANDBOX_ENABLED=true`
- `PROVER_TIMEOUT_S=10`
- `PROVER_MAX_MEMORY_MB=512`
- `PROVER_MAX_OUTPUT_BYTES=1048576`
- `PROVER_NETWORK=disabled`

If these defaults cannot be satisfied in the deployment environment, disable
external subprocess provers rather than running them unsandboxed.
