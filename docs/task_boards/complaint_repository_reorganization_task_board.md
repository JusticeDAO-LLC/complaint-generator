# Reorganize complaint-generator into versioned modules and current documentation

<!-- plan_id: baguqeerav5a3e2emaxj437aorrrppktbttyszjkvvey67asbgihf6kuiu47a -->

Implementation tasks begin pending. Completion requires behavioral validation evidence.

## CIMP-MOD-01 Inventory packages, duplicate owners, and root sprawl

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-inventory
- Subgoal: MODS-inventory
- Depends on: 
- Outputs: docs/architecture/repository_module_map.json, tests/test_cimp_mod_01.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_01.py
- Acceptance: The map records every top-level Python package, the root scripts and markdown files, and the empty root ipfs_datasets_py and mike compatibility directories. Duplicate owners are named for CLI, MCP, deontic logic, and legal-document modules, with file paths and byte sizes, and no source file is moved or rewritten.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-01 Inventory packages, duplicate owners, and root sprawl Targets: docs/architecture/repository_module_map.json, tests/test_cimp_mod_01.py Required outcomes: - The map records every top-level Python package, the root scripts and markdown files, and the empty root ipfs_datasets_py and mike compatibility directories. - Duplicate owners are named for CLI, MCP, deontic logic, and legal-document modules, with file paths and byte sizes, and no source file is moved or rewritten.  Write docs/architecture/repository_module_map.json with schema complaint-generator/repository-module-map@1. Include package paths, the largest Python modules by path and size, root markdown that is a session or batch report, and compatibility directories that are not the external/ submodule checkouts. The test loads that JSON and checks those observations against the current tree. It must fail if a recorded package directory is missing.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-01 Inventory packages, duplicate owners, and root sprawl
> Targets: docs/architecture/repository_module_map.json, tests/test_cimp_mod_01.py
> Required outcomes:
> - The map records every top-level Python package, the root scripts and markdown files, and the empty root ipfs_datasets_py and mike compatibility directories.
> - Duplicate owners are named for CLI, MCP, deontic logic, and legal-document modules, with file paths and byte sizes, and no source file is moved or rewritten.
> 
> Write docs/architecture/repository_module_map.json with schema complaint-generator/repository-module-map@1.
> Include package paths, the largest Python modules by path and size, root markdown that is a session or batch report, and compatibility directories that are not the external/ submodule checkouts.
> The test loads that JSON and checks those observations against the current tree. It must fail if a recorded package directory is missing.

## CIMP-MOD-02 Record documentation paths that no longer match the tree

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-inventory
- Subgoal: MODS-doc-drift
- Depends on: 
- Outputs: docs/architecture/documentation_drift.json, tests/test_cimp_mod_02.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_02.py
- Acceptance: The drift record lists README and DOCUMENTATION_INDEX links whose targets are missing, including root ipfs_datasets_py documentation paths that are not present in this checkout. It records that README workflow badges point at JusticeDAO-LLC while the Git remote is endomorphosis/complaint-generator, and it does not rewrite either document.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-02 Record documentation paths that no longer match the tree Targets: docs/architecture/documentation_drift.json, tests/test_cimp_mod_02.py Required outcomes: - The drift record lists README and DOCUMENTATION_INDEX links whose targets are missing, including root ipfs_datasets_py documentation paths that are not present in this checkout. - It records that README workflow badges point at JusticeDAO-LLC while the Git remote is endomorphosis/complaint-generator, and it does not rewrite either document.  Parse README.md and DOCUMENTATION_INDEX.md for relative links. Classify each as present or missing. Write docs/architecture/documentation_drift.json with schema complaint-generator/documentation-drift@1. The test checks at least one known missing index target and the organization mismatch, and it checks that README.md bytes are unchanged by this task.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-02 Record documentation paths that no longer match the tree
> Targets: docs/architecture/documentation_drift.json, tests/test_cimp_mod_02.py
> Required outcomes:
> - The drift record lists README and DOCUMENTATION_INDEX links whose targets are missing, including root ipfs_datasets_py documentation paths that are not present in this checkout.
> - It records that README workflow badges point at JusticeDAO-LLC while the Git remote is endomorphosis/complaint-generator, and it does not rewrite either document.
> 
> Parse README.md and DOCUMENTATION_INDEX.md for relative links. Classify each as present or missing.
> Write docs/architecture/documentation_drift.json with schema complaint-generator/documentation-drift@1.
> The test checks at least one known missing index target and the organization mismatch, and it checks that README.md bytes are unchanged by this task.

## CIMP-MOD-03 Define the versioned module-interface schema and checker

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-contracts
- Subgoal: MODS-contract-schema
- Depends on: CIMP-MOD-01
- Outputs: docs/architecture/module_interface_schema.json, scripts/check_module_interface.py, tests/test_cimp_mod_03.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_03.py
- Acceptance: The schema requires schema, module, version, owner_modules, and public_symbols, and version must be a major.minor.patch string. The checker accepts a conforming interface module, accepts an empty public surface only when STATUS is facade-only, and rejects a missing version, a server-starting import, and a public symbol that is not defined in an owner module.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-03 Define the versioned module-interface schema and checker Targets: docs/architecture/module_interface_schema.json, scripts/check_module_interface.py, tests/test_cimp_mod_03.py Required outcomes: - The schema requires schema, module, version, owner_modules, and public_symbols, and version must be a major.minor.patch string. - The checker accepts a conforming interface module, accepts an empty public surface only when STATUS is facade-only, and rejects a missing version, a server-starting import, and a public symbol that is not defined in an owner module.  docs/architecture/module_interface_schema.json is complaint-generator/module-interface-schema@1 and describes INTERFACE_SCHEMA complaint-generator/module-interface@1. scripts/check_module_interface.py takes one module name and exits nonzero with a specific reason when the contract fails. The test uses temporary conforming and nonconforming modules. It does not import the large application packages.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-03 Define the versioned module-interface schema and checker
> Targets: docs/architecture/module_interface_schema.json, scripts/check_module_interface.py, tests/test_cimp_mod_03.py
> Required outcomes:
> - The schema requires schema, module, version, owner_modules, and public_symbols, and version must be a major.minor.patch string.
> - The checker accepts a conforming interface module, accepts an empty public surface only when STATUS is facade-only, and rejects a missing version, a server-starting import, and a public symbol that is not defined in an owner module.
> 
> docs/architecture/module_interface_schema.json is complaint-generator/module-interface-schema@1 and describes INTERFACE_SCHEMA complaint-generator/module-interface@1.
> scripts/check_module_interface.py takes one module name and exits nonzero with a specific reason when the contract fails.
> The test uses temporary conforming and nonconforming modules. It does not import the large application packages.

