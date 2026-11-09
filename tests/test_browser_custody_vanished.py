"""Bounded custody restart mechanics with genuine owned kernel disappearances.

The node/root role argv and census rows below are explicit unit fixtures, not
Chromium runtime authority. Their PIDs, parent edges, births and executable
digests are real inert Python children. The stale descendant was genuinely
reaped before its /proc metadata read. Actual pinned Node/Chromium acceptance
is qualified separately by the native-browser custody tests.
"""
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import select
import subprocess
import sys

import pytest

from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

_ROOT_PROGRAM = '''import json,os,subprocess,sys
child = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'pass'])
child.wait(timeout=10)
print(json.dumps({'root': os.getpid(), 'gone': child.pid}), flush=True)
sys.stdin.buffer.read()
'''
_NODE_PROGRAM = '''import subprocess,sys
root = subprocess.Popen([sys.executable, '-I', '-B', '-c', sys.argv[1]],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
try:
    line = root.stdout.readline()
    if not line: raise SystemExit(97)
    print(line, end='', flush=True)
    sys.stdin.buffer.read()
finally:
    root.stdin.close()
    root.wait(timeout=10)
    root.stdout.close()
    if root.returncode: raise SystemExit(root.returncode)
'''


@pytest.fixture
def kernel_scope(tmp_path):
    """Real owned inert lineage; browser role strings are deliberately synthetic."""
    child = subprocess.Popen([sys.executable, '-I', '-B', '-c', _NODE_PROGRAM, _ROOT_PROGRAM],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert select.select([child.stdout], [], [], 20)[0], 'owned inert lineage did not report'
        row = json.loads(child.stdout.readline(8192))
        node_birth = browser._process_birth(child.pid)
        root_birth = browser._process_birth(row['root'])
        assert node_birth[0] == os.getpid() and root_birth[0] == child.pid
        assert not (Path('/proc') / str(row['gone'])).exists()
        with pytest.raises(FileNotFoundError):
            (Path('/proc') / str(row['gone']) / 'stat').read_bytes()
        profile = tmp_path / 'unit-profile'
        profile.mkdir(mode=0o700)
        node = browser.PinnedExecutable('unit-node-role', node_birth[3],
            browser._sha256_file(Path('/proc') / str(child.pid) / 'exe'),
            (node_birth[3], '/unit/driver/cli.js', 'run-driver'))
        chrome = browser.PinnedExecutable('unit-browser-role', root_birth[3],
            browser._sha256_file(Path('/proc') / str(row['root']) / 'exe'), (root_birth[3],))
        root_argv = (chrome.path, '--headless', '--user-data-dir=' + str(profile), '--remote-debugging-pipe')
        live = {child.pid: (os.getpid(), node.argv, node.path),
                row['root']: (child.pid, root_argv, chrome.path)}
        stale = {**live, row['gone']: (row['root'],
            (chrome.path, '--type=renderer', '--user-data-dir=' + str(profile)), chrome.path)}
        yield {'node': node, 'chrome': chrome, 'profile': profile, 'node_pid': child.pid,
               'root_pid': row['root'], 'gone_pid': row['gone'], 'live': live, 'stale': stale}
    finally:
        child.stdin.close()
        child.wait(timeout=20)
        stderr = child.stderr.read()
        child.stdout.close()
        child.stderr.close()
        assert child.returncode == 0, stderr


def _unit_census(monkeypatch, scope, snapshots):
    """Record proof boundaries while all pin/birth reads still hit real /proc."""
    generations, checks = [], []
    actual_pin = browser._pinned_process
    def census():
        generations.append(len(generations) + 1)
        return snapshots[min(len(generations) - 1, len(snapshots) - 1)]
    def pin(pid, executable):
        checks.append((len(generations), pid))
        return actual_pin(pid, executable)
    monkeypatch.setattr(browser, '_process_table', census)
    monkeypatch.setattr(browser, '_pinned_process', pin)
    return generations, checks


def test_genuine_reaped_pid_restarts_the_entire_custody_proof(kernel_scope, monkeypatch):
    scope = kernel_scope
    generations, checks = _unit_census(monkeypatch, scope, [scope['stale'], scope['live']])
    browser._assert_process_custody(scope['node'], scope['chrome'], scope['profile'])
    assert generations == [1, 2]
    for generation in generations:
        assert {scope['node_pid'], scope['root_pid']} <= {pid for epoch, pid in checks if epoch == generation}
    assert (1, scope['gone_pid']) in checks and (2, scope['gone_pid']) not in checks


def test_repeated_genuine_disappearance_stops_after_three_full_proofs_without_sleep(kernel_scope, monkeypatch):
    scope = kernel_scope
    generations, checks = _unit_census(monkeypatch, scope, [scope['stale']])
    with monkeypatch.context() as bounded:
        bounded.setattr(browser.time, 'sleep', lambda *_: pytest.fail('custody reproof must not sleep'))
        with pytest.raises(browser.BrowserCapabilityError):
            browser._assert_process_custody(scope['node'], scope['chrome'], scope['profile'])
    assert generations == [1, 2, 3]
    for generation in generations:
        assert {scope['node_pid'], scope['root_pid'], scope['gone_pid']} <= {
            pid for epoch, pid in checks if epoch == generation}


def test_fresh_census_cannot_borrow_pre_disappearance_driver_arguments(kernel_scope, monkeypatch):
    scope = kernel_scope
    changed = {**scope['live'], scope['node_pid']:
        (os.getpid(), (*scope['node'].argv, '--inspect=0'), scope['node'].path)}
    generations, _ = _unit_census(monkeypatch, scope, [scope['stale'], changed])
    with pytest.raises(browser.BrowserCapabilityError, match='driver arguments'):
        browser._assert_process_custody(scope['node'], scope['chrome'], scope['profile'])
    assert generations == [1, 2]


def test_unproved_numeric_absence_after_tagging_prevents_restart(kernel_scope, monkeypatch):
    scope = kernel_scope
    generations, _ = _unit_census(monkeypatch, scope, [scope['stale'], scope['live']])
    actual_absent = browser._numeric_pid_absent
    checks = []
    def absence(pid):
        checks.append(pid)
        # Unit fault models an unknown or reappeared numeric PID, not a claim
        # that the kernel physically reused the reaped child in this test.
        return actual_absent(pid) if len(checks) == 1 else False
    monkeypatch.setattr(browser, '_numeric_pid_absent', absence)
    with pytest.raises(browser.BrowserCapabilityError):
        browser._assert_process_custody(scope['node'], scope['chrome'], scope['profile'])
    assert checks[:2] == [scope['gone_pid'], scope['gone_pid']]
    assert generations == [1]


def _unit_birth_census(monkeypatch, scope, snapshots):
    generations, reads = [], []
    actual_birth = browser._process_birth
    def census():
        generations.append(len(generations) + 1)
        return snapshots[min(len(generations) - 1, len(snapshots) - 1)]
    def birth(pid):
        reads.append((len(generations), pid))
        return actual_birth(pid)
    monkeypatch.setattr(browser, '_process_table', census)
    monkeypatch.setattr(browser, '_process_birth', birth)
    return generations, reads


def test_genuine_reaped_pid_restarts_the_entire_matching_inventory(kernel_scope, monkeypatch):
    scope = kernel_scope
    generations, reads = _unit_birth_census(monkeypatch, scope, [scope['stale'], scope['live']])
    matched = browser._matching_pids((str(scope['profile']), scope['node'].argv[1]))
    assert matched == {scope['node_pid'], scope['root_pid']}
    assert generations == [1, 2]
    for generation in generations:
        assert {os.getpid(), scope['node_pid'], scope['root_pid']} <= {
            pid for epoch, pid in reads if epoch == generation}
    assert (1, scope['gone_pid']) in reads and (2, scope['gone_pid']) not in reads


def test_matching_inventory_reproof_is_limited_to_three_full_censuses(kernel_scope, monkeypatch):
    scope = kernel_scope
    generations, reads = _unit_birth_census(monkeypatch, scope, [scope['stale']])
    with monkeypatch.context() as bounded:
        bounded.setattr(browser.time, 'sleep', lambda *_: pytest.fail('matching reproof must not sleep'))
        with pytest.raises(browser.BrowserCapabilityError):
            browser._matching_pids((str(scope['profile']), scope['node'].argv[1]))
    assert generations == [1, 2, 3]
    for generation in generations:
        assert {os.getpid(), scope['node_pid'], scope['root_pid'], scope['gone_pid']} <= {
            pid for epoch, pid in reads if epoch == generation}


def test_matching_inventory_rechecks_numeric_absence_before_retry(kernel_scope, monkeypatch):
    scope = kernel_scope
    generations, _ = _unit_birth_census(monkeypatch, scope, [scope['stale'], scope['live']])
    actual_absent, checks = browser._numeric_pid_absent, []
    def absence(pid):
        checks.append(pid)
        return actual_absent(pid) if len(checks) == 1 else False
    monkeypatch.setattr(browser, '_numeric_pid_absent', absence)
    with pytest.raises(browser.BrowserCapabilityError):
        browser._matching_pids((str(scope['profile']), scope['node'].argv[1]))
    assert checks[:2] == [scope['gone_pid'], scope['gone_pid']]
    assert generations == [1]


@pytest.mark.parametrize('error', [
    PermissionError(errno.EACCES, 'unit denied metadata', '/proc/forbidden/stat'),
    FileNotFoundError(errno.ENOENT, 'unit unrelated missing file', '/unit/missing-file'),
    *[browser.BrowserCapabilityError('unit ' + policy + ' failure')
      for policy in ('pin', 'uid', 'CDP', 'profile', 'ancestry')],
])
def test_ordinary_failures_never_acquire_retry_authority(monkeypatch, tmp_path, error):
    calls = []
    def once(*args):
        calls.append(args)
        raise error
    monkeypatch.setattr(browser, '_assert_process_custody_once', once)
    monkeypatch.setattr(browser, '_numeric_pid_absent', lambda *_: pytest.fail('ordinary error requested absence authority'))
    with pytest.raises(type(error)) as caught:
        browser._assert_process_custody(None, None, tmp_path)
    assert caught.value is error and len(calls) == 1


@pytest.mark.parametrize('fault', ['permission', 'non_proc_missing', 'wrong_errno'])
def test_missing_numeric_pid_does_not_reclassify_other_metadata_failures(kernel_scope, monkeypatch, tmp_path, fault):
    pid = kernel_scope['gone_pid']
    target = Path('/proc') / str(pid) / 'stat'
    actual_read = Path.read_bytes
    failure = (PermissionError(errno.EACCES, 'unit denied metadata', str(target)) if fault == 'permission'
        else FileNotFoundError(errno.EIO, 'unit non-disappearance errno', str(target)) if fault == 'wrong_errno'
        else FileNotFoundError(errno.ENOENT, 'unit unrelated file disappeared', str(tmp_path / 'unrelated')))
    def read(path):
        if path == target: raise failure
        return actual_read(path)
    monkeypatch.setattr(Path, 'read_bytes', read)
    with pytest.raises(browser.BrowserCapabilityError) as caught:
        browser._process_birth(pid)
    assert not isinstance(caught.value, browser._VanishedBrowserProcess)
    assert caught.value.__cause__ is failure


@pytest.mark.parametrize('pid', [True, 0, -1])
def test_invalid_pid_never_receives_vanished_process_authority(pid):
    with pytest.raises(browser.BrowserCapabilityError) as caught:
        browser._process_birth(pid)
    assert not isinstance(caught.value, browser._VanishedBrowserProcess)


def test_unreaped_owned_zombie_is_present_and_cannot_be_tagged_vanished():
    child = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'pass'])
    try:
        os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT)
        fields = (Path('/proc') / str(child.pid) / 'stat').read_bytes().rsplit(b')', 1)[1].split()
        assert fields[0] == b'Z'
        assert browser._numeric_pid_absent(child.pid) is False
        with pytest.raises(browser.BrowserCapabilityError) as caught:
            browser._process_birth(child.pid)
        assert not isinstance(caught.value, browser._VanishedBrowserProcess)
    finally:
        assert child.wait(timeout=10) == 0


