"""Real child kernel tests: the test parent never installs a filter."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from integrations.ipfs_accelerate import validation_network as guard


pytestmark = [pytest.mark.no_auto_network, pytest.mark.no_auto_llm, pytest.mark.no_auto_heavy]
ROOT = Path(__file__).resolve().parents[1]


def _inet_creation():
    libc = ctypes.CDLL(None, use_errno=True)
    ctypes.set_errno(0)
    fd = libc.socket(2, 1, 0)
    result = (fd >= 0, 0 if fd >= 0 else ctypes.get_errno())
    if fd >= 0:
        os.close(fd)
    return result


def _write(path, body):
    path.write_text(body)
    path.chmod(0o600)


def _run_child(directory, *, body=None, conftest=None, threaded=False):
    run, candidate = directory / "run", directory / "candidate"
    run.mkdir(mode=0o700)
    candidate.mkdir(mode=0o700)
    binding = guard.prepare_validation_network_guard(run, ROOT)
    manifest = run / "manifest.json"
    _write(run / "network_option_fixture.py", "def pytest_addoption(parser):\n    parser.addoption('--complaint-evidence-path')\n")
    # A CWD module must not displace the absolute-origin host plugin. The actual
    # runner likewise uses -P before -m; PYTHONPATH alone is insufficient.
    _write(candidate / "complaint_owned_network_guard.py", "raise AssertionError('cwd_shadow_loaded')\n")
    _write(candidate / "test_child.py", body or '''
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

def test_kernel_and_exec():
    libc = ctypes.CDLL(None, use_errno=True)
    for family in (2, 10):
        ctypes.set_errno(0)
        assert libc.socket(family, 1, 0) == -1
        assert ctypes.get_errno() == 1
        pair = (ctypes.c_int * 2)(-1, -1)
        ctypes.set_errno(0)
        assert libc.socketpair(family, 1, 0, pair) == -1
        assert ctypes.get_errno() == 1
    pair = (ctypes.c_int * 2)(-1, -1)
    assert libc.socketpair(1, 1, 0, pair) == 0
    try:
        os.write(pair[0], b'unix-still-works')
        assert os.read(pair[1], 64) == b'unix-still-works'
    finally:
        os.close(pair[0]); os.close(pair[1])
    script = "import ctypes; c=ctypes.CDLL(None,use_errno=True); ctypes.set_errno(0); r=c.socket(2,1,0); assert r == -1 and ctypes.get_errno() == 1"
    result = subprocess.run([sys.executable, '-I', '-B', '-c', script], timeout=15, capture_output=True)
    assert result.returncode == 0
''')
    precheck = '''
import json
from pathlib import Path
import sys
p = next(v.split('=', 1)[1] for v in sys.argv if v.startswith('--complaint-evidence-path='))
value = json.loads(Path(p).with_suffix('.network.json').read_text())
assert value['pre']['socket_INET_errno'] == 1
assert value['post'] is None
Path(p).with_suffix('.conftest-observed').write_text('precollection-fenced')
'''
    _write(candidate / "conftest.py", precheck + (conftest or ""))
    args = ["-p", binding["module"], "-p", "network_option_fixture", "--complaint-evidence-path=" + str(manifest),
            "-q", "-o", "addopts=", str(candidate / "test_child.py")]
    if threaded:
        _write(run / "network_thread_fixture.py", '''
import ctypes
import threading
ready = threading.Event()
request = threading.Event()
done = threading.Event()
result = None
def worker():
    global result
    ready.set()
    if not request.wait(20):
        return
    c = ctypes.CDLL(None, use_errno=True)
    ctypes.set_errno(0)
    fd = c.socket(2, 1, 0)
    result = (fd, ctypes.get_errno())
    if fd >= 0:
        import os
        os.close(fd)
    done.set()
thread = threading.Thread(target=worker, daemon=True)
thread.start()
assert ready.wait(10)
''')
        driver = "import sys; import network_thread_fixture; import pytest; sys.argv=['pytest', *sys.argv[1:]]; raise SystemExit(pytest.main(sys.argv[1:]))"
        command = [sys.executable, "-P", "-B", "-c", driver, *args]
    else:
        command = [sys.executable, "-P", "-B", "-m", "pytest", *args]
    home = directory / "home"
    home.mkdir(mode=0o700)
    environment = {"PATH": os.defpath, "HOME": str(home), "PYTHONPATH": str(run),
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                   "LANG": "C.UTF-8"}
    before = _inet_creation()
    result = subprocess.run(command, cwd=candidate, env=environment, capture_output=True, timeout=60)
    assert _inet_creation() == before, "child guard changed parent socket policy"
    _write(directory / "child.stdout", result.stdout.decode(errors="replace"))
    _write(directory / "child.stderr", result.stderr.decode(errors="replace"))
    return binding, manifest, result


def _verify(binding, manifest, code=0):
    return guard.verify_validation_network_proof(
        manifest.with_suffix(".network.json"), expected_plugin_sha256=binding["plugin_sha256"],
        expected_policy_sha256=binding["policy_sha256"], expected_exitstatus=code)


@pytest.fixture(scope="module")
def genuine(tmp_path_factory):
    directory = tmp_path_factory.mktemp("actual-network-child")
    directory.chmod(0o700)
    binding, manifest, result = _run_child(directory)
    assert result.returncode == 0, "real network-plugin child failed; inspect private child logs"
    return binding, manifest


def test_actual_kernel_precollection_and_exec_inheritance(genuine):
    binding, manifest = genuine
    value = _verify(binding, manifest)
    assert value["process"]["pid"] != os.getpid()
    assert value["pre"] == value["post"]
    assert manifest.with_suffix(".conftest-observed").read_text() == "precollection-fenced"
    assert value["completion_authority"] is False
    assert binding["files"] == (ROOT / "integrations/ipfs_accelerate/validation_network.py", binding["plugin_path"])


def test_filter_synchronizes_an_already_existing_thread(tmp_path):
    tmp_path.chmod(0o700)
    binding, manifest, result = _run_child(tmp_path, threaded=True, body='''
def test_existing_thread():
    import network_thread_fixture as t
    t.request.set()
    assert t.done.wait(10)
    assert t.result == (-1, 1)
    t.thread.join(10)
    assert not t.thread.is_alive()
''')
    assert result.returncode == 0, "TSYNC did not fence the existing child thread"
    assert _verify(binding, manifest)["pre"]["tsync"] is True


def test_failed_test_still_has_bound_post_kernel_proof(tmp_path):
    tmp_path.chmod(0o700)
    binding, manifest, result = _run_child(tmp_path, body="def test_failure():\n    assert False\n")
    assert result.returncode == 1
    assert _verify(binding, manifest, 1)["exitstatus"] == 1
    with pytest.raises(ValueError, match="proof_binding"):
        _verify(binding, manifest, 0)


@pytest.mark.parametrize("change", ["pre", "post", "policy", "plugin", "exitstatus", "process"])
def test_verifier_rejects_changed_proof(genuine, change):
    binding, manifest = genuine
    path = manifest.with_suffix(".network.json")
    original = path.read_bytes()
    value = json.loads(original)
    if change in ("pre", "post"):
        value[change]["socketpair_INET6_errno"] = 0
    elif change == "policy":
        value["policy_sha256"] = "0" * 64
    elif change == "plugin":
        value["plugin_sha256"] = "0" * 64
    elif change == "exitstatus":
        value["exitstatus"] = True
    else:
        value["process"]["start_ticks"] = 0
    try:
        path.write_text(json.dumps(value))
        with pytest.raises(ValueError):
            _verify(binding, manifest)
    finally:
        path.write_bytes(original)


def test_verifier_rejects_missing_or_modified_plugin(genuine):
    binding, manifest = genuine
    with pytest.raises(FileNotFoundError):
        _verify(binding, manifest.with_name("absent.json"))
    plugin = binding["plugin_path"]
    original = plugin.read_bytes()
    try:
        plugin.write_bytes(original + b"\n# changed\n")
        with pytest.raises(ValueError, match="plugin_changed"):
            _verify(binding, manifest)
    finally:
        plugin.write_bytes(original)


def test_candidate_cannot_replace_the_preproof(tmp_path):
    tmp_path.chmod(0o700)
    binding, manifest, result = _run_child(tmp_path, conftest="Path(p).with_suffix('.network.json').write_text('{}')\n")
    assert result.returncode != 0
    with pytest.raises(ValueError):
        _verify(binding, manifest, result.returncode)


def test_prepare_refuses_public_or_foreign_origin(tmp_path, monkeypatch):
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="private_directory"):
        guard.prepare_validation_network_guard(tmp_path, ROOT)
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError, match="trusted_origin"):
        guard.prepare_validation_network_guard(tmp_path, tmp_path)
    monkeypatch.setattr(guard.platform, "system", lambda: "unsupported")
    with pytest.raises(ValueError, match="kernel_unavailable"):
        guard.prepare_validation_network_guard(tmp_path, ROOT)


def test_source_generation_is_private_and_cannot_overwrite(tmp_path):
    tmp_path.chmod(0o700)
    before = _inet_creation()
    binding = guard.prepare_validation_network_guard(tmp_path, ROOT)
    assert _inet_creation() == before
    assert binding["plugin_path"].stat().st_mode & 0o777 == 0o600
    assert hashlib.sha256(binding["plugin_path"].read_bytes()).hexdigest() == binding["plugin_sha256"]
    with pytest.raises(FileExistsError):
        guard.prepare_validation_network_guard(tmp_path, ROOT)