## CIMP-MOD-04 Publish the applications package interface

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-contracts
- Subgoal: MODS-package-contracts
- Depends on: CIMP-MOD-03
- Outputs: applications/interface.py, tests/test_cimp_mod_04.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_04.py
- Acceptance: applications.interface version 1.0.0 names the current public route and workspace entry symbols without importing complaint_workspace at interface import time. The test rejects a symbol that is not defined in the declared owner module.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-04 Publish the applications package interface Targets: applications/interface.py, tests/test_cimp_mod_04.py Required outcomes: - applications.interface version 1.0.0 names the current public route and workspace entry symbols without importing complaint_workspace at interface import time. - The test rejects a symbol that is not defined in the declared owner module.  Create a new interface module only. Do not edit the package's existing implementation files. The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules. Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time. The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.  Owner candidates are applications.server, applications.case_routes, and applications.launcher. Choose symbols that already exist.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-04 Publish the applications package interface
> Targets: applications/interface.py, tests/test_cimp_mod_04.py
> Required outcomes:
> - applications.interface version 1.0.0 names the current public route and workspace entry symbols without importing complaint_workspace at interface import time.
> - The test rejects a symbol that is not defined in the declared owner module.
> 
> Create a new interface module only. Do not edit the package's existing implementation files.
> The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules.
> Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time.
> The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.
> 
> Owner candidates are applications.server, applications.case_routes, and applications.launcher. Choose symbols that already exist.

## CIMP-MOD-05 Publish the complaint_generator package interface

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-contracts
- Subgoal: MODS-package-contracts
- Depends on: CIMP-MOD-03
- Outputs: complaint_generator/interface.py, tests/test_cimp_mod_05.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_05.py
- Acceptance: complaint_generator.interface version 1.0.0 names the current entrypoint, workspace, and MCP symbols without importing a server at interface import time. The test rejects a symbol that is not defined in the declared owner module.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-05 Publish the complaint_generator package interface Targets: complaint_generator/interface.py, tests/test_cimp_mod_05.py Required outcomes: - complaint_generator.interface version 1.0.0 names the current entrypoint, workspace, and MCP symbols without importing a server at interface import time. - The test rejects a symbol that is not defined in the declared owner module.  Create a new interface module only. Do not edit the package's existing implementation files. The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules. Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time. The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.  Owner candidates are complaint_generator.entrypoints, complaint_generator.workspace, and complaint_generator.mcp.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-05 Publish the complaint_generator package interface
> Targets: complaint_generator/interface.py, tests/test_cimp_mod_05.py
> Required outcomes:
> - complaint_generator.interface version 1.0.0 names the current entrypoint, workspace, and MCP symbols without importing a server at interface import time.
> - The test rejects a symbol that is not defined in the declared owner module.
> 
> Create a new interface module only. Do not edit the package's existing implementation files.
> The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules.
> Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time.
> The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.
> 
> Owner candidates are complaint_generator.entrypoints, complaint_generator.workspace, and complaint_generator.mcp.

## CIMP-MOD-06 Publish the mediator package interface

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-contracts
- Subgoal: MODS-package-contracts
- Depends on: CIMP-MOD-03
- Outputs: mediator/interface.py, tests/test_cimp_mod_06.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_06.py
- Acceptance: mediator.interface version 1.0.0 names workflow and hook symbols that already exist, and importing the interface does not import mediator.mediator. The test rejects a symbol that is not defined in the declared owner module.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-06 Publish the mediator package interface Targets: mediator/interface.py, tests/test_cimp_mod_06.py Required outcomes: - mediator.interface version 1.0.0 names workflow and hook symbols that already exist, and importing the interface does not import mediator.mediator. - The test rejects a symbol that is not defined in the declared owner module.  Create a new interface module only. Do not edit the package's existing implementation files. The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules. Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time. The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.  Owner candidates are mediator.workflow_service, mediator.hook_runtime, and mediator.state. Do not parse all of mediator.py if a smaller owner already defines the symbol.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-06 Publish the mediator package interface
> Targets: mediator/interface.py, tests/test_cimp_mod_06.py
> Required outcomes:
> - mediator.interface version 1.0.0 names workflow and hook symbols that already exist, and importing the interface does not import mediator.mediator.
> - The test rejects a symbol that is not defined in the declared owner module.
> 
> Create a new interface module only. Do not edit the package's existing implementation files.
> The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules.
> Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time.
> The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.
> 
> Owner candidates are mediator.workflow_service, mediator.hook_runtime, and mediator.state. Do not parse all of mediator.py if a smaller owner already defines the symbol.

## CIMP-MOD-07 Publish the complaint_phases package interface

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-contracts
- Subgoal: MODS-package-contracts
- Depends on: CIMP-MOD-03
- Outputs: complaint_phases/interface.py, tests/test_cimp_mod_07.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_07.py
- Acceptance: complaint_phases.interface version 1.0.0 names phase, graph, and intake symbols that already exist, without executing a phase pipeline on import. The test rejects a symbol that is not defined in the declared owner module.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-07 Publish the complaint_phases package interface Targets: complaint_phases/interface.py, tests/test_cimp_mod_07.py Required outcomes: - complaint_phases.interface version 1.0.0 names phase, graph, and intake symbols that already exist, without executing a phase pipeline on import. - The test rejects a symbol that is not defined in the declared owner module.  Create a new interface module only. Do not edit the package's existing implementation files. The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules. Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time. The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.  Owner candidates are complaint_phases.phase_manager, complaint_phases.knowledge_graph, and complaint_phases.intake_case_file.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-07 Publish the complaint_phases package interface
> Targets: complaint_phases/interface.py, tests/test_cimp_mod_07.py
> Required outcomes:
> - complaint_phases.interface version 1.0.0 names phase, graph, and intake symbols that already exist, without executing a phase pipeline on import.
> - The test rejects a symbol that is not defined in the declared owner module.
> 
> Create a new interface module only. Do not edit the package's existing implementation files.
> The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules.
> Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time.
> The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.
> 
> Owner candidates are complaint_phases.phase_manager, complaint_phases.knowledge_graph, and complaint_phases.intake_case_file.

