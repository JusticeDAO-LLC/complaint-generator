"""Host source admission and custody invariants, using private synthetic roots.

The companion protocol has its own explicitly synthetic, committed SDK tree;
it never assumes the installed Native API is absent. Separate tests admit the
actual current pinned Native module without a companion configuration. Neither
fixture is evidence that an actual campaign claim was released. The SDK's own
tests qualify its real review/reconcile implementation.
"""
from copy import deepcopy
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import pending_claim_runtime as runtime
from integrations.ipfs_accelerate import improvement_runner as runner
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root).decode().strip()


def _protocol_sdk(tmp_path, monkeypatch):
    """Real Git/source custody for an explicitly synthetic companion owner.

    Production source verification is unchanged. Minimal committed modules
    provide only the loader's identity protocol, not Native adjudication.
    """
    sdk = tmp_path / "synthetic-runtime-sdk"; sdk.mkdir()
    parent_name = runtime.MODULE.rsplit(".", 1)[0]
    names = [parent_name, native.__name__,
        parent_name + ".current_incident_adjudication",
        parent_name + ".portal_task_state_control_plane",
        "ipfs_accelerate_py.agent_supervisor.merge.worktree_lifecycle",
        "ipfs_accelerate_py.agent_supervisor.merge.checkout_lock",
        "ipfs_accelerate_py.agent_supervisor.merge.merge_queue",
        "ipfs_accelerate_py.agent_supervisor.merge.workspace_quarantine",
        "ipfs_accelerate_py.agent_supervisor.runtime.grok_cli_runner",
        "ipfs_accelerate_py.agent_supervisor.proof.code_proof_obligations",
        "ipfs_accelerate_py.agent_supervisor.validation.proposal_validation"]
    paths = {}
    for name in names:
        path = sdk / (name.replace(".", "/") + ("/__init__.py" if name == parent_name else ".py"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""Synthetic loader protocol fixture; no Native effects."""\nSYNTHETIC_PROTOCOL_ONLY = True\n')
        paths[name] = path
    _git(sdk, "init", "-q"); _git(sdk, "add", ".")
    _git(sdk, "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
         "commit", "-qm", "Synthetic companion-mode source owner")
    modules = {}
    for name, path in paths.items():
        spec = importlib.util.spec_from_file_location(name, path,
            submodule_search_locations=[str(path.parent)] if name == parent_name else None)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setitem(sys.modules, name, module)
        modules[name] = module
    return sdk, modules[native.__name__], modules[parent_name]


@pytest.fixture
def world(tmp_path, monkeypatch):
    from tests.test_improvement_recovery import _spec_text
    from integrations.ipfs_accelerate.improvement_plan import load_spec, build_improvement_work_plan
    from integrations.ipfs_accelerate.campaign import campaign_artifacts
    root = tmp_path / "root"; root.mkdir()
    state = tmp_path / "state"; state.mkdir(mode=0o700)
    spec = root / runner.SPEC_RELATIVE; spec.parent.mkdir(parents=True); spec.write_text(_spec_text())
    source = load_spec(spec); plan_id = build_improvement_work_plan(source).plan_id
    plan = root / campaign_artifacts(source).plan_relative; plan.write_text('{"synthetic_plan":true}')
    helper_root = tmp_path / "approved-sdk"; helper_root.mkdir()
    helper = helper_root / runtime.RELATIVE; helper.parent.mkdir(parents=True)
    helper.write_text('def review(daemon, *, task_id):\n return {"task_id": task_id}\n'
                      'def reconcile(daemon, *, request):\n return {"protocol_fixture": True}\n')
    _git(helper_root, "init", "-q")
    _git(helper_root, "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
         "add", runtime.RELATIVE)
    _git(helper_root, "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
         "commit", "-qm", "Synthetic loader fixture")
    # Build the plan using the real SDK before installing the deliberately
    # limited protocol modules for this fixture's optional companion branch.
    sdk, protocol_native, parent = _protocol_sdk(tmp_path, monkeypatch)
    config = {"schema": runtime.SCHEMA, "repo_root": str(root), "state_dir": str(state),
              "spec_path": str(spec), "spec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest(),
              "plan_id": plan_id, "plan_path": str(plan), "plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
              "runtime_sdk_root": str(sdk), "runtime_sdk_commit": _git(sdk, "rev-parse", "HEAD"),
              "helper_sdk_root": str(helper_root), "helper_sdk_commit": _git(helper_root, "rev-parse", "HEAD"),
              "helper_blob_oid": _git(helper_root, "rev-parse", "HEAD:" + runtime.RELATIVE),
              "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest()}
    path = state / runtime.CONFIG_NAME
    path.write_text(json.dumps(config)); path.chmod(0o600)
    monkeypatch.delitem(sys.modules, runtime.MODULE, raising=False)
    monkeypatch.delattr(parent, "pending_task_claim_recovery", raising=False)
    yield SimpleNamespace(root=root, spec=spec, state=state, plan=plan, helper=helper,
        helper_root=helper_root, config=config, config_path=path, parent=parent,
        native=protocol_native, record={"plan_id": plan_id})
    sys.modules.pop(runtime.MODULE, None)
    if hasattr(parent, "pending_task_claim_recovery"):
        delattr(parent, "pending_task_claim_recovery")


def _load(w):
    return runtime.load_runtime(w.root, w.spec, w.state, w.record, w.native)


def test_source_pinned_loader_uses_true_canonical_identity_without_changing_native(world):
    # This measures only the explicitly synthetic companion protocol. Actual
    # current Native default admission has separate, unmodified-source tests.
    old_path = list(sys.path); old_package_path = list(world.parent.__path__)
    old_native = sys.modules[world.native.__name__]
    module, proof = _load(world)
    assert module.__name__ == runtime.MODULE
    assert module.__file__ == str(world.helper) == module.__spec__.origin
    assert sys.modules[runtime.MODULE] is world.parent.pending_task_claim_recovery is module
    assert module.review(None, task_id="CIMP-OPS-03") == {"task_id": "CIMP-OPS-03"}
    assert proof["mode"] == "pinned_companion" and proof["sha256"] == world.config["helper_sha256"]
    assert list(sys.path) == old_path and list(world.parent.__path__) == old_package_path
    assert str(world.helper_root) not in sys.path
    assert sys.modules[world.native.__name__] is old_native is world.native
    assert _load(world)[0] is module


@pytest.mark.parametrize("field", ["repo_root", "state_dir", "spec_path", "spec_sha256", "plan_id",
    "plan_path", "plan_sha256", "runtime_sdk_root", "runtime_sdk_commit", "helper_blob_oid", "helper_sha256"])
def test_foreign_scope_or_digest_fails_before_code_execution(world, monkeypatch, field):
    config = dict(world.config); config[field] = "different"
    world.config_path.write_text(json.dumps(config))
    monkeypatch.setattr(runtime, "_verified_module", lambda *_: pytest.fail("unverified source executed"))
    with pytest.raises(ValueError): _load(world)
    assert runtime.MODULE not in sys.modules


@pytest.mark.parametrize("change", ["mode", "symlink", "hardlink", "duplicate", "unknown_field", "nonstring"])
def test_unsafe_config_is_never_an_authority(world, change):
    if change == "mode": world.config_path.chmod(0o640)
    elif change == "symlink":
        saved = world.config_path.with_suffix('.saved'); world.config_path.rename(saved); world.config_path.symlink_to(saved)
    elif change == "hardlink": os.link(world.config_path, world.state / "linked.json")
    elif change == "duplicate":
        text = world.config_path.read_text(); world.config_path.write_text(text[:-1] + ',"schema":"' + runtime.SCHEMA + '"}')
    else:
        config = dict(world.config)
        if change == "unknown_field": config["allow_unpinned"] = True
        else: config["helper_sdk_root"] = 3
        world.config_path.write_text(json.dumps(config))
    with pytest.raises(ValueError): _load(world)
    assert runtime.MODULE not in sys.modules


@pytest.mark.parametrize("change", ["source", "commit", "source_alias", "state_mode", "spec", "plan"])
def test_source_and_campaign_changes_are_detected(world, change):
    if change == "source": world.helper.write_text(world.helper.read_text() + "\nCHANGED = True\n")
    elif change == "commit":
        _git(world.helper_root, "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
             "commit", "-qm", "Different source", "--allow-empty")
    elif change == "source_alias":
        saved = world.helper.with_suffix('.saved'); world.helper.rename(saved); world.helper.symlink_to(saved)
    elif change == "state_mode": world.state.chmod(0o750)
    elif change == "spec": world.spec.write_text(world.spec.read_text() + "\n")
    else: world.plan.write_text('{}')
    with pytest.raises(ValueError): _load(world)
    assert runtime.MODULE not in sys.modules


def test_missing_configuration_and_missing_native_facade_fail_closed(world):
    world.config_path.unlink()
    assert not (Path(world.native.__file__).resolve().parents[3] / runtime.RELATIVE).exists()
    with pytest.raises(ValueError, match="runtime_unavailable"): _load(world)


def test_optional_unavailable_runtime_preserves_default_refusal_without_touching_claim(world):
    world.config_path.unlink()
    claim = world.state / "synthetic-claim.json"; claim.write_bytes(b'{"kept":true}')
    result = runtime.reconcile_pending_claim(world.root, world.spec, world.state, world.record, world.native,
        SimpleNamespace(state_path=world.state / 'state.json'), 'CIMP-OPS-03')
    assert result['reconciled'] is False and result['blocked'] is True
    assert result['reason'] == 'pending_claim_runtime_unavailable'
    assert result['completion_authority'] is result['attempt_refunded'] is result['new_attempt_authority'] is False
    assert claim.read_bytes() == b'{"kept":true}'


def test_existing_different_canonical_module_is_not_replaced(world, monkeypatch):
    foreign = SimpleNamespace(__file__="/foreign.py")
    monkeypatch.setitem(sys.modules, runtime.MODULE, foreign)
    with pytest.raises(ValueError, match="identity_conflict"): _load(world)
    assert sys.modules[runtime.MODULE] is foreign


def test_preimported_native_public_module_does_not_need_companion_marker(world, monkeypatch):
    spec = importlib.util.spec_from_file_location(runtime.MODULE, world.helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setitem(sys.modules, runtime.MODULE, module)
    # world owns this attribute's cleanup; do not schedule a second deletion.
    world.parent.pending_task_claim_recovery = module
    assert not hasattr(module, '__complaint_source_sha256__')
    assert runtime._verified_module(world.helper, world.helper.read_bytes(), native_facade=True) is module


@pytest.mark.parametrize('relative', ['merge/merge_queue.py', 'merge/workspace_quarantine.py', 'runtime/grok_cli_runner.py'])
def test_additional_native_support_changes_are_refused_before_companion_import(world, monkeypatch, relative):
    real_source = runtime._source
    def source(root, commit, path):
        if path.endswith('/' + relative):
            raise ValueError('pending_claim_runtime_working_source_changed')
        return real_source(root, commit, path)
    monkeypatch.setattr(runtime, '_source', source)
    monkeypatch.setattr(runtime, '_verified_module', lambda *_a, **_kw: pytest.fail('changed support admitted'))
    with pytest.raises(ValueError, match='working_source_changed'): _load(world)


def test_native_bound_facades_are_preferred_to_module_functions(world, monkeypatch):
    state = {'implementation_attempts': {'task': 1}}; calls = []
    monkeypatch.setattr(runner, '_read_native_state', lambda *_: (deepcopy(state), {'source': 'synthetic_unit_state'}))
    result = {'reconciled': True, 'blocked': False, 'counters_preserved': True,
        'task_status_unchanged': True, 'reason': 'quiesced_pending_task_claim_released',
        **{key: False for key in ('completion_authority', 'attempt_refunded', 'provider_callback_settled', 'new_attempt_authority')}}
    class FacadeProtocol:
        state_path = world.state / 'synthetic.json'
        def review_quiesced_pending_task_claim(self, *, task_id):
            calls.append(('review', task_id)); return {'task_id': task_id}
        def reconcile_quiesced_pending_task_claim(self, *, request):
            calls.append(('reconcile', request)); return result
    module = SimpleNamespace(review=lambda *_a, **_kw: pytest.fail('module bypassed native facade'),
        reconcile=lambda *_a, **_kw: pytest.fail('module bypassed native facade'))
    monkeypatch.setattr(runtime, 'load_runtime', lambda *_: (module, {'mode': 'native'}))
    assert runtime.reconcile_pending_claim(world.root, world.spec, world.state, world.record, world.native,
        FacadeProtocol(), 'task')['reconciled'] is True
    assert calls == [('review', 'task'), ('reconcile', {'task_id': 'task'})]


@pytest.mark.parametrize("changed_field", [None, "protected_implementation_attempts", "task_statuses", "implementation_attempts"])
def test_claim_release_cannot_hide_any_native_state_change(world, monkeypatch, changed_field):
    state = {"implementation_attempts": {"CIMP-OPS-03": 1}, "task_statuses": {"CIMP-OPS-03": "ready"},
             "protected_implementation_attempts": {}, "opaque_future_counter": 7}
    claim = world.state / "synthetic-claim.json"; claim.write_text('{}')
    monkeypatch.setattr(runner, "_read_native_state", lambda *_: (deepcopy(state), {"source": "synthetic_unit_state"}))
    calls = []
    def reconcile(daemon, *, request):
        calls.append(request); claim.unlink()
        if changed_field: state[changed_field] = {"changed": True}
        return {"reconciled": True, "blocked": False, "counters_preserved": True,
                "task_status_unchanged": True, "reason": "quiesced_pending_task_claim_released",
                **{key: False for key in ("completion_authority", "attempt_refunded", "provider_callback_settled", "new_attempt_authority")}}
    module = SimpleNamespace(review=lambda *_a, **kw: dict(kw), reconcile=reconcile)
    monkeypatch.setattr(runtime, "load_runtime", lambda *_: (module, {"source": "synthetic_unit_protocol"}))
    daemon = SimpleNamespace(state_path=world.state / "state.json")
    if changed_field:
        with pytest.raises(ValueError, match="native_state_changed"):
            runtime.reconcile_pending_claim(world.root, world.spec, world.state, world.record, world.native, daemon, "CIMP-OPS-03")
    else:
        result = runtime.reconcile_pending_claim(world.root, world.spec, world.state, world.record, world.native, daemon, "CIMP-OPS-03")
        assert result["reconciled"] and result["completion_authority"] is False
    assert calls == [{"task_id": "CIMP-OPS-03"}] and not claim.exists()


def test_runtime_reproof_prevents_changed_config_between_review_and_reconcile(world, monkeypatch):
    module, _ = _load(world)
    monkeypatch.setattr(runner, "_read_native_state", lambda *_: ({}, {"source": "synthetic_unit_state"}))
    def review(*_a, **_kw):
        world.config_path.chmod(0o640)
        return {}
    monkeypatch.setattr(module, "review", review)
    monkeypatch.setattr(module, "reconcile", lambda *_a, **_kw: pytest.fail("changed config admitted"))
    with pytest.raises(ValueError, match="unsafe_config"):
        runtime.reconcile_pending_claim(world.root, world.spec, world.state, world.record, world.native,
                                        SimpleNamespace(state_path=world.state / 'state.json'), 'CIMP-OPS-03')


@pytest.fixture
def actual_native(tmp_path):
    """Actual current SDK and source verification; no review/release effect."""
    sdk = Path(native.__file__).resolve().parents[3]
    product = Path(runtime.__file__).resolve().parents[2]
    commit = _git(sdk, "rev-parse", "HEAD")
    assert commit == _git(product, "rev-parse", "HEAD:external/ipfs_accelerate_py")
    assert (sdk / runtime.RELATIVE).is_file()
    root = tmp_path / "host"; root.mkdir()
    state = tmp_path / "state"; state.mkdir(mode=0o700)
    spec = root / "spec.json"; spec.write_text('{}')
    return SimpleNamespace(root=root, state=state, spec=spec, sdk=sdk, commit=commit)


def _actual_load(w):
    return runtime.load_runtime(w.root, w.spec, w.state, {}, native)


def test_actual_pinned_native_runtime_is_admitted_without_companion_configuration(actual_native):
    w = actual_native
    assert not (w.state / runtime.CONFIG_NAME).exists()
    module, binding = _actual_load(w)
    path = w.sdk / runtime.RELATIVE
    assert binding["mode"] == "native" and binding["commit"] == w.commit
    assert binding["path"] == module.__file__ == module.__spec__.origin == str(path)
    assert binding["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert binding["blob_oid"] == _git(w.sdk, "rev-parse", "HEAD:" + runtime.RELATIVE)
    assert sys.modules[runtime.MODULE] is module
    assert callable(module.review) and callable(module.reconcile)
    assert callable(native.PortalImplementationDaemon.review_quiesced_pending_task_claim)
    assert callable(native.PortalImplementationDaemon.reconcile_quiesced_pending_task_claim)
    assert all(row["commit"] == w.commit and Path(row["path"]).is_relative_to(w.sdk)
        for row in binding["native_sources"].values())
    assert not (w.state / runtime.CONFIG_NAME).exists()


def test_actual_native_runtime_does_not_execute_an_obsolete_companion_config(actual_native):
    path = actual_native.state / runtime.CONFIG_NAME
    original = b'{"obsolete_companion":"not_admitted"}\n'
    path.write_bytes(original); path.chmod(0o600)
    module, binding = _actual_load(actual_native)
    assert binding["mode"] == "native" and "config_sha256" not in binding
    assert Path(module.__file__) == actual_native.sdk / runtime.RELATIVE
    assert path.read_bytes() == original


@pytest.mark.parametrize("damage", ["state_mode", "foreign_module"])
def test_actual_native_runtime_refuses_unsafe_state_or_a_foreign_cached_module(actual_native, monkeypatch, damage):
    if damage == "state_mode":
        actual_native.state.chmod(0o750)
        reason = "private_state_required"
    else:
        foreign = SimpleNamespace(__file__="/explicit-synthetic-foreign.py")
        monkeypatch.setitem(sys.modules, runtime.MODULE, foreign)
        reason = "native_facade_origin_changed"
    with pytest.raises(ValueError, match=reason):
        _actual_load(actual_native)
    if damage == "foreign_module":
        assert sys.modules[runtime.MODULE] is foreign


def test_recovery_checkout_lease_uses_campaign_namespace_and_rejects_alias(tmp_path, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.merge import checkout_lock as locks
    seen = []
    real_path = locks.board_scoped_checkout_mutation_lock_path
    monkeypatch.setattr(locks, 'board_scoped_checkout_mutation_lock_path',
                        lambda root, ns: seen.append(ns) or real_path(root, ns))
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    with runner._recovery_checkout_lease(tmp_path, board_namespace='complaint-gui-collaboration'): pass
    with runner._recovery_checkout_lease(tmp_path): pass
    assert seen == ['complaint-gui-collaboration', 'complaint-intake-improvement']
    with pytest.raises(ValueError):
        with runner._recovery_checkout_lease(tmp_path, board_namespace='../foreign'): pass
    assert len(seen) == 2
