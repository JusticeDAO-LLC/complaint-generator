"""Bounded, reproducible local alignment validation; no live network/models."""
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

os.environ.update(
    HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1',
    COMPLAINT_GENERATOR_ENABLE_IPFS_KIT='0',
)

def deny_network(*args, **kwargs):
    raise RuntimeError('Live network forbidden during alignment validation')

socket.create_connection = deny_network
socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network

import pytest

files = [
    'tests/test_complaint_mcp_streamable_http.py',
    'tests/test_complaint_mcp_sdk_contract.py',
    'tests/test_upstream_alignment_contract.py',
    'tests/test_upstream_drift_inventory.py',
    'tests/test_ipfs_adapter_import_boundary.py',
    'tests/test_ipfs_adapter_layer.py',
    'tests/test_multimedia_adapter.py',
    'tests/test_ipfs_logic_adapter.py',
    'tests/test_ipfs_kit_storage_adapter.py',
    'tests/test_accelerate_router_facade.py',
    'tests/test_multimodal_router_backend.py',
    'tests/test_agent_supervisor_jobs.py',
    'tests/test_complaint_supervisor_cli.py',
    'tests/test_alignment_runtime_contract.py',
    'tests/test_proof_report_operator_surfaces.py',
    'tests/test_alignment_watchdog.py',
    'tests/test_alignment_board_projection.py',
    'tests/test_task_board_contracts.py',
    'tests/test_integration_facade_cold_imports.py',
    'tests/test_optimizer_intake_priority.py',
    'tests/test_workflow_phase_guidance.py',
    'tests/test_formal_document_pipeline.py::test_document_api_annotation_prioritizes_document_provenance_grounding_warning',
    'tests/test_formal_document_pipeline.py::test_document_api_annotation_promotes_document_grounding_recovery_action_into_workflow_priority',
    'tests/test_formal_document_pipeline.py::test_document_api_annotation_promotes_document_grounding_improvement_next_action_into_workflow_priority',
    'tests/test_formal_document_pipeline.py::test_document_api_annotation_promotes_document_grounding_retargeting_into_workflow_priority',
]
lib_test_names = [
    'formats_node_data_roundtrip', 'formats_relationship_data_roundtrip',
    'formats_schema_data_roundtrip', 'formats_graph_data_json_roundtrip',
    'formats_iter_nodes_chunked', 'formats_iter_relationships_chunked',
    'formats_migration_format_enum_has_expected_values',
    'formats_register_and_retrieve_custom_format',
    'export_config_defaults', 'export_config_custom', 'export_result_to_dict',
    'export_result_failure_with_errors', 'export_neo4j_exporter_unavailable_without_driver',
    'export_neo4j_exporter_export_fails_without_neo4j',
]
files += ['tests/test_lib_cross_consumer_contracts.py::test_lib_knowledge_graph_' + name for name in lib_test_names]
print('\nFINAL ALIGNMENT REGRESSION: socket connections forbidden; model hubs offline.', flush=True)
print('MCP: test_complaint_mcp_streamable_http + test_alignment_runtime_contract (all 3 versions, tool listing/auth, compatibility stamp); registration setup text.', flush=True)
print('Datasets: multimedia passthrough, graph Client persistence/reopen/equal-count update, lazy legal loader, operator/import boundary, logic temporal behavior.', flush=True)
print('Storage: default-off kit gate, explicit enable construction, injected/kit/router precedence and local cache roundtrip.', flush=True)
print('Routers: all three accelerate loaders, aliases/status, multimodal fake-provider behavior.', flush=True)
print('Supervisor: all three injected jobs, draft-repair CLI available/unavailable behavior; watchdog concurrency, monitoring, timeout, and recovery tests.', flush=True)
print('Limits: storage router runtime failure returns unavailable/error by established contract; local cache used when router symbols absent.', flush=True)
sys.exit(pytest.main([
    '-q', '--run-llm', '--run-network', '--run-heavy',
    '--junitxml=.complaint_workspace/supervisor/alignment_validation.xml', *files,
]))
