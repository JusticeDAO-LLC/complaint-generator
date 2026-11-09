from __future__ import annotations

from pathlib import Path

from applications import complaint_cli
from applications.complaint_workspace import ComplaintWorkspaceService
import ipfs_datasets_py.processors.legal_data as legal_data
from ipfs_datasets_py.processors.legal_data import workspace_dataset as workspace_dataset_module


def _sample_dataset() -> dict:
    return {
        "dataset_id": "dataset-1",
        "docket_id": "1:24-cv-1001",
        "case_name": "Doe v. Acme",
        "court": "D. Example",
        "documents": [
            {
                "id": "doc-1",
                "title": "Complaint",
                "text": "Fair housing complaint",
                "date_filed": "2026-01-01",
                "document_number": "1",
                "metadata": {"kind": "pleading"},
            }
        ],
        "knowledge_graph": {
            "entities": [
                {"id": "issue-1", "type": "legal_issue", "label": "Retaliation"},
                {"id": "issue-2", "type": "claim", "label": "Discrimination"},
                {"id": "doc-entity-1", "type": "document", "label": "Complaint"},
            ],
            "relationships": [
                {"id": "rel-1", "type": "supports", "source": "issue-1", "target": "issue-2"},
                {"id": "rel-2", "type": "describes", "source": "doc-entity-1", "target": "issue-1"},
            ],
        },
        "metadata": {"source": "unit-test"},
    }


def test_docket_tools_are_listed_in_mcp_surface() -> None:
    tools = ComplaintWorkspaceService().list_mcp_tools()["tools"]
    names = {tool["name"] for tool in tools}
    assert "complaint.view_docket_dataset" in names
    assert "complaint.search_docket_dataset" in names
    assert "complaint.get_docket_dataset_metadata" in names
    assert "complaint.get_docket_dataset_graph" in names


def test_workspace_can_project_metadata_and_issue_links(monkeypatch) -> None:
    service = ComplaintWorkspaceService()
    dataset = _sample_dataset()

    monkeypatch.setattr(service, "_load_docket_dataset_payload", lambda *args, **kwargs: dataset)
    monkeypatch.setattr(
        legal_data,
        "summarize_docket_dataset",
        lambda payload: {
            "dataset_id": payload["dataset_id"],
            "document_count": len(payload["documents"]),
            "knowledge_graph_entity_count": len(payload["knowledge_graph"]["entities"]),
            "knowledge_graph_relationship_count": len(payload["knowledge_graph"]["relationships"]),
        },
    )

    metadata = service.get_docket_dataset_metadata("/tmp/docket.json", input_type="json")
    graph = service.get_docket_dataset_graph("/tmp/docket.json", input_type="json")

    assert metadata["dataset_id"] == "dataset-1"
    assert metadata["metadata"]["source"] == "unit-test"
    assert graph["knowledge_graph"]["issue_entity_count"] == 2
    assert graph["knowledge_graph"]["issue_link_count"] == 2
    assert graph["knowledge_graph"]["issue_links"][0]["source_entity"]["id"] == "issue-1"


def test_workspace_dispatches_docket_search_tool(monkeypatch) -> None:
    service = ComplaintWorkspaceService()
    expected = {
        "query": "retaliation",
        "search_backend": "bm25",
        "search_results": {"result_count": 1, "results": [{"id": "doc-1"}]},
    }
    monkeypatch.setattr(service, "search_docket_dataset", lambda *args, **kwargs: expected)

    result = service.call_mcp_tool(
        "complaint.search_docket_dataset",
        {
            "input_path": "/tmp/docket.json",
            "input_type": "json",
            "query": "retaliation",
            "search_backend": "bm25",
        },
    )

    assert result == expected


