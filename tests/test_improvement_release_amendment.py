"""A second pending-only amendment retains the complete immutable pointer chain."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from integrations.ipfs_accelerate import improvement_amendment as prior
from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate import improvement_recovery as recovery
from integrations.ipfs_accelerate import improvement_release_amendment as amendment
from integrations.ipfs_accelerate import improvement_runner as runner
from tests.test_improvement_plan_amendment import (
    stopped, _apply as apply_prior, _change_native, _git, _state, _unamended_synthetic_spec,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.mark.parametrize('narrative_applied',[False,True])
@pytest.mark.parametrize('release_applied',[False,True])
def test_synthetic_fixture_is_independent_of_both_reviewed_source_amendments(narrative_applied,release_applied):
    source=compiler.load_spec(Path(__file__).resolve().parents[1]/compiler.SPEC_RELATIVE)
    baseline=_unamended_synthetic_spec(source)
    candidate=prior.amended_spec(baseline) if narrative_applied else deepcopy(baseline)
    if release_applied:
        candidate=amendment.amended_spec(candidate)
    before=deepcopy(candidate)
    assert _unamended_synthetic_spec(candidate)==baseline
    assert candidate==before


@pytest.mark.parametrize('partial',['target','validation','guidance'])
def test_synthetic_normalization_rejects_partial_unreviewed_recipe(partial):
    source=compiler.load_spec(Path(__file__).resolve().parents[1]/compiler.SPEC_RELATIVE)
    baseline=_unamended_synthetic_spec(source)
    task=next(item for item in baseline['tasks'] if item['id']==prior.TASK)
    if partial=='target':task['targets'].append(prior.BASELINE_TEST)
    elif partial=='validation':task['validation_commands'][0]+=' '+prior.BASELINE_TEST
    else:task['implementation_prompt']+='\n\n'+prior.GUIDANCE
    with pytest.raises(ValueError,match='incomplete or unfamiliar'):
        _unamended_synthetic_spec(baseline)


@pytest.mark.parametrize('partial',['phase','guidance','missing_edge'])
def test_synthetic_normalization_rejects_incomplete_release_phase_recipe(partial):
    source=compiler.load_spec(Path(__file__).resolve().parents[1]/compiler.SPEC_RELATIVE)
    baseline=_unamended_synthetic_spec(source)
    if partial=='missing_edge':baseline=amendment.amended_spec(baseline)
    task=next(item for item in baseline['tasks'] if item['id']==amendment.TASK)
    if partial=='phase':task['validation_commands'][1]=amendment.PRE_ADMISSION_COMMAND
    elif partial=='guidance':task['implementation_prompt']+='\n\n'+amendment.GUIDANCE
    else:task['depends_on'].remove(amendment.PREREQUISITE)
    with pytest.raises(ValueError,match='incomplete release phase'):
        _unamended_synthetic_spec(baseline)


@pytest.fixture
def nested(stopped):
    first = apply_prior(stopped)
    pointer = json.loads((stopped['base'] / 'active_epoch.json').read_text())
    prior_directory = (stopped['base'] / pointer['amendment']).parent
    # Model a genuine later stopped launch using v2, without running a provider.
    launcher_path = stopped['state'] / 'launcher.json'
    launcher = json.loads(launcher_path.read_text())
    launcher['plan_id'] = first['new_plan_id']
    runner._atomic_json(launcher_path, launcher)
    stopped.update(prior_receipt=first, prior_pointer=pointer, prior_directory=prior_directory)
    return stopped


def review(context):
    return amendment.review_release_dependency_amendment(context['root'], context['spec'], context['base'],
        baseline_receipt_sha256=recovery._digest(context['baseline'].read_bytes()))


def apply(context, expected=None):
    return amendment.apply_release_dependency_amendment(context['root'], context['spec'], context['base'],
        expected=expected or review(context))


def immutable(context):
    files=[context['baseline'], context['quarantine'], context['state'] / recovery.RECEIPT_NAME]
    files.extend(path for path in context['prior_directory'].iterdir() if path.is_file())
    return {path:path.read_bytes() for path in files}


def resolve(context):
    return recovery.resolve_active_epoch(context['root'], context['spec'], context['base'])


def test_nested_amendment_adds_pending_release_dependency_with_all_cids_and_history_untouched(nested):
    old_board=nested['board'].read_bytes()
    blocks=prior._blocks(old_board)
    # Preserve status changes and operator notes made after the v2 snapshot.
    later=blocks[prior.TASK].replace(b'- Status: todo\n',
        b'- Status: completed\n- Later opaque runtime note: keep  two spaces\n',1)
    nested['board'].write_bytes(old_board.replace(blocks[prior.TASK],later,1))
    _,native=runner._native_modules(nested['root'])
    old_tasks=prior._tasks(native,nested['root'],nested['board'].read_bytes())
    tui2_cid=old_tasks[prior.TASK].canonical_task_cid
    _change_native(nested,implementation_attempts={prior.BASELINE_TASK:4,prior.TASK:1},
        implementation_attempts_by_cid={prior.BASELINE_CID:4,tui2_cid:1},
        completed_task_ids=[prior.BASELINE_TASK,prior.TASK],
        task_statuses={prior.BASELINE_TASK:'completed',prior.TASK:'completed',amendment.TASK:'waiting'})
    before_state=_state(nested)
    old_files=immutable(nested)
    old_blocks=prior._blocks(nested['board'].read_bytes())
    queue_path=nested['state']/'merge-queue/merge_queue.duckdb'
    queue_bytes=queue_path.read_bytes()
    expected=review(nested)
    assert _state(nested)==before_state
    assert {path:path.read_bytes() for path in old_files}==old_files
    receipt=apply(nested,expected)
    assert receipt['schema']==amendment.SCHEMA
    assert receipt['old_plan_id']!=receipt['new_plan_id']
    assert receipt['added_dependency']==amendment.PREREQUISITE
    assert receipt['pre_admission_validation_command']==amendment.PRE_ADMISSION_COMMAND
    assert receipt['post_completion_validation_command']==amendment.POST_COMPLETION_COMMAND
    assert receipt['changed_task_cid_ids']==[]  # Native semantic IDs exclude dependency edges.
    assert all(receipt[key] is False for key in prior._NO_AUTHORITY)
    assert receipt['preserved_attempts']['implementation_attempts']==before_state['implementation_attempts']
    assert _state(nested)==before_state
    assert queue_path.read_bytes()==queue_bytes
    assert {path:path.read_bytes() for path in old_files}==old_files
    pointer=json.loads((nested['base']/'active_epoch.json').read_text())
    assert pointer['schema']==amendment.POINTER_SCHEMA
    assert pointer['origin_plan_id']==nested['prior_pointer']['origin_plan_id']
    assert pointer['prior_plan_id']==nested['prior_pointer']['plan_id']
    assert resolve(nested)==nested['state']
    after_tasks=prior._tasks(native,nested['root'],nested['board'].read_bytes())
    assert {key:task.canonical_task_cid for key,task in old_tasks.items()}=={key:task.canonical_task_cid for key,task in after_tasks.items()}
    assert after_tasks[amendment.TASK].depends_on==old_tasks[amendment.TASK].depends_on+[amendment.PREREQUISITE]
    assert after_tasks[amendment.TASK].validation==[
        old_tasks[amendment.TASK].validation[0],amendment.PRE_ADMISSION_COMMAND]
    assert amendment.GUIDANCE in after_tasks[amendment.TASK].metadata['runtime guidance']
    assert after_tasks[prior.BASELINE_TASK].canonical_task_cid==prior.BASELINE_CID
    assert {key:task.status for key,task in old_tasks.items()}=={key:task.status for key,task in after_tasks.items()}
    after_blocks=prior._blocks(nested['board'].read_bytes())
    assert all(after_blocks[key]==value for key,value in old_blocks.items() if key!=amendment.TASK)
    old_spec=json.loads((nested['prior_directory']/'new_spec.snapshot').read_bytes())
    new_spec=json.loads(nested['spec'].read_bytes())
    old_plan=compiler.build_improvement_work_plan(old_spec)
    new_plan=compiler.build_improvement_work_plan(new_spec)
    assert {task.task_id:tuple(task.depends_on) for task in old_plan.tasks if task.task_id!=amendment.TASK}=={
        task.task_id:tuple(task.depends_on) for task in new_plan.tasks if task.task_id!=amendment.TASK}
    old_release=next(task for task in old_plan.tasks if task.task_id==amendment.TASK)
    new_release=next(task for task in new_plan.tasks if task.task_id==amendment.TASK)
    assert new_release.depends_on==old_release.depends_on+(amendment.PREREQUISITE,)
    # Current v3 artifacts cannot pass an active v2 check; only its hash-bound
    # historical snapshots authorize the predecessor during nested resolution.
    with pytest.raises(ValueError,match='current amended|current specification'):
        prior.resolve_amended_epoch(nested['root'],nested['spec'],nested['base'],
            nested['prior_pointer'],nested['prior_pointer']['plan_id'])
    before_compile=nested['board'].read_bytes()
    generated=compiler.generate(nested['spec'],nested['root'])
    assert generated['receipt']['plan_id']==receipt['new_plan_id']
    assert nested['board'].read_bytes()==before_compile
    assert _state(nested)==before_state


@pytest.mark.parametrize('damage',['prior_receipt','prior_snapshot','origin','quarantine','new_snapshot',
    'current_spec','current_plan','current_board','current_phase','pointer_prior_plan','pointer_origin_plan','pointer_path'])
def test_nested_chain_rejects_changed_immutable_or_current_contract(nested,damage):
    apply(nested)
    pointer_path=nested['base']/'active_epoch.json'
    pointer=json.loads(pointer_path.read_text())
    directory=(nested['base']/pointer['amendment']).parent
    if damage.startswith('pointer_'):
        key={'pointer_prior_plan':'prior_plan_id','pointer_origin_plan':'origin_plan_id','pointer_path':'amendment'}[damage]
        pointer[key]='foreign-plan' if damage!='pointer_path' else 'amendments/../receipt.json'
        runner._atomic_json(pointer_path,pointer)
    else:
        target={'prior_receipt':nested['prior_directory']/'receipt.json',
            'prior_snapshot':nested['prior_directory']/'old_board.snapshot',
            'origin':nested['state']/recovery.RECEIPT_NAME,'quarantine':nested['quarantine'],
            'new_snapshot':directory/'old_pointer.snapshot','current_spec':nested['spec'],
            'current_plan':nested['root']/compiler.PLAN_RELATIVE,'current_board':nested['board'],
            'current_phase':nested['board']}[damage]
        if damage=='current_plan':
            value=json.loads(target.read_text());value['metadata']['title']='Foreign formal contract'
            target.write_text(json.dumps(value))
        elif damage=='current_board':
            target.write_bytes(target.read_bytes().replace(b'- Depends on: ',b'- Depends on: UNKNOWN-001, ',1))
        elif damage=='current_phase':
            _,native=runner._native_modules(nested['root'])
            before=prior._tasks(native,nested['root'],target.read_bytes())
            target.write_bytes(target.read_bytes().replace(
                amendment.PRE_ADMISSION_COMMAND.encode(),amendment.POST_COMPLETION_COMMAND.encode(),1))
            after=prior._tasks(native,nested['root'],target.read_bytes())
            assert before[amendment.TASK].canonical_task_cid==after[amendment.TASK].canonical_task_cid
            assert before[amendment.TASK].validation!=after[amendment.TASK].validation
        else:target.write_bytes(target.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='amendment|amended|original|plan binding'):
        resolve(nested)


@pytest.mark.parametrize('changes',[
    {'implementation_attempts':{amendment.TASK:1,prior.BASELINE_TASK:4}},
    {'implementation_in_progress':True,'active_task_id':prior.TASK},
    {'blocked_task_ids':[amendment.TASK]},
    {'completed_task_ids':[prior.BASELINE_TASK,amendment.TASK]},
    {'protected_implementation_attempts':{'opaque-latch':{'task_id':amendment.TASK,'attempt':1}}},
])
def test_attempted_held_completed_or_active_task_refuses_second_amendment(nested,changes):
    expected=review(nested)
    _change_native(nested,**changes)
    before={path:path.read_bytes() for path in [nested['spec'],nested['board'],nested['base']/'active_epoch.json']}
    with pytest.raises(ValueError,match='active|completed|held|consumed'):
        apply(nested,expected)
    assert {path:path.read_bytes() for path in before}==before


def test_target_canonical_history_and_strategy_manual_hold_are_not_ignored(nested):
    expected=review(nested)
    events=nested['state']/f'{runner.STATE_PREFIX}_events.jsonl'
    events.write_text(json.dumps({'type':'implementation_started','canonical_task_cid':expected['old_task_cid']})+'\n')
    events.chmod(0o600)
    with pytest.raises(ValueError,match='execution history'):
        apply(nested,expected)
    events.unlink()  # Only remove the synthetic test-created fixture.
    runner._atomic_json(nested['state']/f'{runner.STATE_PREFIX}_strategy.json',{'blocked_tasks':[amendment.TASK]})
    with pytest.raises(ValueError,match='strategy hold'):
        apply(nested,expected)


def test_board_manual_hold_never_grants_an_amendment(nested):
    raw=nested['board'].read_bytes();blocks=prior._blocks(raw)
    changed=blocks[amendment.TASK].replace(b'- Status: todo\n',b'- Status: todo\n- Manual hold: true\n',1)
    nested['board'].write_bytes(raw.replace(blocks[amendment.TASK],changed,1))
    with pytest.raises(ValueError,match='untouched pending'):
        review(nested)


@pytest.mark.parametrize('changed',['source_head','pointer','board'])
def test_second_recipe_uses_exact_reviewed_source_and_pointer_cas(nested,changed):
    expected=review(nested)
    if changed=='source_head':
        _git(nested['root'],'-c','user.name=Synthetic','-c','user.email=test@example.invalid',
            'commit','--allow-empty','-m','Later reviewed source')
    else:
        path=nested['base']/'active_epoch.json' if changed=='pointer' else nested['board']
        path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='CAS inputs'):
        apply(nested,expected)
    assert json.loads((nested['base']/'active_epoch.json').read_text())['schema']==prior.POINTER_SCHEMA


@pytest.mark.parametrize('boundary',['plan','pointer'])
def test_partial_second_publication_preserves_native_history_and_blocks_startup(nested,monkeypatch,boundary):
    before_state=_state(nested)
    before_files=immutable(nested)
    writer=prior._write
    target=nested['root']/compiler.PLAN_RELATIVE if boundary=='plan' else nested['base']/'active_epoch.json'
    def interrupted(path,raw,**kwargs):
        if path==target:raise OSError('synthetic second publication interruption')
        return writer(path,raw,**kwargs)
    monkeypatch.setattr(prior,'_write',interrupted)
    with pytest.raises(OSError,match='publication interruption'):
        apply(nested)
    assert _state(nested)==before_state
    assert {path:path.read_bytes() for path in before_files}==before_files
    with pytest.raises(ValueError,match='plan binding'):
        resolve(nested)
    assert len(list((nested['base']/'amendments').glob('*/receipt.json')))==2
    assert json.loads((nested['base']/'active_epoch.json').read_text())['schema']==prior.POINTER_SCHEMA


def test_recipe_cannot_change_another_dependency_or_apply_twice(nested):
    spec=json.loads(nested['spec'].read_text())
    changed=amendment.amended_spec(spec)
    original=deepcopy(spec)
    release=next(task for task in original['tasks'] if task['id']==amendment.TASK)
    release['depends_on'].append(amendment.PREREQUISITE)
    release['validation_commands'][1]=amendment.PRE_ADMISSION_COMMAND
    release['implementation_prompt']+='\n\n'+amendment.GUIDANCE
    assert changed==compiler.validate_spec(original)
    with pytest.raises(ValueError,match='already applied'):
        amendment.amended_spec(changed)
    apply(nested)
    with pytest.raises(ValueError,match='current v2 pointer'):
        review(nested)
