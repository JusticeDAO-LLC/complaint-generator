"""Load the canonical release checker as a pytest guard without `scripts` lookup."""
from __future__ import annotations

import hashlib
import importlib.util
import io
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
import sys
import warnings

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "scripts/validate_complaint_intake.py"
NAME = "_complaint_intake_release_checker_" + hashlib.sha256(str(SOURCE).encode()).hexdigest()[:16]
checker = sys.modules.get(NAME)
if checker is None:
    specification = importlib.util.spec_from_file_location(NAME, SOURCE)
    if specification is None or specification.loader is None:
        raise ImportError("canonical_release_checker_unavailable")
    checker = importlib.util.module_from_spec(specification)
    # This unique name registers only our exact source. Existing `scripts`
    # packages from SDK dependencies remain untouched.
    sys.modules[NAME] = checker
    try:
        specification.loader.exec_module(checker)
    except BaseException:
        if sys.modules.get(NAME) is checker:
            del sys.modules[NAME]
        raise
if Path(checker.__file__).resolve() != SOURCE.resolve():
    raise ImportError("canonical_release_checker_origin_mismatch")

pytest_sessionfinish = checker.pytest_sessionfinish
_NATIVE_DEFAULT_BOUND = object()


class _BatchedNativeSealOracle:
    """Group genuine Native catalog writes; every decision stays with Native.

    The fresh catalog still receives Native's original INSERTs only after its
    passing-report hook calls remember.  A failed/aborted session cannot turn
    an incomplete catalog into complete behavioral evidence.
    """

    def __init__(self, native, delegate, *, batch_size=64):
        if type(batch_size) is not int or not 1 <= batch_size <= 64:
            raise ValueError("invalid_native_seal_batch_bound")
        if type(delegate) is not native.DuckDbQuackSealOracle:
            raise native.PytestSealCatalogError("native_seal_delegate_required")
        if delegate._connection is None:
            raise native.PytestSealCatalogError("native_seal_catalog_closed")
        # Native deliberately excludes authority=True rows from its cache.
        # Freshness therefore checks the actual tables as well as the caches.
        existing = delegate._connection.execute(
            "SELECT (SELECT count(*) FROM pytest_ast_file_hash), "
            "(SELECT count(*) FROM pytest_ast_seal)"
        ).fetchone()
        if delegate._files or delegate._seals or existing != (0, 0):
            raise native.PytestSealCatalogError("fresh_native_seal_catalog_required")
        self.native = native
        self.delegate = delegate
        self.batch_size = batch_size
        self.completion_authority = False
        self._pending = 0
        self._active = False
        self._failed = False
        self._closed = False

    @property
    def path(self):
        return self.delegate.path

    def _ready(self):
        if self._failed or self._closed or self.delegate._connection is None:
            raise self.native.PytestSealCatalogError("native_seal_batch_unavailable")

    def _failure(self):
        self._failed = True
        if self._active and self.delegate._connection is not None:
            try:
                self.delegate._connection.execute("ROLLBACK")
            except Exception:
                pass
        self._active = False
        self._pending = 0

    def _commit(self):
        if self._active:
            self.delegate._connection.execute("COMMIT")
            self._active = False
            self._pending = 0

    def _write(self, method, *args, **kwargs):
        self._ready()
        try:
            if not self._active:
                self.delegate._connection.execute("BEGIN TRANSACTION")
                self._active = True
            # The canonical Native method performs the real SQL and updates
            # its own in-process cache. No case or file-hash row is invented.
            result = method(*args, **kwargs)
            self._pending += 1
            if self._pending >= self.batch_size:
                self._commit()
            return result
        except BaseException:
            self._failure()
            raise

    def reuse(self, nodeid, seal):
        self._ready()
        return self.delegate.reuse(nodeid, seal)

    def cached_file_hash(self, path):
        self._ready()
        return self.delegate.cached_file_hash(path)

    def remember(self, nodeid, seal, *, file_count):
        return self._write(self.delegate.remember, nodeid, seal, file_count=file_count)

    def remember_file_hash(self, path, *, mtime_ns, size_bytes, content_hash):
        return self._write(self.delegate.remember_file_hash, path, mtime_ns=mtime_ns,
                           size_bytes=size_bytes, content_hash=content_hash)

    def close(self):
        if self._closed:
            if self._failed:
                raise self.native.PytestSealCatalogError("native_seal_batch_failed")
            return
        try:
            if self._failed:
                raise self.native.PytestSealCatalogError("native_seal_batch_failed")
            self._ready()
            self._commit()
        except BaseException:
            self._failure()
            raise
        finally:
            self._closed = True
            self.delegate.close()


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Use Native's existing oracle injection seam for a fresh phase catalog."""
    from ipfs_accelerate_py.testing import pytest_ast_seal as native
    if native not in config.pluginmanager.get_plugins():
        return
    state = getattr(config, native._CONFIG_KEY, None)
    injected = getattr(config, "_pytest_ast_seal_oracle", None)
    delegate = state.get("oracle") if isinstance(state, dict) else injected
    if isinstance(delegate, _BatchedNativeSealOracle):
        if delegate.native is not native:
            raise native.PytestSealCatalogError("native_seal_batch_policy_changed")
        return
    created = delegate is None
    if created:
        delegate = native._oracle_for(config)
    try:
        oracle = _BatchedNativeSealOracle(native, delegate)
    except BaseException:
        if created:
            delegate.close()
        raise
    config._pytest_ast_seal_oracle = oracle
    config._complaint_release_batched_native_oracle = oracle
    if isinstance(state, dict):
        state["oracle"] = oracle


