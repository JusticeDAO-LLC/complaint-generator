# Mediator grounding, source-bound law and private terminal workflow

<!-- plan_id: baguqeerawyd66w4rgas5cocjkxv74mbt4jujxekjtfuad2babtl3xnmpsrkq -->

Implementation tasks begin pending. Completion requires behavioral validation evidence.

## CIMP-MGND-01 Characterize actual chat grounding, edit and resume gaps

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.baseline
- Subgoal: subgoal.mgnd.baseline.public
- Depends on:
- Outputs: docs/task_boards/complaint_mediator_grounding_baseline_receipt.json, tests/test_cimp_mgnd_01.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_01.py --run-llm --run-network --run-heavy
- Acceptance: Add only this one characterization module and a small source-pinned observation receipt; do not change product behavior in this task. Invoke the actual terminal command/service with a new private passphrase fixture and explicit fake observed-router transport. Record that no live Grok call occurred. Measure narrative assertion spans/KG, current dependency/source gaps, real /why metadata, /edit versus shared graph state, and encrypted fresh-service resume. Classify observed gaps separately from the passing characterization mechanics. Keep observations compatible with later fixes: do not require a known defect to remain broken. The receipt names the observed source generation and must never claim all new campaign behavior works. Use short terminal deadlines and no stdin wait in the development worker; output only bounded synthetic diagnostic metadata. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  First task only: demonstrate the real public control path and write an honest baseline. Reuse the existing terminal/private fixture patterns. The prior two synthetic passes are historical starting evidence, not this task's completion.  Exact starting pointers: read only applications/complaint_cli.py:TerminalComplaintWorkspaceService/chat, applications/complaint_workspace.py:ComplaintWorkspaceService.run_intake_chat_turn/apply_shared_interview, mediator/workflow_service.py:_inquiry_from_question/export_session_projection, and the synthetic fixture patterns in tests/test_tui_interview_acceptance.py:_block_network_and_provider_subprocesses/_service plus tests/test_tui_router_trace.py:terminal_service/test_actual_shared_cli_saves_invocation_with_encrypted_cold_resume. Create a fresh TerminalComplaintWorkspaceService(root_dir=tmp_path), call initialize_private_keys(protection="passphrase", passphrase=an authored test value), ensure_private_case_key, and bind the test CLI service to that owned instance. Use an explicit synthetic observed-router transport or persisted local-only policy, never discovery of a real provider. Invoke real chat with bounded input/max_turns, inspect its public session/projection, and create a fresh service for encrypted resume. Keep this task to tests/test_cimp_mgnd_01.py and docs/task_boards/complaint_mediator_grounding_baseline_receipt.json. Do not edit the pre-existing audit JSON, product modules, old tests, spec, plan or boards.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> First task only: demonstrate the real public control path and write an honest baseline. Reuse the existing terminal/private fixture patterns. The prior two synthetic passes are historical starting evidence, not this task's completion.
>
> Exact starting pointers: read only applications/complaint_cli.py:TerminalComplaintWorkspaceService/chat, applications/complaint_workspace.py:ComplaintWorkspaceService.run_intake_chat_turn/apply_shared_interview, mediator/workflow_service.py:_inquiry_from_question/export_session_projection, and the synthetic fixture patterns in tests/test_tui_interview_acceptance.py:_block_network_and_provider_subprocesses/_service plus tests/test_tui_router_trace.py:terminal_service/test_actual_shared_cli_saves_invocation_with_encrypted_cold_resume. Create a fresh TerminalComplaintWorkspaceService(root_dir=tmp_path), call initialize_private_keys(protection="passphrase", passphrase=an authored test value), ensure_private_case_key, and bind the test CLI service to that owned instance. Use an explicit synthetic observed-router transport or persisted local-only policy, never discovery of a real provider. Invoke real chat with bounded input/max_turns, inspect its public session/projection, and create a fresh service for encrypted resume. Keep this task to tests/test_cimp_mgnd_01.py and docs/task_boards/complaint_mediator_grounding_baseline_receipt.json. Do not edit the pre-existing audit JSON, product modules, old tests, spec, plan or boards.

## CIMP-MGND-02 Probe declared current SDK owner capabilities

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.baseline
- Subgoal: subgoal.mgnd.baseline.owners
- Depends on: CIMP-MGND-01
- Outputs: integrations/ipfs_datasets/capabilities.py, integrations/ipfs_datasets/loader.py, docs/task_boards/complaint_mediator_grounding_owner_inventory.json, tests/test_cimp_mgnd_02.py
- Submodules: external/ipfs_accelerate_py, external/ipfs_datasets_py, external/ipfs_kit_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_02.py --run-llm --run-network --run-heavy
- Acceptance: Record exact checked-out A/Data/Kit identities and canonical source paths for the APIs named in this specification; distinguish committed opaque gitlinks from populated checkouts. Probe a bounded actual invocation for the selected KG/legal/logic/private-storage seams, not merely module import; unavailable optional paths yield typed records without installing dependencies. Record enhanced feature flags and the actually enabled path. No global enable-all change, Wikipedia enrichment, model setup, scraping or network call is allowed. Treat the new Data training/definition owners as conditional source or engineering capabilities, never semantic or proof authority. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Use a compact explicit owner table and tiny authored inputs. This inventory augments existing capability metadata; do not redesign discovery or crawl source trees.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Use a compact explicit owner table and tiny authored inputs. This inventory augments existing capability metadata; do not redesign discovery or crawl source trees.

## CIMP-MGND-03 Specify factual, legal, support and proof roles

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.baseline
- Subgoal: subgoal.mgnd.baseline.owners
- Depends on: CIMP-MGND-01, CIMP-MGND-02
- Outputs: mediator/integrations/contracts.py, docs/task_boards/complaint_mediator_grounding_contracts.md, tests/test_cimp_mgnd_03.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_03.py --run-llm --run-network --run-heavy
- Acceptance: Define a versioned contract separating user assertions, extracted candidates, retrieved public law, applicable requirements, corroborating evidence, conditional IR and actual proof results. Carry owner/case/source/version/span/hash and graph revision references without turning user statements or retrieval scores into governing law. Preserve old assertion, dependency and stop contracts; this is a small explicit integration contract, not replacement graphs or a new supervisor framework. Examples reject spoofed verified/satisfied flags and preserve unknown source, edition, applicability and meaning decisions. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Document and type only the new cross-hook handoff fields needed by this campaign. Existing source admission and immutable assertion envelopes remain authoritative.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Document and type only the new cross-hook handoff fields needed by this campaign. Existing source admission and immutable assertion envelopes remain authoritative.

