"""Real accepted Native proposals and exact Git bytes, with no candidate imports."""
from pathlib import Path
import hashlib
import os
import subprocess

import pytest

from integrations.ipfs_accelerate.python_global_preflight import inspect_changed_python_globals
from ipfs_accelerate_py.agent_supervisor.validation.proposal_validation import (
    CandidateDiffEntry, DiffChangeKind, ImplementationProposal, ProposalValidationPolicy,
    validate_implementation_proposal,
)
from ipfs_accelerate_py.agent_supervisor.proof.code_proof_obligations import collect_git_candidate_diff

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
TASK = 'SYNTHETIC-PYTHON-GLOBALS'


def _git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def _accepted(root, before, after, *, name='module.py', baseline=None, policy_overrides=None):
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if baseline is None:
        _git(root, 'init', '-q')
        (root / 'README').write_text('Synthetic static inspection fixture.\n')
        if before is not None:
            target.write_text(before)
        _git(root, 'add', '.')
        _git(root, '-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'Baseline')
        baseline = _git(root, 'rev-parse', 'HEAD')
    if after is None:
        target.unlink()
    else:
        target.write_text(after)
    common = Path(_git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
    repository = 'repository:sha256:' + hashlib.sha256(str(common).encode()).hexdigest()
    entries = tuple(collect_git_candidate_diff(root, base_revision=baseline))
    assert len(entries) == 1 and (entries[0].new_path or entries[0].old_path) == name
    proposal = ImplementationProposal(task_id=TASK, accepted_plan_id='plan:synthetic', repository_id=repository,
        repository_tree_id=baseline, objective_id='objective:synthetic', baseline_id=baseline,
        context_id='context:synthetic', replay_nonce='synthetic-attempt-1', declared_paths=(name,), candidate_diff=entries)
    result = validate_implementation_proposal(proposal, policy=ProposalValidationPolicy(allowed_paths=(name,), **(policy_overrides or {})))
    assert result.accepted, result.to_dict()
    return result


def _inspect(root, accepted):
    return inspect_changed_python_globals(root.resolve(), accepted, expected_task_id=TASK)


def test_actual_opaque_ref_collision_is_rejected_without_executing_candidate(tmp_path):
    before = 'def _opaque_ref(value):\n return bytes(value).hex()\n'
    marker = tmp_path / 'must-not-execute'
    after = before + f"\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n" + 'def _opaque_ref(value):\n return value.get("ref")\n'
    accepted = _accepted(tmp_path, before, after)
    result = _inspect(tmp_path, accepted)
    assert result['passed'] is False and result['reason'] == 'new_duplicate_python_module_global'
    assert result['files'][0]['collisions'] == [{'name':'_opaque_ref','baseline_count':1,'candidate_count':2,'lines':[1,6]}]
    assert not marker.exists()


def test_renamed_helper_passes_and_new_module_duplicate_fails(tmp_path):
    before = 'def _opaque_ref(value):\n return bytes(value).hex()\n'
    root = tmp_path / 'renamed'
    assert _inspect(root, _accepted(root, before, before + 'def _durability_ref(value):\n return value.get("ref")\n'))['passed']
    root = tmp_path / 'new'
    result = _inspect(root, _accepted(root, None, before + before))
    assert not result['passed'] and result['reason'] == 'new_duplicate_python_module_global'


@pytest.mark.parametrize('extra,passed', [('\nVERSION=2\n',True), ('\ndef same():\n return 3\n',False)])
def test_existing_collisions_are_not_approved_or_allowed_to_worsen(tmp_path, extra, passed):
    before='def same():\n return 1\ndef same():\n return 2\n'
    assert _inspect(tmp_path, _accepted(tmp_path, before, before + extra))['passed'] is passed


@pytest.mark.parametrize('body', [
    'if True:\n def f(): pass\nelse:\n def f(): pass\n',
    'class A:\n def f(self): pass\nclass B:\n def f(self): pass\n',
    'def a():\n def nested(): pass\n return nested\ndef b():\n def nested(): pass\n return nested\n',
])
def test_conditional_and_inner_definitions_are_not_module_collisions(tmp_path, body):
    assert _inspect(tmp_path, _accepted(tmp_path, None, body))['passed']


@pytest.mark.parametrize('source', [
    'from typing import overload\n@overload\ndef f(x:int)->int: ...\n@overload\ndef f(x:str)->str: ...\ndef f(x): return x\n',
    'import typing as t\n@t.overload\nasync def f(x:int)->int: ...\nasync def f(x): return x\n',
    'from typing import overload as signature\n@signature\ndef f(x:int)->int: pass\ndef f(x): return x\n',
])
def test_only_real_unambiguous_typing_stub_groups_are_tolerated(tmp_path, source):
    assert _inspect(tmp_path, _accepted(tmp_path, None, source))['passed']


@pytest.mark.parametrize('prefix,decorator,stub', [
    ('def overload(fn): return fn\n','overload','...'),
    ('from typing import overload\noverload=lambda fn:fn\n','overload','...'),
    ('from typing import overload\n','overload','return x'),
    ('from other import overload\n','overload','...'),
    ('import typing\ntyping.overload=lambda fn:fn\n','typing.overload','...'),
])
def test_arbitrary_or_rebound_decorators_cannot_hide_a_collision(tmp_path, prefix, decorator, stub):
    body = prefix + '@'+decorator+'\ndef f(x): '+stub+'\ndef f(x): return x\n'
    result = _inspect(tmp_path, _accepted(tmp_path, None, body))
    assert not result['passed'] and result['reason'] == 'new_duplicate_python_module_global'


@pytest.mark.parametrize('outer', [
    'def trigger(value=(overload := replacement)): pass\n',
    'def trigger(*, value=(overload := replacement)): pass\n',
    'def trigger(value:(overload := replacement)): pass\n',
    'class Trigger((overload := replacement)): pass\n',
])
def test_outer_evaluated_definition_expressions_cannot_rebind_overload_unnoticed(tmp_path, outer):
    source = ('from typing import overload\ndef replacement(fn): return fn\n' + outer
        + '@overload\ndef f(x:int)->int: ...\ndef f(x): return x\n')
    result = _inspect(tmp_path, _accepted(tmp_path, None, source))
    assert result['reason'] == 'new_duplicate_python_module_global'


def test_changed_candidate_and_baseline_fingerprints_cannot_be_substituted(tmp_path):
    before='def f(): return 1\n'; after='def f(): return 2\n'
    accepted=_accepted(tmp_path,before,after)
    (tmp_path/'module.py').write_text(after+'def f(): return 3\n')
    assert _inspect(tmp_path,accepted)['detail']=='entry_fingerprint_mismatch'
    assert not inspect_changed_python_globals(tmp_path.resolve(),accepted,expected_task_id='OTHER')['passed']
    assert not _inspect(tmp_path,accepted.to_dict())['passed']


def test_symlink_hardlink_and_nested_repository_fail_closed(tmp_path):
    for kind in ['symlink','hardlink','nested']:
        root=tmp_path/kind
        before='def f(): return 1\n'; after='def f(): return 2\n'
        accepted=_accepted(root,before,after,name='pkg/module.py')
        target=root/'pkg/module.py'
        if kind in {'symlink','hardlink'}:
            other=root/'other';other.write_text(after);target.unlink()
            (target.symlink_to(other) if kind=='symlink' else os.link(other,target))
        else:
            (root/'pkg/.git').mkdir()
        result=_inspect(root,accepted)
        assert not result['passed'] and result['reason']=='python_global_preflight_unavailable'


def test_foreign_repository_same_commit_cannot_reuse_the_accepted_context(tmp_path):
    root=tmp_path/'one';before='def f():return 1\n';after='def f():return 2\n'
    accepted=_accepted(root,before,after)
    other=tmp_path/'other'
    subprocess.run(['git','clone','--local',str(root),str(other)],check=True,capture_output=True)
    (other/'module.py').write_text(after)
    assert _inspect(other,accepted)['detail']=='repository_id_mismatch'


def test_class_and_async_module_collisions_are_rejected(tmp_path):
    for index,source in enumerate(['class C: pass\nclass C: pass\n','async def f(): pass\nasync def f(): pass\n']):
        root=tmp_path/str(index)
        assert _inspect(root,_accepted(root,None,source))['reason']=='new_duplicate_python_module_global'


def test_real_git_sha256_object_format_and_stub_file_are_supported(tmp_path):
    root = tmp_path / 'sha256'
    root.mkdir()
    _git(root, 'init', '-q', '--object-format=sha256')
    before = 'def f(): return 1\n'
    accepted = _accepted(root, before, before + 'def f(): return 2\n')
    assert len(accepted.proposal.baseline_id) == 64
    assert _inspect(root, accepted)['reason'] == 'new_duplicate_python_module_global'
    stub = 'from typing import overload\n@overload\ndef f(x:int)->int: ...\n@overload\ndef f(x:str)->str: ...\n'
    root = tmp_path / 'stubs'
    assert _inspect(root, _accepted(root, None, stub, name='module.pyi'))['passed']


def test_deleted_source_and_local_typing_shadow_have_explicit_outcomes(tmp_path):
    root = tmp_path / 'deleted'
    accepted = _accepted(root, 'def f(): return 1\n', None, name='gone/module.py')
    (root / 'gone').rmdir()
    assert _inspect(root, accepted)['passed']
    root = tmp_path / 'shadow'
    body = 'from typing import overload\n@overload\ndef f(x:int)->int: ...\ndef f(x): return x\n'
    accepted = _accepted(root, None, body)
    (root / 'typing.py').write_text('def overload(fn): return fn\n')
    assert _inspect(root, accepted)['reason'] == 'new_duplicate_python_module_global'


@pytest.mark.parametrize('source,policy', [
    ('def broken(:\n', {'require_python_syntax':False}),
    ('#' + 'x' * 1_048_576 + '\ndef f(): return 1\n', {'allow_large_files':True, 'max_file_bytes':2_000_000, 'max_patch_bytes':2_000_000}),
    ('x=1\n' * 64_000 + 'def f(): return 1\n', {}),
], ids=['invalid-syntax', 'file-limit', 'ast-limit'])
def test_accepted_but_uninspectable_python_is_a_finite_refusal(tmp_path, source, policy):
    accepted = _accepted(tmp_path, None, source, policy_overrides=policy)
    result = _inspect(tmp_path, accepted)
    assert result['passed'] is False and result['reason'] == 'python_global_preflight_unavailable'
    assert result['detail'] in {'candidate_file_invalid', 'ast_bound', 'bounded_source_inspection_failed'}


def test_existing_workspace_module_is_inspectable_and_duplicate_still_refuses(tmp_path):
    """The production baseline must fit the static gate without importing it."""
    import ast
    from integrations.ipfs_accelerate import python_global_preflight
    source = (Path(__file__).resolve().parents[1] / 'applications' / 'complaint_workspace.py').read_text()
    count = sum(1 for _ in ast.walk(ast.parse(source)))
    assert 100_000 < count < python_global_preflight._MAX_NODES
    assert len(source.encode('utf8')) < python_global_preflight._MAX_FILE
    marker = '\nraise AssertionError("static-only large-module control")\n'
    root = tmp_path / 'valid'
    accepted = _accepted(root, source, source + marker)
    result = _inspect(root, accepted)
    assert result['passed'] is True and result['candidate_executed'] is False
    root = tmp_path / 'duplicate'
    accepted = _accepted(root, source, source + marker + '\nclass ComplaintWorkspaceService: pass\n')
    result = _inspect(root, accepted)
    assert result['reason'] == 'new_duplicate_python_module_global'
    assert result['candidate_executed'] is False
    assert result['files'][0]['collisions'][0]['name'] == 'ComplaintWorkspaceService'


def test_static_rejection_precedes_real_native_execution_and_rename_validates(tmp_path):
    """An unimported changed module cannot hide a collision behind green tests."""
    import json
    import shlex
    from types import SimpleNamespace
    from tests.test_improvement_evidence_gate import _task, _gate, _spec, _observation, _write_output, COMMAND
    from integrations.ipfs_accelerate.improvement_runner import EvidenceValidationScheduler
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalTask
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import ValidationScheduler, build_declared_validation_plan_graph
    from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import sealed_validation_python_runner
    task = _task()
    before = 'def _opaque_ref(value):\n return bytes(value).hex()\n'
    _write_output(tmp_path, task['id'], before)
    _, executor, environment = _gate(tmp_path, task, _observation(tmp_path), _return_measurement=True)
    _git(tmp_path, 'add', 'out', 'tests', 'conftest.py', 'adapter.py', 'complaint_fixture_guard.py')
    _git(tmp_path, '-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'Native preflight baseline')
    baseline = _git(tmp_path, 'rev-parse', 'HEAD')
    common = Path(_git(tmp_path, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
    path = task['targets'][0]
    calls = []
    @sealed_validation_python_runner
    def real_executor(**call):
        calls.append(call['spec'].command)
        spec = call['spec']
        instrumented = spec.command.replace(' -m pytest ', ' -m pytest -p complaint_fixture_guard ', 1)
        assert instrumented != spec.command
        call['spec'] = SimpleNamespace(command=instrumented, raw_command=spec.raw_command)
        return executor(**call)
    def run(body, nonce):
        (tmp_path / path).write_text(body)
        entries = tuple(e for e in collect_git_candidate_diff(tmp_path, base_revision=baseline)
                        if e.new_path == path)
        proposal = ImplementationProposal(task_id=task['id'], accepted_plan_id='plan:synthetic',
            repository_id='repository:sha256:' + hashlib.sha256(str(common).encode()).hexdigest(),
            repository_tree_id=baseline, baseline_id=baseline, objective_id='objective:synthetic',
            context_id='context:synthetic', replay_nonce=nonce, declared_paths=(path,), candidate_diff=entries)
        accepted = validate_implementation_proposal(proposal, policy=ProposalValidationPolicy(allowed_paths=(path,)))
        assert accepted.accepted
        commands, graph = build_declared_validation_plan_graph(
            ['PYTHONPATH=' + shlex.quote(environment['PYTHONPATH']) + ' ' + COMMAND],
            repository_tree_id=baseline, changed_paths=(path,))
        scheduler = EvidenceValidationScheduler(ValidationScheduler(max_workers=1), state_dir=tmp_path / ('evidence-' + nonce),
            spec=_spec(task), defer_readiness=True)
        native_task = PortalTask(task['id'], 'Synthetic owned task', 'todo', '', 'P0', 'synthetic',
            outputs=(path,), validation=[COMMAND], canonical_task_cid='synthetic-task-cid')
        scheduler.bind_task(native_task, tmp_path)
        return scheduler.run_validated(accepted, commands, workspace_path=tmp_path, runner=real_executor,
            environment=environment, impact_graph=graph, require_impact_graph=True,
            require_full_validation=True, scope='pre_merge')
    failed = run(before + 'def _opaque_ref(value):\n return value.get("ref")\n', 'collision')
    assert failed['passed'] is False and failed['returncode'] == 78
    assert calls == []  # Neither collection nor execution was dispatched.
    diagnostic = failed['results'][0]['output']
    assert len(diagnostic) <= 8300 and '_opaque_ref' in diagnostic and path in diagnostic
    assert 'new_duplicate_python_module_global' in diagnostic
    receipt = failed['behavioral_evidence'][0]
    assert receipt['reason'] == 'new_duplicate_python_module_global'
    pinned = next(a for a in receipt['artifacts'] if a['path'].endswith('python-global-preflight.json'))
    preflight = json.loads(Path(pinned['path']).read_text())
    assert preflight['candidate_executed'] is False and preflight['completion_authority'] is False
    assert preflight['files'][0]['collisions'][0]['name'] == '_opaque_ref'
    assert hashlib.sha256(Path(pinned['path']).read_bytes()).hexdigest() == pinned['sha256']
    passed = run(before + 'def _durability_ref(value):\n return value.get("ref")\n', 'rename')
    assert passed['passed'] is True and passed['returncode'] == 0
    assert len(calls) == 2 and '--collect-only' in calls[0] and '--collect-only' not in calls[1]
    receipt = passed['behavioral_evidence'][0]
    assert receipt['admitted'] is True and receipt['completion_authority'] is False
    assert receipt['host_measurement']['python_global_preflight']['passed'] is True
    assert len(receipt['host_measurement']['required_nodeids']) == 2
    assert len([a for a in receipt['host_measurement']['artifacts'] if a['path'].endswith('.network.json')]) == 2
    assert len([a for a in receipt['host_measurement']['artifacts'] if a['path'].endswith('.guard.json')]) == 2
