# Mike Integration Operator Playbook

Current boundary: Mike is the editor at `external/mike`. The handoff field `mike_llm_patch` is a compatibility stamp. Grounded drafting is the MCP connector published as `mike_integration.transport = mcp_connector`. Register complaint-generator at `COMPLAINT_MCP_CONNECTOR_URL` (default `http://localhost:8000/api/complaint-workspace/mcp/rpc`) and call `complaint.generate_grounded_text`, `complaint.search_corpus`, `complaint.get_handoff`, and `complaint.sync_draft`. Sync returns `document_version_content_sha256` for the title plus body. Complaint-generator does not patch Mike's TypeScript LLM router.

This playbook defines the current end-to-end complaint drafting workflow between `complaint-generator` and the `mike` editor submodule.

## 1) Prepare the complaint workspace record

1. Start or resume a complaint workspace session (`/api/complaint-workspace/session`).
2. Complete intake and capture evidence until support review has enough signal for draft work.
3. Generate an initial draft if desired (`complaint.generate_complaint`), or allow automatic draft generation during handoff.

## 2) Hand off to Mike

Use one of the aligned surfaces below:

- MCP tool: `complaint.build_mike_handoff`
- HTTP route: `POST /api/complaint-workspace/mike/handoff`
- Browser SDK: `client.buildMikeHandoff(payload)`
- CLI: `complaint-workspace build-mike-handoff`

### Required handoff inputs

- `user_id`

### Optional handoff inputs

- `mike_base_url` (defaults to `COMPLAINT_MIKE_BASE_URL` or `http://localhost:3000`)
- `project_id`
- `workspace_id`
- `generate_draft_if_missing` (default `true`)

### Handoff outputs

- `handoff_id` (stable correlation key for roundtrip sync)
- `mike.launch_url` (ready-to-open editor URL with query params)
- `handoff_payload` containing:
  - current case synopsis
  - claim type
  - draft body/title/relief
  - support review
  - centralized `router_policy` so Mike routes assistance through Complaint Generator's LLM control plane
  - `skill_asset_manifest` so Mike can roundtrip only complaint-generator-owned skill IDs, including corpus-search, containment-policy, and authority-graph assets owned by complaint-generator
  - `grounding_mode`, `corpus_boundaries`, and `legal_corpus_context`
  - legal-corpus adapter lane metadata that keeps strict containment rooted in `integrations/ipfs_datasets/legal.py`, `search.py`, `policy_rules.py`, and `graphs.py`
  - `logic_handoff` with proof constraints, theorem-export metadata, formal predicates to preserve, and the optional Leanstral assist lane policy for unresolved proof work
  - summarized evidence context by claim element
  - `structured_legal_packet_context` with stable section/paragraph/claim IDs
  - `editor_guardrails` with unsupported elements, weak links, and contradiction hotspots
  - `submodule_inventory` and `compatibility_target_matrix` for repeatable upstream refreshes, including current `HEAD` and `origin/main` SHAs for `mike` and `ipfs_datasets_py`
  - `non_negotiable_constraints` machine-readable must-hold legal/proof invariants

## 2.5) Check integration status and next action

Use one of the aligned surfaces below:

- MCP tool: `complaint.get_mike_integration_status`
- HTTP route: `GET /api/complaint-workspace/mike/status?user_id=...`
- Browser SDK: `client.getMikeIntegrationStatus(userId)`
- CLI: `complaint-workspace mike-status`

The status payload reports:

- `status_contract_version`, `status_contract`, `workflow_state`
- `latest_handoff_id`, `latest_sync_handoff_id`
- `pending_sync`
- `has_mike_synced_draft`
- `has_citation_link_conflicts`, `citation_link_conflict_count`, `citation_link_unknown_element_count`
- `conflict_component` (conflict count, unknown element count, impact statement, required next action)
- `invariants` (pending-sync ID correlation, numeric conflict counters, required action presence)
- `recommended_action`

## 3) Edit and refine in Mike

Use `handoff_payload` as the source-of-truth seed for Mike editing.

Suggested operator behavior:

1. Keep claim framing aligned to the complaint claim type.
2. Preserve evidence-linked statements and citation anchors.
3. Track major redlines so they can be summarized on sync.

## 4) Sync finalized Mike draft back into complaint-generator

Use one of the aligned surfaces below:

- MCP tool: `complaint.sync_mike_final_draft`
- HTTP route: `POST /api/complaint-workspace/mike/sync`
- Browser SDK: `client.syncMikeFinalDraft(payload)`
- CLI: `complaint-workspace sync-mike-draft`

### Required sync inputs

- `user_id`
- `body` (final draft text)

### Optional sync inputs

- `title`
- `requested_relief`
- `handoff_id`
- `project_id`
- `workspace_id`
- `mike_document_id`
- `citation_links`
- `redline_summary`
- `source_updated_at`
- `structured_deltas` (paragraph/citation/claim/relief/metadata edit operations)
- `editor_metadata` (editor attribution/session/source transport metadata)
- `grounding_mode`
- `assertion_annotations` (grounded or unsupported substantive assertions)
- `authority_links` (retrieved legal authorities tied to assertions)
- `sync_provenance` (editor version, enabled skill assets, base-draft identity, redline metadata)

### Sync behavior

- Persists draft text into the complaint workspace session.
- Marks `draft.sync_source = "mike"` with `draft.sync_metadata`.
- Runs citation-link integrity checks and returns conflict metadata (`citation_link_check`) in the sync response.
- Runs legal-corpus grounding checks and returns `legal_corpus_review`.
- Runs prose-to-logic / theorem-export review and returns `logic_review`.
- Returns normalized `sync_provenance` so complaint-generator remains authoritative for enabled skill IDs, base-draft identity, and redline metadata after the editor roundtrip.
- Stores sync diagnostics (`sync_diagnostics`) with severity tiers and remediation guidance.
- Stores tamper-evident `sync_integrity_hash` in sync metadata and sync history.
- Updates Mike integration history (`last_handoff`, `last_sync`).
- Returns refreshed session/review payload for downstream release-gate checks.

## 5) Post-sync quality gate

After sync, run the normal complaint QA lane:

1. `complaint.review_case`
2. `complaint.analyze_complaint_output`
3. `complaint.get_client_release_gate`

If blocked, iterate in Mike and sync again using the same `handoff_id`.

## 6) Improvement backlog (next increments)

1. Add live evidence side-panel linking in Mike using `evidence_context.elements`.
2. Add redline-aware acceptance checks in release-gate scoring.
3. Add signed webhooks for push-based sync from Mike to complaint-generator.
