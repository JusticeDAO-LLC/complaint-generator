"""Request-scoped case authority from real browser and case-policy owners.

This is an in-process capability, never a request document or a key grant.
The actor remains the browser principal. Only a freshly verified case owner
may use the workspace's canonical owner key; delegated policy alone cannot.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from weakref import WeakSet

from .browser_sessions import BrowserSessionService
from .case_access import AuthorizationDecision, CaseActionAuthorizer


class WorkspaceCaseAuthorityError(PermissionError):
    pass


_ISSUED: WeakSet = WeakSet()
_CURRENT: ContextVar = ContextVar("workspace_case_authority", default=None)


@dataclass(frozen=True, eq=False)
class WorkspaceCaseAuthority:
    _decision: AuthorizationDecision = field(repr=False)
    _authorizer: CaseActionAuthorizer = field(repr=False)
    _sessions: BrowserSessionService = field(repr=False)
    _token: str = field(repr=False)
    _generation: int = field(repr=False)
    _registry: Any = field(repr=False)
    _workspace: Any = field(repr=False)
    _case_consent: Any = field(default=None, repr=False)
    _inference_transport: Any = field(default=None, repr=False)

    @property
    def case_id(self):
        return self._decision.case_id

    @property
    def actor_principal_id(self):
        return self._decision.actor_principal_id

    @property
    def canonical_owner_principal_id(self):
        return self._decision.canonical_owner_principal_id

    @property
    def resource_id(self):
        return self._decision.resource_id

    @property
    def action(self):
        return self._decision.action

    def processing_consent(self, *, purpose, actor_principal_id, workspace):
        """Read the configured case owner, never a request-supplied policy."""
        from .case_consent_api import CaseConsentService, PURPOSE_DATA_CLASS
        self.revalidate(actor_principal_id=actor_principal_id, workspace=workspace, require_owner=True)
        if purpose not in PURPOSE_DATA_CLASS or not isinstance(self._case_consent, CaseConsentService):
            raise WorkspaceCaseAuthorityError("case_processing_consent_unavailable")
        def verify():
            self.revalidate(actor_principal_id=actor_principal_id, workspace=workspace, require_owner=True)
        view = self._case_consent.read(actor_principal_id, self.case_id,
            authorizer=self._authorizer, verify_session=verify)
        verify()
        if (view.get("case_id") != self.case_id or view.get("tenant_id") != self._decision.tenant_id
                or view.get("owner_principal_id") != actor_principal_id):
            raise WorkspaceCaseAuthorityError("case_processing_consent_mismatch")
        return view

    def inference_transport(self, *, actor_principal_id, workspace):
        self.revalidate(actor_principal_id=actor_principal_id, workspace=workspace, require_owner=True)
        return self._inference_transport

    def inference_session_binding(self, *, actor_principal_id, workspace):
        """Opaque binding; the received browser credential is never returned."""
        import hashlib
        self.revalidate(actor_principal_id=actor_principal_id, workspace=workspace, require_owner=True)
        return hashlib.sha256(self._token.encode()).hexdigest()

    def revalidate(self, *, actor_principal_id, workspace=None, require_owner=False):
        if type(self) is not WorkspaceCaseAuthority or self not in _ISSUED:
            raise WorkspaceCaseAuthorityError("unissued_workspace_case_authority")
        if workspace is not None and workspace is not self._workspace:
            raise WorkspaceCaseAuthorityError("workspace_case_handler_mismatch")
        try:
            bound = self._sessions.authenticate_token(self._token)
            expected = self._decision
            if bound.principal_id != actor_principal_id or bound.principal_id != expected.actor_principal_id:
                raise WorkspaceCaseAuthorityError("workspace_case_actor_mismatch")
            if bound.generation != self._generation:
                raise WorkspaceCaseAuthorityError("workspace_case_session_changed")
            current = self._authorizer.authorize(boundary=expected.boundary,
                actor_principal_id=bound.principal_id, tenant_id=expected.tenant_id,
                case_id=expected.case_id, resource_id=expected.resource_id,
                action=expected.action, expected_revision=expected.revision,
                expected_membership_revision=expected.membership_revision)
            if current.without_boundary() != expected.without_boundary():
                raise WorkspaceCaseAuthorityError("workspace_case_authorization_changed")
            if self._registry.resolve(current)[1] is not self._workspace:
                raise WorkspaceCaseAuthorityError("workspace_case_handler_changed")
            if (require_owner and (current.membership != "owner" or not current.permits_case_content
                    or current.canonical_owner_principal_id != current.tenant_id)):
                raise WorkspaceCaseAuthorityError("workspace_owner_key_required")
            return current
        except WorkspaceCaseAuthorityError:
            raise
        except Exception:
            raise WorkspaceCaseAuthorityError("workspace_case_authorization_unavailable") from None


def issue_workspace_case_authority(*, authorizer, sessions, token, decision, registry,
                                   case_consent=None, inference_transport=None):
    from .case_routes import CaseHandlerRegistry
    if (not isinstance(authorizer, CaseActionAuthorizer)
            or not isinstance(sessions, BrowserSessionService)
            or type(decision) is not AuthorizationDecision
            or not isinstance(registry, CaseHandlerRegistry)):
        raise WorkspaceCaseAuthorityError("workspace_case_authority_owners")
    try:
        bound = sessions.authenticate_token(token)
        workspace = registry.resolve(decision)[1]
        authority = WorkspaceCaseAuthority(decision, authorizer, sessions, token,
            bound.generation, registry, workspace, case_consent, inference_transport)
        _ISSUED.add(authority)
        authority.revalidate(actor_principal_id=bound.principal_id, workspace=workspace)
        return authority
    except WorkspaceCaseAuthorityError:
        raise
    except Exception:
        raise WorkspaceCaseAuthorityError("workspace_case_authority_unavailable") from None


def current_workspace_case_authority():
    value = _CURRENT.get()
    if value is not None and (type(value) is not WorkspaceCaseAuthority or value not in _ISSUED):
        raise WorkspaceCaseAuthorityError("unissued_workspace_case_authority")
    return value


@contextmanager
def workspace_case_authority_scope(authority):
    if authority is not None and (type(authority) is not WorkspaceCaseAuthority or authority not in _ISSUED):
        raise WorkspaceCaseAuthorityError("unissued_workspace_case_authority")
    token = _CURRENT.set(authority)
    try:
        yield
    finally:
        _CURRENT.reset(token)
        if authority is not None:
            _ISSUED.discard(authority)
