"""Trusted network-only bootstrap for measured validation children.

Preparing or verifying this module never installs a filter in the caller.
The generated explicit pytest plugin installs before candidate conftests.
This extends the release checker's native-ABI socket policy to socketpair,
x32 denial and TSYNC; it does not reuse its browser-incompatible process guard.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import stat

MODULE = "complaint_owned_network_guard"
POLICY = "deny_non_af_unix_sockets"
SCHEMA = "complaint-validation-network-proof@1"
_RELATIVE = "integrations/ipfs_accelerate/validation_network.py"


def _policy():
    machines = {"x86_64": (0xC000003E, 41, 53, 317), "aarch64": (0xC00000B7, 198, 199, 277)}
    if platform.system() != "Linux" or platform.machine() not in machines:
        raise ValueError("validation_network_kernel_unavailable")
    arch, socket_nr, pair_nr, seccomp_nr = machines[platform.machine()]
    denied = 0x00050000 | 1
    rows = [(0x20, 0, 0, 4), (0x15, 1, 0, arch), (0x06, 0, 0, 0x80000000),
            (0x20, 0, 0, 0), (0x45, 0, 1, 0x40000000), (0x06, 0, 0, denied),
            (0x15, 2, 0, socket_nr), (0x15, 1, 0, pair_nr), (0x06, 0, 0, 0x7FFF0000),
            (0x20, 0, 0, 16), (0x15, 1, 0, 1), (0x06, 0, 0, denied),
            (0x06, 0, 0, 0x7FFF0000)]
    return {"machine": platform.machine(), "arch": arch, "socket_nr": socket_nr,
            "socketpair_nr": pair_nr, "seccomp_nr": seccomp_nr, "rows": rows,
            "tsync": True, "scope": "socket_and_socketpair_creation_only"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _private_directory(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("validation_network_private_directory")
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("validation_network_private_directory")
    return path


def _private_read(path):
    path = Path(path)
    _private_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600
                or not 0 < before.st_size <= 65536):
            raise ValueError("validation_network_proof_file")
        raw = os.read(fd, before.st_size + 1)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(raw) != before.st_size or identity(before) != identity(after):
            raise ValueError("validation_network_proof_file")
        return raw
    finally:
        os.close(fd)


def prepare_validation_network_guard(run_directory: Path, trusted_repo_root: Path) -> dict:
    """Materialize one trusted plugin; return locators/hashes, never success evidence."""
    run = _private_directory(run_directory)
    trusted = Path(trusted_repo_root)
    source = Path(__file__).resolve()
    if (not trusted.is_absolute() or trusted.resolve() != trusted
            or source != trusted / _RELATIVE or not source.is_file()):
        raise ValueError("validation_network_trusted_origin")
    policy = _policy()
    policy_sha = _digest(policy)
    plugin = run / (MODULE + ".py")
    body = (_PLUGIN.replace("@@PLUGIN_PATH@@", repr(str(plugin)))
            .replace("@@POLICY@@", repr(policy)).replace("@@POLICY_SHA@@", repr(policy_sha)))
    compile(body, str(plugin), "exec")
    fd = os.open(plugin, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    return {"module": MODULE, "pythonpath": run, "files": (source, plugin), "policy": POLICY,
            "proof_suffix": ".network.json", "plugin_path": plugin,
            "plugin_sha256": hashlib.sha256(body.encode()).hexdigest(), "policy_sha256": policy_sha}


def verify_validation_network_proof(proof_path: Path, *, expected_plugin_sha256: str,
                                    expected_policy_sha256: str, expected_exitstatus: int) -> dict:
    """Require the exact pre/post kernel facts; no proof grants completion authority."""
    path = Path(proof_path)
    value = json.loads(_private_read(path))
    expected_keys = {"schema", "policy", "policy_sha256", "plugin_path", "plugin_sha256",
                     "process", "pre", "post", "exitstatus", "completion_authority", "scope"}
    if (not isinstance(value, dict) or set(value) != expected_keys or value["schema"] != SCHEMA
            or value["policy"] != POLICY or value["policy_sha256"] != expected_policy_sha256
            or value["plugin_sha256"] != expected_plugin_sha256
            or value["plugin_path"] != str(path.parent / (MODULE + ".py"))
            or value["completion_authority"] is not False
            or value["scope"] != "socket_and_socketpair_creation_only"
            or type(value["exitstatus"]) is not int or value["exitstatus"] != expected_exitstatus):
        raise ValueError("validation_network_proof_binding")
    process = value["process"]
    if (not isinstance(process, dict) or set(process) != {"pid", "start_ticks", "boot_id"}
            or type(process["pid"]) is not int or process["pid"] <= 1
            or type(process["start_ticks"]) is not int or process["start_ticks"] <= 0
            or not isinstance(process["boot_id"], str) or len(process["boot_id"]) != 36):
        raise ValueError("validation_network_process_binding")
    expected = {"nnp": 1, "seccomp": 2, "tsync": True, "socket_INET_errno": 1, "socket_INET6_errno": 1,
                "socketpair_INET_errno": 1, "socketpair_INET6_errno": 1, "unix_roundtrip": True,
                "x32_errno": 1 if platform.machine() == "x86_64" else None,
                "inherited_non_unix_socket_fds": 0}
    for phase in ("pre", "post"):
        fact = value[phase]
        if not isinstance(fact, dict) or set(fact) != set(expected):
            raise ValueError("validation_network_proof_incomplete")
        if any(type(fact[k]) is not type(v) or fact[k] != v for k, v in expected.items()):
            raise ValueError("validation_network_kernel_facts")
    if hashlib.sha256(_private_read(path.parent / (MODULE + ".py"))).hexdigest() != expected_plugin_sha256:
        raise ValueError("validation_network_plugin_changed")
    return value


_PLUGIN = r'''"""Host-owned network-only pytest bootstrap. No candidate/environment opt-out."""
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

_EXPECTED_PLUGIN = Path(@@PLUGIN_PATH@@)
_POLICY = @@POLICY@@
_POLICY_SHA = @@POLICY_SHA@@
_LIBC = ctypes.CDLL(None, use_errno=True)
_LIBC.socket.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
_LIBC.socket.restype = ctypes.c_int
_LIBC.socketpair.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
_LIBC.socketpair.restype = ctypes.c_int
_LIBC.syscall.restype = ctypes.c_long
_LIBC.getsockopt.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]


def _fail():
    raise RuntimeError("validation_network_guard_unavailable")


def _private_dir():
    p = _EXPECTED_PLUGIN.parent
    i = p.stat()
    if p.resolve() != p or p.is_symlink() or i.st_uid != os.getuid() or stat.S_IMODE(i.st_mode) != 0o700:
        _fail()


def _read_plugin():
    if Path(__file__).resolve() != _EXPECTED_PLUGIN or Path(__file__).is_symlink():
        _fail()
    fd = os.open(_EXPECTED_PLUGIN, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        i = os.fstat(fd)
        if (not stat.S_ISREG(i.st_mode) or i.st_uid != os.getuid() or i.st_nlink != 1
                or stat.S_IMODE(i.st_mode) != 0o600 or not 0 < i.st_size <= 65536):
            _fail()
        raw = os.read(fd, i.st_size + 1)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(raw) != i.st_size or identity(i) != identity(after):
            _fail()
        return raw
    finally:
        os.close(fd)


def _install():
    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte), ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint)]
    class Program(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]
    rows = _POLICY["rows"]
    filters = (Filter * len(rows))(*(Filter(*row) for row in rows))
    program = Program(len(rows), filters)
    if _LIBC.prctl(38, 1, 0, 0, 0) != 0:
        _fail()
    # TSYNC covers existing threads; future threads/processes inherit this
    # irreversible filter. A positive failing-TID return also fails closed.
    if _LIBC.syscall(_POLICY["seccomp_nr"], 1, 1, ctypes.byref(program)) != 0:
        _fail()


def _socket_errno(family):
    ctypes.set_errno(0)
    fd = _LIBC.socket(family, 1, 0)
    error = ctypes.get_errno()
    if fd >= 0:
        os.close(fd)
        return 0
    return error


def _pair_errno(family):
    pair = (ctypes.c_int * 2)(-1, -1)
    ctypes.set_errno(0)
    code = _LIBC.socketpair(family, 1, 0, pair)
    error = ctypes.get_errno()
    if code == 0:
        os.close(pair[0]); os.close(pair[1])
        return 0
    return error


def _facts():
    inherited = 0
    for name in os.listdir("/proc/self/fd"):
        try:
            fd = int(name)
        except ValueError:
            continue
        domain, size = ctypes.c_int(), ctypes.c_uint(ctypes.sizeof(ctypes.c_int))
        if _LIBC.getsockopt(fd, 1, 39, ctypes.byref(domain), ctypes.byref(size)) == 0 and domain.value != 1:
            inherited += 1
    pair = (ctypes.c_int * 2)(-1, -1)
    if _LIBC.socketpair(1, 1, 0, pair) != 0:
        _fail()
    try:
        os.write(pair[0], b"network-guard-unix")
        unix = os.read(pair[1], 64) == b"network-guard-unix"
    finally:
        os.close(pair[0]); os.close(pair[1])
    x32 = None
    if _POLICY["machine"] == "x86_64":
        ctypes.set_errno(0)
        fd = _LIBC.syscall(0x40000000 | _POLICY["socket_nr"], 2, 1, 0)
        x32 = ctypes.get_errno() if fd < 0 else 0
        if fd >= 0:
            os.close(fd)
    result = {"nnp": _LIBC.prctl(39, 0, 0, 0, 0), "seccomp": _LIBC.prctl(21, 0, 0, 0, 0),
              "tsync": True, "socket_INET_errno": _socket_errno(2), "socket_INET6_errno": _socket_errno(10),
              "socketpair_INET_errno": _pair_errno(2), "socketpair_INET6_errno": _pair_errno(10),
              "unix_roundtrip": unix, "x32_errno": x32, "inherited_non_unix_socket_fds": inherited}
    if (result["nnp"] != 1 or result["seccomp"] != 2 or not unix or inherited
            or any(result[k] != errno.EPERM for k in ("socket_INET_errno", "socket_INET6_errno", "socketpair_INET_errno", "socketpair_INET6_errno"))
            or (_POLICY["machine"] == "x86_64" and x32 != errno.EPERM)):
        _fail()
    return result


def _manifest_path():
    values = []
    for index, value in enumerate(sys.argv):
        if value.startswith("--complaint-evidence-path="):
            values.append(value.split("=", 1)[1])
        elif value == "--complaint-evidence-path" and index + 1 < len(sys.argv):
            values.append(sys.argv[index + 1])
    if len(values) != 1:
        _fail()
    path = Path(values[0])
    if not path.is_absolute() or path.parent != _EXPECTED_PLUGIN.parent or path.is_symlink():
        _fail()
    return path


def _write(path, value, *, exclusive):
    flags = os.O_WRONLY | os.O_NOFOLLOW | (os.O_CREAT | os.O_EXCL if exclusive else 0)
    fd = os.open(path, flags, 0o600)
    try:
        i = os.fstat(fd)
        if not stat.S_ISREG(i.st_mode) or i.st_uid != os.getuid() or i.st_nlink != 1 or stat.S_IMODE(i.st_mode) != 0o600:
            _fail()
        if not exclusive and (i.st_dev, i.st_ino) != _PROOF_ID:
            _fail()
        raw = json.dumps(value, sort_keys=True).encode()
        os.ftruncate(fd, 0)
        remaining = memoryview(raw)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                _fail()
            remaining = remaining[written:]
        os.fsync(fd)
        return (i.st_dev, i.st_ino), raw
    finally:
        os.close(fd)


_private_dir()
_PLUGIN_SHA = hashlib.sha256(_read_plugin()).hexdigest()
_install()
_PRE = _facts()
_MANIFEST = _manifest_path()
_PROOF = _MANIFEST.with_suffix(".network.json")
_raw_stat = Path("/proc/self/stat").read_bytes().rsplit(b")", 1)[1].split()
_PROCESS = {"pid": os.getpid(), "start_ticks": int(_raw_stat[19]), "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
_VALUE = {"schema": "complaint-validation-network-proof@1", "policy": "deny_non_af_unix_sockets",
          "policy_sha256": _POLICY_SHA, "plugin_path": str(_EXPECTED_PLUGIN), "plugin_sha256": _PLUGIN_SHA,
          "process": _PROCESS, "pre": _PRE, "post": None, "exitstatus": None,
          "completion_authority": False, "scope": "socket_and_socketpair_creation_only"}
_PROOF_ID, _PRE_BYTES = _write(_PROOF, _VALUE, exclusive=True)

import pytest


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    _private_dir()
    if hashlib.sha256(_read_plugin()).hexdigest() != _PLUGIN_SHA:
        _fail()
    fd = os.open(_PROOF, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        i = os.fstat(fd)
        if (i.st_dev, i.st_ino) != _PROOF_ID or os.read(fd, len(_PRE_BYTES) + 1) != _PRE_BYTES:
            _fail()
    finally:
        os.close(fd)
    value = dict(_VALUE)
    value.update(post=_facts(), exitstatus=int(exitstatus))
    _write(_PROOF, value, exclusive=False)
'''