def pytest_unconfigure(config):
    oracle = getattr(config, "_complaint_release_batched_native_oracle", None)
    if oracle is not None and not oracle._closed:
        oracle.close()


class _NativeImportEdgeCache:
    """Cache immutable import names, never ASTs, file hashes, or test outcomes.

    Native's traversal still rereads every visited file and resolves each
    import against the current filesystem.  Sharing import names therefore
    saves repeated parsing/walking without freezing a closure or its seal.
    """

    def __init__(self, native, *, max_entries=512, max_bytes=16 * 1024 * 1024,
                 max_imports=32768, max_file_bytes=2 * 1024 * 1024):
        self.native = native
        self.canonical_closure = native.ast_closure
        self.default_max_files = native.ast_closure.__kwdefaults__["max_files"]
        self._parse = native.ast.parse
        self._imported_modules = native._imported_modules
        self._module_file = native._module_file
        self._conftest_chain = native._conftest_chain
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.max_imports = max_imports
        self.max_file_bytes = max_file_bytes
        if any(type(value) is not int or value < 0 for value in
               (max_entries, max_bytes, max_imports, max_file_bytes)):
            raise ValueError("invalid_import_cache_bound")
        self._entries = OrderedDict()
        self._bytes = 0
        self._imports = 0
        self.parse_count = 0
        self.hit_count = 0

    def _names(self, root, path):
        # One immutable read supplies both key and parse input. TextIOWrapper
        # retains canonical Path.read_text UTF-8/universal-newline semantics.
        raw = path.read_bytes()
        # A warnings-as-errors policy is part of parser behavior as well.
        policy = (tuple(warnings.filters), warnings.defaultaction)
        key = (str(root), str(path), hashlib.sha256(raw).digest(), policy)
        try:
            hash(key)
        except TypeError:
            key = None
        cached = self._entries.get(key) if key is not None else None
        if cached is not None and cached[0] == raw:
            self._entries.move_to_end(key)
            self.hit_count += 1
            return cached[1]
        with io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8") as handle:
            source = handle.read()
        tree = self._parse(source, filename=str(path))
        self.parse_count += 1
        names = tuple(self._imported_modules(root, path, tree))
        # The mutable tree is discarded; no caller or later traversal can
        # mutate an AST that another closure will reuse.
        del tree
        weight = len(raw) + sum(len(name.encode("utf-8")) for name in names)
        if (key is None or not self.max_entries or len(raw) > self.max_file_bytes or weight > self.max_bytes
                or len(names) > self.max_imports):
            return names
        # Same path with new contents cannot retain unbounded old versions.
        for previous in tuple(self._entries):
            if previous[:2] == key[:2]:
                self._discard(previous)
        while self._entries and (len(self._entries) >= self.max_entries
                or self._bytes + weight > self.max_bytes
                or self._imports + len(names) > self.max_imports):
            self._discard(next(iter(self._entries)))
        self._entries[key] = (raw, names, weight)
        self._bytes += weight
        self._imports += len(names)
        return names

    def _discard(self, key):
        raw, names, weight = self._entries.pop(key)
        self._bytes -= weight
        self._imports -= len(names)

    def closure(self, repo, test_file, *, max_files=_NATIVE_DEFAULT_BOUND):
        """Native ast_closure's traversal with only parsed import names cached."""
        if max_files is _NATIVE_DEFAULT_BOUND:
            max_files = self.default_max_files
        # A change to Native's parsing/resolution helpers invalidates this
        # optimization rather than silently using a mixed implementation.
        if (self.native.ast.parse is not self._parse
                or self.native._imported_modules is not self._imported_modules
                or self.native._module_file is not self._module_file
                or self.native._conftest_chain is not self._conftest_chain
                or self.canonical_closure.__kwdefaults__["max_files"] != self.default_max_files):
            raise RuntimeError("native_import_cache_policy_changed")
        root = repo.resolve()
        pending = [test_file.resolve(), *self._conftest_chain(root, test_file)]
        seen = set()
        ordered = []
        while pending:
            path = pending.pop()
            if path in seen:
                continue
            seen.add(path)
            if root not in path.parents and path != root:
                continue
            if not path.is_file() or path.suffix != ".py":
                continue
            ordered.append(path)
            if len(ordered) > max_files:
                return None
            try:
                names = self._names(root, path)
            except (OSError, UnicodeError, SyntaxError):
                return None
            for module in names:
                resolved = self._module_file(root, module)
                if resolved is not None and resolved.resolve() not in seen:
                    pending.append(resolved.resolve())
        return tuple(sorted(ordered))


@contextmanager
def _native_collection_cache(native, cache):
    original = native.ast_closure
    if original is not cache.canonical_closure:
        raise RuntimeError("native_import_cache_closure_changed")
    replacement = cache.closure
    native.ast_closure = replacement
    try:
        yield
    finally:
        native.ast_closure = original


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Bound this session's cache to Native's real collection/sealing hook."""
    from ipfs_accelerate_py.testing import pytest_ast_seal as native
    cache = _NativeImportEdgeCache(native)
    config._complaint_release_import_edge_cache = cache
    # No oracle, seal, hash, case, skip decision, or Native SDK file changes.
    # Actual tests run after this scope has restored Native's original API.
    with _native_collection_cache(native, cache):
        yield
