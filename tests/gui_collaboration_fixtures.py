"""Compact synthetic worlds for offline and unavailable GUI outcomes.

The original recipes isolate failure mapping with explicit in-process
collaborators. Actual owner/recipient HTTP and Chromium cases below use the
existing real encrypted fixture worlds instead of those unit collaborators.
"""

from __future__ import annotations

import base64
import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI

from applications.browser_sessions import (
    BrowserSessionConfiguration,
    BrowserSessionService,
    VerifiedPrincipal,
)
from applications.case_directory import CaseDirectory
from applications.case_routes import compose_case_routes
from applications.case_storage_api import CaseStorageService
from applications.principal_store import PrincipalStore
from integrations.ipfs_datasets.llm import (
    build_complaint_privacy_context,
    clear_remote_invocation_bindings,
    privacy_policy_for_mode,
)
from integrations.private_storage import UserOwnedKeySession
from mediator.hook_runtime import clear_gui_inference_holds, source_binding_hash

OWNER = "owner-57"
CASE = "case-57"
SESSION = "session-57"
GRAPH = "graph-57"
PASSPHRASE = "synthetic-passphrase-57"
SECRET = b"synthetic-ciphertext-57"


def actual_unavailable_world(tmp_path):
    """Real actor, canonical case, encrypted workspace and persisted consent.

    No model transport, storage service, corpus, or proof producer is injected.
    The app and all positive private reads are the actual production owners.
    """
    from applications.case_consent_api import CaseConsentService
    from tests.test_cimp_gui_14 import _composed_case_world
    world = _composed_case_world(tmp_path)
    world.service = world.services[world.case.case_id]
    world.app.state.case_consent = CaseConsentService(tmp_path / 'actual-consent',
        cases=world.cases, key=os.urandom(32), key_id='synthetic-unavailable-consent',
        clock=lambda: 1_700_000_100)
    return world


def choose_actual_purpose(client, world, csrf_token, purpose, *, cloud=False):
    path = '/api/cases/' + world.case.case_id + '/processing-consent'
    current = client.get(path)
    assert current.status_code == 200, current.text
    body = {'purpose': purpose, 'mode': 'grok_cloud' if cloud else 'local_private',
        'expected_generation': current.json()['generation']}
    if cloud:
        body['explicit_case_purpose'] = True
    response = client.post(path, headers={'x-csrf-token': csrf_token}, json=body)
    assert response.status_code == 200, response.text
    return response.json()


class Kit:
    """In-process Kit stand-in. Failures stay on the methods the storage owner calls."""

    def __init__(self, *, corrupt: bool = False, offline: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.calls: list[str] = []
        self.corrupt = corrupt
        self.offline = offline
        self._n = 0

    def manifest(self, data: bytes) -> dict[str, object]:
        self.calls.append("manifest")
        if self.offline:
            raise OSError("backend offline")
        self._n += 1
        ref = f"kit-57-{self._n}"
        self.objects[ref] = bytes(data)
        return {"ref": ref, "state": "local_commit"}

    def queue_replication(self, ref: str) -> dict[str, object]:
        self.calls.append("queue_replication")
        return {"ref": ref, "state": "queued"}

    def pin(self, ref: str) -> dict[str, object]:
        self.calls.append("pin")
        return {"ref": ref, "pinned": True}

    def readback(self, ref: str) -> bytes:
        self.calls.append("readback")
        if self.corrupt:
            return b"not-ciphertext"
        return self.objects[ref]


class _Adapter:
    def __init__(self, principals: dict[str, VerifiedPrincipal]) -> None:
        self.principals = principals

    def verify_credential(self, material: dict) -> VerifiedPrincipal:
        principal = self.principals.get(str(material.get("credential") or ""))
        if principal is None:
            raise RuntimeError("authentication_failed")
        return principal


def reset_inference_bindings() -> None:
    clear_gui_inference_holds()
    clear_remote_invocation_bindings()


def storage_world(tmp_path: Path, kit: Kit | None = None, *, with_key: bool = True) -> dict:
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key-57")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key-57")
    owner = principals.register_from_request({})
    case = cases.create_case(actor_principal_id=owner.principal_id)
    sessions: dict[str, UserOwnedKeySession] = {}
    if with_key:
        session = UserOwnedKeySession(tmp_path / "owner-keys")
        session.create(protection="passphrase", passphrase=PASSPHRASE)
        session.ensure_data_key(case.tenant_id, case.case_id)
        sessions[owner.principal_id] = session
    service = CaseStorageService(cases, sessions, kit or Kit())
    return {"owner": owner, "case": case, "service": service, "kit": service._kit}