## CIMP-MGND-04 Build reusable guarded synthetic case fixtures

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.baseline
- Subgoal: subgoal.mgnd.baseline.owners
- Depends on: CIMP-MGND-01, CIMP-MGND-03
- Outputs: tests/mgnd_fixtures.py, tests/test_cimp_mgnd_04.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_04.py --run-llm --run-network --run-heavy
- Acceptance: Provide a small set of authored narratives, complete public-law source bytes, dates/jurisdictions and evidence markers for later focused modules. Fixtures create all session/key/index/receipt paths under their private temporary root; block provider executables and remote sockets while preserving subprocess class interfaces. Expose real public service/terminal factories and genuine source-record admission helpers; never seed a satisfied legal graph, FakeBackend state or fabricated Native completion. Fixtures label missing-authority, contradiction, unknown, cancellation and storage-outage cases without pretending a fake transport is a live route observation. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Keep fixtures small and importable by the new modules. No real sessions or global backend mutation survives teardown.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Keep fixtures small and importable by the new modules. No real sessions or global backend mutation survives teardown.

## CIMP-MGND-05 Bind new hook execution contexts to current case revisions

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.hooks
- Subgoal: subgoal.mgnd.hooks.context
- Depends on: CIMP-MGND-03, CIMP-MGND-04
- Outputs: mediator/hook_runtime.py, mediator/mediator.py, tests/test_cimp_mgnd_05.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_05.py --run-llm --run-network --run-heavy
- Acceptance: Add a small host-owned context for the newly activated legal/evidence operations: operation id, owner/case/session, graph revision, legal-context identity, consent/purpose and deadline. Reject wrong case, stale revision, missing purpose and changed source/context bindings before effectful dispatch. Reuse existing intake request/revision/consent checks; do not force legacy callers onto unreviewed new behavior. Context/public receipts contain opaque identifiers and hashes, not private prompts, raw source passages or keys. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Implement the context value/validation seam only; no legal search, evidence publication or provider call yet.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Implement the context value/validation seam only; no legal search, evidence publication or provider call yet.

## CIMP-MGND-06 Declare typed legal and evidence hook operations

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.hooks
- Subgoal: subgoal.mgnd.hooks.context
- Depends on: CIMP-MGND-05
- Outputs: mediator/hook_runtime.py, mediator/workflow_service.py, tests/test_cimp_mgnd_06.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_06.py --run-llm --run-network --run-heavy
- Acceptance: This task declares schemas, operation registry and disabled handler bindings only. Effectful acquisition/ingestion/refresh must refuse until the persisted operation consent and encrypted private artifact/index prerequisites are implemented and verified; registration alone never enables dispatch or writes. Negative tests prove no provider/backend/storage action on registration, missing consent, unavailable key/private store, or an unready derived-index boundary. Define bounded request/result schemas for acquire_legal_sources, ingest_private_evidence and refresh_grounding alongside the existing extraction/question roles. Each result declares candidate/source/support/proof status explicitly with bounded source references; unknown or extra effect-bearing fields fail closed. Only host-owned targets may be selected; a model cannot supply arbitrary tools, destinations, file paths, provider commands or satisfied-node edits. An operation registry maps to existing canonical owners with declared prerequisites and no implicit unbounded chain. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Add a narrow dispatcher for these three operations only. Keep model proposals separate from host-authorized execution.  This is the early contract/registry seam, not activation: keep effectful handlers disabled or returning typed prerequisite-unavailable until the later consent and encrypted storage/index tasks are satisfied. Do not dispatch or persist case data in this task.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Add a narrow dispatcher for these three operations only. Keep model proposals separate from host-authorized execution.
>
> This is the early contract/registry seam, not activation: keep effectful handlers disabled or returning typed prerequisite-unavailable until the later consent and encrypted storage/index tasks are satisfied. Do not dispatch or persist case data in this task.

## CIMP-MGND-07 Record bounded sanitized hook outcomes

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.hooks
- Subgoal: subgoal.mgnd.hooks.trace
- Depends on: CIMP-MGND-06
- Outputs: mediator/hook_runtime.py, mediator/mediator.py, tests/test_cimp_mgnd_07.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_07.py --run-llm --run-network --run-heavy
- Acceptance: Record ordered operation/request/revision/outcome receipts for successful, empty, denied, malformed, timeout, cancelled and unavailable results. Preserve empty source search versus source failure versus rejected admission; no generic success receipt hides a failed stage. Use safe error codes/types and bounded counts; adversarial error text containing fixture secrets is not logged or returned publicly. No fallback provider, retry loop or raw private content is introduced by diagnostics. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Connect the new dispatcher outcome records to existing sanitized mediator/router logs, without logging tool payloads.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Connect the new dispatcher outcome records to existing sanitized mediator/router logs, without logging tool payloads.

## CIMP-MGND-08 Make hook effects replay-safe and graph-bound

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.hooks
- Subgoal: subgoal.mgnd.hooks.trace
- Depends on: CIMP-MGND-07
- Outputs: mediator/hook_runtime.py, mediator/workflow_service.py, tests/test_cimp_mgnd_08.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_08.py --run-llm --run-network --run-heavy
- Acceptance: Bind effect receipts to current source/context preimages and accepted graph revisions. Identical replay returns the same accepted result without duplicate source/evidence/support records; changed preimages or stale graph revisions are refused. A late cancelled/stale result cannot mutate the current graph, pending inquiry or saved case. Record candidate acquisition separately from admitted source/graph effect; receipt existence alone is not durability or proof. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Implement idempotent operation acceptance using existing transaction/revision owners; do not create a second session database.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Implement idempotent operation acceptance using existing transaction/revision owners; do not create a second session database.

## CIMP-MGND-09 Connect declared KG extraction to factual candidate roles

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.facts
- Subgoal: subgoal.mgnd.facts.extraction
- Depends on: CIMP-MGND-02, CIMP-MGND-05, CIMP-MGND-28
- Outputs: integrations/ipfs_datasets/graphs.py, complaint_phases/knowledge_graph.py, tests/test_cimp_mgnd_09.py
- Submodules: external/ipfs_datasets_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_09.py --run-llm --run-network --run-heavy
- Acceptance: Exercise the actual selected Data KnowledgeGraphExtractor path on authored text with external enrichment/model auto-download disabled. Preserve local extraction fallback/unavailable provenance; schema-valid model/extractor output remains a candidate until exact user-source binding is checked. Do not promote legal text, retrieved graph claims or Wikidata/Wikipedia facts to user assertions. Record which enabled path ran; generic import availability does not count as the extractor executing. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Reuse prepare_private_extraction and the current Data KG owner. Make only the missing role/provenance handoff changes.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Reuse prepare_private_extraction and the current Data KG owner. Make only the missing role/provenance handoff changes.

