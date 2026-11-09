"""Actual source-derived requirements remain distinct from user statements.

Synthetic source bytes enter at the explicit local corpus I/O boundary. Source
verification, typed dependency construction, encrypted workflow storage, browser
sessions and current owner authorization remain the real implementations.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import pytest

from applications.case_access import ASSIGNED_LAWYER_ACTIONS
from applications.graph_api import LegalDependencyGraphError, project_law_derived_dependency_graph
from complaint_phases.dependency_graph import Dependency, DependencyNode, DependencyType, NodeType
from integrations.ipfs_datasets.types import build_user_assertion_envelope
from tests.test_authority_dependency_pipeline import _CONTEXT, _source_record
from tests.test_gui27_typed_law_projection import _actual
from tests.test_cimp_gui_14 import _composed_case_world, _composed_headers, _composed_login

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
NARRATIVE = "My employer discriminated against me." + _CONTEXT
MODEL_TEXT = "A model claims that personal malice is always required."


def _materials(tmp_path, monkeypatch):
    source, case, graph, nodes = _actual(tmp_path, monkeypatch)
    case["user_narrative"] = NARRATIVE
    before = deepcopy(case)
    for index, (kind, text) in enumerate([
        (DependencyType.SUPPORTS, "Synthetic user received notice."),
        (DependencyType.CONTRADICTS, "Synthetic witness denies notice."),
        (DependencyType.SUPPORTS, MODEL_TEXT),
    ]):
        proof = {}
        if index < 2:
            envelope = build_user_assertion_envelope(source_text=text, source_kind="user_statement",
                message_id=f"synthetic-law-view-{index}", assertion_status="asserted",
                extractor_version="synthetic-gui27-view",
                source_span={"start": 0, "end": len(text.encode()), "text": text, "unit": "byte"})
            proof = {"user_assertion": envelope.as_dict()}
        node = DependencyNode(id=f"synthetic-view-fact-{index}", node_type=NodeType.FACT, name=text,
            attributes={"activity_status": "active", "origin": "model" if index == 2 else "user",
                        "provenance": proof})
        graph.add_node(node)
        graph.add_dependency(Dependency(id=f"synthetic-view-link-{index}", source_id=node.id,
                                        target_id=nodes[0].id, dependency_type=kind))
    return source, case, graph, before


def test_projection_keeps_admitted_rules_apart_from_narratives(tmp_path, monkeypatch):
    source, case, graph, before = _materials(tmp_path, monkeypatch)
    payload = project_law_derived_dependency_graph(case, dependency_graph=graph, case_id="synthetic-case")
    assert payload["task_id"] == "CIMP-GUI-27" and payload["admitted_count"] == 1
    assert payload["proof"] is False and payload["legal_sufficiency"] is False
    assert payload["rules_rewritten_by_user_or_model"] is False and payload["user_facts_are_not_law"] is True
    rule = payload["requirements"][0]
    assert rule["requirement"] and rule["requirement"] in source["source_text"]
    assert rule["jurisdiction"] == "OR" and rule["admitted_law"] is True
    assert rule["burden"] == "" and rule["burden_status"] == "unavailable_from_source_owner"
    assert MODEL_TEXT not in rule["requirement"] and NARRATIVE not in rule["requirement"]
    links = payload["factual_links"]
    assert any(row["link_kind"] == "supports" and row["authority_is_user_fact"] for row in links)
    assert any(row["link_kind"] == "contradicts" and row["authority_is_user_fact"] for row in links)
    model = next(row for row in links if row.get("fact_text") == MODEL_TEXT)
    assert model["authority_is_user_fact"] is False and model["effective_support"] is False
    assert all(row["rewrites_legal_rule"] is False for row in links)
    assert case == before
    empty = project_law_derived_dependency_graph({"user_narrative": NARRATIVE}, case_id="synthetic-case")
    assert empty["requirements"] == [] and empty["research_gap"] == "unresolved_current_legal_context"
    with pytest.raises(LegalDependencyGraphError) as missing:
        project_law_derived_dependency_graph(None)
    assert missing.value.code == "legal_dependency_unavailable"


def test_http_projects_actual_encrypted_owner_and_denies_policy_only_lawyer_and_rewrite(tmp_path, monkeypatch):
    from mediator.legal_authority_hooks import LegalAuthorityStorageHook

    source = _source_record("synthetic-http-rule", "notice")
    # An authored local corpus I/O fixture, not a source-admission or key guard.
    monkeypatch.setattr(LegalAuthorityStorageHook, "get_authorities_by_claim", lambda self, user_id, claim_type: [deepcopy(source)])
    world = _composed_case_world(tmp_path)
    assert world.case.tenant_id != world.owner.principal_id
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        headers = _composed_headers(world.case, csrf)
        started = client.post("/api/complaint-workspace/intake-chat", headers=headers,
                              json={"message": NARRATIVE, "interview_action": "start"})
        assert started.status_code == 200, started.text
        path = f"/api/graphs/{world.case.case_id}/legal-dependency"
        owner = client.get(path, headers=headers)
        assert owner.status_code == 200, owner.text
        assert owner.json()["admitted_count"] >= 1
        assert all(row["requirement"] in source["source_text"] for row in owner.json()["requirements"])
        rewrite = client.post(path, headers=headers, json={"requirement": MODEL_TEXT})
        assert rewrite.status_code == 400 and rewrite.json()["error"] == "narrative_not_law"
        assert client.get(path + "?case_id=synthetic-foreign", headers=headers).status_code == 403
        grant = world.authorizer.grant_assigned_lawyer(owner_principal_id=world.owner.principal_id,
            lawyer_principal_id=world.lawyer.principal_id, case_id=world.case.case_id,
            resource_id=world.case.resource_id, tenant_id=world.case.tenant_id,
            actions=set(ASSIGNED_LAWYER_ACTIONS), expected_case_revision=world.case.revision)
        _composed_login(client, "synthetic-lawyer-credential")
        delegated = _composed_headers(world.case)
        delegated["x-expected-membership-revision"] = str(grant.revision)
        lawyer = client.get(path, headers=delegated)
        assert lawyer.status_code == 403 and source["source_text"] not in lawyer.text
        _composed_login(client, "synthetic-stranger-credential")
        stranger = client.get(path, headers=_composed_headers(world.case))
        assert stranger.status_code == 403 and source["source_text"] not in stranger.text


def test_view_renders_real_source_rules_and_facts_in_separate_sections(tmp_path, monkeypatch):
    _source, case, graph, _before = _materials(tmp_path, monkeypatch)
    payload = project_law_derived_dependency_graph(case, dependency_graph=graph)
    script = r'''
const view = require(process.argv[1]);
const payload = JSON.parse(process.argv[2]);
const html = view.renderLawDerivedDependencyGraph({innerHTML:""}, payload);
const legal = html.split('data-role="factual-links"')[0];
const facts = html.split('data-role="factual-links"')[1].split('data-role="rejected-narratives"')[0];
if (!legal.includes('data-role="legal-rule"') || !legal.includes(payload.requirements[0].requirement)) process.exit(2);
if (legal.includes(payload.factual_links.find(row => row.link_kind === "supports").fact_text)) process.exit(3);
if (!facts.includes('data-link-kind="supports"') || !facts.includes('data-link-kind="contradicts"')) process.exit(4);
if (!facts.includes('data-rewrites-legal-rule="false"')) process.exit(5);
process.stdout.write("ok");
'''
    completed = subprocess.run(["node", "-e", script, str(ROOT / "static/complaint_graph_view.js"), json.dumps(payload)],
                                cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert completed.returncode == 0 and completed.stdout == "ok", completed.stderr
