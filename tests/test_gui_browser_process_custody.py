"""Legacy parser/in-memory custody units retain their refusal intent.

Their synthetic process tables do not qualify real browser ownership. Actual
kernel/Chromium authority is exercised separately by the maintenance and02 cases.
"""
from pathlib import Path
import shlex

import pytest

from tests import gui_native_browser as browser

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

PROFILE = Path('/owned/private-profile')
CHROME = browser.PinnedExecutable('chromium', '/approved/chromium', '1' * 64, ('/approved/chromium', '--remote-debugging-pipe'))
NODE = browser.PinnedExecutable('node', '/approved/node', '2' * 64, ('/approved/node', '/approved/cli.js', 'run-driver'))
ARGV = (CHROME.path, '--headless', '--user-data-dir=' + str(PROFILE), '--remote-debugging-pipe', 'about:blank')


def test_chromium_single_linux_title_has_exact_original_arguments():
    assert browser._chromium_title_argv((shlex.join(ARGV),), CHROME, PROFILE) == ARGV
    assert browser._chromium_title_argv(ARGV, CHROME, PROFILE) == ARGV


@pytest.mark.parametrize('argv', [
    (CHROME.path, '--user-data-dir=' + str(PROFILE)),
    (*ARGV, '--remote-debugging-pipe'),
    (*ARGV, '--remote-debugging-pipe=1'),
    (*ARGV, '--user-data-dir=' + str(PROFILE)),
    (*ARGV, '--user-data-dir=/foreign'),
    (*ARGV, '--user-data-dir', str(PROFILE)),
    (*ARGV, '--remote-debugging-port=0'),
    (*ARGV, '--remote-debugging-port', '9222'),
    (*ARGV, '--remote-debugging-address=127.0.0.1'),
    (*ARGV, '--remote-debugging-address', '127.0.0.1'),
    ('/foreign/chromium', *ARGV[1:]),
    (CHROME.path + ' "unterminated',),
    (CHROME.path + '\0' + shlex.join(ARGV[1:]),),
    (*ARGV, 'x' * 65537),
])
def test_title_cannot_change_executable_profile_pipe_or_debug_transport(argv):
    with pytest.raises(browser.BrowserCapabilityError):
        browser._chromium_title_argv(argv, CHROME, PROFILE)


def _table():
    return {10: (1, NODE.argv, NODE.path), 20: (10, (shlex.join(ARGV),), CHROME.path)}


def test_unverified_executable_never_reaches_title_normalization(monkeypatch):
    table = _table()
    monkeypatch.setattr(browser, '_process_table', lambda: table)
    monkeypatch.setattr(browser, '_chromium_title_argv', lambda *args: pytest.fail('unverified title was parsed'))
    def verify(pid, pin):
        if pid == 20:
            raise browser.BrowserCapabilityError('foreign executable')
        return (1, 100, (1000,) * 4, pin.path)
    monkeypatch.setattr(browser, '_pinned_process', verify)
    with pytest.raises(browser.BrowserCapabilityError, match='foreign executable'):
        browser._assert_process_custody(NODE, CHROME, PROFILE)


def test_foreign_parent_never_reaches_title_normalization(monkeypatch):
    monkeypatch.setattr(browser, '_process_table', _table)
    monkeypatch.setattr(browser, '_pinned_process', lambda pid, pin: (1 if pid == 10 else 90, pid * 10, (1000,) * 4, pin.path))
    monkeypatch.setattr(browser, '_process_birth', lambda pid: (pid, pid * 10, (1000,) * 4, '/foreign'))
    monkeypatch.setattr(browser, '_chromium_title_argv', lambda *args: pytest.fail('foreign title was parsed'))
    with pytest.raises(browser.BrowserCapabilityError, match='not owned'):
        browser._assert_process_custody(NODE, CHROME, PROFILE)


