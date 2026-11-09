import json
from pathlib import Path

import duckdb
import pytest

from applications.complaint_mcp_protocol import handle_jsonrpc_message, tool_list_payload
from complaint_generator import ComplaintWorkspaceService


pytestmark = [pytest.mark.no_auto_network]


def _call_mcp_tool(service: ComplaintWorkspaceService, request_id: int, tool_name: str, arguments: dict):
    response = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        },
    )
    assert response is not None
    assert "error" not in response
    result = response["result"]
    assert result["isError"] is False
    return result["structuredContent"]


def _build_evidence_db(path: Path, *, user_id: str) -> str:
    conn = duckdb.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE evidence (
                id BIGINT,
                user_id VARCHAR,
                evidence_cid VARCHAR,
                evidence_type VARCHAR,
                timestamp TIMESTAMP,
                metadata JSON,
                claim_type VARCHAR,
                claim_element_id VARCHAR,
                parsed_text_preview TEXT,
                graph_entity_count INTEGER,
                graph_relationship_count INTEGER,
                chunk_count INTEGER,
                source_url VARCHAR,
                description TEXT,
                provenance JSON
            )
            """
        )
        conn.execute(
            """
            INSERT INTO evidence VALUES
            (1, ?, 'bafy-evidence', 'document', CURRENT_TIMESTAMP, ?, 'housing_discrimination', 'causation',
             'Lease notice preview text.', 2, 1, 3, 'https://example.com/lease-notice', 'Lease notice', ?)
            """,
            [
                user_id,
                json.dumps({"title": "Lease notice", "source_family": "email"}),
                json.dumps({"source": "legacy_evidence_db"}),
            ],
        )
    finally:
        conn.close()
    return str(path)


def _build_legal_authority_db(path: Path, *, user_id: str) -> str:
    conn = duckdb.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE legal_authorities (
                id BIGINT,
                user_id VARCHAR,
                claim_type VARCHAR,
                authority_type VARCHAR,
                source VARCHAR,
                citation VARCHAR,
                title TEXT,
                content TEXT,
                url VARCHAR,
                metadata JSON,
                relevance_score FLOAT,
                timestamp TIMESTAMP,
                claim_element_id VARCHAR,
                jurisdiction VARCHAR,
                provenance JSON
            )
            """
        )
        conn.execute(
            """
            INSERT INTO legal_authorities VALUES
            (10, ?, 'housing_discrimination', 'statute', 'us_code', '42 U.S.C. § 3604',
             'Fair Housing Act', 'It shall be unlawful to discriminate in housing.', 'https://example.com/fha',
             ?, 0.91, CURRENT_TIMESTAMP, 'protected_activity', 'federal', ?)
            """,
            [
                user_id,
                json.dumps({"topic": "fair_housing"}),
                json.dumps({"source": "legacy_legal_authority_db"}),
            ],
        )
    finally:
        conn.close()
    return str(path)