## CIMP-MOD-08 Publish the ipfs_accelerate integration interface

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-contracts
- Subgoal: MODS-package-contracts
- Depends on: CIMP-MOD-03
- Outputs: integrations/ipfs_accelerate/interface.py, tests/test_cimp_mod_08.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_08.py
- Acceptance: The accelerate integration interface version 1.0.0 names campaign and plan symbols that already exist, without starting a supervisor on import. The test rejects a symbol that is not defined in the declared owner module.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-08 Publish the ipfs_accelerate integration interface Targets: integrations/ipfs_accelerate/interface.py, tests/test_cimp_mod_08.py Required outcomes: - The accelerate integration interface version 1.0.0 names campaign and plan symbols that already exist, without starting a supervisor on import. - The test rejects a symbol that is not defined in the declared owner module.  Create a new interface module only. Do not edit the package's existing implementation files. The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules. Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time. The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.  Owner candidates are integrations.ipfs_accelerate.campaign and integrations.ipfs_accelerate.improvement_plan.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-08 Publish the ipfs_accelerate integration interface
> Targets: integrations/ipfs_accelerate/interface.py, tests/test_cimp_mod_08.py
> Required outcomes:
> - The accelerate integration interface version 1.0.0 names campaign and plan symbols that already exist, without starting a supervisor on import.
> - The test rejects a symbol that is not defined in the declared owner module.
> 
> Create a new interface module only. Do not edit the package's existing implementation files.
> The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules.
> Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time.
> The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.
> 
> Owner candidates are integrations.ipfs_accelerate.campaign and integrations.ipfs_accelerate.improvement_plan.

## CIMP-MOD-09 Publish the ipfs_datasets integration interface

- Status: completed
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-contracts
- Subgoal: MODS-package-contracts
- Depends on: CIMP-MOD-03
- Outputs: integrations/ipfs_datasets/interface.py, tests/test_cimp_mod_09.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_09.py
- Acceptance: The datasets integration interface version 1.0.0 names loader and adapter symbols that already exist, without updating a submodule on import. The test rejects a symbol that is not defined in the declared owner module.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-09 Publish the ipfs_datasets integration interface Targets: integrations/ipfs_datasets/interface.py, tests/test_cimp_mod_09.py Required outcomes: - The datasets integration interface version 1.0.0 names loader and adapter symbols that already exist, without updating a submodule on import. - The test rejects a symbol that is not defined in the declared owner module.  Create a new interface module only. Do not edit the package's existing implementation files. The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules. Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time. The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.  Owner candidates are integrations.ipfs_datasets.loader and one other existing adapter module in that package. Do not import external.ipfs_datasets_py at interface import time.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-09 Publish the ipfs_datasets integration interface
> Targets: integrations/ipfs_datasets/interface.py, tests/test_cimp_mod_09.py
> Required outcomes:
> - The datasets integration interface version 1.0.0 names loader and adapter symbols that already exist, without updating a submodule on import.
> - The test rejects a symbol that is not defined in the declared owner module.
> 
> Create a new interface module only. Do not edit the package's existing implementation files.
> The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules.
> Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time.
> The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.
> 
> Owner candidates are integrations.ipfs_datasets.loader and one other existing adapter module in that package. Do not import external.ipfs_datasets_py at interface import time.

## CIMP-MOD-10 Publish the mike integration interface

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: MODG-contracts
- Subgoal: MODS-package-contracts
- Depends on: CIMP-MOD-03
- Outputs: integrations/mike/interface.py, tests/test_cimp_mod_10.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_10.py
- Acceptance: The mike integration interface version 1.0.0 records the current connector symbols, or an explicit empty public surface when the package has no import-time API. Importing the interface does not import the root mike compatibility directory or external.mike.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-10 Publish the mike integration interface Targets: integrations/mike/interface.py, tests/test_cimp_mod_10.py Required outcomes: - The mike integration interface version 1.0.0 records the current connector symbols, or an explicit empty public surface when the package has no import-time API. - Importing the interface does not import the root mike compatibility directory or external.mike.  Create a new interface module only. Do not edit the package's existing implementation files. The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules. Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time. The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.  Inspect integrations/mike. An empty PUBLIC_SYMBOLS tuple is valid only with STATUS = "facade-only" and a reason string. Do not create a fake connector.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-10 Publish the mike integration interface
> Targets: integrations/mike/interface.py, tests/test_cimp_mod_10.py
> Required outcomes:
> - The mike integration interface version 1.0.0 records the current connector symbols, or an explicit empty public surface when the package has no import-time API.
> - Importing the interface does not import the root mike compatibility directory or external.mike.
> 
> Create a new interface module only. Do not edit the package's existing implementation files.
> The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules.
> Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time.
> The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.
> 
> Inspect integrations/mike. An empty PUBLIC_SYMBOLS tuple is valid only with STATUS = "facade-only" and a reason string. Do not create a fake connector.