def test_ancestry_birth_change_refuses_after_argument_verification(monkeypatch):
    monkeypatch.setattr(browser, '_process_table', _table)
    monkeypatch.setattr(browser.os, 'getpid', lambda: 1)
    monkeypatch.setattr(browser, '_pinned_process', lambda pid, pin: (1 if pid == 10 else 10, pid * 10, (1000,) * 4, pin.path))
    monkeypatch.setattr(browser, '_process_birth', lambda pid: (0, 1, (1000,) * 4, '/python') if pid == 1 else (10, 999, (1000,) * 4, CHROME.path))
    with pytest.raises(browser.BrowserCapabilityError, match='ancestry changed'):
        browser._assert_process_custody(NODE, CHROME, PROFILE)


def test_unrelated_driver_is_not_inspected_or_used_as_browser_owner(monkeypatch):
    table = _table()
    table[30] = (90, NODE.argv, NODE.path)
    identities = {1: (0, 1, (1000,) * 4, '/python'), 10: (1, 100, (1000,) * 4, NODE.path), 20: (10, 200, (1000,) * 4, CHROME.path)}
    checked = []
    monkeypatch.setattr(browser.os, 'getpid', lambda: 1)
    monkeypatch.setattr(browser, '_process_table', lambda: table)
    def pin(pid, _pin):
        checked.append(pid)
        assert pid != 30, 'foreign driver must not participate in this validator proof'
        return identities[pid]
    monkeypatch.setattr(browser, '_pinned_process', pin)
    monkeypatch.setattr(browser, '_process_birth', identities.__getitem__)
    browser._assert_process_custody(NODE, CHROME, PROFILE)
    assert set(checked) == {10, 20}  # Each owned process is pinned; reproof may repeat.
    table[20] = (30, table[20][1], CHROME.path)
    identities[20] = (30, 200, (1000,) * 4, CHROME.path)
    identities[30] = (90, 300, (1000,) * 4, NODE.path)
    identities[90] = (90, 900, (1000,) * 4, '/foreign')
    with pytest.raises(browser.BrowserCapabilityError, match='not owned'):
        browser._assert_process_custody(NODE, CHROME, PROFILE)


def test_kernel_uid_and_running_executable_digest_must_match(monkeypatch):
    import os
    pid = os.getpid()
    exe = os.readlink('/proc/self/exe')
    pin = browser.PinnedExecutable('self', exe, browser._sha256_file(Path('/proc/self/exe')), (exe,))
    before = browser._pinned_process(pid, pin)
    assert before[1] > 0 and before[2] == (os.getuid(),) * 4
    bad_pin = browser.PinnedExecutable('self', exe, '0' * 64, (exe,))
    with pytest.raises(browser.BrowserCapabilityError, match='does not match'):
        browser._pinned_process(pid, bad_pin)
    actual_uid = os.getuid()
    monkeypatch.setattr(browser.os, 'getuid', lambda: actual_uid + 1)
    with pytest.raises(browser.BrowserCapabilityError, match='identity'):
        browser._process_birth(pid)


@pytest.mark.parametrize('argv', [
    (*NODE.argv, '--inspect=0'),
    (NODE.path, '--require', '/foreign/module.js', *NODE.argv[1:]),
    (NODE.path, '-e', 'process.exit(0)', *NODE.argv[1:]),
    (NODE.path, NODE.argv[2], NODE.argv[1]),
    (*NODE.argv, 'extra'),
])
def test_owned_node_requires_exact_pinned_driver_arguments(monkeypatch, argv):
    table = _table()
    table[10] = (1, argv, NODE.path)
    monkeypatch.setattr(browser.os, 'getpid', lambda: 1)
    monkeypatch.setattr(browser, '_process_table', lambda: table)
    monkeypatch.setattr(browser, '_process_birth', lambda pid: (0, 1, (1000,) * 4, '/python'))
    monkeypatch.setattr(browser, '_pinned_process', lambda *args: pytest.fail('wrong driver arguments were admitted'))
    with pytest.raises(browser.BrowserCapabilityError, match='driver arguments'):
        browser._assert_process_custody(NODE, CHROME, PROFILE)
