"""Bounded static rejection of new direct module-global Python redefinitions.

This is a preflight, not a general binding/type checker or an approval of old
collisions. Conditional and inner scopes are outside this deliberately narrow
check. It never imports or executes candidate Python.

Unchanged or reduced baseline collisions are tolerated, not approved. Only
unambiguously bound direct imports of typing.overload with inert stub bodies
and a single implementation (or a .pyi stub group) collapse to one definition.
Arbitrary decorators, rebound aliases, and local typing shadows do not qualify.
Inputs are the actual accepted Native result, exact Git baseline blobs and
no-follow owned candidate bytes; serialized/model-provided source locators
cannot substitute for that result. Bounds are 64 entries, 1 MiB per file,
8 MiB total, 250,000 AST nodes per file and a ten-second Git/inspection budget.
"""
from __future__ import annotations

import ast
from collections import Counter, defaultdict
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import time

_MAX_FILE = 1_048_576
_MAX_TOTAL = 8 * _MAX_FILE
_MAX_FILES = 64
_MAX_NODES = 250_000
_SECONDS = 10.0
_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class _Unavailable(ValueError):
    pass


def _need(value, code):
    if not value:
        raise _Unavailable(code)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _git_blob_id(value, width):
    framed = b'blob ' + str(len(value)).encode('ascii') + b'\0' + value
    return (hashlib.sha1(framed) if width == 40 else hashlib.sha256(framed)).hexdigest()


def _relative(value):
    _need(isinstance(value, str) and 0 < len(value.encode('utf8')) <= 1024
          and not any(ord(c) < 32 for c in value) and '\\' not in value,
          'path_invalid')
    path = PurePosixPath(value)
    _need(not path.is_absolute() and value == path.as_posix()
          and not any(p in {'', '.', '..', '.git'} for p in path.parts), 'path_invalid')
    return path.parts


def _signature(item):
    return tuple(getattr(item, name) for name in
        ('st_dev', 'st_ino', 'st_uid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def _candidate_bytes(root, value):
    parts = _relative(value)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
            except FileNotFoundError:
                return None
            os.close(descriptor); descriptor = child
            try:
                os.stat('.git', dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise _Unavailable('nested_repository')
        try:
            leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=descriptor)
        except FileNotFoundError:
            return None
        try:
            before = os.fstat(leaf)
            _need(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                  and before.st_nlink == 1 and before.st_size <= _MAX_FILE, 'candidate_file_invalid')
            pieces, size = [], 0
            while True:
                chunk = os.read(leaf, min(65536, _MAX_FILE + 1 - size))
                if not chunk:
                    break
                pieces.append(chunk); size += len(chunk)
                _need(size <= _MAX_FILE, 'file_bound')
            current = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
            _need(_signature(before) == _signature(os.fstat(leaf)) == _signature(current), 'candidate_changed')
            return b''.join(pieces)
        finally:
            os.close(leaf)
    finally:
        os.close(descriptor)


class _Repository:
    def __init__(self, root, deadline):
        self.root, self.deadline = root, deadline
        self.executable = shutil.which('git', path=os.defpath)
        _need(self.executable and Path(self.executable).is_absolute(), 'git_unavailable')
        self.environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.environment.update(GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0',
            GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_OPTIONAL_LOCKS='0')

    def git(self, *args):
        remaining = self.deadline - time.monotonic()
        _need(remaining > 0, 'time_bound')
        result = subprocess.run([self.executable, '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null',
            '-C', str(self.root), *args], env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=min(3.0, remaining), check=False)
        _need(result.returncode == 0 and len(result.stdout) <= _MAX_FILE + 4096, 'git_context_unavailable')
        return result.stdout

    def blob(self, baseline, path):
        _relative(path)
        rows = self.git('ls-tree', '-z', baseline, '--', ':(literal)' + path).split(b'\0')
        rows = [r for r in rows if r]
        if not rows:
            return None
        _need(len(rows) == 1, 'baseline_path_ambiguous')
        header, name = rows[0].split(b'\t', 1)
        mode, kind, oid = header.split()
        _need(name == path.encode('utf8') and mode in {b'100644', b'100755'} and kind == b'blob', 'baseline_file_invalid')
        size = self.git('cat-file', '-s', oid.decode()).strip()
        _need(size.isdigit() and int(size) <= _MAX_FILE, 'file_bound')
        data = self.git('cat-file', 'blob', oid.decode())
        _need(len(data) == int(size), 'baseline_changed')
        return data


def _tree(data, deadline):
    _need(data is not None and len(data) <= _MAX_FILE and b'\0' not in data, 'file_bound')
    text = data.decode('utf8', errors='strict')
    _need(not text.startswith('\ufeff'), 'encoding_invalid')
    tree = ast.parse(text, mode='exec')
    count = 0
    for _ in ast.walk(tree):
        count += 1
        _need(count <= _MAX_NODES, 'ast_bound')
        if count % 4096 == 0:
            _need(time.monotonic() < deadline, 'time_bound')
    return tree


def _typing_bindings(tree):
    bindings, changes = Counter(), set()
    direct, modules = set(), set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == 'typing' and node.level == 0:
            direct.update(item.asname or item.name for item in node.names if item.name == 'overload')
        elif isinstance(node, ast.Import):
            modules.update(item.asname or item.name for item in node.names if item.name == 'typing')
    def visit(node):
        if isinstance(node, _DEFINITIONS):
            bindings[node.name] += 1
            # Defaults/decorators/bases execute in the containing scope;
            # their named expressions can rebind an imported overload alias.
            # Do not treat parameter names, bodies or 3.12 type parameters as
            # containing-scope bindings.
            values = list(node.decorator_list)
            if isinstance(node, ast.ClassDef):
                values += [*node.bases, *(item.value for item in node.keywords)]
            else:
                arguments = node.args
                values += [*arguments.defaults, *arguments.kw_defaults, node.returns]
                values += [arg.annotation for arg in [*arguments.posonlyargs, *arguments.args,
                    *arguments.kwonlyargs, arguments.vararg, arguments.kwarg] if arg is not None]
            for value in values:
                if value is None:
                    continue
                visit(value)
            return
        if isinstance(node, ast.Lambda):
            return
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for item in node.names:
                bindings[item.asname or item.name.split('.')[0]] += 1
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bindings[node.id] += 1
        elif (isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del))
              and isinstance(node.value, ast.Name) and node.attr == 'overload'):
            changes.add(node.value.id)
        for child in ast.iter_child_nodes(node):
            visit(child)
    for node in tree.body:
        visit(node)
    return {name for name in direct if bindings[name] == 1}, {name for name in modules if bindings[name] == 1 and name not in changes}


