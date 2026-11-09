"""Actual encrypted case owners and issued browser sessions for security checks.

The original transport probes remain useful for route admission. This fixture
uses the real workspace, mediator, recipient grants, key sessions and review
service for every positive admission. All case material is authored synthetic.
"""
import os

from fastapi import FastAPI

from applications.admin_api import OperationalAdminService
from applications.browser_sessions import (BrowserSessionConfiguration,
    BrowserSessionService, PrincipalStoreCredentialAdapter)
from applications.case_assignment_api import CaseAssignmentService
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.review_ui import attach_static_asset_routes
from applications.site_ui import attach_core_site_ui_routes
from tests.test_gui32_private_review_http import _world as review_world

ADMIN_CREDENTIAL = "synthetic-real55-admin"


def actual_security_world(tmp_path):
    world = review_world(tmp_path, actual_workspace_as_mediator=True)
    assert world.owner.principal_id != world.case.tenant_id
    world.admin = world.principals.install_server_role(role="operational_admin")
    world.sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(world.principals, {
            "synthetic-owner-credential": world.owner.principal_id,
            "synthetic-stranger-credential": world.stranger.principal_id,
            "synthetic-lawyer-credential": world.lawyer.principal_id,
            ADMIN_CREDENTIAL: world.admin.principal_id}),
        signing_key=os.urandom(32), ttl_seconds=300), clock=lambda: world.clock["now"])
    registry = CaseHandlerRegistry()
    for case in (world.case, world.second, world.foreign):
        service = world.services[case.case_id]
        if case.case_id == world.case.case_id:
            registry.bind(case, mediator=service, workspace_service=service,
                authorize_delegated=world.reviews.authorize_bound)
        else:
            registry.bind(case, mediator=service, workspace_service=service)
    world.handlers = registry
    world.assignments = CaseAssignmentService(principals=world.principals, cases=world.cases,
        memberships=world.memberships, key_grants=world.grants,
        sessions={world.owner.principal_id: world.owner_keys,
                  world.lawyer.principal_id: world.recipient}, clock=lambda: int(world.clock['now']))
    admin = OperationalAdminService(principals=world.principals, sessions=world.sessions,
        clock=lambda: int(world.clock['now']))
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=registry, case_reviews=world.reviews, case_assignments=world.assignments,
        operational_admin=admin, include_review=False, include_document=False)
    attach_static_asset_routes(app)
    attach_core_site_ui_routes(app)
    world.review_app = app
    return world