## CIMP-MGND-10 Preserve exact factual source spans and assertion identity

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.facts
- Subgoal: subgoal.mgnd.facts.extraction
- Depends on: CIMP-MGND-09
- Outputs: complaint_phases/knowledge_graph.py, integrations/ipfs_datasets/types.py, tests/test_cimp_mgnd_10.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_10.py --run-llm --run-network --run-heavy
- Acceptance: Carry exact source bytes/hash, source kind, message/answer identity and UTF-8 spans for accepted facts and relationships. Cover non-ASCII, repeated phrases, unknown/refused answers, and a legal passage presented as narrative; missing/conflicting spans remain deficient. Preserve record distinctions between user fact, extraction hypothesis, relationship and supporting evidence. Do not repair an unbound source using a model claim or silently normalize offsets into a different source generation. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Extend existing user_assertion.v1 envelope use at the real hook boundaries; avoid a parallel provenance schema.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Extend existing user_assertion.v1 envelope use at the real hook boundaries; avoid a parallel provenance schema.

## CIMP-MGND-11 Expose a revision-safe public factual correction operation

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.facts
- Subgoal: subgoal.mgnd.facts.correction
- Depends on: CIMP-MGND-08, CIMP-MGND-10
- Outputs: mediator/workflow_service.py, mediator/mediator.py, tests/test_cimp_mgnd_11.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_11.py --run-llm --run-network --run-heavy
- Acceptance: Add the missing public correction handoff to existing process_denoising_answer factual_action/supersedes machinery with stable assertion/event ids. Reject missing, cross-case or stale targets; replay of the same correction event is idempotent. Retain original and replacement source envelopes and explicit supersession/retraction lineage; do not overwrite old factual evidence. Return the actual new graph/session revisions and affected support targets rather than a display-only edit. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Use existing KG supersede_assertion/retract_assertion and mediator transition code. Do not implement another correction engine.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Use existing KG supersede_assertion/retract_assertion and mediator transition code. Do not implement another correction engine.

## CIMP-MGND-12 Route terminal edit through canonical graph correction

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.facts
- Subgoal: subgoal.mgnd.facts.correction
- Depends on: CIMP-MGND-11
- Outputs: applications/complaint_cli.py, applications/complaint_workspace.py, tests/test_cimp_mgnd_12.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_12.py --run-llm --run-network --run-heavy
- Acceptance: Replace the display/history-only /edit path with the public correction operation for the last eligible accepted answer, bound to its stable source target. Actual chat /edit changes the shared factual graph and corresponding revision while preserving old assertion/history records. Preserve an unrelated pending question; reopen/reselect it only when its bound target is affected. Stale concurrent edits are refused. Encrypted cold resume sees the corrected graph and original audit lineage, not mismatched intake_answers and shared_interview state. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Fix the concrete _apply_edit/control-loop wiring gap. Original terminal controls and privacy prompts remain usable.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Fix the concrete _apply_edit/control-loop wiring gap. Original terminal controls and privacy prompts remain usable.

## CIMP-MGND-13 Invalidate factual dependents without promoting retrieval nominations

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.facts
- Subgoal: subgoal.mgnd.facts.revision
- Depends on: CIMP-MGND-11
- Outputs: complaint_phases/knowledge_graph.py, complaint_phases/dependency_graph.py, mediator/integrations/graph_tools.py, tests/test_cimp_mgnd_13.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_13.py --run-llm --run-network --run-heavy
- Acceptance: Superseding/retracting a fact invalidates only dependent support/proof-cache references and reopens the affected inquiry targets. GraphRetrievalAugmentor supports_claims/retrieval confidence stays a candidate nomination until exact claim/requirement/source-span binding is rechecked. Unrelated graph identities and support remain stable; contradictory facts remain visible without becoming satisfied legal requirements. Evidence supports factual allegations without changing the governing legal requirement text or source identity. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Reuse existing invalidate_dependents and epistemic support builders. Scope the fix to the nomination-to-support handoff.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Reuse existing invalidate_dependents and epistemic support builders. Scope the fix to the nomination-to-support handoff.

## CIMP-MGND-14 Persist factual revisions through canonical private graph artifacts

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.facts
- Subgoal: subgoal.mgnd.facts.revision
- Depends on: CIMP-MGND-10, CIMP-MGND-13
- Outputs: integrations/ipfs_datasets/graphs.py, applications/complaint_workspace.py, tests/test_cimp_mgnd_14.py
- Submodules: external/ipfs_datasets_py, external/ipfs_kit_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_14.py --run-llm --run-network --run-heavy
- Acceptance: Persist factual graph/revision provenance through the existing automatic-private-artifact owner and reload it under the same owner/case binding. Ciphertext storage ids are distinct from plaintext source/assertion ids; no plaintext CID, cache or JSON fallback is allowed. Wrong key/case/corrupt bytes fail without overwriting the last committed graph. Actual roundtrip preserves assertion states, relationships, invalidations and unresolved conflicts. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Wire the factual graph artifact into the existing encrypted case transaction, not a second graph store.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Wire the factual graph artifact into the existing encrypted case transaction, not a second graph store.

## CIMP-MGND-15 Bind acquisition plans to explicit legal context

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.law
- Subgoal: subgoal.mgnd.law.acquisition
- Depends on: CIMP-MGND-03, CIMP-MGND-06
- Outputs: integrations/ipfs_datasets/legal.py, mediator/mediator.py, tests/test_cimp_mgnd_15.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_15.py --run-llm --run-network --run-heavy
- Acceptance: Build a bounded legal acquisition request only after explicit jurisdiction, applicable-law date and claim candidate selection. Unknown/ambiguous jurisdiction, uncertain date or unsupported claim produces a targeted inquiry and no guessed jurisdiction/corpus default. Separate event, applicable-law, filing-reference and retrieval dates; a law-query date cannot satisfy a factual chronology gap. Requests carry claim/requirement targets and public-law query terms; raw case narrative is not needed to fetch a citation. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Reuse intake_legal_selection, legal_context_questions and existing corpus program contracts; do not add heuristic governing law.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Reuse intake_legal_selection, legal_context_questions and existing corpus program contracts; do not add heuristic governing law.