def _overload_group(group, typing_names, *, stub_file):
    direct, modules = typing_names
    def overload(node):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or len(node.decorator_list) != 1:
            return False
        deco = node.decorator_list[0]
        return ((isinstance(deco, ast.Name) and deco.id in direct)
            or (isinstance(deco, ast.Attribute) and deco.attr == 'overload'
                and isinstance(deco.value, ast.Name) and deco.value.id in modules))
    def stub(node):
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            body = body[1:]
        return bool(body) and all(isinstance(item, ast.Pass) or (isinstance(item, ast.Expr)
            and isinstance(item.value, ast.Constant) and item.value.value is Ellipsis) for item in body)
    if not group or not all(type(node) is type(group[-1]) for node in group):
        return False
    if not all(overload(node) and stub(node) for node in group[:-1]):
        return False
    return ((stub_file and overload(group[-1]) and stub(group[-1]))
        or (isinstance(group[-1], (ast.FunctionDef, ast.AsyncFunctionDef)) and not group[-1].decorator_list))


def _counts(tree, path, *, typing_shadowed):
    groups = defaultdict(list)
    for node in tree.body:
        if isinstance(node, _DEFINITIONS):
            groups[node.name].append(node)
    typing_names = (set(), set()) if typing_shadowed else _typing_bindings(tree)
    return {name: (1 if len(nodes) > 1 and _overload_group(nodes, typing_names, stub_file=path.endswith('.pyi')) else len(nodes), nodes)
            for name, nodes in groups.items()}