def storage_body(world: dict, *, idempotency_key: str, content: bytes = SECRET) -> dict:
    case = world["case"]
    return {
        "tenant_id": case.tenant_id,
        "case_id": case.case_id,
        "resource_id": case.resource_id,
        "revision": "r57",
        "idempotency_key": idempotency_key,
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


def authenticated_storage_app(world: dict, *, mount_storage: bool):
    case = world["case"]
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=_Adapter({
            "synthetic-owner-57": VerifiedPrincipal(world["owner"].principal_id, case.tenant_id, ("complainant",)),
        }),
        signing_key=os.urandom(32),
        ttl_seconds=600,
    ))
    app = FastAPI()
    compose_case_routes(
        app,
        authorizer=None,
        browser_sessions=sessions,
        case_storage=world["service"] if mount_storage else None,
        include_workspace=False,
        include_review=False,
        include_document=False,
    )
    return app


def source_bindings(text: str = "synthetic fragment 57") -> list[dict[str, str]]:
    return [{"source_id": "src-57", "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}]


def inference_bundle(*, revoked: bool = False, session_id: str = SESSION) -> dict:
    policy = privacy_policy_for_mode(OWNER, CASE, "grok")
    bindings = source_bindings()
    grant = {
        "grant_id": "grant-57",
        "case_id": CASE,
        "generation": 1,
        "source_revision": source_binding_hash(bindings),
        "revoked": revoked,
    }
    record = {
        "found": True,
        "case_match": True,
        "user_id": OWNER,
        "case_id": CASE,
        "privacy_policy": policy,
        "operation_consent": {"generation": 1, "revoked": False},
    }
    return {
        "policy_record": record,
        "grant": grant,
        "bindings": bindings,
        "privacy_context": build_complaint_privacy_context(policy, user_id=OWNER, case_id=CASE, data_class="raw_intake"),
        "legal_context": {
            "status": "explicit",
            "jurisdiction": "synthetic",
            "jurisdiction_explicit": True,
            "context_revision": 1,
        },
        "deadline": datetime.now(timezone.utc) + timedelta(minutes=5),
        "now": datetime.now(timezone.utc),
        "session_id": session_id,
        "inputs": {"source_text": "synthetic fragment 57", "target_ref": "entity-57"},
    }


def research_authority(*, revoked: bool = False):
    decision = {
        "purpose": "citation_acquisition",
        "generation": 1,
        "egress_authorized": False,
        "revoked": revoked,
        "explicit": False,
        "mode": "local_private",
        "data_class": "public_legal_source_graph",
    }

    def processing_consent(**_kwargs):
        return {"decisions": {"citation_acquisition": decision}}

    return SimpleNamespace(actor_principal_id=OWNER, case_id=CASE, processing_consent=processing_consent)


def research_mediator(*, absent_hook: bool = False, absent_law: bool = False):
    case_file: dict = {}
    mediator = SimpleNamespace(intake_case_file=case_file)

    def build_legal_acquisition_request(case_file_arg, **_kwargs):
        return {
            "ready": not absent_law,
            "selection_status": "pending" if absent_law else "selected",
            "unresolved_reasons": ["law_corpus_absent"] if absent_law else [],
            "case_file": case_file_arg,
        }

    def acquire_bounded_canonical_sources(_binding, **_kwargs):
        if absent_law:
            return {
                "status": "unavailable",
                "error_code": "missing_archive",
                "candidates": [{"model_text": True, "text": "not law"}],
                "operations": [{
                    "status": "unavailable",
                    "error_code": "missing_archive",
                    "source_family": "statute",
                    "version": "",
                    "withheld": [{"reason": "model_text"}],
                }],
            }
        return {"status": "complete", "candidates": [], "operations": []}

    if not absent_hook:
        mediator.build_legal_acquisition_request = build_legal_acquisition_request
        mediator.legal_authority_search = SimpleNamespace(
            acquire_bounded_canonical_sources=acquire_bounded_canonical_sources,
        )
    return mediator


def research_body() -> dict:
    return {
        "purpose": "citation_acquisition",
        "query": "synthetic citation 57",
        "retrieval_mode": "offline",
        "expected_consent_generation": 1,
        "operation_id": "op-57",
        "max_results": 1,
        "deadline_seconds": 1,
        "max_bytes": 256,
    }


def proof_mediator() -> SimpleNamespace:
    return SimpleNamespace(intake_case_file={})


def proof_body(*, status: str) -> dict:
    return {
        "request_id": "proof-57",
        "source_identity": "source-57",
        "legal_sufficiency": True,
        "obligations": [{
            "obligation_id": "ob-57",
            "statement": "synthetic obligation",
            "source_span": "span-57",
            "source_identity": "source-57",
            "proof_status": status,
            "engine_name": "absent-prover" if status == "missing_prover" else "named-engine",
            "engine_version": "" if status == "missing_prover" else "0",
            "prover_missing": status == "missing_prover",
            "green_checkmark": True,
        }],
    }


def owner_lawyer_journey_world(tmp_path: Path, *, previous=None):
    """Real shared owners; empty invitations/reviews, or fresh encrypted readers.

    Case/key provisioning is an operator fixture action. The test performs the
    intake, invitation, acceptance, sharing, messages and review through the
    mounted app. Reopening constructs fresh services/wallets at the same roots;
    it never copies the decrypted case, mediator, or a rendered response.
    """
    import time
    from applications.case_api import CaseCatalog
    from applications.case_access import CaseActionAuthorizer
    from applications.case_assignment_api import CaseAssignmentService
    from applications.case_consent_api import CaseConsentService
    from applications.case_membership import CaseMembershipStore
    from applications.case_message_api import CaseMessageService
    from applications.case_messages import CaseMessageStore
    from applications.case_review_store import CaseReviewService
    from applications.case_routes import CaseHandlerRegistry
    from applications.complaint_workspace import ComplaintWorkspaceService
    from applications.browser_sessions import PrincipalStoreCredentialAdapter
    from applications.review_ui import attach_static_asset_routes
    from applications.site_ui import attach_core_site_ui_routes
    from integrations.private_collaboration import CaseResourceKeyGrantStore
    from tests.test_cimp_gui_14 import PASSPHRASE

    # These keys are authored, in-memory operator fixture configuration. No
    # browser receives them, and no production key/profile is inspected.
    if previous is None:
        keys = {name: os.urandom(32) for name in
                ('principals', 'cases', 'memberships', 'grants', 'messages', 'consent', 'cookies')}
        now = {'t': int(time.time())}
    else:
        keys, now = previous.fixture_keys, previous.now
    clock = lambda: now['t']
    if previous is None:
        principals = PrincipalStore(tmp_path/'principals', key=keys['principals'], key_id='journey-principals')
        cases = CaseDirectory(tmp_path/'cases', key=keys['cases'], key_id='journey-cases')
        authorizer = CaseActionAuthorizer(principals, cases)
    else:
        # Cold scope is the workspace, wallets and encrypted domain stores,
        # not a claim that process-local operator policy became durable.
        principals, cases, authorizer = previous.principals, previous.cases, previous.authorizer
    catalog = CaseCatalog(cases, authorizer, key=keys['cases'], key_id='journey-cases')
    if previous is None:
        owner = principals.register_from_request({})
        lawyer = principals.install_server_role(role='lawyer')
        stranger = principals.register_from_request({})
        created = catalog.create(owner.principal_id, {'label':'owner-lawyer-journey'})
        case = cases.select_case(actor_principal_id=owner.principal_id, case_id=created['case_id'])
    else:
        owner, lawyer, stranger = previous.owner, previous.lawyer, previous.stranger
        case = cases.select_case(actor_principal_id=owner.principal_id, case_id=previous.case.case_id)
    service_root = tmp_path/'workspace'
    service = ComplaintWorkspaceService(root_dir=service_root)
    if previous is None:
        service.initialize_private_keys(protection='passphrase', passphrase=PASSPHRASE)
        service.ensure_private_case_key(case.tenant_id, case.case_id)
    else:
        assert service.unlock_private_keys(passphrase=PASSPHRASE)['unlocked'] is True
    owner_keys = UserOwnedKeySession(service_root/'private-keys')
    owner_keys.unlock_passphrase(PASSPHRASE)
    recipient = UserOwnedKeySession(tmp_path/'recipient-keys')
    if previous is None:
        recipient.create(protection='passphrase', passphrase='synthetic-recipient-password')
    else:
        recipient.unlock_passphrase('synthetic-recipient-password')
    wallets = {owner.principal_id:owner_keys, lawyer.principal_id:recipient}
    memberships = CaseMembershipStore(tmp_path/'memberships', key=keys['memberships'], key_id='journey-memberships',
        principals=principals, cases=cases, clock=clock)
    grants = CaseResourceKeyGrantStore(tmp_path/'grants', key=keys['grants'], key_id='journey-grants',
        principals=principals, cases=cases, memberships=memberships)
    assignments = CaseAssignmentService(principals=principals, cases=cases, memberships=memberships,
        key_grants=grants, sessions=wallets, clock=clock)
    messages = CaseMessageStore(tmp_path/'messages', key=keys['messages'], key_id='journey-messages',
        principals=principals, cases=cases, memberships=memberships, clock=clock)
    reviews = CaseReviewService(tmp_path/'reviews', cases=cases, authorizer=authorizer,
        memberships=memberships, grants=grants, sessions=wallets)
    reviews.bind_case(case, service)
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=service, workspace_service=service, authorize_delegated=reviews.authorize_bound)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            'synthetic-owner-credential':owner.principal_id,
            'synthetic-lawyer-credential':lawyer.principal_id,
            'synthetic-stranger-credential':stranger.principal_id}),
        signing_key=keys['cookies'], ttl_seconds=1800), clock=clock)
    consent = CaseConsentService(tmp_path/'consent', cases=cases, key=keys['consent'], key_id='journey-consent', clock=clock)
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        case_catalog=catalog, case_assignments=assignments, case_messages=CaseMessageService(messages),
        case_reviews=reviews, case_consent=consent, include_review=False, include_document=False)
    attach_static_asset_routes(app)
    attach_core_site_ui_routes(app)
    return SimpleNamespace(app=app, service=service, service_root=service_root, root=tmp_path,
        case=case, journey_case=case, principals=principals, cases=cases, authorizer=authorizer,
        owner=owner, lawyer=lawyer, stranger=stranger, sessions=sessions, memberships=memberships,
        grants=grants, assignments=assignments, messages=messages, reviews=reviews, recipient=recipient,
        owner_keys=owner_keys, consent=consent, now=now, fixture_keys=keys)


def workflow_case(*, corrupt_snapshot: bool = False) -> dict:
    if corrupt_snapshot:
        return {
            "workflow_domains": {
                "factual": {"status": "stale", "revision": 2, "assertions": [{"bound": False, "revision": 1}]},
                "legal": {"status": "admitted", "revision": 2, "factual_revision": 9, "authority_id": "auth-57", "governing_law": True},
                "evidence": {"status": "bound", "revision": 2, "factual_revision": 2, "legal_revision": 2, "exhibits": []},
                "proof": {"status": "executed", "result": "verified", "revision": 2, "factual_revision": 1, "evidence_revision": 1},
            },
            "workflow_checkboxes": {"ready": True},
            "draft_workflow": {"versions": [{"draft_id": "d57", "revision": 1, "domain_snapshot": {"factual": 0}}], "reviews": [], "exports": []},
        }
    return {
        "workflow_domains": {
            "factual": {"status": "current", "revision": 3, "assertions": [{"bound": True, "revision": 3}]},
            "legal": {"status": "pending", "revision": 0},
            "evidence": {},
            "proof": {"status": "not_executed"},
        },
    }