## CIMP-MGND-16 Acquire bounded canonical legal-source candidates

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.law
- Subgoal: subgoal.mgnd.law.acquisition
- Depends on: CIMP-MGND-15, CIMP-MGND-28
- Outputs: integrations/ipfs_datasets/legal.py, mediator/legal_authority_hooks.py, tests/test_cimp_mgnd_16.py
- Submodules: external/ipfs_datasets_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_16.py --run-llm --run-network --run-heavy
- Acceptance: Use the declared Data local/corpus parameter APIs with explicit context, per-operation deadline/result/byte bounds and allowed backends. Local-first acquisition can work without model inference; remote acquisition must pass the purpose/data-class gate before dispatch. Return complete owned source text/locator/version/retrieval provenance as candidates; search hit/snippet/relevance alone is not applicability or proof. Empty, unavailable, timeout and missing-edition results remain distinct and resumable; do not initialize CommonCrawl or download corpora. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Connect existing search_us_code_corpus_from_parameters, search_state_law_corpus_from_parameters, search_federal_register_corpus_from_parameters and search_court_rules_corpus_from_parameters as declared by actual capability inventory.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Connect existing search_us_code_corpus_from_parameters, search_state_law_corpus_from_parameters, search_federal_register_corpus_from_parameters and search_court_rules_corpus_from_parameters as declared by actual capability inventory.

## CIMP-MGND-17 Admit acquired authorities through stored source records

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.law
- Subgoal: subgoal.mgnd.law.admission
- Depends on: CIMP-MGND-08, CIMP-MGND-16, CIMP-MGND-32
- Outputs: mediator/legal_authority_hooks.py, mediator/mediator.py, integrations/ipfs_datasets/logic.py, tests/test_cimp_mgnd_17.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_17.py --run-llm --run-network --run-heavy
- Acceptance: Pass acquired candidates through canonical source storage/admission and _collect_verified_legal_requirements before adding legal dependency nodes. Recompute source/authority/span hashes from owned bytes and preserve authority version, jurisdiction/date and source locator. Reject caller verified/applicable/support_eligible flags, independently substituted metadata text and model-invented citations. Record acquisition and admission as separate outcomes; legal-source absence leaves a nonempty unresolved dependency graph. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Reuse add_authority/upsert_authority, extract_source_bound_rule_candidates and existing source-record bounds. Do not seed legal nodes or replace source admission.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Reuse add_authority/upsert_authority, extract_source_bound_rule_candidates and existing source-record bounds. Do not seed legal nodes or replace source admission.

## CIMP-MGND-18 Preserve legal editions and adverse treatment across acquisition

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.law
- Subgoal: subgoal.mgnd.law.admission
- Depends on: CIMP-MGND-17
- Outputs: integrations/ipfs_datasets/legal.py, complaint_phases/legal_graph.py, complaint_phases/dependency_graph.py, tests/test_cimp_mgnd_18.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_18.py --run-llm --run-network --run-heavy
- Acceptance: Admit only the selected edition/effective interval for the explicit legal context; overlapping/unknown versions remain unresolved. Retain treatment records from canonical and metadata layers; adverse/superseding/repealing treatment cannot be erased by an empty alias. Do not replace retrieval time with applicable-law time or mix two versions sharing an authority id. A changed treatment/version invalidates affected legal support without modifying user facts. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Extend the newly acquired-source handoff only, using existing temporal/treatment validators.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Extend the newly acquired-source handoff only, using existing temporal/treatment validators.

## CIMP-MGND-19 Expose a public legal-research action in the terminal workflow

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.law
- Subgoal: subgoal.mgnd.law.refresh
- Depends on: CIMP-MGND-17, CIMP-MGND-28, CIMP-MGND-31
- Outputs: applications/complaint_cli.py, applications/complaint_workspace.py, mediator/workflow_service.py, tests/test_cimp_mgnd_19.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_19.py --run-llm --run-network --run-heavy
- Acceptance: Add a deliberate terminal/service legal-research action for the current source gap; it is not stored as a factual answer. Invoke the typed bounded acquisition/admission operation through the same authorized private case transaction. Show retrieved/admitted/rejected/unavailable counts and a resumable next action without saying that research proves the complaint. Do not research automatically on every status/resume command or dispatch duplicate work when the action is replayed. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Close the missing public stored-authority acquisition path. Choose one concise control and document it; preserve existing chat invocation and controls.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Close the missing public stored-authority acquisition path. Choose one concise control and document it; preserve existing chat invocation and controls.

## CIMP-MGND-20 Refresh current legal dependencies after source or context changes

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.law
- Subgoal: subgoal.mgnd.law.refresh
- Depends on: CIMP-MGND-18, CIMP-MGND-19
- Outputs: mediator/mediator.py, complaint_phases/dependency_graph.py, applications/complaint_workspace.py, tests/test_cimp_mgnd_20.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_20.py --run-llm --run-network --run-heavy
- Acceptance: After admitted acquisition, jurisdiction/date/version/treatment change or source outage, call refresh_verified_legal_dependencies and re-read current source admission. Preserve unaffected nodes and user facts; invalidate/recompute affected requirements, support/proof identities and question targets. Source outage after a previously available source cannot leave satisfied stale law or replace the whole graph with success-empty. Exercise this through the public service inquiry/research flow rather than a manually classified or satisfied fixture graph. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Connect source/context effect receipts to the existing reconciliation owner with one atomic case revision.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Connect source/context effect receipts to the existing reconciliation owner with one atomic case revision.

## CIMP-MGND-21 Carry admitted source identities into canonical LegalIR stages

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: goal.mgnd.formal
- Subgoal: subgoal.mgnd.formal.ir
- Depends on: CIMP-MGND-17
- Outputs: integrations/ipfs_datasets/logic.py, mediator/mediator.py, tests/test_cimp_mgnd_21.py
- Submodules: external/ipfs_datasets_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_21.py --run-llm --run-network --run-heavy
- Acceptance: Build current source-bound compiler requests from admitted law and separately bound factual premises using compile_canonical_legal_ir. Retain parse/elaboration/formalization/bridge/source-map identities and unresolved assumptions; preserve UTF-8 source correspondence. Malformed/unsupported input or absent compiler capability yields typed unavailable/failed stage evidence, not a fabricated IR success. Emitted formal text or a compilable AST does not establish governing-law meaning or prove a claim. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Wire the mediator handoff to the existing canonical compiler pipeline and source maps; do not reimplement the compiler.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Wire the mediator handoff to the existing canonical compiler pipeline and source maps; do not reimplement the compiler.

## CIMP-MGND-22 Attach current source-sampling context and contextual definition evidence

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: goal.mgnd.formal
- Subgoal: subgoal.mgnd.formal.definitions
- Depends on: CIMP-MGND-21
- Outputs: integrations/ipfs_datasets/definition_evidence.py, tests/test_cimp_mgnd_22.py
- Submodules: external/ipfs_datasets_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_22.py --run-llm --run-network --run-heavy
- Acceptance: Add a thin first-party adapter to legal_source_sampling_review_context.prepare/validate/record_response/validate_response/summarize and contextual definition binding/review prepare/validate owners. Bind whole source/context/attachment populations and explicit declaration/request hashes; no copied historical artifact implementation. Preserve separate candidate, source review and meaning review states, including unreviewed supporting sources. Context preparation/replay grants no applicability, truth, training, graph or proof authority. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Implement only the context/binding adapter with tiny authored inputs and actual owner validators.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Implement only the context/binding adapter with tiny authored inputs and actual owner validators.