def inspect_changed_python_globals(root, accepted, *, expected_task_id):
    """Read only actual accepted Native entries and their exact owned Git bytes."""
    report = {'schema':'complaint-python-global-preflight@1', 'passed':False,
        'reason':'python_global_preflight_unavailable', 'files':[], 'candidate_executed':False,
        'completion_authority':False, 'scope':'direct module definitions only; old collisions are not approved'}
    try:
        from ipfs_accelerate_py.agent_supervisor.validation.proposal_validation import ProposalValidationResult
        _need(type(accepted) is ProposalValidationResult and accepted.accepted is True, 'accepted_context_missing')
        proposal = accepted.proposal
        _need(proposal.task_id == expected_task_id and bool(proposal.proposal_id), 'task_context_mismatch')
        baseline = proposal.baseline_id
        _need(re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', baseline) and proposal.repository_tree_id == baseline, 'baseline_id_invalid')
        root = Path(root)
        _need(root.is_absolute() and root.resolve(strict=True) == root, 'root_alias')
        before_root = root.lstat()
        _need(stat.S_ISDIR(before_root.st_mode) and before_root.st_uid == os.getuid(), 'root_custody')
        deadline = time.monotonic() + _SECONDS
        repository = _Repository(root, deadline)
        _need(Path(repository.git('rev-parse', '--show-toplevel').decode().strip()) == root, 'repository_root_mismatch')
        common = Path(repository.git('rev-parse', '--path-format=absolute', '--git-common-dir').decode().strip()).resolve(strict=True)
        _need(proposal.repository_id == 'repository:sha256:' + _sha(str(common).encode()), 'repository_id_mismatch')
        _need(repository.git('cat-file', '-t', baseline).strip() == b'commit', 'baseline_not_commit')
        entries = proposal.candidate_diff
        _need(0 < len(entries) <= _MAX_FILES and tuple(sorted({p for e in entries for p in (e.old_path, e.new_path) if p})) == proposal.changed_paths, 'changed_paths_mismatch')
        total, collisions = 0, []
        for entry in entries:
            old, new = entry.old_path, entry.new_path
            if not any(p.lower().endswith(('.py', '.pyi')) for p in (old, new) if p):
                continue
            kind = entry.change_kind.value
            _need(kind in {'add', 'modify', 'delete', 'rename', 'copy'} and not entry.binary, 'entry_kind_invalid')
            before = repository.blob(baseline, old) if old else None
            after = _candidate_bytes(root, new) if new else None
            for raw, content, identity in ((before, entry.before_source, entry.before_blob_id), (after, entry.after_source, entry.after_blob_id)):
                if raw is None:
                    _need(content is None and identity == '', 'entry_fingerprint_mismatch')
                else:
                    _need(isinstance(identity, str) and len(identity) == len(baseline)
                        and re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', identity)
                        and _git_blob_id(raw, len(baseline)) == identity
                        and (content is None or content.encode('utf8') == raw), 'entry_fingerprint_mismatch')
                    total += len(raw)
                    _need(total <= _MAX_TOTAL, 'total_bound')
            _need((kind == 'add') == (before is None) and (kind == 'delete') == (after is None), 'entry_existence_mismatch')
            if kind == 'delete' or (kind == 'rename' and old != new):
                _need(_candidate_bytes(root, old) is None, 'old_path_retained')
            if not new or not new.lower().endswith(('.py', '.pyi')):
                continue
            baseline_current = before if old == new else repository.blob(baseline, new)
            if old != new:
                _need(baseline_current is None, 'target_baseline_ambiguous')
            old_tree = _tree(baseline_current, deadline) if baseline_current is not None else ast.Module(body=[], type_ignores=[])
            new_tree = _tree(after, deadline)
            # A local typing module makes a purported stdlib import ambiguous.
            shadow = any((root / p).exists() or (root / p).is_symlink() for p in ('typing.py', 'typing/__init__.py'))
            old_shadow = any(repository.blob(baseline, p) is not None for p in ('typing.py', 'typing/__init__.py'))
            prior, current = _counts(old_tree, new, typing_shadowed=old_shadow), _counts(new_tree, new, typing_shadowed=shadow)
            found = []
            for name, (count, nodes) in current.items():
                old_count = prior.get(name, (0, []))[0]
                if count > 1 and count > old_count:
                    found.append({'name':name[:128], 'baseline_count':old_count, 'candidate_count':count,
                        'lines':[n.lineno for n in nodes[:8]]})
            row = {'path':new, 'before_sha256':_sha(baseline_current) if baseline_current is not None else '',
                   'after_sha256':_sha(after), 'collisions':found[:20]}
            report['files'].append(row); collisions.extend(found)
        _need((root.lstat().st_dev, root.lstat().st_ino) == (before_root.st_dev, before_root.st_ino), 'root_changed')
        _need(time.monotonic() < deadline, 'time_bound')
        report.update(passed=not collisions, reason='new_duplicate_python_module_global' if collisions else '',
            proposal_id=proposal.proposal_id, baseline_id=baseline, changed_paths=list(proposal.changed_paths))
    except _Unavailable as exc:
        report['detail'] = str(exc)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, MemoryError, SyntaxError, subprocess.TimeoutExpired):
        report['detail'] = 'bounded_source_inspection_failed'
    return report