def test_workspace_pdf_ingest_records_source_sha256(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nsource document bytes\n")

    monkeypatch.setattr(
        workspace_dataset_module,
        "_extract_pdf_text",
        lambda *args, **kwargs: {
            "text": "HACC must review accommodation requests.",
            "backend": "unit-test",
            "page_count": 1,
            "errors": [],
        },
    )

    dataset = workspace_dataset_module.WorkspaceDatasetBuilder().build_from_pdf_paths(
        [pdf_path],
        workspace_id="hash-workspace",
        include_knowledge_graph=False,
        include_bm25=False,
        include_vector_index=False,
        include_formal_logic=False,
    )

    metadata = dataset.documents[0].metadata
    assert metadata["sha256"]
    assert metadata["content_sha256"] == metadata["sha256"]
    assert metadata["source_digest"] == {
        "algorithm": "sha256",
        "value": metadata["sha256"],
        "file_size_bytes": pdf_path.stat().st_size,
    }


def test_workspace_dataset_graph_explorer_projects_entities_and_logic(monkeypatch) -> None:
    service = ComplaintWorkspaceService()
    dataset = {
        "dataset_id": "workspace-dataset-1",
        "workspace_id": "workspace-1",
        "workspace_name": "Workspace One",
        "source_type": "workspace",
        "documents": [
            {
                "document_id": "doc-accommodation",
                "title": "Accommodation Notice",
                "text": "HACC must provide reasonable accommodation.",
                "metadata": {"document_type": "pdf"},
            }
        ],
        "collections": [],
        "knowledge_graph": {
            "entities": [
                {"id": "doc-accommodation", "type": "document", "label": "Accommodation Notice"},
                {"id": "entity-hacc", "type": "agency", "label": "HACC"},
            ],
            "relationships": [
                {
                    "id": "rel-contains",
                    "type": "CONTAINS_DOCUMENT",
                    "source": "entity-hacc",
                    "target": "doc-accommodation",
                }
            ],
        },
        "metadata": {
            "artifact_status": {"knowledge_graph": True, "formal_logic": True},
            "artifact_provenance": {"knowledge_graph": {"backend": "test"}},
            "formal_logic_summary": {
                "deontic_statement_count": 1,
                "proof_count": 1,
                "deontic_conflict_count": 1,
            },
            "formal_logic": {
                "document_analyses": {
                    "doc-accommodation": {
                        "deontic_statements": [
                            {
                                "id": "stmt-1",
                                "entity": "HACC",
                                "modality": "obligation",
                                "action": "provide reasonable accommodation",
                                "conditions": ["tenant has a disability-related need"],
                                "exceptions": ["request is only a preference"],
                                "source_document": "doc-accommodation",
                                "source_text": "HACC must provide reasonable accommodation.",
                            },
                            {
                                "id": "stmt-2",
                                "entity": "HACC",
                                "modality": "prohibition",
                                "action": "deny reasonable accommodation without review",
                                "conditions": ["request is complete"],
                                "exceptions": [],
                                "source_document": "doc-accommodation",
                                "source_text": "HACC cannot deny reasonable accommodation without review.",
                            }
                        ],
                        "events": [
                            {
                                "id": "stmt-1:event",
                                "agent": "HACC",
                                "label": "provide reasonable accommodation",
                                "time": "",
                            },
                            {
                                "id": "stmt-2:event",
                                "agent": "HACC",
                                "label": "deny reasonable accommodation without review",
                                "time": "",
                            },
                        ],
                        "frames": [
                            {
                                "frame_id": "frame-1",
                                "object_id": "stmt-1",
                                "slots": {"document_id": "doc-accommodation"},
                            }
                        ],
                    }
                },
                "deontic_conflicts": [
                    {
                        "id": "conflict-1",
                        "severity": "high",
                        "explanation": "HACC accommodation conflict",
                    }
                ],
                "temporal_fol": {"backend": "tdfol_constructor", "formulas": ["Eventually(accommodation_reviewed)"]},
                "first_order_logic": {"backend": "fol_constructor", "formulas": ["Allowed(HACC, provide)"]},
                "deontic_cognitive_event_calculus": {"backend": "eng_dcec_wrapper", "formulas": ["Obligation(HACC, provide)"]},
                "frame_logic": {"frame-1": {"frame_id": "frame-1", "isa": "DeonticStatement"}},
                "proof_store": {
                    "proofs": {
                        "proof-1": {
                            "proof_id": "proof-1",
                            "status": "proved",
                            "query": "provide reasonable accommodation",
                            "root_conclusion": "HACC provides reasonable accommodation",
                            "proof_hash": "abc123",
                            "certificates": ["cert-1"],
                        }
                    },
                    "certificates": [
                        {
                            "certificate_id": "cert-1",
                            "backend": "groth16",
                            "format": "groth16_zksnark",
                            "theorem": "provide reasonable accommodation",
                            "assumptions": ["tenant has a disability-related need"],
                        }
                    ],
                    "summary": {"proof_count": 1},
                    "metadata": {
                        "backend": "formal_logic_proof_store",
                        "zkp_status": {
                            "available": True,
                            "backend": "groth16",
                            "backend_info": {"binary_available": True, "curve_id": "bn254"},
                        },
                    },
                },
            },
        },
    }

    monkeypatch.setattr(service, "_load_workspace_dataset_payload", lambda *args, **kwargs: dataset)

    graph = service.get_workspace_dataset_graph(
        "/tmp/workspace.parquet",
        input_type="single",
        entity_query="HACC",
        relationship_type="CONTAINS",
        limit=10,
    )

    assert graph["source"] == "complaint_workspace_dataset_graph"
    assert graph["knowledge_graph"]["matched_entity_count"] == 1
    assert graph["knowledge_graph"]["matched_relationship_count"] == 1
    assert graph["logical_flow"]["returned_statement_count"] == 2
    assert graph["logical_flow"]["statements"][0]["proof_certificate_count"] == 1
    assert graph["logical_flow"]["statements"][0]["conditions"] == ["tenant has a disability-related need"]
    assert graph["logical_flow"]["returned_event_count"] == 2
    assert graph["logical_flow"]["returned_event_flow_edge_count"] >= 4
    assert graph["logical_flow"]["deontic_status_counts"]["required"] == 1
    assert graph["logical_flow"]["deontic_status_counts"]["prohibited"] == 1
    assert graph["logical_flow"]["deontic_analysis"][1]["status"] == "prohibited"
    assert graph["logical_flow"]["returned_conflict_count"] == 1
    assert graph["logical_flow"]["formulas"]["temporal_fol"] == ["Eventually(accommodation_reviewed)"]
    assert graph["logical_flow"]["logic_systems"]["deontic_temporal_first_order_logic"]["backend"] == "tdfol_constructor"
    assert graph["logical_flow"]["logic_systems"]["first_order_logic"]["sample"] == ["Allowed(HACC, provide)"]
    assert graph["logical_flow"]["logic_systems"]["deontic_cognitive_event_calculus"]["backend"] == "eng_dcec_wrapper"
    assert graph["logical_flow"]["proof_system"]["zero_knowledge_proofs"]["available"] is True
    assert graph["logical_flow"]["proof_system"]["zero_knowledge_proofs"]["backend"] == "groth16"
    assert graph["logical_flow"]["proof_system"]["certificate_backend_counts"]["groth16"] == 1
    assert graph["logical_flow"]["statements"][0]["proof_status"] == "proved"
    assert graph["logical_flow"]["statements"][0]["proof_backends"] == ["groth16"]
    assert graph["logical_flow"]["statements"][0]["zkp_certificate_ids"] == ["cert-1"]

    prohibited = service.get_workspace_dataset_graph(
        "/tmp/workspace.parquet",
        input_type="single",
        entity_query="HACC",
        modality="prohibited",
        limit=10,
    )
    assert prohibited["logical_flow"]["returned_statement_count"] == 1
    assert prohibited["logical_flow"]["deontic_analysis"][0]["event"] == "deny reasonable accommodation without review"


def test_cli_docket_graph_command_uses_workspace_service(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        complaint_cli.service,
        "get_docket_dataset_graph",
        lambda input_path, input_type="packaged": {
            "input_path": input_path,
            "input_type": input_type,
            "knowledge_graph": {"issue_link_count": 3},
        },
    )

    complaint_cli.docket_graph("/tmp/bundle_manifest.json", input_type="packaged")
    rendered = capsys.readouterr().out

    assert '"issue_link_count": 3' in rendered