## CIMP-MGND-23 Bind norm definitions and scope correspondence to source evidence

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: goal.mgnd.formal
- Subgoal: subgoal.mgnd.formal.definitions
- Depends on: CIMP-MGND-22
- Outputs: integrations/ipfs_datasets/definition_evidence.py, mediator/claim_support_hooks.py, tests/test_cimp_mgnd_23.py
- Submodules: external/ipfs_datasets_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_23.py --run-llm --run-network --run-heavy
- Acceptance: Use legal_norm_definition_evidence_v1.prepare_norm_definition_evidence_v1/validate_norm_definition_evidence_v1 and legal_norm_scope_correspondence_v1.prepare_norm_scope_correspondence_v1/validate_norm_scope_correspondence_v1. Preserve occurrence/span/entity/edition identities and distinguish a governing definition from two separate asserted uses. Conflicting or absent definition/scope evidence remains an explicit unresolved dependency rather than a model-filled binding. Forward conditional evidence to the relevant requirement without changing the admitted legal text or satisfying its proof. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Add only source-bound definition/scope records and links using the current Data owners.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Add only source-bound definition/scope records and links using the current Data owners.

## CIMP-MGND-24 Preserve independent norm review and bound-variable decisions

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: goal.mgnd.formal
- Subgoal: subgoal.mgnd.formal.definitions
- Depends on: CIMP-MGND-23
- Outputs: integrations/ipfs_datasets/definition_evidence.py, mediator/claim_support_hooks.py, tests/test_cimp_mgnd_24.py
- Submodules: external/ipfs_datasets_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_24.py --run-llm --run-network --run-heavy
- Acceptance: Use legal_norm_interpretation_review_v1 prepare_norm_review_evidence_v1/build_norm_review_subject_v1/assess_norm_reviews_v1/validate_norm_review_assessment_v1 and legal_bound_variable_definition_v1 prepare/validate APIs. Keep source/edition/meaning/context permissions independent; unsigned or unprovided reviews cannot be synthesized by Grok or a fixture. Retain alternatives, explicit assumptions and bound-variable carrier/scope correspondence under source-pinned hashes. Generated conditional Lean remains unbuilt/unproved unless an actual declared prover result exists. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Reuse exact current review/variable owners. Test their negative authority boundary as well as tiny valid conditional envelopes.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Reuse exact current review/variable owners. Test their negative authority boundary as well as tiny valid conditional envelopes.

## CIMP-MGND-25 Connect proof obligations and truthful available/unavailable outcomes

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: goal.mgnd.formal
- Subgoal: subgoal.mgnd.formal.proof
- Depends on: CIMP-MGND-21, CIMP-MGND-24
- Outputs: integrations/ipfs_datasets/logic.py, mediator/claim_support_hooks.py, complaint_phases/dependency_graph.py, tests/test_cimp_mgnd_25.py
- Submodules: external/ipfs_datasets_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_25.py --run-llm --run-network --run-heavy
- Acceptance: Use generate_bound_legal_ir_proof_obligations and route_bound_legal_ir_proof with exact current source, premise, requirement and assumption identities. Preserve proved/disproved/unknown/timeout/unavailable/cancelled distinctions; no solver, generated Lean or review packet becomes a proved result. Only an actual verified proof result with matching current bindings may support the corresponding proof field; factual assertion and legal sufficiency remain separate. Changing a premise/definition/source or adverse treatment invalidates replay_satisfied_element_proof/proof_cache_identity. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Connect existing proof owners to the new definition handoff; no external prover install, network service or fake proof receipt.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Connect existing proof owners to the new definition handoff; no external prover install, network service or fake proof receipt.

## CIMP-MGND-26 Gate qualified model outputs as candidates rather than authority

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: goal.mgnd.formal
- Subgoal: subgoal.mgnd.formal.proof
- Depends on: CIMP-MGND-02, CIMP-MGND-25
- Outputs: integrations/ipfs_datasets/definition_evidence.py, integrations/ipfs_datasets/logic.py, tests/test_cimp_mgnd_26.py
- Submodules: external/ipfs_datasets_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_26.py --run-llm --run-network --run-heavy
- Acceptance: Describe optional legal_compact_content_persistent_v1 load/score and predicate_training_v1.inspect/checkpoint identity using exact qualified source-space/conditioning/policy/checkpoint metadata. Predicate objective/training preparation and numerical qualification are engineering evidence; candidate output cannot select governing law, satisfy a definition review or prove an element. Missing/incompatible model/checkpoint/runtime yields an asserted unavailable/ineligible result with zero required skips. No train_compact_content_persistent_v1, training, optimizer, model download, restore or numerical fit is run by mandatory development checks. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Provide a small eligibility/provenance adapter for the newly published owners, using metadata/negative controls. Do not start a modeling programme.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Provide a small eligibility/provenance adapter for the newly published owners, using metadata/negative controls. Do not start a modeling programme.

## CIMP-MGND-27 Declare Grok inference purposes at the hook boundary

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.router
- Subgoal: subgoal.mgnd.router.purpose
- Depends on: CIMP-MGND-02, CIMP-MGND-05
- Outputs: mediator/hook_runtime.py, integrations/ipfs_datasets/llm.py, backends/llm_router_backend.py, tests/test_cimp_mgnd_27.py
- Submodules: external/ipfs_accelerate_py, external/ipfs_datasets_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_27.py --run-llm --run-network --run-heavy
- Acceptance: Pin inference owner ipfs_accelerate_py.llm_router, provider grok_cli and model grok-4.7 with local/cross-provider fallback disabled. Declare extraction, question proposal and any new explanation/candidate purpose with bounded allowed inputs/outputs; model proposals cannot invoke tools or mark requirements satisfied. Local extraction, citation acquisition and deterministic source/graph checks do not cause an unnecessary model dispatch. Route diagnostics distinguish requested/selected/observed identity; a synthetic transport never verifies live model/build identity. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Extend the existing purpose/typed intake boundary, not a new LLM client.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Extend the existing purpose/typed intake boundary, not a new LLM client.

