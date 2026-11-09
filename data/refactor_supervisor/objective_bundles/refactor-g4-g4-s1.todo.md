# Objective Bundle: refactor/g4/g4-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-13: REF-013 Define smoke, adapter, mediator, document, and UI test lanes

## REF-013 Define smoke, adapter, mediator, document, and UI test lanes

- Status: completed
- Completion: manual
- Priority: P1
- Track: G4
- Depends on: 
- Outputs: pytest.ini, Makefile, docs/VERIFICATION_SUMMARY.md
- Validation: python -m pytest --collect-only -q
- Bundle: refactor/g4/g4-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G4.S1
- Missing evidence: The repo has many tests; refactor agents need fast confidence lanes.
- AST symbols: 
- Merge key: refactor/g4/g4-s1
- Candidate kind: seed
- Todo vector key: ref-013-definesmokeadaptermediatordocumentanduitestlanes
- Acceptance: A documented test lane map exists.; Each P0 workstream has a named validation command.

- [x] Task checkbox-14: REF-014 Add import and dependency-boundary tests for production modules

## REF-014 Add import and dependency-boundary tests for production modules

- Status: completed
- Completion: manual
- Priority: P1
- Track: G4
- Depends on: 
- Outputs: tests, pyproject.toml
- Validation: python -m pytest tests/test_package_imports.py -q
- Bundle: refactor/g4/g4-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G4.S1
- Missing evidence: Dependency drift is a recurring refactor risk.
- AST symbols: 
- Merge key: refactor/g4/g4-s1
- Candidate kind: seed
- Todo vector key: ref-014-addimportanddependency-boundarytestsforproductio
- Acceptance: Tests catch direct production imports where adapters are required.; Tests avoid blocking intentional test-only imports.