## CIMP-MOD-11 Publish the lib package interface

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: MODG-contracts
- Subgoal: MODS-package-contracts
- Depends on: CIMP-MOD-03
- Outputs: lib/interface.py, tests/test_cimp_mod_11.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_11.py
- Acceptance: lib.interface version 1.0.0 names the current lib owners for logging, formal logic, and document helpers that already exist. The test rejects a symbol that is not defined in the declared owner module and records that lib.deontic_logic and lib.legal_document are legacy owners pending the ownership tasks.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-11 Publish the lib package interface Targets: lib/interface.py, tests/test_cimp_mod_11.py Required outcomes: - lib.interface version 1.0.0 names the current lib owners for logging, formal logic, and document helpers that already exist. - The test rejects a symbol that is not defined in the declared owner module and records that lib.deontic_logic and lib.legal_document are legacy owners pending the ownership tasks.  Create a new interface module only. Do not edit the package's existing implementation files. The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules. Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time. The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.  Owner candidates are lib.log, lib.formal_logic, and lib.knowledge_graph_export. Mention the duplicate deontic and legal-document modules in INTERFACE_NOTES, not by merging them.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-11 Publish the lib package interface
> Targets: lib/interface.py, tests/test_cimp_mod_11.py
> Required outcomes:
> - lib.interface version 1.0.0 names the current lib owners for logging, formal logic, and document helpers that already exist.
> - The test rejects a symbol that is not defined in the declared owner module and records that lib.deontic_logic and lib.legal_document are legacy owners pending the ownership tasks.
> 
> Create a new interface module only. Do not edit the package's existing implementation files.
> The module defines INTERFACE_SCHEMA, INTERFACE_VERSION, OWNER_MODULES as a tuple of importable module names, and PUBLIC_SYMBOLS as a tuple of attribute names that already exist in those owner modules.
> Confirm each public symbol by parsing the owner module with ast, or by a lazy import of that module alone. Do not import mediator.mediator, applications.complaint_workspace, or document_pipeline from the interface module at import time.
> The test imports only the new interface module and fails if a declared symbol is absent from the parsed owner, if the version is not 1.0.0, or if importing the interface starts a server or reads a private workspace path.
> 
> Owner candidates are lib.log, lib.formal_logic, and lib.knowledge_graph_export. Mention the duplicate deontic and legal-document modules in INTERFACE_NOTES, not by merging them.

## CIMP-MOD-12 Ratchet imports so new files use the package interfaces

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-boundaries
- Subgoal: MODS-import-ratchet
- Depends on: CIMP-MOD-04, CIMP-MOD-05, CIMP-MOD-06, CIMP-MOD-07, CIMP-MOD-08, CIMP-MOD-09, CIMP-MOD-10, CIMP-MOD-11
- Outputs: docs/architecture/import_boundary_baseline.json, scripts/check_import_boundaries.py, tests/test_cimp_mod_12.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_12.py
- Acceptance: The baseline records the current internal imports that bypass a published interface, and the checker fails when a Python file newer than the baseline adds another bypass. Existing large modules remain allowed by the baseline. The test proves a synthetic new bypass fails and an interface import passes.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-12 Ratchet imports so new files use the package interfaces Targets: docs/architecture/import_boundary_baseline.json, scripts/check_import_boundaries.py, tests/test_cimp_mod_12.py Required outcomes: - The baseline records the current internal imports that bypass a published interface, and the checker fails when a Python file newer than the baseline adds another bypass. - Existing large modules remain allowed by the baseline. The test proves a synthetic new bypass fails and an interface import passes.  A bypass is an import of mediator.mediator, applications.complaint_workspace, complaint_phases.denoiser, or document_pipeline from a file that is not the owner package and not listed in the baseline. Do not rewrite existing imports in this task. Generate the baseline from the current tree and store file path plus imported module. scripts/check_import_boundaries.py exits nonzero for an unlisted bypass. The test uses temporary files.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-12 Ratchet imports so new files use the package interfaces
> Targets: docs/architecture/import_boundary_baseline.json, scripts/check_import_boundaries.py, tests/test_cimp_mod_12.py
> Required outcomes:
> - The baseline records the current internal imports that bypass a published interface, and the checker fails when a Python file newer than the baseline adds another bypass.
> - Existing large modules remain allowed by the baseline. The test proves a synthetic new bypass fails and an interface import passes.
> 
> A bypass is an import of mediator.mediator, applications.complaint_workspace, complaint_phases.denoiser, or document_pipeline from a file that is not the owner package and not listed in the baseline.
> Do not rewrite existing imports in this task. Generate the baseline from the current tree and store file path plus imported module.
> scripts/check_import_boundaries.py exits nonzero for an unlisted bypass. The test uses temporary files.

## CIMP-MOD-13 Give CLI entry points one versioned owner

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-boundaries
- Subgoal: MODS-entry-shims
- Depends on: CIMP-MOD-05
- Outputs: complaint_generator/entrypoint_ownership.json, tests/test_cimp_mod_13.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_13.py
- Acceptance: The ownership record names complaint_generator.entrypoints as the owner and lists applications.cli, applications.complaint_cli, and complaint_generator.cli as callers or duplicates. No CLI body is merged unless the test shows the public callable names and signatures already match. Divergent signatures stay recorded and unmodified.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-13 Give CLI entry points one versioned owner Targets: complaint_generator/entrypoint_ownership.json, tests/test_cimp_mod_13.py Required outcomes: - The ownership record names complaint_generator.entrypoints as the owner and lists applications.cli, applications.complaint_cli, and complaint_generator.cli as callers or duplicates. - No CLI body is merged unless the test shows the public callable names and signatures already match. Divergent signatures stay recorded and unmodified.  Compare the public functions with ast. Write complaint_generator/entrypoint_ownership.json with schema complaint-generator/entrypoint-ownership@1 and interface_version 1.0.0. A shim may be added only inside complaint_generator/entrypoints.py when it re-exports an existing function without changing argv behavior. Otherwise write the record only. The test fails if a recorded callable is absent, and it fails if a shim changes a function signature.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-13 Give CLI entry points one versioned owner
> Targets: complaint_generator/entrypoint_ownership.json, tests/test_cimp_mod_13.py
> Required outcomes:
> - The ownership record names complaint_generator.entrypoints as the owner and lists applications.cli, applications.complaint_cli, and complaint_generator.cli as callers or duplicates.
> - No CLI body is merged unless the test shows the public callable names and signatures already match. Divergent signatures stay recorded and unmodified.
> 
> Compare the public functions with ast. Write complaint_generator/entrypoint_ownership.json with schema complaint-generator/entrypoint-ownership@1 and interface_version 1.0.0.
> A shim may be added only inside complaint_generator/entrypoints.py when it re-exports an existing function without changing argv behavior. Otherwise write the record only.
> The test fails if a recorded callable is absent, and it fails if a shim changes a function signature.