@contextmanager
def _owned_waiter():
    child = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import sys; sys.stdin.buffer.read()'],
        stdin=subprocess.PIPE)
    try:
        yield child
    finally:
        if not child.stdin.closed: child.stdin.close()
        assert child.wait(timeout=10) == 0


@pytest.mark.parametrize('unrelated', [False, True])
def test_executable_digest_disappearance_requires_its_exact_proc_path(monkeypatch, tmp_path, unrelated):
    with _owned_waiter() as child:
        birth = browser._process_birth(child.pid)
        target = Path('/proc') / str(child.pid) / 'exe'
        actual_sha = browser._sha256_file
        pin = browser.PinnedExecutable('owned-inert-python', birth[3], actual_sha(target), (birth[3],))
        def digest(path):
            if path == target:
                child.stdin.close()
                assert child.wait(timeout=10) == 0
                if unrelated:
                    raise FileNotFoundError(errno.ENOENT, 'unit unrelated file', str(tmp_path / 'unrelated'))
            return actual_sha(path)
        monkeypatch.setattr(browser, '_sha256_file', digest)
        with pytest.raises(browser.BrowserCapabilityError) as caught:
            browser._pinned_process(child.pid, pin)
        assert isinstance(caught.value, browser._VanishedBrowserProcess) is not unrelated
        if not unrelated:
            assert caught.value.pid == child.pid
            assert isinstance(caught.value.__cause__, FileNotFoundError)
            assert caught.value.__cause__.filename == str(target)
