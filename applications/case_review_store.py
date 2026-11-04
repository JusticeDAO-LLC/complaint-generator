"""Recipient-scoped encrypted lawyer reviews, with explicit owner sharing.

The owner authenticates the real joined snapshot once when sharing it. A
recipient subsequently uses only their own key session and issued grants.
The current joined-head hash is a drift precondition, never law/proof authority.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
import base64
import fcntl
import hashlib
import json
import os
import stat
import uuid
from urllib.parse import urlencode

from applications.case_access import AuthorizationDecision, CaseActionAuthorizer
from applications.case_directory import CaseDirectory, CaseNamespace
from applications.case_membership import CaseMembershipStore
from applications.complaint_workspace import ComplaintWorkspaceService
from applications.workspace_case_authority import WorkspaceCaseAuthority
from integrations.private_collaboration import CaseResourceKeyGrantStore
from integrations.private_storage import (UserOwnedKeySession, PrivateArtifactBinding,
    open_private_artifact, seal_private_artifact, read_private_revision,
    private_revision_source_scope)

SOURCE_KIND = 'case-review-source'
REVIEW_KIND = 'case-review'
REVIEW_ARTIFACT_REVISION = 'review-v1'
_DRAFT_SUGGESTION_OPERATIONS = {'propose_bounded_change','record_draft_model_suggestion','record_draft_machine_proof'}
_SUGGESTION_ERROR = {
    'draft_field':'lawyer_review_field','draft_bounds':'lawyer_review_bounds',
    'actor_not_permitted':'lawyer_assignment_required','draft_revision_required':'proposal_required',
    'proposal_required':'proposal_required','stale_revision':'stale_revision','replay_mismatch':'replay_mismatch',
}
_LIMIT = 4 * 1024 * 1024
_LOCKS = {}
_LOCKS_GUARD = RLock()


class CaseReviewStoreError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _suggestion_rows(collaborative):
    stored = collaborative.get('draft_suggestion_records') if isinstance(collaborative, dict) and isinstance(collaborative.get('draft_suggestion_records'), dict) else {}
    rows = []
    for key in ('human_reviews','model_suggestions','machine_proofs','messages','acceptances'):
        rows.extend(row for row in stored.get(key) or [] if isinstance(row, dict))
    return rows


def _suggestion_error(exc):
    code = _SUGGESTION_ERROR.get(getattr(exc, 'code', ''), 'lawyer_review_field')
    raise CaseReviewStoreError(code) from exc


def _read(path, *, absent=False):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except FileNotFoundError:
        if absent:
            return None
        raise CaseReviewStoreError('review_unavailable') from None
    try:
        item = os.fstat(fd)
        if (not stat.S_ISREG(item.st_mode) or item.st_uid != os.getuid() or item.st_nlink != 1
                or stat.S_IMODE(item.st_mode) != 0o600 or not 0 < item.st_size <= _LIMIT):
            raise CaseReviewStoreError('review_integrity')
        data = bytearray()
        while len(data) <= item.st_size:
            part = os.read(fd, min(65536, item.st_size + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        after = os.fstat(fd)
        identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        if len(data) != item.st_size or identity(item) != identity(after):
            raise CaseReviewStoreError('review_integrity')
        return bytes(data)
    finally:
        os.close(fd)


def _atomic(path, data, before_publish):
    if len(data) > _LIMIT:
        raise CaseReviewStoreError('lawyer_review_bounds')
    temporary = path.parent / ('.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise CaseReviewStoreError('review_write_failed')
            view = view[count:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.fsync(directory)
        before_publish()
        os.replace(temporary, path)
        os.fsync(directory)
    finally:
        if fd >= 0:
            os.close(fd)
        temporary.unlink(missing_ok=True)
        os.close(directory)


@dataclass(frozen=True)
class _Case:
    namespace: CaseNamespace
    workspace: ComplaintWorkspaceService
    directory: Path
    directory_identity: tuple


class CaseReviewService:
    """Trusted factory owner. JSON never supplies keys, paths or service objects."""

    def __init__(self, root, *, cases, authorizer, memberships, grants, sessions):
        if (not isinstance(cases, CaseDirectory) or not isinstance(authorizer, CaseActionAuthorizer)
                or not isinstance(memberships, CaseMembershipStore)
                or not isinstance(grants, CaseResourceKeyGrantStore)
                or not isinstance(sessions, dict)
                or any(not isinstance(k, str) or not isinstance(v, UserOwnedKeySession) for k, v in sessions.items())):
            raise CaseReviewStoreError('review_authority_owners')
        self.root = Path(os.path.abspath(root))
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.resolve() != self.root:
            raise CaseReviewStoreError('review_integrity')
        item = self.root.lstat()
        if item.st_uid != os.getuid() or not stat.S_ISDIR(item.st_mode) or stat.S_IMODE(item.st_mode) != 0o700:
            raise CaseReviewStoreError('review_integrity')
        self.cases, self.authorizer, self.memberships, self.grants = cases, authorizer, memberships, grants
        self.root_identity=(item.st_dev,item.st_ino)
        self.sessions, self.bindings = dict(sessions), {}
        self.lock_path = self.root / '.lock'
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        os.close(fd)

    def bind_case(self, case, workspace):
        if not isinstance(case, CaseNamespace) or not isinstance(workspace, ComplaintWorkspaceService) or case.case_id in self.bindings:
            raise CaseReviewStoreError('review_case_binding')
        directory = self.root / _sha([case.tenant_id, case.case_id, case.resource_id])
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.resolve() != directory or directory.lstat().st_uid != os.getuid() or stat.S_IMODE(directory.lstat().st_mode) != 0o700:
            raise CaseReviewStoreError('review_integrity')
        info=directory.lstat()
        self.bindings[case.case_id] = _Case(case, workspace, directory,(info.st_dev,info.st_ino))

    def _case(self, case_id):
        bound = self.bindings.get(case_id)
        if bound is None:
            raise CaseReviewStoreError('review_unavailable')
        for directory, expected in ((self.root,self.root_identity),(bound.directory,bound.directory_identity)):
            item=directory.lstat()
            if (directory.resolve()!=directory or (item.st_dev,item.st_ino)!=expected
                    or not stat.S_ISDIR(item.st_mode) or item.st_uid!=os.getuid() or stat.S_IMODE(item.st_mode)!=0o700):
                raise CaseReviewStoreError('review_integrity')
        current = self.cases.select_case(actor_principal_id=bound.namespace.owner_principal_id, case_id=case_id)
        if (current.tenant_id, current.resource_id, current.owner_principal_id) != (
                bound.namespace.tenant_id, bound.namespace.resource_id, bound.namespace.owner_principal_id):
            raise CaseReviewStoreError('review_case_binding')
        return bound, current

    @contextmanager
    def _locked(self):
        with _LOCKS_GUARD:
            lock = _LOCKS.setdefault(str(self.lock_path), RLock())
        with lock:
            fd = os.open(self.lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                    raise CaseReviewStoreError('review_integrity')
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    @staticmethod
    def _scope(case):
        return {name: getattr(case, name) for name in ('tenant_id', 'case_id', 'resource_id')}

    def _access(self, actor, case_id, authority, action):
        bound, case = self._case(case_id)
        if type(authority) is not WorkspaceCaseAuthority:
            raise CaseReviewStoreError('lawyer_review_ungranted')
        decision = authority.revalidate(actor_principal_id=actor, workspace=bound.workspace, require_owner=False)
        if decision.action != action or decision.case_id != case_id or decision.actor_principal_id != actor:
            raise CaseReviewStoreError('lawyer_review_ungranted')
        return bound, case, decision

    def _session(self, actor):
        value = self.sessions.get(actor)
        if value is None or not value.unlocked:
            raise CaseReviewStoreError('review_key_locked')
        return value

    def _local_binding(self, actor, case_id):
        return PrivateArtifactBinding(tenant_id=actor, case_id=actor, principal_id=actor,
            artifact_kind='review-recipient-routing', revision=_sha([actor, case_id]))

    def _credentials(self, actor, bound):
        session = self._session(actor)
        binding = self._local_binding(actor, bound.namespace.case_id)
        key_id, key = session.provider().resolve(binding)
        envelope = _read(bound.directory / ('member-' + _sha(actor)))
        try:
            payload = json.loads(open_private_artifact(envelope, binding=binding, key=key, expected_key_id=key_id))
        except Exception:
            raise CaseReviewStoreError('review_key_grant_required') from None
        if payload.get('actor') != actor or payload.get('scope') != self._scope(bound.namespace):
            raise CaseReviewStoreError('review_key_grant_required')
        return payload, session

    @staticmethod
    def _grant_args(actor, case, credentials, session, *, source=False, source_revision=None):
        return dict(actor_principal_id=actor, tenant_id=case.tenant_id, case_id=case.case_id,
            resource_id=case.resource_id, membership_grant_id=credentials['membership_id'],
            membership_version=credentials['membership_version'],
            key_grant_id=credentials['source_grant'] if source else credentials['review_grant'],
            artifact_kind=SOURCE_KIND if source else REVIEW_KIND,
            artifact_revision=source_revision if source else REVIEW_ARTIFACT_REVISION,
            recipient_session=session)

    def _source(self, actor, bound, case):
        credentials, session = self._credentials(actor, bound)
        package = json.loads(_read(bound.directory / 'source'))
        revision = package.get('revision')
        if not isinstance(revision, str) or not revision.isascii() or not revision.isdecimal():
            raise CaseReviewStoreError('review_integrity')
        envelope = base64.b64decode(package['envelope'], validate=True)
        args = self._grant_args(actor, case, credentials, session, source=True, source_revision=revision)
        opened = self.grants.read_delegated(**args, envelope=envelope)
        payload = json.loads(opened['data'])
        if (payload.get('schema') != 'case-review-source@1' or payload.get('scope') != self._scope(case)
                or payload.get('case_revision') != case.revision or payload.get('private_revision') != revision):
            raise CaseReviewStoreError('review_source_changed')
        shared = payload.get('shared_interview')
        from mediator.workflow_service import WorkflowActionService
        from complaint_phases.knowledge_graph import KnowledgeGraph
        if (not isinstance(shared, dict) or shared.get('schema_version') != WorkflowActionService.SESSION_PROJECTION_VERSION
                or type(shared.get('session_revision')) is not int or not isinstance(shared.get('intake_case_file'), dict)):
            raise CaseReviewStoreError('review_integrity')
        KnowledgeGraph.from_dict(deepcopy(shared['knowledge_graph']))
        return payload, envelope, opened, args, credentials, session

    def authorize_bound(self, decision):
        """A registry checker performs real recipient crypto, never a policy bool."""
        if type(decision) is not AuthorizationDecision:
            return False
        bound, case = self._case(decision.case_id)
        if decision.membership == 'owner':
            return decision.actor_principal_id == case.owner_principal_id
        if decision.membership != 'assigned-lawyer':
            return False
        self._source(decision.actor_principal_id, bound, case)
        return True

    def _owner_snapshot(self, bound, case, owner_session, identity):
        key_id, key = owner_session.provider().resolve(PrivateArtifactBinding(tenant_id=case.tenant_id,
            case_id=case.case_id, principal_id=case.tenant_id, artifact_kind='session', revision='session-v1'))
        opened = read_private_revision(bound.workspace.joined_revision_repository(case.tenant_id, case.case_id),
            tenant_id=case.tenant_id, case_id=case.case_id, principal_id=case.tenant_id, key=key, key_id=key_id)
        if opened is None:
            raise CaseReviewStoreError('review_unavailable')
        state = json.loads(opened['session'])
        shared = state.get('shared_interview')
        if state.get('user_id') != case.tenant_id or not isinstance(shared, dict):
            raise CaseReviewStoreError('review_integrity')
        from applications.complaint_workspace import case_legal_source_scope
        return {'schema':'case-review-source@1', 'scope':self._scope(case), 'case_revision':case.revision,
            'private_revision':opened['revision'], 'source_head_sha256':identity['head_sha256'],
            'case_key_id':key_id,
            'source_scope_sha256':case_legal_source_scope(state,case_id=case.case_id),
            'shared_interview':deepcopy(shared)}

    def sharing_status(self, actor, *, case_id, authority):
        bound, case, decision = self._access(actor, case_id, authority, 'case.read')
        if decision.membership != 'owner':
            raise CaseReviewStoreError('owner_share_required')
        with private_revision_source_scope(bound.workspace.joined_revision_repository(case.tenant_id, case.case_id)) as identity:
            source = self._owner_snapshot(bound, case, self._session(actor), identity)
            self._access(actor, case_id, authority, 'case.read')
        return {'case_id':case_id, 'private_revision':source['private_revision'], 'case_revision':case.revision,
            'owner_can_share':True, 'read_only':True, 'proof':False}

    def share_source(self, actor, *, case_id, request, authority):
        bound, case, decision = self._access(actor, case_id, authority, 'case.update')
        if decision.membership != 'owner' or actor != case.owner_principal_id:
            raise CaseReviewStoreError('owner_share_required')
        if (not isinstance(request, dict) or set(request) != {'membership_id','expected_membership_version','expected_private_revision'}
                or type(request['expected_membership_version']) is not int or type(request['expected_private_revision']) is not str):
            raise CaseReviewStoreError('lawyer_review_field')
        member = self.memberships.load(request['membership_id'])
        if (member.owner_principal_id != actor or member.case_id != case_id or member.tenant_id != case.tenant_id
                or member.resource_id != case.resource_id or member.status != 'accepted'
                or member.version != request['expected_membership_version'] or 'case.read' not in member.actions):
            raise CaseReviewStoreError('review_membership_required')
        member_action='case.review' if 'case.review' in member.actions else 'case.read'
        self.memberships.authorize(actor_principal_id=member.member_principal_id, grant_id=member.grant_id,
            tenant_id=case.tenant_id, case_id=case_id, resource_id=case.resource_id,
            action=member_action, expected_version=member.version)
        owner, recipient = self._session(actor), self._session(member.member_principal_id)
        with private_revision_source_scope(bound.workspace.joined_revision_repository(case.tenant_id, case_id)) as identity:
            source = self._owner_snapshot(bound, case, owner, identity)
            if source['private_revision'] != request['expected_private_revision']:
                raise CaseReviewStoreError('review_source_changed')
            def late():
                self._access(actor, case_id, authority, 'case.update')
                if not owner.unlocked or not recipient.unlocked:
                    raise CaseReviewStoreError('review_key_locked')
                current = self.memberships.load(member.grant_id)
                if current != member:
                    raise CaseReviewStoreError('review_membership_required')
                self.memberships.authorize(actor_principal_id=member.member_principal_id,grant_id=member.grant_id,
                    tenant_id=case.tenant_id,case_id=case_id,resource_id=case.resource_id,
                    action=member_action,expected_version=member.version)
                current_key,_material=owner.provider().resolve(PrivateArtifactBinding(tenant_id=case.tenant_id,
                    case_id=case_id,principal_id=case.tenant_id,artifact_kind='session',revision='session-v1'))
                if current_key!=source['case_key_id']:
                    raise CaseReviewStoreError('review_key_locked')
            late()
            policy=self.authorizer.grant_assigned_lawyer(owner_principal_id=actor, lawyer_principal_id=member.member_principal_id,
                case_id=case_id, tenant_id=case.tenant_id, resource_id=case.resource_id,
                actions=set(member.actions), expected_case_revision=case.revision)
            source_binding = PrivateArtifactBinding(tenant_id=case.tenant_id, case_id=case_id, principal_id=case.tenant_id,
                artifact_kind=SOURCE_KIND, revision=source['private_revision'])
            key_id, key = owner.provider().resolve(source_binding)
            envelope = seal_private_artifact(_json(source), binding=source_binding, key=key, key_id=key_id)
            issued = {}
            for role, kind, revision in [('source',SOURCE_KIND,source['private_revision']),('review',REVIEW_KIND,REVIEW_ARTIFACT_REVISION)]:
                late()
                issued[role] = self.grants.issue(actor_principal_id=actor, recipient_principal_id=member.member_principal_id,
                    membership_grant_id=member.grant_id, membership_version=member.version,
                    tenant_id=case.tenant_id, case_id=case_id, resource_id=case.resource_id,
                    artifact_kind=kind, artifact_revision=revision, owner_session=owner, recipient_session=recipient,
                    idempotency_key='review-'+_sha([role,member.grant_id,member.version,revision]),before_publish=late)
            with self._locked():
                late()
                if _read(bound.directory/'head', absent=True) is None:
                    empty = {'schema':'case-review-ledger@1','scope':self._scope(case),'review_revision':0,'rows':[]}
                    binding = PrivateArtifactBinding(tenant_id=case.tenant_id,case_id=case_id,principal_id=case.tenant_id,
                        artifact_kind=REVIEW_KIND,revision=REVIEW_ARTIFACT_REVISION)
                    kid, material = owner.provider().resolve(binding)
                    sealed = seal_private_artifact(_json(empty),binding=binding,key=material,key_id=kid)
                    _atomic(bound.directory/'head',_json({'revision':0,'envelope':base64.b64encode(sealed).decode()}),late)
                _atomic(bound.directory/'source',_json({'revision':source['private_revision'],
                    'envelope':base64.b64encode(envelope).decode()}),late)
                routing = {'actor':member.member_principal_id,'scope':self._scope(case),
                    'membership_id':member.grant_id,'membership_version':member.version,
                    'source_grant':issued['source'].key_grant_id,'review_grant':issued['review'].key_grant_id}
                binding = self._local_binding(member.member_principal_id,case_id)
                late()
                recipient.ensure_data_key(member.member_principal_id,member.member_principal_id)
                kid, material = recipient.provider().resolve(binding)
                sealed = seal_private_artifact(_json(routing),binding=binding,key=material,key_id=kid)
                _atomic(bound.directory/('member-'+_sha(member.member_principal_id)),sealed,late)
        return {'task_id':'CIMP-GUI-32','case_id':case_id,'status':'shared','private_revision':source['private_revision'],
            'recipient_principal_id':member.member_principal_id,'proof':False,'owner_keys_needed_for_recipient':False,
            'review_url':'/api/legal-analysis/'+case_id+'/lawyer-workspace?'+urlencode({**self._scope(case),
                'expected_revision':case.revision,'expected_membership_revision':policy.revision})}

    def _ledger(self, actor, bound, case, credentials, session):
        record = json.loads(_read(bound.directory/'head'))
        envelope = base64.b64decode(record['envelope'],validate=True)
        args = self._grant_args(actor,case,credentials,session)
        receipt = self.grants.read_delegated(**args,envelope=envelope)
        ledger = json.loads(receipt['data'])
        if (ledger.get('schema') != 'case-review-ledger@1' or ledger.get('scope') != self._scope(case)
                or type(ledger.get('review_revision')) is not int or type(record.get('revision')) is not int
                or record.get('revision') != ledger['review_revision']
                or not isinstance(ledger.get('rows'),list) or len(ledger['rows']) > 2048):
            raise CaseReviewStoreError('review_integrity')
        return ledger,envelope,receipt,args

    @staticmethod
    def _live(source):
        shared = source['shared_interview']
        case_file = shared['intake_case_file']
        attachment = case_file.get('canonical_legal_ir_attachment') or {}
        binding = attachment.get('source_binding') or {}
        identity = binding.get('content_hash') or ''
        verified = False
        try:
            from applications.legal_research_api import verified_reviewed_source_records
            records=verified_reviewed_source_records(case_file,source_scope_sha256=source['source_scope_sha256'])
            manifest={claim:rows for claim,rows in records.items() if rows}
            if manifest:
                identity='reviewed-sources-'+_sha(manifest)
                verified=True
            if binding.get('content_hash'):
                from applications.legal_analysis_api import current_case_legal_ir_source
                selected=current_case_legal_ir_source(case_file,binding['content_hash'],case_id=source['scope']['case_id'])
                if (binding.get('source_scope_sha256')==source['source_scope_sha256']
                        and selected['admission'].get('source_scope_sha256')==source['source_scope_sha256']):
                    identity=binding['content_hash'];verified=True
        except Exception:
            # A missing/changed owner is unavailable, never reconstructed from
            # a source id, cached flag or caller-reported proof label.
            verified=False
        return {'case_revision':source['case_revision'], 'source_identity':identity if verified else '',
            'source_revision':'source-'+_sha([source['source_head_sha256'],case_file.get('legal_source_passage_index'),binding,
                case_file.get('legal_context'),case_file.get('legal_context_overrides')]),
            'fact_revision':'facts-'+_sha(shared['knowledge_graph']),
            'proof_revision':'proof-'+_sha([attachment.get('typed_obligations'),attachment.get('source_binding')]),
            'proof_bound':False,'checked_proof_producer_available':False,'source_bound':verified,
            'private_revision':source['private_revision'],'session_revision':shared['session_revision'],
            'governing_legal_authority':False,'legal_sufficiency':False,'admitted_law':False,
            'promotes_changed_law':False,'promotes_changed_facts':False}

    def _project(self, ledger, live, case_id):
        from applications.case_review import project_lawyer_reviews, project_collaborative_reviews
        projection = project_lawyer_reviews({'lawyer_review_ledger':deepcopy(ledger['rows'])},
            case_revision=live['case_revision'], live_context=live)
        projection.update(case_id=case_id, review_revision=ledger['review_revision'],
            private_revision=live['private_revision'],session_revision=live['session_revision'],
            read_only=True, owner_keys_needed_for_recipient=False)
        collaborative = deepcopy(ledger.get('collaborative_case_file') or {})
        projection['collaborative_reviews']=project_collaborative_reviews(collaborative)
        from applications.case_review import project_draft_review_actions
        projection['draft_review_actions']=project_draft_review_actions(collaborative)
        return projection

    def _late(self, actor, case_id, authority, action, source_receipt, source_envelope, source_args,
              review_receipt, review_envelope, review_args):
        self._access(actor,case_id,authority,action)
        self.grants.admit_late_result(**source_args,envelope=source_envelope,
            prepared_generation=source_receipt['generation'],action='case.read')
        self.grants.admit_late_result(**review_args,envelope=review_envelope,
            prepared_generation=review_receipt['generation'],action='case.review' if action=='case.review' else 'case.read')
        self._access(actor,case_id,authority,action)

    def read(self, actor, *, case_id, authority):
        bound,case,decision = self._access(actor,case_id,authority,'case.read')
        if decision.membership == 'owner':
            return self._read_owner(actor,bound,case,authority)
        with private_revision_source_scope(bound.workspace.joined_revision_repository(case.tenant_id,case_id)) as identity:
            source,envelope,sreceipt,sargs,credentials,session = self._source(actor,bound,case)
            if source['source_head_sha256'] != identity['head_sha256']:
                raise CaseReviewStoreError('review_source_changed')
            with self._locked():
                ledger,renvelope,rreceipt,rargs = self._ledger(actor,bound,case,credentials,session)
                result = self._project(ledger,self._live(source),case_id)
                self._late(actor,case_id,authority,'case.read',sreceipt,envelope,sargs,rreceipt,renvelope,rargs)
                return result

    def _read_owner(self, actor, bound, case, authority):
        owner=self._session(actor)
        with private_revision_source_scope(bound.workspace.joined_revision_repository(case.tenant_id,case.case_id)) as identity:
            source=self._owner_snapshot(bound,case,owner,identity)
            with self._locked():
                record=_read(bound.directory/'head',absent=True)
                if record is None:
                    ledger={'review_revision':0,'rows':[]}
                else:
                    metadata=json.loads(record)
                    receipt=self.grants.read_as_owner(actor_principal_id=actor,tenant_id=case.tenant_id,
                        case_id=case.case_id,resource_id=case.resource_id,artifact_kind=REVIEW_KIND,
                        artifact_revision=REVIEW_ARTIFACT_REVISION,
                        envelope=base64.b64decode(metadata['envelope'],validate=True),owner_session=owner)
                    ledger=json.loads(receipt['data'])
                    if ledger.get('scope')!=self._scope(case) or ledger.get('review_revision')!=metadata['revision']:
                        raise CaseReviewStoreError('review_integrity')
                result=self._project(ledger,self._live(source),case.case_id)
                self._owner_snapshot(bound,case,owner,identity)
                self._access(actor,case.case_id,authority,'case.read')
                result['owner_can_share']=True
                return result

    def write(self, actor, *, case_id, request, authority):
        return self._write(actor,case_id=case_id,request=request,authority=authority,kind='lawyer')

    def write_item(self, actor, *, case_id, request, authority):
        return self._write(actor,case_id=case_id,request=request,authority=authority,kind='items')

    def accept_owner_transition(self, actor, *, case_id, request, authority):
        bound,_case,decision=self._access(actor,case_id,authority,'case.update')
        if decision.membership!='owner':
            raise CaseReviewStoreError('owner_share_required')
        if isinstance(request, dict) and request.get('operation')=='accept_draft_suggestion':
            return self._accept_draft_suggestion(actor, bound=bound, case=_case, request=request, authority=authority)
        allowed={'proposal_id','expected_review_revision','expected_private_revision','expected_session_revision','request_id'}
        if not isinstance(request,dict) or set(request)!=allowed:
            raise CaseReviewStoreError('lawyer_review_field')
        method=getattr(ComplaintWorkspaceService,'accept_case_review_fact_proposal',None)
        if type(bound.workspace) is not ComplaintWorkspaceService or method is None:
            raise CaseReviewStoreError('review_transition_owner_unavailable')
        from applications.complaint_workspace import WorkspaceAccess, workspace_access_scope
        with workspace_access_scope(WorkspaceAccess.authenticated(actor,case_id)):
            return method(bound.workspace,actor,case_id=case_id,review_service=self,**request)

    def _owner_ledger(self, actor, bound, case, owner):
        raw=_read(bound.directory/'head')
        metadata=json.loads(raw)
        receipt=self.grants.read_as_owner(actor_principal_id=actor,tenant_id=case.tenant_id,
            case_id=case.case_id,resource_id=case.resource_id,artifact_kind=REVIEW_KIND,
            artifact_revision=REVIEW_ARTIFACT_REVISION,
            envelope=base64.b64decode(metadata['envelope'],validate=True),owner_session=owner)
        ledger=json.loads(receipt['data'])
        if (ledger.get('schema')!='case-review-ledger@1' or ledger.get('scope')!=self._scope(case)
                or type(ledger.get('review_revision')) is not int or type(metadata.get('revision')) is not int
                or ledger['review_revision']!=metadata['revision']):
            raise CaseReviewStoreError('review_integrity')
        return ledger,hashlib.sha256(raw).hexdigest()

    def read_proposal_for_owner(self, actor, *, case_id, proposal_id, authority):
        """Resolve an immutable AEAD proposal under the live real owner cap.

        This returns server material to the canonical owner adapter, not a
        caller-supplied proposal or permission to alter a canonical fact.
        """
        bound,case,decision=self._access(actor,case_id,authority,'case.update')
        if decision.membership!='owner' or not isinstance(proposal_id,str):
            raise CaseReviewStoreError('owner_share_required')
        owner=self._session(actor)
        with private_revision_source_scope(bound.workspace.joined_revision_repository(case.tenant_id,case_id)) as identity:
            source=self._owner_snapshot(bound,case,owner,identity)
            with self._locked():
                ledger,ledger_hash=self._owner_ledger(actor,bound,case,owner)
                items=(ledger.get('collaborative_case_file') or {}).get('collaborative_review_items',[])
                record=next((row for row in items if row.get('item_id')==proposal_id and row.get('item_type')=='review_proposal'),None)
                if record is None:raise CaseReviewStoreError('proposal_required')
                base=record.get('source_base') or {}
                if (base.get('source_head_sha256')!=identity['head_sha256']
                        or base.get('private_revision')!=source['private_revision']
                        or base.get('session_revision')!=source['shared_interview']['session_revision']):
                    raise CaseReviewStoreError('stale_approval')
                self._owner_snapshot(bound,case,owner,identity)
                self._access(actor,case_id,authority,'case.update')
                return {'schema':'case-review-owner-proposal@1','case_id':case_id,'actor_principal_id':actor,
                    'canonical_owner_principal_id':case.tenant_id,'review_revision':ledger['review_revision'],
                    'review_ledger_sha256':ledger_hash,'proposal_id':proposal_id,'record':deepcopy(record),
                    'record_sha256':_sha(record),'source_base':deepcopy(base)}

    def reprove_proposal_for_owner(self, actor, *, case_id, proposal_id, authority,
                                  expected_review_revision, expected_record_sha256):
        """Late review-CAS proof for a caller already holding canonical source CAS.

        Lock order is canonical source then review. This method intentionally
        does not acquire another source flock: the actual canonical writer
        already holds it and must reprove its own source/key/session before
        calling this immediately before publication.
        """
        bound,case,decision=self._access(actor,case_id,authority,'case.update')
        if decision.membership!='owner':raise CaseReviewStoreError('owner_share_required')
        with self._locked():
            ledger,_digest=self._owner_ledger(actor,bound,case,self._session(actor))
            items=(ledger.get('collaborative_case_file') or {}).get('collaborative_review_items',[])
            record=next((row for row in items if row.get('item_id')==proposal_id and row.get('item_type')=='review_proposal'),None)
            if (type(expected_review_revision) is not int or ledger['review_revision']!=expected_review_revision
                    or record is None or _sha(record)!=expected_record_sha256):
                raise CaseReviewStoreError('stale_revision')
            self._access(actor,case_id,authority,'case.update')
            return deepcopy(record)

    def _accept_draft_suggestion(self, actor, *, bound, case, request, authority):
        """Owner acceptance stays in the review ledger and does not rewrite draft bytes."""
        allowed={'operation','proposal_id','request_id','draft_id','expected_revision','expected_text_digest','proposed_text','expected_review_revision'}
        if not isinstance(request, dict) or set(request) != allowed or type(request.get('expected_revision')) is not int or type(request.get('expected_review_revision')) is not int:
            raise CaseReviewStoreError('lawyer_review_field')
        owner=self._session(actor)
        with private_revision_source_scope(bound.workspace.joined_revision_repository(case.tenant_id, case.case_id)) as identity:
            source=self._owner_snapshot(bound, case, owner, identity)
            with self._locked():
                ledger,_digest=self._owner_ledger(actor, bound, case, owner)
                if ledger['review_revision'] != request['expected_review_revision']:
                    raise CaseReviewStoreError('stale_revision')
                collaborative=deepcopy(ledger.get('collaborative_case_file') or {})
                from applications.case_review import CaseReviewError, accept_draft_suggestion
                try:
                    created=accept_draft_suggestion(collaborative, request, actor_principal_id=actor,
                        canonical_owner_principal_id=case.tenant_id, membership='owner', action='case.update')
                except CaseReviewError as exc:
                    _suggestion_error(exc)
                updated={'schema':'case-review-ledger@1','scope':self._scope(case),
                    'review_revision':ledger['review_revision']+1,'rows':ledger.get('rows') or [],
                    'collaborative_case_file':collaborative}
                binding=PrivateArtifactBinding(tenant_id=case.tenant_id, case_id=case.case_id, principal_id=case.tenant_id,
                    artifact_kind=REVIEW_KIND, revision=REVIEW_ARTIFACT_REVISION)
                key_id, material=owner.provider().resolve(binding)
                sealed=seal_private_artifact(_json(updated), binding=binding, key=material, key_id=key_id)
                def late():
                    self._owner_snapshot(bound, case, owner, identity)
                    self._access(actor, case.case_id, authority, 'case.update')
                _atomic(bound.directory/'head', _json({'revision':updated['review_revision'],
                    'envelope':base64.b64encode(sealed).decode()}), late)
                late()
                created=dict(created)
                created.update(case_id=case.case_id, review_revision=updated['review_revision'],
                    private_revision=source['private_revision'], adopted_into_owner_draft=False)
                return created

    def _write(self, actor, *, case_id, request, authority, kind):
        from applications.case_review import submit_review_record, submit_collaborative_record
        bound,case,decision = self._access(actor,case_id,authority,'case.review')
        if decision.membership != 'assigned-lawyer':
            raise CaseReviewStoreError('lawyer_assignment_required')
        allowed={'operation','request_id','expected_review_revision','expected_case_revision','expected_source_revision',
            'expected_fact_revision','expected_proof_revision','interpretation','source_citation','proposal_id','approval_id',
            'decision','model_id','suggestion','engine_name','engine_version','governing_legal_authority','legal_sufficiency','admitted_law',
            'draft_id','expected_revision','expected_text_digest','provenance','proposed_text'}
        if kind=='items':
            allowed={'operation','request_id','expected_review_revision','expected_case_revision','expected_source_revision',
                'expected_fact_revision','expected_proof_revision','body','title','target_kind','target_id','proposed_text','proposal_id'}
        if (not isinstance(request,dict) or set(request)-allowed or len(_json(request))>65536
                or type(request.get('expected_review_revision')) is not int):
            raise CaseReviewStoreError('lawyer_review_field')
        if request.get('operation') == 'record_machine_proof':
            raise CaseReviewStoreError('proof_producer_unavailable')
        if kind=='items' and request.get('operation') not in {'create_task','create_comment','create_proposal','dissent'}:
            raise CaseReviewStoreError('review_transition_owner_unavailable')
        with private_revision_source_scope(bound.workspace.joined_revision_repository(case.tenant_id,case_id)) as identity:
            source,envelope,sreceipt,sargs,credentials,session = self._source(actor,bound,case)
            if source['source_head_sha256'] != identity['head_sha256']:
                raise CaseReviewStoreError('review_source_changed')
            live = self._live(source)
            if request.get('operation') in {'review','promote'} and not live['source_bound']:
                raise CaseReviewStoreError('review_source_unbound')
            with self._locked():
                ledger,renvelope,rreceipt,rargs = self._ledger(actor,bound,case,credentials,session)
                fingerprint = _sha(request)
                collaborative=deepcopy(ledger.get('collaborative_case_file') or {})
                rows=ledger['rows'] if kind=='lawyer' else collaborative.get('collaborative_review_items',[])
                all_rows=ledger['rows']+collaborative.get('collaborative_review_items',[])+_suggestion_rows(collaborative)
                old = next((row for row in all_rows if row.get('request_id')==request.get('request_id')),None)
                if old is not None:
                    if old.get('request_fingerprint') != fingerprint or old.get('actor_principal_id') != actor:
                        raise CaseReviewStoreError('replay_mismatch')
                    result=self._project(ledger,live,case_id)
                    self._late(actor,case_id,authority,'case.review',sreceipt,envelope,sargs,rreceipt,renvelope,rargs)
                    result.update(record=deepcopy(old),replayed=True,operation=request['operation'])
                    if kind=='items':
                        return {**result['collaborative_reviews'],'case_id':case_id,'review_revision':ledger['review_revision'],
                            'live_revisions':live,'record':deepcopy(old),'replayed':True,'operation':request['operation']}
                    return result
                if request['expected_review_revision'] != ledger['review_revision']:
                    raise CaseReviewStoreError('stale_revision')
                if kind=='lawyer' and request.get('operation') in _DRAFT_SUGGESTION_OPERATIONS:
                    from applications.case_review import CaseReviewError, submit_draft_suggestion
                    try:
                        created=submit_draft_suggestion(collaborative, request, actor_principal_id=actor,
                            canonical_owner_principal_id=case.tenant_id, membership=decision.membership, action='case.review')
                    except CaseReviewError as exc:
                        _suggestion_error(exc)
                    row=created['record']; row['request_fingerprint']=fingerprint
                    updated={'schema':'case-review-ledger@1','scope':self._scope(case),
                        'review_revision':ledger['review_revision']+1,'rows':ledger['rows'],
                        'collaborative_case_file':collaborative}
                    sealed=self.grants.write_delegated(**rargs,plaintext=_json(updated),action='case.review')
                    def late_suggestion():
                        self._late(actor,case_id,authority,'case.review',sreceipt,envelope,sargs,sealed,sealed['envelope'],rargs)
                    _atomic(bound.directory/'head',_json({'revision':updated['review_revision'],
                        'envelope':base64.b64encode(sealed['envelope']).decode()}),late_suggestion)
                    result=self._project(updated,live,case_id)
                    late_suggestion()
                    result.update(read_only=False,record=deepcopy(row),operation=request['operation'],
                        draft_review_actions=created)
                    return result
                pure_file={'lawyer_review_ledger':deepcopy(ledger['rows'])}
                if kind=='lawyer':
                    created=submit_review_record(pure_file,request,actor_principal_id=actor,
                        canonical_owner_principal_id=case.tenant_id,case_revision=case.revision,
                        membership=decision.membership,live_context=live)
                else:
                    from applications.case_review import _require_live
                    _require_live(request,live)
                    created=submit_collaborative_record(collaborative,request,actor_principal_id=actor,
                        canonical_owner_principal_id=case.tenant_id,case_id=case_id,
                        membership=decision.membership,authorized=True)
                row=created['record'];row['request_fingerprint']=fingerprint
                if row.get('record_kind')=='model_suggestion':
                    row.update(author_kind='human_report',producer_verified=False,reported_model_id=row.get('model_id'))
                row['source_binding_verified']=live['source_bound']
                row['source_base']={k:live[k] for k in ('private_revision','session_revision','source_revision','fact_revision','proof_revision')}
                row['source_base']['source_head_sha256']=source['source_head_sha256']
                updated={'schema':'case-review-ledger@1','scope':self._scope(case),
                    'review_revision':ledger['review_revision']+1,'rows':pure_file['lawyer_review_ledger'],
                    'collaborative_case_file':collaborative}
                if kind=='lawyer':updated['rows'][-1]=row
                else:updated['collaborative_case_file']['collaborative_review_items'][-1]=row
                sealed=self.grants.write_delegated(**rargs,plaintext=_json(updated),action='case.review')
                def late():
                    self._late(actor,case_id,authority,'case.review',sreceipt,envelope,sargs,sealed,sealed['envelope'],rargs)
                _atomic(bound.directory/'head',_json({'revision':updated['review_revision'],
                    'envelope':base64.b64encode(sealed['envelope']).decode()}),late)
                result=self._project(updated,live,case_id)
                # The earlier head commit stays valid. Its plaintext response
                # still needs current access after potentially slow projection.
                late()
                result.update(read_only=False,record=deepcopy(row),operation=request['operation'])
                if kind=='items':
                    return {**result['collaborative_reviews'],'case_id':case_id,'review_revision':updated['review_revision'],
                        'private_revision':live['private_revision'],'live_revisions':live,'record':deepcopy(row),
                        'read_only':False,'replayed':False,'operation':request['operation']}
                return result