## CIMP-MOD-14 Give MCP servers one versioned owner

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: MODG-boundaries
- Subgoal: MODS-entry-shims
- Depends on: CIMP-MOD-05
- Outputs: complaint_generator/mcp_ownership.json, tests/test_cimp_mod_14.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_14.py
- Acceptance: The ownership record names the current MCP owner modules and the duplicate server modules in applications and complaint_generator. No server is started, and no protocol response is treated as success when the owner module cannot be imported.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-14 Give MCP servers one versioned owner Targets: complaint_generator/mcp_ownership.json, tests/test_cimp_mod_14.py Required outcomes: - The ownership record names the current MCP owner modules and the duplicate server modules in applications and complaint_generator. - No server is started, and no protocol response is treated as success when the owner module cannot be imported.  Inspect applications/complaint_mcp_server.py, applications/complaint_mcp_protocol.py, complaint_generator/mcp.py, and complaint_generator/mcp_server.py. Write complaint_generator/mcp_ownership.json with schema complaint-generator/mcp-ownership@1 and interface_version 1.0.0. Do not bind a new network socket. The test parses the record and the AST of the named owners.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-14 Give MCP servers one versioned owner
> Targets: complaint_generator/mcp_ownership.json, tests/test_cimp_mod_14.py
> Required outcomes:
> - The ownership record names the current MCP owner modules and the duplicate server modules in applications and complaint_generator.
> - No server is started, and no protocol response is treated as success when the owner module cannot be imported.
> 
> Inspect applications/complaint_mcp_server.py, applications/complaint_mcp_protocol.py, complaint_generator/mcp.py, and complaint_generator/mcp_server.py.
> Write complaint_generator/mcp_ownership.json with schema complaint-generator/mcp-ownership@1 and interface_version 1.0.0.
> Do not bind a new network socket. The test parses the record and the AST of the named owners.

## CIMP-MOD-15 Record the deontic-logic owner without merging implementations

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: MODG-boundaries
- Subgoal: MODS-duplicate-owners
- Depends on: CIMP-MOD-07, CIMP-MOD-11
- Outputs: docs/architecture/deontic_logic_ownership.json, tests/test_cimp_mod_15.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_15.py
- Acceptance: The record compares public functions in lib/deontic_logic.py and complaint_phases/deontic_logic.py and names one owner only when the signatures match. When the signatures differ, both implementations stay unchanged and the record status is divergent.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-15 Record the deontic-logic owner without merging implementations Targets: docs/architecture/deontic_logic_ownership.json, tests/test_cimp_mod_15.py Required outcomes: - The record compares public functions in lib/deontic_logic.py and complaint_phases/deontic_logic.py and names one owner only when the signatures match. - When the signatures differ, both implementations stay unchanged and the record status is divergent.  Use ast only. Do not execute either module and do not delete either file. Schema complaint-generator/duplicate-owner@1, interface_version 1.0.0. The test checks the status against the current signatures.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-15 Record the deontic-logic owner without merging implementations
> Targets: docs/architecture/deontic_logic_ownership.json, tests/test_cimp_mod_15.py
> Required outcomes:
> - The record compares public functions in lib/deontic_logic.py and complaint_phases/deontic_logic.py and names one owner only when the signatures match.
> - When the signatures differ, both implementations stay unchanged and the record status is divergent.
> 
> Use ast only. Do not execute either module and do not delete either file.
> Schema complaint-generator/duplicate-owner@1, interface_version 1.0.0.
> The test checks the status against the current signatures.

## CIMP-MOD-16 Add a legal-document facade without merging the three owners

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: MODG-boundaries
- Subgoal: MODS-duplicate-owners
- Depends on: CIMP-MOD-07
- Outputs: complaint_phases/legal_document_facade.py, docs/architecture/legal_document_owners.json, tests/test_cimp_mod_16.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_16.py
- Acceptance: The facade version 1.0.0 re-exports only symbols already defined in complaint_phases/legal_document.py and records lib/legal_document.py and mediator/formal_document.py as separate owners. Importing the facade does not import mediator.mediator, and none of the three implementation bodies is rewritten.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-16 Add a legal-document facade without merging the three owners Targets: complaint_phases/legal_document_facade.py, docs/architecture/legal_document_owners.json, tests/test_cimp_mod_16.py Required outcomes: - The facade version 1.0.0 re-exports only symbols already defined in complaint_phases/legal_document.py and records lib/legal_document.py and mediator/formal_document.py as separate owners. - Importing the facade does not import mediator.mediator, and none of the three implementation bodies is rewritten.  The facade defines INTERFACE_SCHEMA and INTERFACE_VERSION. The JSON record uses schema complaint-generator/duplicate-owner@1. The test parses all three owners and fails if the facade exposes a symbol that complaint_phases/legal_document.py does not define.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-16 Add a legal-document facade without merging the three owners
> Targets: complaint_phases/legal_document_facade.py, docs/architecture/legal_document_owners.json, tests/test_cimp_mod_16.py
> Required outcomes:
> - The facade version 1.0.0 re-exports only symbols already defined in complaint_phases/legal_document.py and records lib/legal_document.py and mediator/formal_document.py as separate owners.
> - Importing the facade does not import mediator.mediator, and none of the three implementation bodies is rewritten.
> 
> The facade defines INTERFACE_SCHEMA and INTERFACE_VERSION. The JSON record uses schema complaint-generator/duplicate-owner@1.
> The test parses all three owners and fails if the facade exposes a symbol that complaint_phases/legal_document.py does not define.

