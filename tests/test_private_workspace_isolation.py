"""Tenant and case isolation for private complaint workspaces.

Synthetic principals only. No live model, network, keyring, daemon, or real complaint files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.complaint_mcp_protocol import handle_jsonrpc_message
from applications.complaint_workspace import (
    ComplaintWorkspaceService,
    PrincipalRegistry,
    WorkspaceAccess,
    WorkspaceAuthorizationDenied,
    WorkspacePersistenceError,
    workspace_access_scope,
    WorkspaceAuthorizer,
    _slugify_user_id,
    principal_namespace,
)
from applications.complaint_workspace_api import create_complaint_workspace_router
from complaint_generator.workspace import set_privacy_policy, start_session

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ALICE = "alice/bob"
BOB = "alice bob"
MARKER = "SYNTHETIC_PRIVATE_MARKER_cimp_priv_002"
OTHER_MARKER = "SYNTHETIC_OTHER_MARKER_cimp_priv_002"


class _DenyAll(WorkspaceAuthorizer):
    def __call__(self, requirement, context) -> bool:
        return False


_FIXTURE_PASSPHRASE = "synthetic isolation fixture protection phrase"


def _service(root: Path, access: WorkspaceAccess, authorizer=None, *, users=()) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root_dir=root, access=access, authorizer=authorizer)
    if access.trust == "unauthenticated" or authorizer is not None:
        return service  # Refusal subjects need no private key capability.
    with workspace_access_scope(WorkspaceAccess.trusted_local()):
        if service.private_key_status()["status"] == "absent":
            service.initialize_private_keys(protection="passphrase", passphrase=_FIXTURE_PASSPHRASE)
        else:
            service.unlock_private_keys(passphrase=_FIXTURE_PASSPHRASE)
        bindings = list(users)
        if access.principal_id and access.case_id:
            bindings.append((access.principal_id, access.case_id))
        for owner, case_id in bindings:
            service.ensure_private_case_key(owner, case_id)
    return service


def _plant_legacy(service: ComplaintWorkspaceService, owner: str, marker: str) -> Path:
    path = service._legacy_session_path(owner)
    path.write_text(
        json.dumps(
            {
                "user_id": owner,
                "case_id": owner,
                "intake_answers": {"party_name": marker},
            }
        ),
        encoding="utf-8",
    )
    return path


def _registry() -> PrincipalRegistry:
    registry = PrincipalRegistry()
    registry.register("token-alice", ALICE, case_id=ALICE)
    registry.register("token-bob", BOB, case_id=BOB)
    return registry


def _client(service: ComplaintWorkspaceService, registry: PrincipalRegistry | None = None, *, trusted_local: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_complaint_workspace_router(
            service,
            principal_registry=registry,
            trusted_local=trusted_local,
        )
    )
    return TestClient(app)


def test_colliding_legacy_slugs_do_not_share_namespace_or_data(tmp_path: Path) -> None:
    assert _slugify_user_id(ALICE) == _slugify_user_id(BOB)
    assert principal_namespace(ALICE) != principal_namespace(BOB)

    root = tmp_path / "sessions"
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    bob = _service(root, WorkspaceAccess.authenticated(BOB, case_id=BOB))
    legacy = _plant_legacy(alice, ALICE, MARKER)
    legacy_bytes = legacy.read_bytes()

    migrated = alice.migrate_legacy_private_session(ALICE)
    assert migrated["complete"] and migrated["private_session_verified"]
    assert migrated["source_bytes_preserved"] and not migrated["cleanup_performed"]
    alice_session = alice.get_session(ALICE)
    bob_session = bob.get_session(BOB)

    assert alice_session["session"]["intake_answers"]["party_name"] == MARKER
    assert bob_session["session"]["intake_answers"] == {}
    assert MARKER not in json.dumps(bob_session)
    assert alice._session_path(ALICE) != bob._session_path(BOB)
    successor = root / (alice._session_path(ALICE).name + ".cgpe")
    assert successor.is_file() and successor.read_bytes().startswith(b"CGPE")
    assert MARKER.encode() not in successor.read_bytes()
    assert bob._session_path(BOB).is_file()
    assert legacy.read_bytes() == legacy_bytes
    legacy_name = alice._legacy_filename(ALICE)
    assert legacy_name == f"{_slugify_user_id(ALICE)}.json"
    assert not (root / "legacy-namespace-map.json").exists()

    alice.set_privacy_policy(ALICE, "grok")
    bob.set_privacy_policy(BOB, "local")
    assert alice.get_privacy_policy(ALICE)["policy"]["processing_mode"] != bob.get_privacy_policy(BOB)["policy"]["processing_mode"]
    assert bob.get_privacy_policy(BOB)["at_rest_protection"] == "private_envelope"
    assert MARKER not in json.dumps(bob.get_privacy_policy(BOB))


def test_legacy_owner_mismatch_is_not_deserialized_or_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    legacy = _plant_legacy(alice, ALICE, MARKER)
    payload = json.loads(legacy.read_text())
    payload["user_id"] = "someone-else"
    legacy.write_text(json.dumps(payload))
    before = legacy.read_bytes()
    opened = alice.get_session(ALICE)
    assert opened["session"]["intake_answers"] == {}
    assert MARKER not in json.dumps(opened)
    assert legacy.read_bytes() == before
    assert not (root / "legacy-namespace-map.json").exists()


def test_unauthenticated_and_foreign_principals_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    owner = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    owner.submit_intake_answers(ALICE, {"party_name": MARKER})
    anonymous = _service(root, WorkspaceAccess.unauthenticated())
    foreign = _service(root, WorkspaceAccess.authenticated(BOB, case_id=BOB))
    denied_authorizer = _service(root, WorkspaceAccess.trusted_local(), authorizer=_DenyAll())

    for actor, requested in (
        (anonymous, ALICE),
        (foreign, ALICE),
        (denied_authorizer, ALICE),
    ):
        with pytest.raises(WorkspaceAuthorizationDenied) as caught:
            actor.get_session(requested)
        assert str(caught.value) == "authorization_denied"
        assert MARKER not in str(caught.value)

    copied = owner.get_session(ALICE)["session"]
    copied["user_id"] = BOB
    copied["intake_answers"] = {"party_name": OTHER_MARKER}
    owner._session_path(ALICE).write_text(json.dumps(copied), encoding="utf-8")
    with pytest.raises(WorkspaceAuthorizationDenied) as wrong_owner:
        owner.get_session(ALICE)
    assert MARKER not in str(wrong_owner.value)
    assert OTHER_MARKER not in str(wrong_owner.value)


def test_wrong_case_and_reference_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    alice.submit_intake_answers(ALICE, {"party_name": MARKER})
    alice.remember_private_reference(ALICE, cid="cid-owned", storage_key="key-owned", case_id=ALICE)
    admitted = alice.resolve_private_reference(ALICE, case_id=ALICE, cid="cid-owned", storage_key="key-owned")
    assert admitted["admitted"] is True
    assert admitted["at_rest_protection"] == "private_envelope"
    assert MARKER not in json.dumps(admitted)

    with pytest.raises(WorkspaceAuthorizationDenied) as wrong_case:
        alice.get_session(ALICE, case_id="other-case")
    assert MARKER not in str(wrong_case.value)

    with pytest.raises(WorkspaceAuthorizationDenied):
        alice.resolve_private_reference(ALICE, case_id=ALICE, cid="cid-foreign")
    with pytest.raises(WorkspaceAuthorizationDenied):
        alice.resolve_private_reference(ALICE, case_id="other-case", storage_key="key-owned")

    soft = alice.get_privacy_policy(ALICE, case_id="other-case")
    assert soft["load"]["admitted"] is False
    assert soft["at_rest_protection"] == "private_envelope"
    assert MARKER not in json.dumps(soft)

    bob = _service(root, WorkspaceAccess.authenticated(BOB, case_id=BOB))
    with pytest.raises(WorkspaceAuthorizationDenied):
        bob.resolve_private_reference(ALICE, case_id=ALICE, cid="cid-owned", storage_key="key-owned")


def test_traversal_and_symlink_escape_do_not_read_or_write(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text(MARKER, encoding="utf-8")
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    namespace = alice._session_path(ALICE)
    if namespace.exists() or namespace.is_symlink():
        namespace.unlink()
    namespace.symlink_to(secret)

    with pytest.raises(WorkspaceAuthorizationDenied) as symlink_read:
        alice.get_session(ALICE)
    assert MARKER not in str(symlink_read.value)
    assert secret.read_text(encoding="utf-8") == MARKER

    namespace.unlink()
    alice.write_contained_workspace_file(ALICE, "owned-note.txt", b"owned-note")
    private_root = root / 'private-files' / f'p-{principal_namespace(ALICE)}' / f'c-{principal_namespace(ALICE)}'
    escape = private_root / "escape"
    escape.symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceAuthorizationDenied):
        alice.read_contained_workspace_file(ALICE, "escape/secret.txt")
    with pytest.raises(WorkspaceAuthorizationDenied):
        alice.write_contained_workspace_file(ALICE, "../outside/secret.txt", b"overwritten")
    with pytest.raises(WorkspaceAuthorizationDenied):
        alice.write_contained_workspace_file(ALICE, "escape/secret.txt", b"overwritten")
    assert secret.read_text(encoding="utf-8") == MARKER

    written = alice.write_contained_workspace_file(ALICE, "note.txt", b"owned-note")
    assert written["at_rest_protection"] == "private_envelope"
    assert alice.read_contained_workspace_file(ALICE, "note.txt") == b"owned-note"


def test_http_mcp_and_facade_authorization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "sessions"
    service = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    service.submit_intake_answers(ALICE, {"party_name": MARKER})
    registry = _registry()
    client = _client(service, registry)

    denied = client.get("/api/complaint-workspace/session", params={"user_id": ALICE})
    assert denied.status_code == 403
    assert MARKER not in denied.text

    forged = client.get(
        "/api/complaint-workspace/session",
        params={"user_id": BOB},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert forged.status_code == 403
    assert MARKER not in forged.text

    allowed = client.get(
        "/api/complaint-workspace/session",
        params={"user_id": ALICE},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["session"]["intake_answers"]["party_name"] == MARKER
    assert allowed.json()["session"]["user_id"] == ALICE

    wrong_case = client.get(
        "/api/complaint-workspace/session",
        params={"user_id": ALICE, "case_id": "other-case"},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert wrong_case.status_code == 403
    assert MARKER not in wrong_case.text

    export_denied = client.get(
        "/api/complaint-workspace/export/download",
        params={"user_id": BOB, "output_format": "json"},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert export_denied.status_code == 403
    assert MARKER not in export_denied.text

    export_ok = client.get(
        "/api/complaint-workspace/export/download",
        params={"user_id": ALICE, "output_format": "json"},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert export_ok.status_code == 200
    assert MARKER in export_ok.text

    monkeypatch.setenv("COMPLAINT_MCP_AUTH_TOKEN", "generic-token")
    generic_call = client.post(
        "/api/complaint-workspace/mcp/call",
        json={"tool_name": "complaint.start_session", "arguments": {"user_id": ALICE}},
        headers={"Authorization": "Bearer generic-token"},
    )
    assert generic_call.status_code == 200
    assert generic_call.json()["isError"] is True
    assert generic_call.json()["error"] == "authorization_denied"
    assert MARKER not in generic_call.text

    generic_rpc = client.post(
        "/api/complaint-workspace/mcp/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "complaint.start_session", "arguments": {"user_id": ALICE, "case_id": ALICE}},
        },
        headers={"Authorization": "Bearer generic-token"},
    )
    assert generic_rpc.status_code == 200
    assert generic_rpc.json()["result"]["isError"] is True
    assert MARKER not in generic_rpc.text

    monkeypatch.delenv("COMPLAINT_MCP_AUTH_TOKEN", raising=False)
    owned_call = client.post(
        "/api/complaint-workspace/mcp/call",
        json={"tool_name": "complaint.start_session", "arguments": {"user_id": ALICE, "case_id": ALICE}},
        headers={"Authorization": "Bearer token-alice"},
    )
    assert owned_call.status_code == 200
    assert owned_call.json()["session"]["intake_answers"]["party_name"] == MARKER

    owned_rpc = client.post(
        "/api/complaint-workspace/mcp/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "complaint.resolve_private_reference",
                "arguments": {"user_id": BOB, "cid": "cid-owned"},
            },
        },
        headers={"Authorization": "Bearer token-alice"},
    )
    assert owned_rpc.status_code == 200
    assert owned_rpc.json()["result"]["isError"] is True
    assert MARKER not in owned_rpc.text

    direct = handle_jsonrpc_message(
        service,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "complaint.start_session", "arguments": {"user_id": ALICE}},
        },
        access=WorkspaceAccess.unauthenticated(),
    )
    assert direct["result"]["isError"] is True
    assert MARKER not in json.dumps(direct)

    local_operator = _service(root, WorkspaceAccess.trusted_local(), users=[("local-operator", "local-operator")])
    local_client = _client(local_operator, trusted_local=True)
    local_session = local_client.get("/api/complaint-workspace/session", params={"user_id": "local-operator"})
    assert local_session.status_code == 200
    assert local_session.json()["session"]["user_id"] == "local-operator"
    assert MARKER not in local_session.text

    facade_root = tmp_path / "facade"
    facade_operator = _service(facade_root, WorkspaceAccess.trusted_local(), users=[(ALICE, ALICE), (BOB, BOB)])
    first = start_session(ALICE, service=facade_operator)
    set_privacy_policy(ALICE, "local", service=facade_operator)
    second = start_session(BOB, service=facade_operator)
    assert first["session"]["user_id"] == ALICE
    assert second["session"]["user_id"] == BOB
    assert principal_namespace(first["session"]["user_id"]) != principal_namespace(second["session"]["user_id"])
    assert MARKER not in json.dumps(second)
    listed = local_client.get("/api/complaint-workspace/mcp/tools")
    assert listed.status_code == 200


@pytest.mark.parametrize('transport', ['http', 'mcp', 'rpc', 'service'])
def test_contained_files_cannot_read_or_overwrite_another_principal(tmp_path, transport):
    root = tmp_path / 'sessions'
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    bob = _service(root, WorkspaceAccess.authenticated(BOB, case_id=BOB))
    bob.submit_intake_answers(BOB, {'party_name': OTHER_MARKER})
    target = bob._session_path(BOB)
    original = target.read_bytes()
    client = _client(alice, _registry())
    headers = {'Authorization': 'Bearer token-alice'}
    for operation in ['read', 'write']:
        args = {'user_id': ALICE, 'relative_name': target.name, 'content': 'overwrite'}
        if transport == 'service':
            with pytest.raises(WorkspaceAuthorizationDenied):
                if operation == 'read':
                    alice.read_contained_workspace_file(ALICE, target.name)
                else:
                    alice.write_contained_workspace_file(ALICE, target.name, b'overwrite')
        elif transport == 'http':
            if operation == 'read':
                response = client.get('/api/complaint-workspace/contained-file', params=args, headers=headers)
            else:
                response = client.post('/api/complaint-workspace/contained-file', json=args, headers=headers)
            assert response.status_code == 403
            assert OTHER_MARKER not in response.text
        elif transport == 'mcp':
            response = client.post('/api/complaint-workspace/mcp/call', headers=headers,
                json={'tool_name': f'complaint.{operation}_contained_file', 'arguments': args})
            assert response.json()['isError'] is True
            assert response.json()['error'] == 'authorization_denied'
        else:
            response = client.post('/api/complaint-workspace/mcp/rpc', headers=headers,
                json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                      'params': {'name': f'complaint.{operation}_contained_file', 'arguments': args}})
            assert response.json()['result']['isError'] is True
            assert response.json()['result']['content'][0]['text'] == 'authorization_denied'
        assert target.read_bytes() == original


def test_same_filename_and_case_denials_preserve_scoped_artifacts(tmp_path):
    root = tmp_path / 'sessions'
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    bob = _service(root, WorkspaceAccess.authenticated(BOB, case_id=BOB))
    alice.submit_intake_answers(ALICE, {"party_name": MARKER})
    bob.submit_intake_answers(BOB, {"party_name": OTHER_MARKER})
    alice.write_contained_workspace_file(ALICE, 'nested/note.txt', MARKER.encode())
    bob.write_contained_workspace_file(BOB, 'nested/note.txt', OTHER_MARKER.encode())
    fresh_alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    assert fresh_alice.read_contained_workspace_file(ALICE, 'nested/note.txt') == MARKER.encode()
    assert bob.read_contained_workspace_file(BOB, 'nested/note.txt') == OTHER_MARKER.encode()
    wrong_case = _service(root, WorkspaceAccess.authenticated(ALICE, case_id='foreign-case'))
    # A wrong expected case cannot authenticate the opaque session envelope.
    # Require the exact typed refusal and preservation, without adding a
    # plaintext case sidecar merely to classify cryptographic rejection.
    protected = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    for operation in (lambda: wrong_case.read_contained_workspace_file(ALICE, 'nested/note.txt'),
                      lambda: wrong_case.write_contained_workspace_file(ALICE, 'nested/note.txt', b'overwrite')):
        with pytest.raises(WorkspacePersistenceError) as refused:
            operation()
        assert refused.value.code == "authentication_failed"
        assert refused.value.public_status == "recoverable"
        assert MARKER not in str(refused.value) and OTHER_MARKER not in str(refused.value)
        assert all(path.read_bytes() == content for path, content in protected.items())
    assert fresh_alice.read_contained_workspace_file(ALICE, 'nested/note.txt') == MARKER.encode()
    assert bob.read_contained_workspace_file(BOB, 'nested/note.txt') == OTHER_MARKER.encode()
    assert not (root / 'nested').exists()


@pytest.mark.parametrize('mutation', ['root_symlink', 'root_ancestor_symlink', 'root_replaced', 'private_parent_symlink', 'leaf_hardlink'])
def test_private_file_directory_and_inode_boundaries_refuse_before_mutation(tmp_path, mutation):
    root, outside = tmp_path / 'sessions', tmp_path / 'outside'
    outside.mkdir()
    secret = outside / 'note.txt'; secret.write_text(MARKER)
    if mutation == 'root_symlink':
        root.symlink_to(outside, target_is_directory=True)
        with pytest.raises(WorkspaceAuthorizationDenied):
            _service(root, WorkspaceAccess.authenticated(ALICE))
    elif mutation == 'root_ancestor_symlink':
        alias = tmp_path / 'alias'; alias.symlink_to(outside, target_is_directory=True)
        with pytest.raises(WorkspaceAuthorizationDenied):
            _service(alias / 'sessions', WorkspaceAccess.authenticated(ALICE))
        assert not (outside / 'sessions').exists()
    else:
        alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
        alice.write_contained_workspace_file(ALICE, 'note.txt', b'owned-note')
        artifact = root / 'private-files' / f'p-{principal_namespace(ALICE)}' / f'c-{principal_namespace(ALICE)}' / 'note.txt'
        if mutation == 'root_replaced':
            root.rename(tmp_path / 'preserved-original')
            root.symlink_to(outside, target_is_directory=True)
        elif mutation == 'private_parent_symlink':
            artifact.parent.rename(artifact.parent.with_name('preserved-original'))
            artifact.parent.symlink_to(outside, target_is_directory=True)
        else:
            artifact.unlink(); os.link(secret, artifact)
        with pytest.raises(WorkspaceAuthorizationDenied):
            alice.read_contained_workspace_file(ALICE, 'note.txt')
        with pytest.raises(WorkspaceAuthorizationDenied):
            alice.write_contained_workspace_file(ALICE, 'note.txt', b'overwrite')
    assert secret.read_text() == MARKER


@pytest.mark.parametrize('record', [{}, {'user_id': BOB, 'case_id': BOB}, ['invalid'], 'invalid-json'])
def test_unowned_or_invalid_namespaced_record_is_not_relabelled_or_replaced(tmp_path, record):
    alice = _service(tmp_path, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    target = alice._session_path(ALICE)
    target.write_text(json.dumps(record) if record != 'invalid-json' else '{')
    original = target.read_bytes()
    expected = WorkspaceAuthorizationDenied if isinstance(record, dict) else WorkspacePersistenceError
    for operation in (lambda: alice.get_session(ALICE), lambda: alice._save_state({'user_id': ALICE, 'case_id': ALICE, 'intake_answers': {}})):
        with pytest.raises(expected) as refused:
            operation()
        if expected is WorkspacePersistenceError:
            assert refused.value.code == "corrupt_session"
            assert refused.value.public_status == "recoverable"
        assert target.read_bytes() == original


@pytest.mark.parametrize('path', [
    '/docket-dataset/metadata', '/docket-dataset/graph', '/docket-dataset/view',
    '/docket-dataset/search', '/workspace-dataset/view', '/workspace-dataset/search',
    '/workspace-dataset/graph', '/packaged-docket/view',
    '/packaged-docket/operator-dashboard', '/packaged-docket/operator-dashboard-report',
])
@pytest.mark.parametrize('authenticated', [False, True])
def test_path_only_http_readers_refuse_before_backend_or_foreign_file_access(tmp_path, monkeypatch, path, authenticated):
    service = _service(tmp_path / 'sessions', WorkspaceAccess.trusted_local())
    foreign = tmp_path / 'foreign.json'; foreign.write_text(MARKER)
    original = foreign.read_bytes()
    def backend_forbidden(*args, **kwargs):
        pytest.fail('unauthorized reader reached dataset backend')
    monkeypatch.setattr(service, '_load_docket_dataset_payload', backend_forbidden)
    monkeypatch.setattr(service, '_load_workspace_dataset_payload', backend_forbidden)
    client = _client(service, _registry())
    response = client.get('/api/complaint-workspace' + path,
        params={'input_path': str(foreign), 'manifest_path': str(foreign), 'input_type': 'json', 'query': 'synthetic'},
        headers={'Authorization': 'Bearer token-alice'} if authenticated else {})
    assert response.status_code == 403
    assert response.json()['detail'] == 'authorization_denied'
    assert MARKER not in response.text and str(foreign) not in response.text
    assert foreign.read_bytes() == original


@pytest.mark.parametrize('tool,args', [
    ('complaint.get_docket_dataset_metadata', {'input_path': '/foreign/private.json'}),
    ('complaint.search_email_duckdb', {'index_path': '/foreign/private.duckdb', 'query': 'synthetic'}),
    ('complaint.get_workspace_data_schema', {'manifest_path': '/foreign/manifest.json'}),
    ('complaint.migrate_legacy_workspace_data', {'output_dir': '/foreign/output'}),
    ('complaint.review_generated_exports', {'artifact_dir': '/foreign/exports'}),
    ('complaint.review_ui', {'screenshot_dir': '/foreign/screenshots'}),
    ('complaint.review_ui', {'screenshot_paths': ['/foreign/private.png']}),
])
def test_mcp_host_path_capability_is_not_granted_by_authentication(tmp_path, tool, args):
    service = _service(tmp_path, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    with pytest.raises(WorkspaceAuthorizationDenied):
        service.call_mcp_tool(tool, {'user_id': ALICE, **args})


def test_explicit_local_dataset_operator_and_public_corpus_discovery_remain_available(tmp_path, monkeypatch):
    service = _service(tmp_path, WorkspaceAccess.trusted_local())
    payload = {'dataset_id': 'synthetic-public', 'documents': [], 'metadata': {'source': 'public-legal'}}
    monkeypatch.setattr(service, '_load_docket_dataset_payload', lambda *a, **k: payload)
    assert service.get_docket_dataset_graph('/operator-selected/public.json', input_type='json')['dataset_id'] == 'synthetic-public'
    monkeypatch.setattr(service, 'search_corpus', lambda *a, **k: {'public_corpus': True})
    from applications.complaint_workspace import workspace_access_scope
    with workspace_access_scope(WorkspaceAccess.unauthenticated()):
        assert service.call_mcp_tool('complaint.search_corpus', {'query': 'public law'}) == {'public_corpus': True}


def test_transport_errors_never_echo_backend_private_paths_or_values(tmp_path, monkeypatch):
    service = _service(tmp_path, WorkspaceAccess.trusted_local())
    def fail(*a, **k):
        raise RuntimeError(MARKER + '/foreign/private/path')
    monkeypatch.setattr(service, 'read_contained_workspace_file', fail)
    client = _client(service, _registry())
    headers = {'Authorization': 'Bearer token-alice'}
    response = client.get('/api/complaint-workspace/contained-file', params={'relative_name': 'note.txt'}, headers=headers)
    assert response.status_code == 500 and response.json()['detail'] == 'workspace_operation_failed'
    assert MARKER not in response.text and '/foreign/private/path' not in response.text
    for endpoint, payload in [
        ('/mcp/call', {'tool_name': 'complaint.read_contained_file', 'arguments': {'relative_name': 'note.txt'}}),
        ('/mcp/rpc', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'complaint.read_contained_file', 'arguments': {'relative_name': 'note.txt'}}}),
    ]:
        response = client.post('/api/complaint-workspace' + endpoint, json=payload, headers=headers)
        assert 'workspace_operation_failed' in response.text
        assert MARKER not in response.text and '/foreign/private/path' not in response.text


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink"])
def test_legacy_namespace_filesystem_denials_preserve_outside_bytes(tmp_path, unsafe):
    root = tmp_path / "sessions"
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"user_id": ALICE, "case_id": ALICE, "intake_answers": {"party_name": MARKER}}))
    original = outside.read_bytes()
    legacy = alice._legacy_session_path(ALICE)
    if unsafe == "symlink":
        legacy.symlink_to(outside)
    else:
        os.link(outside, legacy)
    with pytest.raises(WorkspaceAuthorizationDenied, match="^authorization_denied$"):
        alice.get_session(ALICE)
    assert outside.read_bytes() == original
    assert legacy.read_bytes() == original
    assert not alice._session_path(ALICE).exists()
    assert not (root / (alice._session_path(ALICE).name + ".cgpe")).exists()


@pytest.mark.parametrize("corrupt", [b"{", b"[]", b"null", b'"synthetic-not-a-session"'])
def test_corrupt_legacy_namespace_remains_recoverable_without_empty_replacement(tmp_path, corrupt):
    root = tmp_path / "sessions"
    alice = _service(root, WorkspaceAccess.authenticated(ALICE, case_id=ALICE))
    legacy = alice._legacy_session_path(ALICE)
    legacy.write_bytes(corrupt)
    with pytest.raises(WorkspacePersistenceError) as refused:
        alice.get_session(ALICE)
    assert refused.value.code == "corrupt_session"
    assert refused.value.public_status == "recoverable"
    assert MARKER not in str(refused.value)
    assert legacy.read_bytes() == corrupt
    assert not alice._session_path(ALICE).exists()
    assert not (root / (alice._session_path(ALICE).name + ".cgpe")).exists()
