"""Synthetic multi-role world for adversarial GUI isolation tests.

The fixture binds one principal store, one case directory, and one mediator
per case. Production apps are built through ``compose_case_routes``, the same
seam used by the server and review applications. Markers stay synthetic.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from types import SimpleNamespace

from applications.admin_api import OperationalAdminService
from applications.browser_sessions import (
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_api import CaseCatalog
from applications.case_assignment_api import CaseAssignmentService
from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.case_message_api import CaseMessageService
from applications.case_messages import CaseMessageStore
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from applications.review_api import create_review_api_app
from applications.server import SERVER
from integrations.private_collaboration import CaseResourceKeyGrantStore

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
ADMIN_CREDENTIAL = "synthetic-api-key"
STRANGER_CREDENTIAL = "synthetic-access-token"
OWNER_MARKER = "synthetic-owner-marker"
STRANGER_MARKER = "synthetic-stranger-marker"
MESSAGE = "synthetic-message-orchid"
LAWYER_SCOPE = frozenset({"case.read", "case.review", "case.download", "case.message.send"})
NOW = 1_700_000_000


class _Mediator:
    def __init__(self, marker: str) -> None:
        self.calls: list[tuple] = []
        self.marker = marker
        self.state = self

    def get_element_proof_cards(self, user, claim_type=None):
        self.calls.append(("cards", user, claim_type))
        return {"cards": [self.marker], "user": user}

    def io_payload(self, text):
        self.calls.append(("io_payload", text))
        return {"message": "synthetic-reply", "inquiry": {"marker": self.marker}}

    def io(self, text):
        self.calls.append(("io", text))
        return "synthetic-reply"


class _Workspace:
    def __init__(self, marker: str) -> None:
        self.calls: list[tuple] = []
        self.marker = marker

    def list_mcp_tools(self):
        self.calls.append(("list_mcp_tools",))
        return {"tools": [{"name": "complaint.review_case", "description": "Synthetic case backend."}]}

    def call_mcp_tool(self, tool_name, arguments):
        self.calls.append(("call_mcp_tool", tool_name, arguments))
        return {"ok": True, "marker": self.marker}


def build_security_world(tmp_path):
    """Create isolated synthetic principals, cases, sessions, and handlers."""

    now = {"t": NOW}

    def clock():
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    admin = principals.install_server_role(role="operational_admin")
    stranger = principals.register_from_request({})
    case = cases.create_case(actor_principal_id=owner.principal_id)
    other = cases.create_case(actor_principal_id=stranger.principal_id)
    memberships = CaseMembershipStore(
        tmp_path / "memberships", key=os.urandom(32), key_id="membership-key",
        principals=principals, cases=cases, clock=clock,
    )
    key_grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants", key=os.urandom(32), key_id="resource-grant-key",
        principals=principals, cases=cases, memberships=memberships,
    )
    messages = CaseMessageStore(
        tmp_path / "messages", key=os.urandom(32), key_id="message-key",
        principals=principals, cases=cases, memberships=memberships, clock=clock,
    )
    assignments = CaseAssignmentService(
        principals=principals, cases=cases, memberships=memberships, key_grants=key_grants,
        sessions={}, clock=clock,
    )
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            ADMIN_CREDENTIAL: admin.principal_id,
            STRANGER_CREDENTIAL: stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=600,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    policy = authorizer.grant_assigned_lawyer(
        owner_principal_id=owner.principal_id,
        lawyer_principal_id=lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=set(LAWYER_SCOPE),
        expected_case_revision=case.revision,
    )
    invited = memberships.invite(
        owner_principal_id=owner.principal_id,
        member_principal_id=lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=set(LAWYER_SCOPE),
        expires_at=NOW + 900,
        expected_case_revision=case.revision,
        idempotency_key="security-invite",
    )
    accepted = memberships.accept(
        member_principal_id=lawyer.principal_id,
        grant_id=invited.grant_id,
        expected_version=invited.version,
        idempotency_key="security-accept",
    )
    owner_mediator, owner_workspace = _Mediator(OWNER_MARKER), _Workspace(OWNER_MARKER)
    stranger_mediator, stranger_workspace = _Mediator(STRANGER_MARKER), _Workspace(STRANGER_MARKER)
    owner_root = tmp_path / "owner-downloads"
    stranger_root = tmp_path / "stranger-downloads"
    owner_root.mkdir()
    stranger_root.mkdir()
    owner_document = owner_root / "owner.txt"
    stranger_document = stranger_root / "stranger.txt"
    owner_document.write_text(OWNER_MARKER, encoding="utf-8")
    stranger_document.write_text(STRANGER_MARKER, encoding="utf-8")
    handlers = CaseHandlerRegistry()

    def lawyer_key(decision):
        return (
            decision.actor_principal_id == lawyer.principal_id
            and decision.case_id == case.case_id
            and decision.membership == "assigned-lawyer"
        )

    handlers.bind(case, mediator=owner_mediator, workspace_service=owner_workspace,
                  download_root=owner_root, authorize_delegated=lawyer_key)
    handlers.bind(other, mediator=stranger_mediator, workspace_service=stranger_workspace,
                  download_root=stranger_root)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    message_service = CaseMessageService(messages)
    admin_service = OperationalAdminService(
        principals=principals, sessions=sessions, clock=clock,
        audit_principal_ids=(admin.principal_id,),
    )
    return SimpleNamespace(
        principals=principals, cases=cases, owner=owner, lawyer=lawyer, admin=admin, stranger=stranger,
        case=case, other=other, sessions=sessions, authorizer=authorizer, handlers=handlers,
        owner_mediator=owner_mediator, stranger_mediator=stranger_mediator,
        owner_workspace=owner_workspace, stranger_workspace=stranger_workspace,
        owner_document=owner_document, stranger_document=stranger_document,
        catalog=catalog, assignments=assignments, messages=message_service, admin_service=admin_service,
        policy_revision=policy.revision, grant_id=accepted.grant_id, grant_version=accepted.version,
        now=now,
    )


def compose_security_app(world):
    """Mount workspace, review, download, messages, and admin on one seam."""

    from fastapi import FastAPI

    app = FastAPI()
    compose_case_routes(
        app,
        authorizer=world.authorizer,
        mediator=world.owner_mediator,
        browser_sessions=world.sessions,
        case_handlers=world.handlers,
        case_catalog=world.catalog,
        case_assignments=world.assignments,
        case_messages=world.messages,
        operational_admin=world.admin_service,
    )
    return app


def server_app(world):
    """Legacy and workspace server sharing the same owners."""

    return SERVER(
        world.owner_mediator, world.authorizer,
        browser_sessions=world.sessions, case_handlers=world.handlers, case_catalog=world.catalog,
    ).app


def review_app(world):
    """Review application sharing the same owners."""

    return create_review_api_app(
        world.owner_mediator, world.authorizer,
        browser_sessions=world.sessions, case_handlers=world.handlers, case_catalog=world.catalog,
    )


def case_headers(case, action=None, *, revision=None, membership_revision=None, extra=None):
    values = {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision if revision is None else revision),
    }
    if action is not None:
        values["x-case-action"] = action
    if membership_revision is not None:
        values["x-expected-membership-revision"] = str(membership_revision)
    if extra:
        values.update(extra)
    return values


def login(client, credential):
    from applications.browser_sessions import SESSION_COOKIE

    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    body = response.json()
    return body["csrf_token"], body


def csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


@contextmanager
def open_browser(tmp_path, app):
    """Qualified Task02 Chromium. Same-origin HTTP is dispatched into ``app``."""

    from tests import gui_native_browser as browser

    denial = browser.probe_inherited_network_denial()
    bridge = browser.SameOriginAsgiBridge(app)
    node, chromium = browser.pin_executables()
    os.environ["PLAYWRIGHT_NODEJS_PATH"] = node.path
    profile = tmp_path / "security-browser-profile"
    profile.mkdir(mode=0o700)
    playwright = None
    context = None
    observed = set()
    try:
        playwright = browser._load_sync_playwright()().start()
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        browser._assert_process_custody(node, chromium, profile)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(20000)
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        yield SimpleNamespace(
            page=page, context=context, bridge=bridge, playwright=playwright,
            chromium_path=chromium.path, browser=browser, node=node, observed=observed,
            network_denial=denial,
        )
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()
        cleanup = browser._wait_for_cleanup(observed)
        if not cleanup["cleaned"]:
            raise browser.BrowserCapabilityError("owned Chromium/Node descendants did not quiesce")