## CIMP-MOD-17 Rewrite the README around the current modules and remote

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-docs
- Subgoal: MODS-root-docs
- Depends on: CIMP-MOD-01, CIMP-MOD-02
- Outputs: README.md, tests/test_cimp_mod_17.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_17.py
- Acceptance: The README names the current packages, the external submodule checkouts, and the endomorphosis/complaint-generator remote, and it no longer presents JusticeDAO-LLC workflow badges as this repository's status. It describes versioned package interfaces and tells readers not to import giant implementation modules from new code. It does not link to root session or batch reports.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-17 Rewrite the README around the current modules and remote Targets: README.md, tests/test_cimp_mod_17.py Required outcomes: - The README names the current packages, the external submodule checkouts, and the endomorphosis/complaint-generator remote, and it no longer presents JusticeDAO-LLC workflow badges as this repository's status. - It describes versioned package interfaces and tells readers not to import giant implementation modules from new code. It does not link to root session or batch reports.  Replace the stale overview with the current intake, mediator, phase, application, and integration layout. Keep the description of complaint preparation accurate. Do not claim a feature exists unless the module map or source names it. The test reads README.md and fails on JusticeDAO-LLC badge URLs, missing-package claims, and links to SESSION_ or BATCH_ root files.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-17 Rewrite the README around the current modules and remote
> Targets: README.md, tests/test_cimp_mod_17.py
> Required outcomes:
> - The README names the current packages, the external submodule checkouts, and the endomorphosis/complaint-generator remote, and it no longer presents JusticeDAO-LLC workflow badges as this repository's status.
> - It describes versioned package interfaces and tells readers not to import giant implementation modules from new code. It does not link to root session or batch reports.
> 
> Replace the stale overview with the current intake, mediator, phase, application, and integration layout.
> Keep the description of complaint preparation accurate. Do not claim a feature exists unless the module map or source names it.
> The test reads README.md and fails on JusticeDAO-LLC badge URLs, missing-package claims, and links to SESSION_ or BATCH_ root files.

## CIMP-MOD-18 Rebuild the documentation index from files that exist

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-docs
- Subgoal: MODS-root-docs
- Depends on: CIMP-MOD-01, CIMP-MOD-02
- Outputs: DOCUMENTATION_INDEX.md, tests/test_cimp_mod_18.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_18.py
- Acceptance: Every relative link in DOCUMENTATION_INDEX.md resolves to a file in this checkout, including the replacement for the missing root ipfs_datasets_py logic index. The index points at docs/architecture/repository_module_map.json and the versioned interface schema, and it does not describe tests/README.md as a 19-file suite unless that is still true.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-18 Rebuild the documentation index from files that exist Targets: DOCUMENTATION_INDEX.md, tests/test_cimp_mod_18.py Required outcomes: - Every relative link in DOCUMENTATION_INDEX.md resolves to a file in this checkout, including the replacement for the missing root ipfs_datasets_py logic index. - The index points at docs/architecture/repository_module_map.json and the versioned interface schema, and it does not describe tests/README.md as a 19-file suite unless that is still true.  Rebuild DOCUMENTATION_INDEX.md from the current tree. Drop or retarget links recorded as missing by the drift report. The test extracts relative links and fails when a target is absent. It does not fetch external documentation.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-18 Rebuild the documentation index from files that exist
> Targets: DOCUMENTATION_INDEX.md, tests/test_cimp_mod_18.py
> Required outcomes:
> - Every relative link in DOCUMENTATION_INDEX.md resolves to a file in this checkout, including the replacement for the missing root ipfs_datasets_py logic index.
> - The index points at docs/architecture/repository_module_map.json and the versioned interface schema, and it does not describe tests/README.md as a 19-file suite unless that is still true.
> 
> Rebuild DOCUMENTATION_INDEX.md from the current tree. Drop or retarget links recorded as missing by the drift report.
> The test extracts relative links and fails when a target is absent. It does not fetch external documentation.

## CIMP-MOD-19 Archive root session reports out of the repository root

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: MODG-docs
- Subgoal: MODS-root-docs
- Depends on: CIMP-MOD-17, CIMP-MOD-18
- Outputs: docs/archive/sessions/INDEX.md, tests/test_cimp_mod_19.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_19.py
- Acceptance: Root session, batch, old-README, and completion-summary markdown listed by the module map moves to docs/archive/sessions, and README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, and TODO.md stay at the root. The archive index lists every moved file, and no remaining root markdown link in the README or documentation index points at a moved file.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-19 Archive root session reports out of the repository root Targets: docs/archive/sessions/INDEX.md, tests/test_cimp_mod_19.py Required outcomes: - Root session, batch, old-README, and completion-summary markdown listed by the module map moves to docs/archive/sessions, and README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, and TODO.md stay at the root. - The archive index lists every moved file, and no remaining root markdown link in the README or documentation index points at a moved file.  Move only historical root markdown. Do not move plan files under docs/task_boards or architecture records created by earlier tasks. Use git mv so history is preserved. docs/archive/sessions/INDEX.md is schema-free markdown with one relative link per archived file. The test checks the keep-list remains at the root and every index link resolves.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-19 Archive root session reports out of the repository root
> Targets: docs/archive/sessions/INDEX.md, tests/test_cimp_mod_19.py
> Required outcomes:
> - Root session, batch, old-README, and completion-summary markdown listed by the module map moves to docs/archive/sessions, and README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, and TODO.md stay at the root.
> - The archive index lists every moved file, and no remaining root markdown link in the README or documentation index points at a moved file.
> 
> Move only historical root markdown. Do not move plan files under docs/task_boards or architecture records created by earlier tasks.
> Use git mv so history is preserved. docs/archive/sessions/INDEX.md is schema-free markdown with one relative link per archived file.
> The test checks the keep-list remains at the root and every index link resolves.