## CIMP-MGND-28 Apply per-case consent and minimization to all new remote operations

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.router
- Subgoal: subgoal.mgnd.router.purpose
- Depends on: CIMP-MGND-27
- Outputs: mediator/hook_runtime.py, integrations/ipfs_datasets/llm.py, applications/complaint_workspace.py, tests/test_cimp_mgnd_28.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_28.py --run-llm --run-network --run-heavy
- Acceptance: Read persisted owner/case policy before loading any remote provider or submitting a new hook query. Consent for Grok raw-intake processing does not silently authorize unrelated web/archive providers, tools or case data classes. Minimize purpose-specific prompts/queries and preserve local-private mode; unknown/missing consent refuses effectful remote dispatch. Revocation is rechecked before accepting late results, and a different case cannot reuse consent or invocation binding. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Reuse existing policy/context builders and revocation tests. Distinguish public-law citation-only queries from private facts rather than copying the whole complaint into search.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Reuse existing policy/context builders and revocation tests. Distinguish public-law citation-only queries from private facts rather than copying the whole complaint into search.

## CIMP-MGND-29 Preserve observed route identity and bounded cancellation

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.router
- Subgoal: subgoal.mgnd.router.observations
- Depends on: CIMP-MGND-07, CIMP-MGND-27
- Outputs: backends/llm_router_backend.py, integrations/ipfs_datasets/llm.py, mediator/hook_runtime.py, tests/test_cimp_mgnd_29.py
- Submodules: external/ipfs_accelerate_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_29.py --run-llm --run-network --run-heavy
- Acceptance: Use the current Native observed generation/capture seam, with no fallback/substitution and denied tool execution, for new hook purposes. Timeout/cancellation/quota/malformed output produces bounded safe receipts and leaves the pending case revision recoverable. Cancellation reaps only the owned child before returning; a late answer cannot be accepted after revocation/revision change. Required tests use explicit fake observation types and real process ownership fixtures; they make no live Grok claim. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Extend current cancellation/observation bindings narrowly for hook requests; preserve the qualified default Native constructor and resource owners.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Extend current cancellation/observation bindings narrowly for hook requests; preserve the qualified default Native constructor and resource owners.

## CIMP-MGND-30 Persist private invocation associations without replay dispatch

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.router
- Subgoal: subgoal.mgnd.router.observations
- Depends on: CIMP-MGND-08, CIMP-MGND-28, CIMP-MGND-29
- Outputs: applications/complaint_cli.py, applications/complaint_workspace.py, mediator/hook_runtime.py, tests/test_cimp_mgnd_30.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_30.py --run-llm --run-network --run-heavy
- Acceptance: Associate each real/fake-labeled invocation receipt with purpose, request, case/session and accepted graph revision in the encrypted transaction. Cold resume and /status preserve existing associations without inventing an invocation or rerunning provider work. Receipts are bounded and sanitized; fixture prompts, law passages, keys, environment values and native tool arguments do not leak publicly. Duplicate progress-display/receipt handling cannot repeat a provider call. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Reuse existing router_trace persistence; add only the new operation association fields.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Reuse existing router_trace persistence; add only the new operation association fields.

## CIMP-MGND-31 Route private evidence hook bytes through encrypted storage

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.storage
- Subgoal: subgoal.mgnd.storage.hooks
- Depends on: CIMP-MGND-05, CIMP-MGND-28
- Outputs: mediator/evidence_hooks.py, integrations/ipfs_datasets/storage.py, applications/complaint_workspace.py, tests/test_cimp_mgnd_31.py
- Submodules: external/ipfs_kit_py, external/ipfs_datasets_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_31.py --run-llm --run-network --run-heavy
- Acceptance: Before enabling new public evidence ingestion, pass private bytes through store_automatic_private_artifact/store_private_artifact and expected owner/case/key bindings. Legacy EvidenceStorageHook raw add_bytes is not used for private evidence; public legal corpora remain explicitly public and separate. Ciphertext is produced before public hash/cache/pin/index/replica operations; missing key/storage failure never writes plaintext or a simulated durable CID. Real encrypted roundtrip and wrong-key/case controls preserve provenance without treating local deterministic ids as remote durability. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Inject the existing private artifact context into newly activated hook paths. Do not replace the Kit encryption owner.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Inject the existing private artifact context into newly activated hook paths. Do not replace the Kit encryption owner.

## CIMP-MGND-32 Contain private derived hook indexes and caches

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.storage
- Subgoal: subgoal.mgnd.storage.hooks
- Depends on: CIMP-MGND-31
- Outputs: mediator/evidence_hooks.py, mediator/claim_support_hooks.py, mediator/legal_authority_hooks.py, applications/complaint_workspace.py, tests/test_cimp_mgnd_32.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_32.py --run-llm --run-network --run-heavy
- Acceptance: Audit only newly created synthetic hook database rows and route private derived text/indexes to an encrypted durable owner or owned ephemeral rebuildable index. Owner/case-local interview-db naming and mode bits alone are not claimed as encryption; prevent persistent plaintext private facts/previews in the enabled path. Index rebuild/close/crash behavior is bounded and cannot publish plaintext fallback files or mix two cases. Separate public-law source cache from private support/claim associations and preserve honest persistence-unavailable results. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Scope changes to constructor/storage lifecycle and selected private columns, not a rewrite of all hook query code.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Scope changes to constructor/storage lifecycle and selected private columns, not a rewrite of all hook query code.

## CIMP-MGND-33 Migrate explicitly selected legacy hook artifacts safely

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.storage
- Subgoal: subgoal.mgnd.storage.migration
- Depends on: CIMP-MGND-31, CIMP-MGND-32
- Outputs: integrations/private_storage.py, applications/complaint_workspace.py, tests/test_cimp_mgnd_33.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_33.py --run-llm --run-network --run-heavy
- Acceptance: Expose an explicit single-case migration preflight/commit for synthetic legacy private hook artifacts with source preimage and destination bindings. No automatic scan, import or rewrite of existing sessions, user trees, campaign artifacts or historical qualifiers is allowed. Interrupted/wrong-key/corrupt/aliased-source migration preserves original bytes and last valid encrypted head; plaintext retirement occurs only after verified commit under the selected retention policy. Migration receipt says what was encrypted or remains pending; mode changes or a local copy do not establish encryption/durability. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Reuse existing legacy-session migration and retention owners for one declared artifact class; no broad disk discovery.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Reuse existing legacy-session migration and retention owners for one declared artifact class; no broad disk discovery.

