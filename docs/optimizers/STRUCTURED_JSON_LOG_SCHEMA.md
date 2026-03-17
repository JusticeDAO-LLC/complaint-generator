# Structured JSON Log Schema (Optimizers)

_Last updated: 2026-02-25_

This document defines the canonical JSON log shape for optimizer pipelines.
Use it for GraphRAG, logic theorem, and agentic optimizer emitters.

## Required Top-Level Fields
- `timestamp`: ISO-8601 UTC timestamp string.
- `level`: one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
- `event`: stable event code (for example `PIPELINE_RUN`, `PIPELINE_BATCH`).
- `module`: python module path (for example `optimizers.graphrag.ontology_pipeline`).
- `component`: logical component name (for example `ontology_pipeline`, `query_optimizer`).
- `optimizer_type`: one of `graphrag`, `logic`, `agentic`, `common`.
- `run_id`: stable identifier for one end-to-end run.
- `schema_version`: integer schema version for log parsing compatibility.
- `message`: human-readable short summary.

## Recommended Common Fields
- `session_id`: optional session identifier when available.
- `domain`: optional domain label (`legal`, `technical`, `financial`, etc.).
- `duration_ms`: operation duration in milliseconds.
- `status`: `started`, `success`, `failed`, `partial`.
- `error_code`: stable error code for triage dashboards.

## Event-Specific Payload
- Put event-specific fields under `payload`:
  - `payload.entities_count`
  - `payload.relationships_count`
  - `payload.score_overall`
  - `payload.round_index`
- Keep `payload` JSON-serializable and stable across patch releases.

## Redaction and Safety Rules
- Never log secrets in cleartext: API keys, tokens, passwords, private keys.
- For sensitive values, emit:
  - `*_present: true/false`
  - or redacted form (`sk-...abcd`).
- Never place raw credentials in `payload`, exception messages, or stack metadata.

## Backward Compatibility Rules
- Additive fields are allowed in minor versions.
- Removing/renaming required fields requires incrementing `schema_version`.
- Dashboards/parsers must key on `(event, schema_version)`.

## Implementation Checklist
- Ensure each emitter includes all required top-level fields.
- Ensure timestamps are UTC ISO-8601.
- Ensure error paths still emit `event`, `status`, and `error_code`.
- Add/keep tests asserting required-key presence for representative events.