## CIMP-MOD-20 Document the applications package and its interface

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: MODG-docs
- Subgoal: MODS-package-docs
- Depends on: CIMP-MOD-04
- Outputs: applications/README.md, tests/test_cimp_mod_20.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_20.py
- Acceptance: The applications README names interface version 1.0.0, the owner modules, and the rule that new code imports applications.interface rather than complaint_workspace. Every relative link in that README resolves, and the test imports applications.interface.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-20 Document the applications package and its interface Targets: applications/README.md, tests/test_cimp_mod_20.py Required outcomes: - The applications README names interface version 1.0.0, the owner modules, and the rule that new code imports applications.interface rather than complaint_workspace. - Every relative link in that README resolves, and the test imports applications.interface.  Write applications/README.md from the interface module and the module map. Do not document a route the interface does not name.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-20 Document the applications package and its interface
> Targets: applications/README.md, tests/test_cimp_mod_20.py
> Required outcomes:
> - The applications README names interface version 1.0.0, the owner modules, and the rule that new code imports applications.interface rather than complaint_workspace.
> - Every relative link in that README resolves, and the test imports applications.interface.
> 
> Write applications/README.md from the interface module and the module map. Do not document a route the interface does not name.

## CIMP-MOD-21 Document the mediator package and its interface

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: MODG-docs
- Subgoal: MODS-package-docs
- Depends on: CIMP-MOD-06
- Outputs: mediator/readme.md, tests/test_cimp_mod_21.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_21.py
- Acceptance: The mediator readme names interface version 1.0.0 and states that mediator.py remains the legacy implementation behind the interface. Every relative link resolves, and the test imports mediator.interface without importing mediator.mediator.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-21 Document the mediator package and its interface Targets: mediator/readme.md, tests/test_cimp_mod_21.py Required outcomes: - The mediator readme names interface version 1.0.0 and states that mediator.py remains the legacy implementation behind the interface. - Every relative link resolves, and the test imports mediator.interface without importing mediator.mediator.  Update the existing mediator/readme.md. Do not create a second README.md that splits the package documentation.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-21 Document the mediator package and its interface
> Targets: mediator/readme.md, tests/test_cimp_mod_21.py
> Required outcomes:
> - The mediator readme names interface version 1.0.0 and states that mediator.py remains the legacy implementation behind the interface.
> - Every relative link resolves, and the test imports mediator.interface without importing mediator.mediator.
> 
> Update the existing mediator/readme.md. Do not create a second README.md that splits the package documentation.

## CIMP-MOD-22 Document the complaint_phases package and its interface

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: MODG-docs
- Subgoal: MODS-package-docs
- Depends on: CIMP-MOD-07
- Outputs: complaint_phases/README.md, tests/test_cimp_mod_22.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_22.py
- Acceptance: The phase README names interface version 1.0.0 and distinguishes the phase pipeline from the separate legal and deontic owners. Every relative link resolves, and the test imports complaint_phases.interface.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-22 Document the complaint_phases package and its interface Targets: complaint_phases/README.md, tests/test_cimp_mod_22.py Required outcomes: - The phase README names interface version 1.0.0 and distinguishes the phase pipeline from the separate legal and deontic owners. - Every relative link resolves, and the test imports complaint_phases.interface.  Update complaint_phases/README.md. Do not describe a three-phase diffusion product claim that the interface does not expose.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-22 Document the complaint_phases package and its interface
> Targets: complaint_phases/README.md, tests/test_cimp_mod_22.py
> Required outcomes:
> - The phase README names interface version 1.0.0 and distinguishes the phase pipeline from the separate legal and deontic owners.
> - Every relative link resolves, and the test imports complaint_phases.interface.
> 
> Update complaint_phases/README.md. Do not describe a three-phase diffusion product claim that the interface does not expose.

## CIMP-MOD-23 Document the integration packages and their interfaces

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: MODG-docs
- Subgoal: MODS-package-docs
- Depends on: CIMP-MOD-08, CIMP-MOD-09, CIMP-MOD-10
- Outputs: integrations/README.md, tests/test_cimp_mod_23.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_23.py
- Acceptance: The integrations README names the accelerate, datasets, and mike interface versions and states that external/ pins are not advanced by documentation work. Every relative link resolves, and the test imports the three integration interface modules.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-23 Document the integration packages and their interfaces Targets: integrations/README.md, tests/test_cimp_mod_23.py Required outcomes: - The integrations README names the accelerate, datasets, and mike interface versions and states that external/ pins are not advanced by documentation work. - Every relative link resolves, and the test imports the three integration interface modules.  Create integrations/README.md. Point submodule checkouts at external/ and identify the empty root ipfs_datasets_py and mike directories as compatibility paths, not the SDK trees.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-23 Document the integration packages and their interfaces
> Targets: integrations/README.md, tests/test_cimp_mod_23.py
> Required outcomes:
> - The integrations README names the accelerate, datasets, and mike interface versions and states that external/ pins are not advanced by documentation work.
> - Every relative link resolves, and the test imports the three integration interface modules.
> 
> Create integrations/README.md. Point submodule checkouts at external/ and identify the empty root ipfs_datasets_py and mike directories as compatibility paths, not the SDK trees.

## CIMP-MOD-24 Document the complaint_generator package and its interface

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P1
- Goal: MODG-docs
- Subgoal: MODS-package-docs
- Depends on: CIMP-MOD-05
- Outputs: complaint_generator/README.md, tests/test_cimp_mod_24.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_24.py
- Acceptance: The package README names interface version 1.0.0 and names the CLI and MCP modules that the interface already lists. Every relative link resolves, and the test imports complaint_generator.interface.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-24 Document the complaint_generator package and its interface Targets: complaint_generator/README.md, tests/test_cimp_mod_24.py Required outcomes: - The package README names interface version 1.0.0 and names the CLI and MCP modules that the interface already lists. - Every relative link resolves, and the test imports complaint_generator.interface.  Create complaint_generator/README.md. Do not link to entrypoint_ownership.json or mcp_ownership.json; those files belong to later tasks. Describe the current modules by paths that already exist.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-24 Document the complaint_generator package and its interface
> Targets: complaint_generator/README.md, tests/test_cimp_mod_24.py
> Required outcomes:
> - The package README names interface version 1.0.0 and names the CLI and MCP modules that the interface already lists.
> - Every relative link resolves, and the test imports complaint_generator.interface.
> 
> Create complaint_generator/README.md. Do not link to entrypoint_ownership.json or mcp_ownership.json; those files belong to later tasks. Describe the current modules by paths that already exist.