## CIMP-MGND-34 Commit complete grounded snapshots atomically

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.storage
- Subgoal: subgoal.mgnd.storage.durability
- Depends on: CIMP-MGND-14, CIMP-MGND-26, CIMP-MGND-30, CIMP-MGND-32
- Outputs: applications/complaint_workspace.py, integrations/ipfs_datasets/storage.py, tests/test_cimp_mgnd_34.py
- Submodules: external/ipfs_kit_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_34.py --run-llm --run-network --run-heavy
- Acceptance: Include current factual/legal graph revisions, source references, conditional IR/proof statuses, hook receipts, pending inquiry and stop policy in one canonical encrypted snapshot transaction. Expected-revision conflict, interrupted write or corrupted candidate does not replace the prior readable head. Cold read preserves exact source/graph/receipt bindings without reextracting narrative or replaying hooks/model calls. Declare external public-law/ephemeral-index dependencies honestly; snapshot existence does not claim all remote replicas exist. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Extend assemble/persist/load interview snapshot using current owners and bounded schemas.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Extend assemble/persist/load interview snapshot using current owners and bounded schemas.

## CIMP-MGND-35 Verify encrypted replica durability and restore bindings

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.storage
- Subgoal: subgoal.mgnd.storage.durability
- Depends on: CIMP-MGND-34
- Outputs: integrations/ipfs_datasets/storage.py, applications/complaint_workspace.py, tests/test_cimp_mgnd_35.py
- Submodules: external/ipfs_kit_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_35.py --run-llm --run-network --run-heavy
- Acceptance: Use publish_encrypted_replicas/reconcile_encrypted_replicas/restore_encrypted_replicas/restore_encrypted_workspace and count_verified_ciphertext_replicas. Only authenticated ciphertext readback with current object/key/case/version binding counts; acknowledgements, local CIDs and fixture providers are labeled accurately. Offline/corrupt/stale/partial replicas preserve local committed state and truthful unavailable/degraded durability counts. Tests use owned ciphertext-directory fixtures and no live node/provider; live durability remains a separate optional qualification. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Attach existing Kit durability receipts to the complete grounded snapshot; no custom crypto or replication daemon.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Attach existing Kit durability receipts to the complete grounded snapshot; no custom crypto or replication daemon.

## CIMP-MGND-36 Preserve actual inquiry grounding through shared projection

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.interview
- Subgoal: subgoal.mgnd.interview.why
- Depends on: CIMP-MGND-06, CIMP-MGND-10
- Outputs: mediator/workflow_service.py, applications/complaint_workspace.py, tests/test_cimp_mgnd_36.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_36.py --run-llm --run-network --run-heavy
- Acceptance: Carry host-selected objective/target/revision/why/expected-answer/update/source references from the actual question into pending_inquiry and encrypted projection. Do not replace missing objective/target fields with invented ids or model-authored graph references. Actual service /why uses this metadata; repeated /why does not store an answer, alter graph/session revision or dispatch a provider. Cold resume preserves the same explanation and target bindings; legacy thin snapshots receive explicit unknown grounding rather than false restored detail. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Fix the _inquiry_from_question/export_session_projection/public /why metadata gap using the existing renderer and selection contract.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Fix the _inquiry_from_question/export_session_projection/public /why metadata gap using the existing renderer and selection contract.

## CIMP-MGND-37 Render factual versus law-derived question support clearly

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.interview
- Subgoal: subgoal.mgnd.interview.why
- Depends on: CIMP-MGND-20, CIMP-MGND-36
- Outputs: complaint_phases/denoiser.py, applications/complaint_cli.py, applications/complaint_workspace.py, tests/test_cimp_mgnd_37.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_37.py --run-llm --run-network --run-heavy
- Acceptance: Display the current question's factual target separately from the law-derived requirement and admitted authority citation/version/span references. Show user assertion/corroboration/candidate/applicability/proof states without equating them or presenting a retrieval score as proof. Unknown authority, source outage, contradiction and missing definition/review are understandable with a relevant next action. Rendering stays bounded, accessible in narrow ASCII/no-color terminals and does not expose private content in diagnostic receipts. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Extend the existing /why formatter and public payload only where new grounding fields need presentation; do not rebuild a UI.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Extend the existing /why formatter and public payload only where new grounding fields need presentation; do not rebuild a UI.

## CIMP-MGND-38 Offer finite source/evidence next actions without false completion

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.interview
- Subgoal: subgoal.mgnd.interview.handoff
- Depends on: CIMP-MGND-25, CIMP-MGND-37
- Outputs: complaint_phases/denoiser.py, mediator/workflow_service.py, applications/complaint_workspace.py, tests/test_cimp_mgnd_38.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_38.py --run-llm --run-network --run-heavy
- Acceptance: Reuse existing stopping states and target dispositions to distinguish awaiting user, source research, evidence request, review, unavailable provider and no-progress. An empty question pool, plateau, turn cap, skipped/unknown answer or completed hook cannot establish factual/legal/proof/filing sufficiency. When answerable questions saturate but legal/evidence dependencies remain open, publish a concrete authorized research/evidence/review action with bounded attempts and resumable context. Budget/no-progress exhaustion terminates the operation honestly; it does not busy-loop, wait for developer stdin or claim a stalled worker is an awaiting-user session. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Connect new hook outcomes to project_stopping_policy/evaluate_interview_stop rather than adding another stop engine.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Connect new hook outcomes to project_stopping_policy/evaluate_interview_stop rather than adding another stop engine.

## CIMP-MGND-39 Resume corrections and research across real terminal sessions

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.interview
- Subgoal: subgoal.mgnd.interview.resume
- Depends on: CIMP-MGND-12, CIMP-MGND-34, CIMP-MGND-38
- Outputs: applications/complaint_cli.py, applications/complaint_workspace.py, mediator/workflow_service.py, tests/test_cimp_mgnd_39.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_39.py --run-llm --run-network --run-heavy
- Acceptance: Actual chat control flow captures narrative, performs correction/research action, pauses and resumes in a fresh service/process with identical pending inquiry and graph revisions. Preserve old and new factual sources, current legal edition/proof state, consent and operation receipts under encryption. Stale concurrent answer/edit/research requests are rejected without changing the accepted state. EOF/Ctrl-C/quit retain documented exit semantics and a recoverable pending operation without duplicate extraction or dispatch. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Exercise the real public terminal and session service with authored inputs and owned temporary keys.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Exercise the real public terminal and session service with authored inputs and owned temporary keys.

## CIMP-MGND-40 Cover adverse hook and storage outcomes in the public flow

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.interview
- Subgoal: subgoal.mgnd.interview.resume
- Depends on: CIMP-MGND-29, CIMP-MGND-35, CIMP-MGND-39
- Outputs: applications/complaint_workspace.py, mediator/hook_runtime.py, tests/test_cimp_mgnd_40.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_40.py --run-llm --run-network --run-heavy
- Acceptance: Cover malformed/late model proposal, consent revocation, wrong key, legal-source outage, interrupted snapshot and corrupt replica through actual public operations. Each case preserves the last valid graph/head, pending inquiry and safe error code with no fake legal completion. Required operations have bounded deadlines and owned child cleanup; no provider/network or unrelated process is touched. Resume is possible or the exact nonrecoverable boundary is stated; unavailable capability is an asserted outcome, not a skipped case. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Add only focused adverse regressions for newly wired paths using shared guarded fixtures.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Add only focused adverse regressions for newly wired paths using shared guarded fixtures.