def _build_claim_support_db(path: Path, *, user_id: str) -> str:
    conn = duckdb.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE claim_requirements (
                user_id VARCHAR,
                complaint_id VARCHAR,
                claim_type VARCHAR,
                element_id VARCHAR,
                element_index INTEGER,
                element_text TEXT,
                metadata JSON,
                timestamp TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE claim_support (
                id BIGINT,
                user_id VARCHAR,
                complaint_id VARCHAR,
                claim_type VARCHAR,
                claim_element_id VARCHAR,
                claim_element_text TEXT,
                support_kind VARCHAR,
                support_ref VARCHAR,
                support_label TEXT,
                source_table VARCHAR,
                support_strength FLOAT,
                metadata JSON,
                timestamp TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE claim_testimony (
                id BIGINT,
                testimony_id VARCHAR,
                user_id VARCHAR,
                claim_type VARCHAR,
                claim_element_id VARCHAR,
                claim_element_text TEXT,
                raw_narrative TEXT,
                event_date VARCHAR,
                actor_name TEXT,
                act_text TEXT,
                target_text TEXT,
                harm_text TEXT,
                firsthand_status VARCHAR,
                source_confidence FLOAT,
                metadata JSON,
                timestamp TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE claim_support_snapshot (
                id BIGINT,
                user_id VARCHAR,
                claim_type VARCHAR,
                snapshot_kind VARCHAR,
                required_support_kinds JSON,
                payload JSON,
                metadata JSON,
                timestamp TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO claim_requirements VALUES
            (?, 'cmp-1', 'housing_discrimination', 'causation', 1, 'Causation', ?, CURRENT_TIMESTAMP)
            """,
            [user_id, json.dumps({"priority": "high"})],
        )
        conn.execute(
            """
            INSERT INTO claim_support VALUES
            (21, ?, 'cmp-1', 'housing_discrimination', 'causation', 'Causation', 'document_artifact',
             'bafy-evidence', 'Lease notice support', 'evidence', 0.88, ?, CURRENT_TIMESTAMP)
            """,
            [user_id, json.dumps({"lane": "document_review"})],
        )
        conn.execute(
            """
            INSERT INTO claim_testimony VALUES
            (31, 'testimony-1', ?, 'housing_discrimination', 'protected_activity', 'Protected activity',
             'I requested a two bedroom accommodation and was refused.', '2026-02-04', 'Plaintiff',
             'Requested accommodation', 'Housing authority', 'Housing instability', 'firsthand', 0.82, ?, CURRENT_TIMESTAMP)
            """,
            [user_id, json.dumps({"source": "legacy_claim_support_db"})],
        )
        conn.execute(
            """
            INSERT INTO claim_support_snapshot VALUES
            (41, ?, 'housing_discrimination', 'support_matrix', ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                user_id,
                json.dumps(["document_artifact", "legal_authority"]),
                json.dumps({"ready_to_advance": False, "gap_count": 1}),
                json.dumps({"snapshot_source": "legacy_claim_support_db"}),
            ],
        )
    finally:
        conn.close()
    return str(path)


def test_workspace_schema_snapshot_surfaces_design_hints(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "workspace-sessions")
    user_id = "schema-user"
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Benjamin Barber",
            "opposing_party": "Housing Authority",
            "protected_activity": "Requested a two bedroom accommodation.",
            "adverse_action": "Received an eviction notice.",
            "timeline": "Request in January 2026; notice in February 2026.",
            "harm": "Housing instability and lost time.",
            "court_header": "FOR THE DISTRICT OF OREGON",
        },
    )
    service.save_evidence(
        user_id,
        kind="document",
        claim_element_id="causation",
        title="Accommodation denial email",
        content="The email said the request for a two bedroom voucher was denied.",
        source="gmail_import:msg-1",
    )
    evidence_db = _build_evidence_db(tmp_path / "evidence.duckdb", user_id=user_id)
    snapshot = service.get_workspace_data_schema(user_id, evidence_db_path=evidence_db)

    assert snapshot["schema_version"] == "workspace_data_schema.v1"
    assert snapshot["summary"]["document_count"] >= 2
    assert "source_type" in snapshot["filter_dimensions"]
    assert any(item["id"] == "dual_search_modes" for item in snapshot["ui_design_hints"])
    assert any(item["id"] == "schema_guided_filters" for item in snapshot["mcp_design_hints"])


def test_migrate_legacy_workspace_data_packages_bundle_and_tools(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "workspace-sessions")
    user_id = "migration-user"
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Benjamin Barber",
            "opposing_party": "Housing Authority of Clackamas County",
            "protected_activity": "Requested a reasonable accommodation.",
            "adverse_action": "Received an eviction notice.",
            "timeline": "Accommodation request before eviction notice.",
            "harm": "Lost housing stability.",
            "court_header": "FOR THE DISTRICT OF OREGON",
        },
    )

    evidence_db = _build_evidence_db(tmp_path / "evidence.duckdb", user_id=user_id)
    legal_db = _build_legal_authority_db(tmp_path / "legal.duckdb", user_id=user_id)
    support_db = _build_claim_support_db(tmp_path / "claim_support.duckdb", user_id=user_id)
    output_dir = tmp_path / "migration-output"

    migrated = service.migrate_legacy_workspace_data(
        user_id,
        output_dir=output_dir,
        evidence_db_path=evidence_db,
        legal_authority_db_path=legal_db,
        claim_support_db_path=support_db,
        include_car=False,
    )

    assert migrated["status"] == "success"
    assert Path(migrated["manifest_json_path"]).exists()
    assert Path(migrated["single_parquet_path"]).exists()
    assert migrated["schema_snapshot"]["summary"]["document_count"] >= 4

    tools_payload = tool_list_payload(service)
    tool_names = {tool["name"] for tool in tools_payload["tools"]}
    assert "complaint.get_workspace_data_schema" in tool_names
    assert "complaint.migrate_legacy_workspace_data" in tool_names

    mcp_schema = _call_mcp_tool(
        service,
        201,
        "complaint.get_workspace_data_schema",
        {"manifest_path": migrated["manifest_json_path"], "user_id": user_id},
    )
    assert mcp_schema["source"] == "packaged_workspace_manifest"
    assert mcp_schema["summary"]["document_count"] >= 4

    mcp_migration = _call_mcp_tool(
        service,
        202,
        "complaint.migrate_legacy_workspace_data",
        {
            "user_id": user_id,
            "output_dir": str(tmp_path / "migration-output-mcp"),
            "evidence_db_path": evidence_db,
            "legal_authority_db_path": legal_db,
            "claim_support_db_path": support_db,
            "include_car": False,
        },
    )
    assert mcp_migration["status"] == "success"
    assert Path(mcp_migration["manifest_json_path"]).exists()