## CIMP-MOD-25 Write the repository operator guide for module boundaries

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-docs
- Subgoal: MODS-operator-guide
- Depends on: CIMP-MOD-12, CIMP-MOD-17
- Outputs: docs/architecture/REPOSITORY.md, tests/test_cimp_mod_25.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_25.py
- Acceptance: The guide states the package map, the interface version, the import ratchet, the submodule pin policy, and the files new work must not edit. It tells an operator how to run scripts/check_module_interface.py and scripts/check_import_boundaries.py, and every relative link resolves.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-25 Write the repository operator guide for module boundaries Targets: docs/architecture/REPOSITORY.md, tests/test_cimp_mod_25.py Required outcomes: - The guide states the package map, the interface version, the import ratchet, the submodule pin policy, and the files new work must not edit. - It tells an operator how to run scripts/check_module_interface.py and scripts/check_import_boundaries.py, and every relative link resolves.  docs/architecture/REPOSITORY.md is the current architecture guide. Include the parallel work rule: tasks may edit only their declared targets. State that origin/main and origin/master already contain the published UX work, and this reorganization does not reopen those boards. The test resolves links and checks the pin and quarantine warnings are present.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-25 Write the repository operator guide for module boundaries
> Targets: docs/architecture/REPOSITORY.md, tests/test_cimp_mod_25.py
> Required outcomes:
> - The guide states the package map, the interface version, the import ratchet, the submodule pin policy, and the files new work must not edit.
> - It tells an operator how to run scripts/check_module_interface.py and scripts/check_import_boundaries.py, and every relative link resolves.
> 
> docs/architecture/REPOSITORY.md is the current architecture guide. Include the parallel work rule: tasks may edit only their declared targets.
> State that origin/main and origin/master already contain the published UX work, and this reorganization does not reopen those boards.
> The test resolves links and checks the pin and quarantine warnings are present.

## CIMP-MOD-26 Add the repository-organization acceptance command

- Status: todo
- Completion: validation
- No-change completion: allowed
- Priority: P0
- Goal: MODG-closure
- Subgoal: MODS-acceptance
- Depends on: CIMP-MOD-13, CIMP-MOD-14, CIMP-MOD-15, CIMP-MOD-16, CIMP-MOD-19, CIMP-MOD-20, CIMP-MOD-21, CIMP-MOD-22, CIMP-MOD-23, CIMP-MOD-24, CIMP-MOD-25
- Outputs: scripts/validate_repository_organization.py, docs/task_boards/complaint_repository_reorganization_completion_contract.json, tests/test_cimp_mod_26.py
- Submodules: 
- Validation: python -m pytest -q tests/test_cimp_mod_26.py
- Acceptance: The acceptance command checks every published interface version, the import baseline, the documentation index links, and the archive index, and it exits nonzero when any check fails. The completion contract records completion_authority false and does not mark any CIMP-MOD task complete.
- Implementation provider: grok
- Provider role: grok-only
- Model: grok-4.7
- Router: ipfs_accelerate_py.llm_router
- Provider fallback: disabled
- Runtime guidance: Implement this bounded repository-organization task on the current complaint-generator source. Constraints for this task: - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules. - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules. - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns. - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips. - Run only the declared validation command. Do not start a supervisor, server, browser, or provider. - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state. - Missing capability is an explicit unavailable result. Do not catch ImportError and report success. - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.  Task: CIMP-MOD-26 Add the repository-organization acceptance command Targets: scripts/validate_repository_organization.py, docs/task_boards/complaint_repository_reorganization_completion_contract.json, tests/test_cimp_mod_26.py Required outcomes: - The acceptance command checks every published interface version, the import baseline, the documentation index links, and the archive index, and it exits nonzero when any check fails. - The completion contract records completion_authority false and does not mark any CIMP-MOD task complete.  The validator is a read-only command. It must not edit files, start a supervisor, or write campaign state. The completion contract schema is complaint-generator/repository-reorganization-completion@1 with completion_authority false. The test runs the validator against the current tree and against a temporary broken interface version.

Implementation instructions:

> Implement this bounded repository-organization task on the current complaint-generator source.
> Constraints for this task:
> - Preserve current behavior. Add versioned facades, ownership records, and documentation. Do not rewrite applications/complaint_workspace.py, mediator/mediator.py, mediator/claim_support_hooks.py, complaint_phases/denoiser.py, document_pipeline.py, or other multi-hundred-kilobyte modules.
> - Do not edit external/, submodule gitlinks, or dependency pins. Do not run git submodule update, and do not initialize nested submodules.
> - Do not touch campaign runtime state, quarantine records, DuckDB, launcher files, attempt counters, or other campaigns.
> - Write only the declared target files. A focused pytest module must contain meaningful positive and negative cases and zero skips.
> - Run only the declared validation command. Do not start a supervisor, server, browser, or provider.
> - Public interface modules, when this task creates one, must define INTERFACE_SCHEMA = "complaint-generator/module-interface@1" and INTERFACE_VERSION = "1.0.0". They must import without starting a server or reading private workspace state.
> - Missing capability is an explicit unavailable result. Do not catch ImportError and report success.
> - The completed intake, mediator-grounding, GUI collaboration, and GUI UX boards stay historical. Do not edit them.
> 
> Task: CIMP-MOD-26 Add the repository-organization acceptance command
> Targets: scripts/validate_repository_organization.py, docs/task_boards/complaint_repository_reorganization_completion_contract.json, tests/test_cimp_mod_26.py
> Required outcomes:
> - The acceptance command checks every published interface version, the import baseline, the documentation index links, and the archive index, and it exits nonzero when any check fails.
> - The completion contract records completion_authority false and does not mark any CIMP-MOD task complete.
> 
> The validator is a read-only command. It must not edit files, start a supervisor, or write campaign state.
> The completion contract schema is complaint-generator/repository-reorganization-completion@1 with completion_authority false.
> The test runs the validator against the current tree and against a temporary broken interface version.
