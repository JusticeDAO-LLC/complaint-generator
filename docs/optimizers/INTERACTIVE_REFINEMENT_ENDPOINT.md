# Interactive Refinement Endpoint

Lightweight FastAPI endpoints for interactive ontology refinement preview and strategy application.

## Module

- `ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/refinement_ui_endpoint.py`

## Purpose

Expose a minimal UI/API surface for:

- Rendering a refinement preview page
- Getting strategy suggestions from `OntologyMediator`
- Previewing impact before applying a strategy
- Comparing strategy options
- Applying one or multiple strategies

## Endpoints

### UI

- `GET /refinement`
  - Returns simple HTML scaffold for preview UI.

- `GET /refinement/{ontology_id}`
  - Returns ontology-scoped UI fragment; 404 if ontology not found.

### API

- `GET /api/refinement/{ontology_id}/suggestions`
  - Uses mediator `suggest_refinement_strategy`.
  - Returns primary recommendation plus alternatives.

- `POST /api/refinement/{ontology_id}/preview`
  - Returns non-mutating impact preview payload.

- `POST /api/refinement/{ontology_id}/compare`
  - Uses mediator `compare_strategies`.

- `POST /api/refinement/{ontology_id}/apply`
  - Applies one strategy via mediator `refine_ontology`.
  - Persists updated ontology in the provided store.

- `POST /api/refinement/{ontology_id}/apply-batch`
  - Applies an ordered sequence of strategies.

## App/Router Construction

- `create_refinement_ui_router(mediator, ontology_store=None)`
- `create_refinement_ui_app(mediator, ontology_store=None)`

Both accept:

- `mediator`: `OntologyMediator`-compatible object
- `ontology_store`: mutable mapping `{ontology_id: ontology_dict}`

## Testing

Validated by:

- `ipfs_datasets_py/tests/unit/optimizers/graphrag/test_batch_337_refinement_ui_endpoint.py`

Focused run:

```bash
pytest -q ipfs_datasets_py/tests/unit/optimizers/graphrag/test_batch_337_refinement_ui_endpoint.py
```

## Notes

- This module is intentionally lightweight and framework-agnostic beyond FastAPI.
- It can be mounted into an existing FastAPI app via router inclusion.
- Default scoring for suggestions is a proxy heuristic when only ontology payload is available.