def test_schema_guided_recommendations_surface_across_contracts(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "schema-guided-contracts")
    user_id = "schema-guided-user"
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Jordan Example",
            "opposing_party": "Housing Authority",
            "protected_activity": "Requested a reasonable accommodation.",
            "adverse_action": "Received an eviction notice.",
            "timeline": "Request in January 2026; notice in February 2026.",
            "harm": "Housing instability and lost time.",
            "court_header": "FOR THE DISTRICT OF OREGON",
        },
    )
    evidence_db = _build_evidence_db(tmp_path / "schema-guided-evidence.duckdb", user_id=user_id)

    tooling_contract = service.get_tooling_contract(user_id)
    workflow_capabilities = service.get_workflow_capabilities(user_id)

    assert "workspace-data-schema" in tooling_contract["cli_commands"]
    assert "migrate-legacy-workspace-data" in tooling_contract["cli_commands"]
    assert "getWorkspaceDataSchema" in tooling_contract["browser_sdk_methods"]
    assert "migrateLegacyWorkspaceData" in tooling_contract["browser_sdk_methods"]
    assert any(step["id"] == "workspace_data_schema" for step in tooling_contract["core_flow_steps"])
    assert any(step["id"] == "workspace_data_migration" for step in tooling_contract["core_flow_steps"])
    assert any(item["id"] == "workspace_schema_refresh" for item in tooling_contract["schema_guided_recommendations"])

    schema_snapshot = service.get_workspace_data_schema(user_id, evidence_db_path=evidence_db)
    assert schema_snapshot["summary"]["document_count"] >= 2
    assert any(item["id"] == "workspace_schema_refresh" for item in workflow_capabilities["schema_guided_recommendations"])
    assert workflow_capabilities["workspace_data_schema"]["schema_version"] == "workspace_data_schema.v1"


def test_search_workspace_dataset_supports_schema_filters(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "workspace-search-sessions")
    user_id = "workspace-search-user"
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Casey Example",
            "opposing_party": "Housing Authority of Clackamas County",
            "protected_activity": "Requested a reasonable accommodation.",
            "adverse_action": "Received an eviction notice.",
            "timeline": "Request in January 2026; notice in February 2026.",
            "harm": "Housing instability and lost time.",
            "court_header": "FOR THE DISTRICT OF OREGON",
        },
    )
    evidence_db = _build_evidence_db(tmp_path / "workspace-search-evidence.duckdb", user_id=user_id)
    output_dir = tmp_path / "workspace-search-output"
    migrated = service.migrate_legacy_workspace_data(
        user_id,
        output_dir=output_dir,
        evidence_db_path=evidence_db,
        include_car=False,
    )

    search_payload = service.search_workspace_dataset(
        migrated["manifest_json_path"],
        query="lease notice",
        search_backend="bm25",
        claim_type="housing_discrimination",
        claim_element_id="causation",
        source_type="workspace",
    )
    assert search_payload["source"] == "complaint_workspace_dataset_search"
    assert search_payload["applied_filters"]["claim_type"] == "housing_discrimination"
    assert search_payload["search_results"]["result_count"] >= 1

    tool_names = {tool["name"] for tool in tool_list_payload(service)["tools"]}
    assert "complaint.search_workspace_dataset" in tool_names

    mcp_search = _call_mcp_tool(
        service,
        203,
        "complaint.search_workspace_dataset",
        {
            "input_path": migrated["manifest_json_path"],
            "query": "lease notice",
            "search_backend": "bm25",
            "claim_type": "housing_discrimination",
            "claim_element_id": "causation",
        },
    )
    assert mcp_search["search_results"]["result_count"] >= 1


def test_view_workspace_dataset_supports_filtered_previews(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path / "workspace-view-sessions")
    user_id = "workspace-view-user"
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Morgan Example",
            "opposing_party": "Housing Authority of Clackamas County",
            "protected_activity": "Requested a reasonable accommodation.",
            "adverse_action": "Received an eviction notice.",
            "timeline": "Request in January 2026; notice in February 2026.",
            "harm": "Housing instability and lost time.",
            "court_header": "FOR THE DISTRICT OF OREGON",
        },
    )
    evidence_db = _build_evidence_db(tmp_path / "workspace-view-evidence.duckdb", user_id=user_id)
    migrated = service.migrate_legacy_workspace_data(
        user_id,
        output_dir=tmp_path / "workspace-view-output",
        evidence_db_path=evidence_db,
        include_car=False,
    )

    view_payload = service.view_workspace_dataset(
        migrated["manifest_json_path"],
        claim_type="housing_discrimination",
        claim_element_id="causation",
        document_limit=5,
    )
    assert view_payload["source"] == "complaint_workspace_dataset_view"
    assert view_payload["applied_filters"]["claim_type"] == "housing_discrimination"
    assert len(view_payload["documents"]) >= 1

    mcp_view = _call_mcp_tool(
        service,
        204,
        "complaint.view_workspace_dataset",
        {
            "input_path": migrated["manifest_json_path"],
            "claim_type": "housing_discrimination",
            "claim_element_id": "causation",
            "document_limit": 5,
        },
    )
    assert len(mcp_view["documents"]) >= 1
