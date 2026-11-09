"""Real Native ingestion and the source-bound synthetic screenshot inputs."""
from pathlib import Path
from graphlib import TopologicalSorter
import hashlib
import json
import struct

import pytest

from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate import improvement_runner as runner

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
ROOT = Path(__file__).resolve().parents[1]
SPEC = 'docs/task_boards/complaint_gui_ux_overhaul_spec.json'
DOC = ROOT/'docs/ux/complaint_ux_overhaul'


def test_actual_native_roundtrip_keeps_old_programs_and_new_tasks_open(tmp_path):
    historical = [
        'docs/task_boards/complaint_intake_task_board.md',
        'docs/task_boards/complaint_mediator_grounding_task_board.md',
        'docs/task_boards/complaint_gui_collaboration_task_board.md',
    ]
    before = {name:(ROOT/name).read_bytes() for name in historical if (ROOT/name).is_file()}
    for name, raw in before.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    source=tmp_path/SPEC;source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes((ROOT/SPEC).read_bytes())
    result=compiler.generate(source,tmp_path)
    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import FormalWorkPlan
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import parse_task_file
    actual=FormalWorkPlan.from_dict(json.loads(Path(result['plan_path']).read_text()))
    expected=compiler.build_improvement_work_plan(compiler.load_spec(source))
    assert actual.plan_id==expected.plan_id and actual.to_dict()==expected.to_dict()
    assert (len(actual.goals),len(actual.subgoals),len(actual.tasks))==(9,22,68)
    tasks=parse_task_file(Path(result['board_path']),task_header_prefix=runner.TASK_PREFIX)
    assert {task.task_id for task in tasks}=={f'CIMP-UX-{n:02d}' for n in range(1,69)}
    assert all(task.status!='completed' for task in tasks)
    assert actual.events==() and result['receipt']['tasks_completed_by_ingestion']==0
    again=compiler.generate(source,tmp_path)
    assert again['receipt']['board_preserved'] is True
    for name,raw in before.items():
        assert (ROOT/name).read_bytes()==raw and (tmp_path/name).read_bytes()==raw


def test_only_baseline_is_initially_ready_and_final_closure_covers_every_task():
    spec=compiler.load_spec(ROOT/SPEC);tasks={task['id']:task for task in spec['tasks']}
    order=tuple(TopologicalSorter({key:set(task['depends_on']) for key,task in tasks.items()}).static_order())
    assert len(order)==68
    assert {key for key,task in tasks.items() if not task['depends_on']}=={'CIMP-UX-01'}
    pending=list(tasks['CIMP-UX-68']['depends_on']);ancestors=set()
    while pending:
        current=pending.pop()
        if current not in ancestors:
            ancestors.add(current);pending.extend(tasks[current]['depends_on'])
    assert ancestors==set(tasks)-{'CIMP-UX-68'}
    assert {'CIMP-UX-22','CIMP-UX-29'}<=ancestors
    inventory=json.loads((DOC/'mediator_hook_source_audit.json').read_text())
    assert len(inventory['hook_matrix'])==13
    assert len({row['hook'] for row in inventory['hook_matrix']})==13
    assert all(row['runtime_qualified_by_this_audit'] is False for row in inventory['hook_matrix'])
    assert spec['provider']=={'router':'ipfs_accelerate_py.llm_router','provider':'grok_cli','model':'grok-4.7','allow_fallback':False}


def test_screenshot_inputs_are_real_complete_synthetic_viewport_bound_pngs():
    manifest=json.loads((DOC/'baseline/screenshot_manifest.json').read_text())
    assert manifest['application_base_commit']=='6f27c60c3b49b8bad49088bd46e788fa31c646eb'
    assert manifest['completed'] is True and manifest['synthetic_data_only'] is True
    assert manifest['provider_invoked'] is False and manifest['mock_api_used'] is False
    assert manifest['screenshot_count']==len(manifest['screenshots'])==13
    assert all(row['cleaned'] and not row['remaining_pids'] for row in manifest['cleanup'])
    seen=set()
    for row in manifest['screenshots']:
        path=DOC/'baseline'/row['path'];assert path.parent==DOC/'baseline'
        raw=path.read_bytes();assert raw[:8]==b'\x89PNG\r\n\x1a\n'
        assert hashlib.sha256(raw).hexdigest()==row['sha256'] and len(raw)==row['bytes']
        assert struct.unpack('>II',raw[16:24])==(row['viewport']['width'],row['viewport']['height'])
        assert row['synthetic'] and row['diagnostic_test_panels_mounted'] is False and row['dom_checks']
        assert row['id'] not in seen;seen.add(row['id'])
    assert {row['viewport']['width'] for row in manifest['screenshots']}=={390,1440}
    assert {'/','/workspace','/case-messages','/admin'}<={row['route'].split('?')[0] for row in manifest['screenshots']}