## CIMP-MGND-41 Observe the separate campaign without mutating the old 58-task state

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.operations
- Subgoal: subgoal.mgnd.operations.health
- Depends on: CIMP-MGND-02, CIMP-MGND-04
- Outputs: integrations/ipfs_accelerate/improvement_runner.py, integrations/ipfs_accelerate/improvement_plan.py, tests/test_cimp_mgnd_41.py
- Submodules: external/ipfs_accelerate_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_41.py --run-llm --run-network --run-heavy
- Acceptance: Exercise generic campaign artifact selection for this spec/plan/board namespace using isolated synthetic control-plane state and actual public Native read/status seams. Bind health observations to the new plan/CID/source generation and retain old completed 58-task artifacts as immutable historical baseline. Assert pinned Grok4.7 route, implement/resource caps, pool1 and no fallback; no provider starts in tests. Characterization/manual metadata does not grant completion; only genuine accepted Native validation/merge/callback can close tasks. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Root supplies the small campaign-artifacts selector. Add focused tests/integration adjustments only if needed; do not recreate the supervisor or use production campaign state.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Root supplies the small campaign-artifacts selector. Add focused tests/integration adjustments only if needed; do not recreate the supervisor or use production campaign state.

## CIMP-MGND-42 Bound worker health and recovery while preserving legitimate user waits

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.operations
- Subgoal: subgoal.mgnd.operations.health
- Depends on: CIMP-MGND-07, CIMP-MGND-41
- Outputs: integrations/ipfs_accelerate/improvement_runner.py, tests/test_cimp_mgnd_42.py
- Submodules: external/ipfs_accelerate_py
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_42.py --run-llm --run-network --run-heavy
- Acceptance: Report claim/worker/provider/validation/merge liveness separately from application awaiting_user and paused interview states. Use existing Native monitor/recovery owners for typed timeout/stall reconciliation; no claim edits, forced task completion, attempt refunds or silent provider retry. Synthetic recovery test proves bounded observation, preserved accounting/ownership and no duplicate dispatch or leaked children. A worker cannot wait on stdin for the user's complaint or block indefinitely on provider progress. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Extend only campaign-scoped health projection and tests; preserve existing Native constructor, scheduler and cleanup policy.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Extend only campaign-scoped health projection and tests; preserve existing Native constructor, scheduler and cleanup policy.

## CIMP-MGND-43 Prove the new grounded public journey with synthetic source evidence

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.operations
- Subgoal: subgoal.mgnd.operations.acceptance
- Depends on: CIMP-MGND-40, CIMP-MGND-42
- Outputs: tests/mgnd_fixtures.py, tests/test_cimp_mgnd_43.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_43.py --run-llm --run-network --run-heavy
- Acceptance: Use actual chat/service entrypoints for narrative→source-bound factual KG→explicit legal context→source acquisition/admission→dependency refresh→question /why→correction→encrypted cold resume. Assert source spans/versions, separate factual/legal identities, current support/proof outcomes, real graph effects and zero hidden skips. Cover a clean success-to-review path and explicit unknown/contradiction/source-unavailable paths; no manually satisfied nodes or caller classification shortcuts. Run only this bounded acceptance module, not the entire repository or old 83-module release closure; attach current source/test/case/result identities. Fake observed inference and fixture ciphertext providers remain labeled synthetic; no live Grok, numerical training, legal advice or remote durability qualification is claimed. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Write a small nonrecursive end-to-end acceptance module over the integrated new public paths. It is not Native completion authority.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Write a small nonrecursive end-to-end acceptance module over the integrated new public paths. It is not Native completion authority.

## CIMP-MGND-44 Document grounded operations and audit campaign completion honestly

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: goal.mgnd.operations
- Subgoal: subgoal.mgnd.operations.acceptance
- Depends on: CIMP-MGND-24, CIMP-MGND-33, CIMP-MGND-35, CIMP-MGND-43
- Outputs: docs/task_boards/complaint_mediator_grounding_operator_guide.md, docs/task_boards/complaint_mediator_grounding_completion_contract.json, tests/test_cimp_mgnd_44.py
- Submodules:
- Validation: HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q tests/test_cimp_mgnd_44.py --run-llm --run-network --run-heavy
- Acceptance: Document the canonical chat command, consent modes, legal/evidence actions, /why, correction, pause/resume, source/proof limits and encrypted storage/durability distinctions. Define pre-completion versus post-Native-callback audit contracts: this task's validation remains self-pending and never manufactures its own completion. Require the separate new plan's actual accepted task/CID/goal/subgoal evidence and current-source public acceptance; report unavailable/blocked work explicitly. Old 58-task receipts remain historical scoped evidence; do not remap them to new task ids or call this a fresh old-release qualification. Docs and contract tests are small, nonrecursive, source-bound and have no provider/state/publication authority. The focused module collects nonempty meaningful cases and passes with zero required skips using synthetic private fixtures; failures/unavailability remain truthful.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.  Deliver operator guidance and a pure completion-contract evaluator with focused tests. Root performs the actual post-callback audit outside the task; no private campaign reads inside tests.

Implementation instructions:

> Implement only this bounded task in the supplied isolated checkout. Budget: 64 agent turns and 900 seconds; stop with a typed limitation if a prerequisite is absent. Inspect only declared targets, their direct owners and synthetic fixtures; no full-repository analysis. Reuse existing first-party adapters and task-declared pinned upstream APIs. No dependency installation, model download, training, paid test inference, live provider canary, real complaint/session/evidence/secret reads, external publication, or other campaign/state/process changes. Never weaken an assertion, add a required skip, fake a backend completion, manually satisfy a legal node, synthesize a Native receipt, or call a provider to obtain test evidence. Use temporary private HOME/session trees, class-preserving provider guards and bounded cleanup. Any fake transport is explicitly synthetic and cannot verify live Grok identity. Keep an awaiting_user interview distinct from a stalled worker. Run the one declared focused module; the trusted supervisor owns sealed validation and completion. If worker dependencies are unavailable, preserve meaningful tests and report the limitation for the host validator; do not vendor or bypass it.
>
> Deliver operator guidance and a pure completion-contract evaluator with focused tests. Root performs the actual post-callback audit outside the task; no private campaign reads inside tests.
