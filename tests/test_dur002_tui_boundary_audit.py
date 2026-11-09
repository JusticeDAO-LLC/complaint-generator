"""Real terminal boundaries with synthetic storage faults; no migration claim."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

MARKER = "SYNTHETIC_DUR2_TERMINAL_ANSWER_43820"

CHILD = r'''
import hashlib, json, os, socket, subprocess, sys
from pathlib import Path
def blocked(*a, **k):
    raise RuntimeError("external operation blocked")
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
for n in ("Popen", "run", "call", "check_call", "check_output"):
    setattr(subprocess, n, blocked)
os.system = blocked
for n in ("execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
          "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
          "posix_spawn", "posix_spawnp"):
    if hasattr(os, n):
        setattr(os, n, blocked)
import applications.complaint_workspace as workspace
workspace._SESSION_DIR = Path(sys.argv[1])
service = workspace.ComplaintWorkspaceService(workspace._SESSION_DIR)
user = "dur2-cli-audit-user"
service.initialize_private_keys(protection="passphrase", passphrase="synthetic-only-private-unlock-phrase")
service.ensure_private_case_key(user, user)
mode = sys.argv[2]
proof_path = Path(sys.argv[3])
proof = {"fault_reached": False, "answer_requested": False, "answer_in_state": False,
         "state_preserved": False,
         "network_guard": socket.create_connection is blocked, "process_guard": subprocess.Popen is blocked}
real_load, real_save = service._load_state, service._save_state
armed = False
before = None
def fingerprint():
    path = service._session_path(user)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
def fault(code, status):
    global before
    before = fingerprint()
    proof["fault_reached"] = True
    raise workspace.WorkspacePersistenceError("SYNTHETIC_DUR2_TERMINAL_ANSWER_43820",
                                            code=code, public_status=status)
def load(identity):
    if mode == "locked-start":
        fault("unlock_needed", "unlock_needed")
    if mode == "corrupt-start":
        fault("authentication_failed", "recoverable")
    return real_load(identity)
def save(state):
    global before
    if armed:
        proof["answer_in_state"] = state.get("original_complaint", {}).get("text") == "SYNTHETIC_DUR2_TERMINAL_ANSWER_43820"
        if not proof["answer_in_state"]:
            return real_save(state)
        if mode == "locked-after-answer":
            fault("unlock_needed", "unlock_needed")
        before = fingerprint()
        proof["fault_reached"] = True
        raise OSError("SYNTHETIC_DUR2_TERMINAL_ANSWER_43820")
    return real_save(state)
class ObservedInput:
    """Observe consumption of the real pipe without replacing its input."""
    def __init__(self, stream):
        self.stream = stream
    def readline(self, *args, **kwargs):
        global armed
        line = self.stream.readline(*args, **kwargs)
        if line.rstrip("\r\n") == "SYNTHETIC_DUR2_TERMINAL_ANSWER_43820":
            armed = True
            proof["answer_requested"] = True
        return line
    def __getattr__(self, name):
        return getattr(self.stream, name)
service._load_state, service._save_state = load, save
sys.stdin = ObservedInput(sys.stdin)
import complaint_generator.cli as cli
import applications.complaint_cli as implementation
implementation.service = service
sys.argv = ["complaint-workspace", "chat", "--user-id", user, "--max-turns", "1"]
try:
    with workspace.workspace_access_scope(workspace.WorkspaceAccess.authenticated(user, case_id=user)):
        if mode == "direct-chat":
            implementation.chat(user_id=user, max_turns=1)
        else:
            cli.main()
except BaseException:
    proof["state_preserved"] = fingerprint() == before
    proof_path.write_text(json.dumps(proof, sort_keys=True))
    raise
else:
    proof_path.write_text(json.dumps(proof, sort_keys=True))
'''

@pytest.mark.parametrize("mode", ["locked-start", "corrupt-start", "locked-after-answer", "save-oserror", "direct-chat"])
def test_real_terminal_private_storage_refusal_is_safe(tmp_path, mode):
    script = tmp_path / "actual_cli_child.py"
    script.write_text(CHILD)
    session, home = tmp_path / "sessions", tmp_path / "home"
    home.mkdir()
    proof_path = tmp_path / "closed_child_proof.json"
    env = dict(os.environ)
    env.update({"HOME": str(home), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "TERM": "dumb", "NO_COLOR": "1"})
    result = subprocess.run([sys.executable, str(script), str(session), mode, str(proof_path)],
        cwd=Path(__file__).resolve().parents[1], env=env, input=MARKER + "\n\n",
        capture_output=True, text=True, timeout=20)
    combined = result.stdout + result.stderr
    safe_exit, no_trace, no_marker = result.returncode == 2, "Traceback" not in combined, MARKER not in combined
    assert safe_exit, "real terminal did not return documented private-storage refusal code"
    assert no_trace, "real terminal emitted an uncaught private persistence traceback"
    assert no_marker, "real terminal disclosed an answer in operational diagnostics"
    proof = json.loads(proof_path.read_text())
    assert proof["fault_reached"], "terminal refused before intended real service IO fault"
    assert proof["state_preserved"], "injected IO refusal changed prior persisted state"
    assert proof["network_guard"] and proof["process_guard"]
    assert proof["answer_requested"] is (mode not in {"locked-start", "corrupt-start"})
    assert proof["answer_in_state"] is (mode not in {"locked-start", "corrupt-start"})
    reports = []
    for line in result.stdout.splitlines():
        if line.startswith("{"):
            try:
                reports.append(json.loads(line))
            except ValueError:
                pass
    assert len(reports) == 1
    report = reports[0]
    expected = {"locked-start": ("unlock_needed", "unlock_needed"),
                "locked-after-answer": ("unlock_needed", "unlock_needed"),
                "corrupt-start": ("recoverable", "authentication_failed")}
    assert (report["status"], report["code"]) == expected.get(mode, ("unavailable", "workspace_operation_failed"))
    assert report["awaiting_user"] is True
    assert "worker_may_continue" not in report and "worker_state" not in report
    assert report["persistence_outcome"] == "unverified"
