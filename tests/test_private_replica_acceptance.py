"""Trusted host acceptance, separate from the provider's DUR005 target tests.

An entirely absent replica API is explicitly unsupported baseline behavior.
The trusted Runner rejects that capability for CIMP-DUR-005 even if these
baseline characterizations pass. Partial API surfaces always fail. No check
turns a fixture, local pin, or provider acknowledgement into remote durability.

Concrete API names and local-primary layout follow the unmerged DUR005 proposal.
The optional ``timeout_seconds`` contract is required on remote operations.
Seven fixed owned child probes use the current Data ProcessSupervisor; their
permission and source inventory must be qualified before candidate admission.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import time

import pytest

from integrations import private_storage as storage


API_NAMES = (
    "replica_policy", "publish_encrypted_replicas", "reconcile_encrypted_replicas",
    "restore_encrypted_workspace", "upstream_replication_fixture_qualification",
)
UPSTREAM_SUITES = (
    "tests/runtime_readiness/replication/test_replica_contracts.py",
    "tests/runtime_readiness/replication/test_reconciler.py",
    "tests/runtime_readiness/replication/test_joined_convergence.py",
)
KEY = bytes(range(32))
TRIPLET = (b"synthetic-replica-complaint", b'{"synthetic_fact":1}', b"synthetic-proof-r1")


def _api(record_property):
    present = [callable(getattr(storage, name, None)) for name in API_NAMES]
    assert all(present) or not any(present), "Partial replica APIs are not supported"
    capability = "supported" if all(present) else "unsupported"
    record_property("private_replica_capability", capability)
    return storage if all(present) else None


def _options(**overrides):
    return {"tenant_id": "synthetic-tenant", "case_id": "synthetic-case",
            "principal_id": "synthetic-principal", "key": KEY, "key_id": "synthetic-key",
            **overrides}


def _publish(api, root, *, remote=None, revision="r1", triplet=TRIPLET, **overrides):
    names = tuple(remote or {})
    return api.publish_encrypted_replicas(
        root, **_options(**overrides), revision=revision,
        complaint=triplet[0], fact_graph=triplet[1], proof=triplet[2],
        policy=api.replica_policy(desired_replicas=1 + len(names), minimum_replicas=1,
                                 mode="private_remote" if names else "local_private",
                                 remote_providers=names),
        providers=remote, clock=lambda: 100.0,
    )


class _CiphertextDirectory:
    """A real fsynced synthetic directory copy, not a remote durability claim."""

    def __init__(self, root, *, mode="available"):
        self.root = root
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.mode = mode

    def _record(self, kind):
        fd = os.open(self.root / (kind + "-events"),
                     os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "ab") as stream:
            stream.write((kind + "\n").encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def readback_count(self):
        path = self.root / "readback-events"
        return len(path.read_bytes().splitlines()) if path.exists() else 0

    def place(self, *, digest, version, frame, **_deadline):
        self._record("place")
        assert type(frame) is bytes and all(value not in frame for value in TRIPLET)
        assert hashlib.sha256(frame).hexdigest() == digest
        if self.mode == "queued":
            return {"status": "queued", "pin_state": "queued"}
        path = self.root / digest
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(frame)
                stream.flush()
                os.fsync(stream.fileno())
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        return {"status": "stored", "pin_state": "pinned"}

    def readback(self, *, digest, version, **_deadline):
        self._record("readback")
        if self.mode in {"unavailable", "queued"}:
            return {"status": self.mode}
        frame = (self.root / digest).read_bytes()
        if self.mode == "corrupt":
            frame += b"corrupt"
        return {"status": "available", "frame": frame, "version": version}


def test_replica_api_capability_is_explicit(record_property):
    api = _api(record_property)
    if api is None:
        assert all(not hasattr(storage, name) for name in API_NAMES)
        return
    assert all(callable(getattr(api, name)) for name in API_NAMES)


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_reconcile_rechecks_actual_local_primary(tmp_path, record_property, damage):
    api = _api(record_property)
    if api is None:
        return
    root = tmp_path / "case"
    _publish(api, root)
    primary = root / "replica-ledger" / "primary.frame"
    assert primary.is_file()
    primary.unlink() if damage == "missing" else primary.write_bytes(b"corrupt")
    receipt = api.reconcile_encrypted_replicas(root, clock=lambda: 1000.0)
    assert receipt["primary_verified"] is False
    assert receipt["verified_replica_count"] == 0
    assert receipt["status"] == "unavailable"
    assert receipt["meets_minimum"] is False


@pytest.mark.parametrize("mode", ["queued", "corrupt"])
def test_replica_count_requires_ciphertext_readback_not_placement(tmp_path, record_property, mode):
    api = _api(record_property)
    if api is None:
        return
    provider = _CiphertextDirectory(tmp_path / "ciphertext-copy", mode=mode)
    root = tmp_path / "case"
    receipt = _publish(api, root, remote={"fixture-copy": provider})
    assert receipt["verified_replica_count"] == 1
    assert receipt["meets_desired"] is False
    assert "fixture-copy" in receipt["unavailable_providers"]
    assert all(not row["counted"] for row in receipt["placements"]
               if row["provider"] == "fixture-copy")
    frame = (root / "replica-ledger" / "primary.frame").read_bytes()
    assert all(value not in frame for value in TRIPLET)


@pytest.mark.parametrize("damage", ["unavailable", "corrupt"])
def test_reconcile_rechecks_previously_counted_provider(tmp_path, record_property, damage):
    api = _api(record_property)
    if api is None:
        return
    provider = _CiphertextDirectory(tmp_path / "ciphertext-copy")
    root = tmp_path / "case"
    first = _publish(api, root, remote={"fixture-copy": provider})
    assert first["verified_replica_count"] == 2
    provider.mode = damage
    calls = provider.readback_count()
    receipt = api.reconcile_encrypted_replicas(
        root, providers={"fixture-copy": provider}, clock=lambda: 1000.0)
    assert provider.readback_count() > calls
    assert receipt["verified_replica_count"] == 1
    assert "fixture-copy" in receipt["unavailable_providers"]
    assert all(not row["counted"] for row in receipt["placements"]
               if row["provider"] == "fixture-copy")


@pytest.mark.parametrize("identity", ["tenant_id", "case_id", "principal_id"])
def test_other_owner_cannot_overwrite_existing_case(tmp_path, record_property, identity):
    api = _api(record_property)
    if api is None:
        return
    root = tmp_path / "case"
    _publish(api, root)
    before = {p.relative_to(root).as_posix(): p.read_bytes()
              for p in root.rglob("*") if p.is_file()}
    with pytest.raises(api.PrivateStorageError):
        _publish(api, root, **{identity: "different-owner"})
    assert {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()} == before
    restored = api.restore_encrypted_workspace(root, **_options())
    assert tuple(restored[name] for name in ("complaint", "fact_graph", "proof")) == TRIPLET


def test_interrupted_publication_preserves_one_complete_generation(tmp_path, monkeypatch, record_property):
    api = _api(record_property)
    if api is None:
        return
    replacement = (b"synthetic-next-complaint", b'{"synthetic_fact":2}', b"synthetic-proof-r2")
    original_replace = os.replace
    discovery = tmp_path / "discovery-case"
    _publish(api, discovery)
    publication_points = []

    def observe_replace(source, destination, *args, **kwargs):
        result = original_replace(source, destination, *args, **kwargs)
        if Path(destination).is_relative_to(discovery):
            publication_points.append(Path(destination).relative_to(discovery).as_posix())
        return result

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "replace", observe_replace)
        _publish(api, discovery, revision="r2", triplet=replacement)
    assert 0 < len(publication_points) <= 32, "Publication replacement population must be bounded"

    class PowerLoss(BaseException):
        pass

    # Exercise every observed real publication replace, including points after
    # an owner/lease metadata update. Stopping only at the first metadata write
    # would miss a later frame/ledger generation split.
    for position in range(1, len(publication_points) + 1):
        root = tmp_path / ("fault-" + str(position))
        _publish(api, root)
        actual_points = []
        injected = []

        def replace_then_interrupt(source, destination, *args, **kwargs):
            result = original_replace(source, destination, *args, **kwargs)
            if Path(destination).is_relative_to(root):
                actual_points.append(Path(destination).relative_to(root).as_posix())
                if len(actual_points) == position:
                    injected.append(position)
                    raise PowerLoss()
            return result

        with monkeypatch.context() as guarded:
            guarded.setattr(os, "replace", replace_then_interrupt)
            try:
                _publish(api, root, revision="r2", triplet=replacement)
            except PowerLoss:
                pass
        assert injected == [position]
        restored = api.restore_encrypted_workspace(root, **_options())
        actual = tuple(restored[name] for name in ("complaint", "fact_graph", "proof"))
        assert (restored["revision"], actual) in {("r1", TRIPLET), ("r2", replacement)}


def test_exact_upstream_replication_suites_are_not_presence_success(tmp_path, record_property):
    api = _api(record_property)
    if api is None:
        return
    report = api.upstream_replication_fixture_qualification(tmp_path)
    assert tuple(row["suite"] for row in report["suites"]) == UPSTREAM_SUITES
    assert report["executed"] is False and report["passed"] is False
    assert all(row["status"] == "missing" and row["passed"] is False
               and row["counts_as_passed"] is False for row in report["suites"])


# Fixed synthetic-only child. Actual API calls, crypto and disk readbacks happen
# here; no serialized success replaces execution. A deliberately blocked method
# must be bounded by the candidate before the outer supervisor's safety timeout.
REPLICA_PROBE = r'''
import ctypes, hashlib, json, os, sys, time
from pathlib import Path
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
owner = int(sys.argv[1])
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(1, 9, 0, 0, 0) != 0 or os.getppid() != owner:
    raise RuntimeError("probe_parent_changed")
root, workspace, operation, packages, control = sys.argv[2:]
control=Path(control)
ready_temporary=control/(".ready-"+str(os.getpid())+".tmp")
fd=os.open(ready_temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
try:
    with os.fdopen(fd,"w") as stream:
        json.dump(dict(pid=os.getpid(),owner=os.getppid()),stream)
        stream.flush();os.fsync(stream.fileno())
    os.link(ready_temporary,control/"ready",follow_symlinks=False)
finally:
    os.unlink(ready_temporary)
directory_fd=os.open(control,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
    os.fsync(directory_fd)
finally:
    os.close(directory_fd)
barrier_deadline=time.monotonic()+2.0
while not (control/"go").exists():
    if time.monotonic()>=barrier_deadline or os.getppid()!=owner:
        raise RuntimeError("probe_release_unavailable")
    time.sleep(0.002)
if (control/"go").read_bytes()!=b"go":
    raise RuntimeError("probe_release_changed")
if operation == "escape_control":
    read_fd,write_fd=os.pipe()
    escaped=os.fork()
    if escaped==0:
        os.close(read_fd)
        os.setsid()
        # Do not retain DataSupervisor's output pipes while the inert escaped
        # child sleeps; the root must be able to return its real JSON/exit.
        for descriptor in (0,1,2):
            os.close(descriptor)
        os.write(write_fd,b"ready");os.close(write_fd)
        time.sleep(30.0)
        os._exit(0)
    os.close(write_fd)
    if os.read(read_fd,5)!=b"ready":
        raise RuntimeError("inert_escape_not_ready")
    os.close(read_fd)
    print(json.dumps(dict(operation=operation,inert_session_escaped=True)))
    raise SystemExit(0)
sys.path[:0] = [root, str(Path(root)/"external/ipfs_datasets_py"),
                str(Path(root)/"external/ipfs_kit_py"),
                str(Path(root)/"external/ipfs_accelerate_py"), packages]
from integrations import private_storage as api
workspace = Path(workspace)
case = workspace/"case"
remote = workspace/"ciphertext-copy"
remote.mkdir(parents=True, exist_ok=True, mode=0o700)
key = bytes(range(32))
options = dict(tenant_id="synthetic-tenant",case_id="synthetic-case",
               principal_id="synthetic-principal",key=key,key_id="synthetic-key")
triplet = (b"synthetic-replica-complaint",b'{"synthetic_fact":1}',b"synthetic-proof-r1")
class Provider:
    blocked = False
    def place(self, *, digest, version, frame, **deadline):
        if self.blocked:
            time.sleep(30.0)
        if any(value in frame for value in triplet):
            raise AssertionError("plaintext_at_provider")
        p = remote/digest
        if not p.exists():
            fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"wb") as stream:
                stream.write(frame);stream.flush();os.fsync(stream.fileno())
            fd=os.open(remote,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        return dict(status="stored")
    def readback(self, *, digest, version, **deadline):
        if self.blocked:
            time.sleep(30.0)
        return dict(status="available",frame=(remote/digest).read_bytes(),version=version)
provider=Provider()
policy=api.replica_policy(desired_replicas=2,minimum_replicas=1,
                          mode="private_remote",remote_providers=("fixture-copy",))
def publish(timeout=0.1):
    return api.publish_encrypted_replicas(case,**options,complaint=triplet[0],
        fact_graph=triplet[1],proof=triplet[2],revision="r1",policy=policy,
        providers={"fixture-copy":provider},timeout_seconds=timeout)
if operation == "concurrent_publish":
    import threading
    entered, release = threading.Event(), threading.Event()
    original_place = provider.place
    def gated_place(**kwargs):
        entered.set()
        if not release.wait(1.0):
            raise RuntimeError("finite_fixture_barrier_expired")
        return original_place(**kwargs)
    provider.place = gated_place
    outcomes=[]
    failures=[]
    second=(b"synthetic-next-complaint",b'{"synthetic_fact":2}',b"synthetic-proof-r2")
    def publish_one(revision, values, remote_policy):
        try:
            result=api.publish_encrypted_replicas(case,**options,complaint=values[0],
                fact_graph=values[1],proof=values[2],revision=revision,
                policy=policy if remote_policy else api.replica_policy(desired_replicas=1,minimum_replicas=1),
                providers={"fixture-copy":provider} if remote_policy else {},timeout_seconds=1.0)
            outcomes.append(result)
        except api.PrivateStorageError as error:
            if error.code not in {"revision_conflict","owner_conflict","conflict","replica_conflict"}:
                failures.append(type(error).__name__)
        except BaseException as error:
            failures.append(type(error).__name__)
    first=threading.Thread(target=publish_one,args=("r1",triplet,True))
    other=threading.Thread(target=publish_one,args=("r2",second,False))
    first.start()
    assert entered.wait(1.0)
    other.start()
    other.join(0.2)
    release.set()
    first.join(2.0);other.join(2.0)
    assert not first.is_alive() and not other.is_alive() and outcomes and not failures
    restored=api.restore_encrypted_workspace(case,**options,
        providers={"fixture-copy":provider},timeout_seconds=1.0)
    actual=tuple(restored[n] for n in ("complaint","fact_graph","proof"))
    assert (restored["revision"],actual) in {("r1",triplet),("r2",second)}
    print(json.dumps(dict(operation=operation,complete_generation=True)))
elif operation == "restart_publish":
    first=publish(timeout=2.0)
    assert first["verified_replica_count"]==2
    print(json.dumps(dict(operation=operation,ciphertext_verified=True)))
elif operation == "restart_restore":
    restored=api.restore_encrypted_workspace(case,**options,
        providers={"fixture-copy":provider},timeout_seconds=0.1)
    assert restored["source"]=="replica" and restored["revision"]=="r1"
    assert tuple(restored[n] for n in ("complaint","fact_graph","proof"))==triplet
    print(json.dumps(dict(operation=operation,triplet_restored=True)))
else:
    if operation != "deadline_publish":
        publish(timeout=2.0)
        if operation == "deadline_restore":
            (case/"replica-ledger"/"primary.frame").unlink()
    provider.blocked=True
    start=time.monotonic()
    if operation == "deadline_publish":
        result=publish()
    elif operation == "deadline_reconcile":
        result=api.reconcile_encrypted_replicas(case,providers={"fixture-copy":provider},
                                               timeout_seconds=0.1)
    elif operation == "deadline_restore":
        try:
            result=api.restore_encrypted_workspace(case,**options,
                providers={"fixture-copy":provider},timeout_seconds=0.1)
        except api.PrivateStorageError as error:
            assert error.code in {"timeout","replica_timeout","replica_unavailable"}
            result=dict(status="unavailable")
    else:
        raise AssertionError("unknown_probe")
    elapsed=time.monotonic()-start
    assert elapsed < 1.0, "candidate_failed_own_deadline"
    assert result["status"] in {"unavailable","degraded"}
    assert result.get("verified_replica_count",0) < 2
    print(json.dumps(dict(operation=operation,bounded_unavailable=True)))
'''


class _ProbeCustody:
    """Own a fresh private probe subtree even when a candidate changes SID.

    The existing Data supervisor closes its managed group first. This verified
    subreaper then fences only fresh kernel-owned direct/adopted children by
    pidfd and birth identity, reaps them, and requires two empty full child
    censuses. Unknown ownership never grants a signal or a successful probe.
    """

    def __init__(self):
        import ctypes
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.owner = os.getpid()
        self.owner_identity = self._identity(self.owner)
        self.started_ticks = time.clock_gettime_ns(time.CLOCK_BOOTTIME) * os.sysconf("SC_CLK_TCK") // 1_000_000_000
        self.old = ctypes.c_int()
        assert self.libc.prctl(37, ctypes.byref(self.old), 0, 0, 0) == 0
        assert self.old.value in {0, 1}
        assert self._children() == (), "Probe worker must start with no owned children"
        assert self.libc.prctl(36, 1, 0, 0, 0) == 0
        observed = ctypes.c_int()
        assert self.libc.prctl(37, ctypes.byref(observed), 0, 0, 0) == 0 and observed.value == 1
        self.child = None
        self.child_fd = None
        self.adopted_reaped = 0

    @staticmethod
    def _identity(pid):
        path = Path("/proc") / str(pid)
        fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "uid": path.stat().st_uid, "ppid": int(fields[1]),
                "pgid": int(fields[2]), "sid": int(fields[3]), "ticks": int(fields[19])}

    def _children(self):
        task_root = Path("/proc") / str(self.owner) / "task"
        for _attempt in range(3):
            try:
                tasks = tuple(sorted(int(p.name) for p in task_root.iterdir() if p.name.isdecimal()))
                children = []
                for tid in tasks:
                    children.extend(int(p) for p in (task_root / str(tid) / "children").read_text().split())
                if tasks != tuple(sorted(int(p.name) for p in task_root.iterdir() if p.name.isdecimal())):
                    continue
                assert len(children) == len(set(children)) and len(children) <= 64
                return tuple(sorted(children))
            except FileNotFoundError:
                continue
        raise RuntimeError("Complete probe child census unavailable")

    def bind(self, pid, control):
        deadline = time.monotonic() + 1.0
        while not (control / "ready").exists():
            assert time.monotonic() < deadline, "Fixed probe did not reach pre-import custody barrier"
            time.sleep(0.002)
        ready = json.loads((control / "ready").read_bytes())
        before = self._identity(pid)
        assert ready == {"pid": pid, "owner": self.owner}
        assert (before["uid"] == os.getuid() and before["ppid"] == self.owner
                and before["pgid"] == pid and before["sid"] == pid
                and before["ticks"] >= self.started_ticks)
        assert self._children() == (pid,)
        descriptor = os.pidfd_open(pid, 0)
        try:
            assert self._identity(pid) == before
        except BaseException:
            os.close(descriptor)
            raise
        self.child, self.child_fd = before, descriptor
        temporary = control / (".go-" + str(self.owner) + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(b"go"); stream.flush(); os.fsync(stream.fileno())
            os.link(temporary, control / "go", follow_symlinks=False)
        finally:
            os.unlink(temporary)
        directory_fd = os.open(control, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def close(self):
        import signal
        deadline = time.monotonic() + 2.0
        closed = False
        try:
            while time.monotonic() < deadline:
                owner = self._identity(self.owner)
                assert owner["uid"] == self.owner_identity["uid"] and owner["ticks"] == self.owner_identity["ticks"]
                children = self._children()
                if not children:
                    if self._children() == ():
                        closed = True
                        break
                for pid in children:
                    try:
                        before = self._identity(pid)
                        assert (before["uid"] == os.getuid() and before["ppid"] == self.owner
                                and before["ticks"] >= self.started_ticks)
                        reaped, _status = os.waitpid(pid, os.WNOHANG)
                        if reaped > 0:
                            self.adopted_reaped += 1
                            continue
                        descriptor = os.pidfd_open(pid, 0)
                        try:
                            after = self._identity(pid)
                            assert all(before[k] == after[k] for k in ("pid", "uid", "ppid", "ticks"))
                            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                        finally:
                            os.close(descriptor)
                        reaped, _status = os.waitpid(pid, os.WNOHANG)
                        self.adopted_reaped += int(reaped > 0)
                    except (FileNotFoundError, ProcessLookupError):
                        # A raced exit is never an empty census; repeat it.
                        continue
                time.sleep(0.005)
            assert closed, "Owned probe descendants are not confirmed absent"
        finally:
            if self.child_fd is not None:
                os.close(self.child_fd)
                self.child_fd = None
            if closed:
                assert self.libc.prctl(36, self.old.value, 0, 0, 0) == 0


@pytest.fixture(autouse=True)
def _replica_acceptance_whole_case_custody():
    # Cover inline local/reconcile/owner/crash API calls too, not only explicit
    # child probes. Module import itself remains under the trusted host guard.
    custody = _ProbeCustody()
    try:
        yield
    finally:
        custody.close()


def _probe(tmp_path, operation):
    import cryptography
    from ipfs_datasets_py.logic.hammers.process_lifecycle import ProcessLimits, ProcessSupervisor

    root = Path(storage.__file__).resolve().parents[1]
    packages = Path(cryptography.__file__).resolve().parents[1]
    workspace = tmp_path / "probe-workspace"
    workspace.mkdir(mode=0o700, exist_ok=True)
    home = tmp_path / "probe-home"
    home.mkdir(mode=0o700, exist_ok=True)
    environment = {"PATH": os.defpath, "HOME": str(home), "TMPDIR": str(tmp_path),
                   "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    control = tmp_path / (operation + "-barrier")
    control.mkdir(mode=0o700)
    custody = _ProbeCustody()
    try:
        with ProcessSupervisor(state_directory=tmp_path / (operation + "-custody"), recover=False) as supervisor:
            handle = supervisor.launch(
                [sys.executable, "-I", "-S", "-B", "-c", REPLICA_PROBE, str(os.getpid()),
                 str(root), str(workspace), operation, str(packages), str(control)],
                cwd=workspace, env=environment,
                limits=ProcessLimits(wall_time_seconds=5.0, cpu_seconds=4.0, memory_mb=512,
                                     graceful_shutdown_seconds=0.25, forced_cleanup_seconds=0.75),
                input_text=None,
            )
            custody.bind(handle.pid, control)
            result = handle.wait()
            assert result.process_group_reaped is True and supervisor.active_process_count == 0
            assert result.timed_out is False, "Candidate exceeded the outer owned probe bound"
            assert result.returncode == 0 and result.error is None
    finally:
        custody.close()
    value = json.loads(result.stdout)
    assert value["operation"] == operation
    value["adopted_children_reaped"] = custody.adopted_reaped
    return value


@pytest.mark.parametrize("operation", ["deadline_publish", "deadline_reconcile", "deadline_restore"])
def test_provider_blocking_is_bounded_and_owned(tmp_path, record_property, operation):
    if _api(record_property) is None:
        return
    assert _probe(tmp_path, operation)["bounded_unavailable"] is True


def test_real_crypto_triplet_restores_in_a_new_process(tmp_path, record_property):
    if _api(record_property) is None:
        return
    assert _probe(tmp_path, "restart_publish")["ciphertext_verified"] is True
    primary = tmp_path / "probe-workspace" / "case" / "replica-ledger" / "primary.frame"
    assert primary.is_file()
    primary.unlink()
    assert _probe(tmp_path, "restart_restore")["triplet_restored"] is True


def test_concurrent_publications_do_not_mix_ledger_and_ciphertext(tmp_path, record_property):
    if _api(record_property) is None:
        return
    assert _probe(tmp_path, "concurrent_publish")["complete_generation"] is True


def test_probe_custody_reaps_an_inert_escaped_session(tmp_path):
    value = _probe(tmp_path, "escape_control")
    assert value["inert_session_escaped"] is True
    assert value["adopted_children_reaped"] == 1
