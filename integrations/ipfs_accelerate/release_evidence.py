"""Read the existing Native campaign; never publish task or goal completion.

The journal and target-bound merge store establish historical execution.  They
do not establish that old whole-source measurements still describe this
checkout.  A release checker must measure current semantic coverage separately.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping

from . import improvement_plan as compiler


SCHEMA = "complaint-native-release-evidence@1"
TASK_PREFIX = "## CIMP-"
SELF_TASK = "CIMP-REL-03"
MAX_METADATA = 20 * 1024 * 1024
MAX_JOURNAL = 128 * 1024 * 1024
MAX_EVENTS = 100_000
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40,64}\Z")


class ReleaseEvidenceError(ValueError):
    """An existing source cannot be read within this audit's boundary."""


def _directory(path: Path, *, private: bool = False) -> Path:
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ReleaseEvidenceError("aliased_path")
    value = path.lstat()
    if (not stat.S_ISDIR(value.st_mode) or value.st_uid != os.getuid()
            or value.st_mode & (0o022 if private else 0o002)):
        raise ReleaseEvidenceError("unowned_or_writable_directory")
    return path


def _read(path: Path, *, maximum: int = MAX_METADATA, source: bool = False) -> bytes:
    if path.resolve(strict=True) != path:
        raise ReleaseEvidenceError("aliased_path")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or before.st_mode & (0o002 if source else 0o022)
                or not 0 < before.st_size <= maximum):
            raise ReleaseEvidenceError("unowned_or_unbounded_file")
        chunks = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after, current = os.fstat(fd), path.lstat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(raw) != before.st_size or any(
                getattr(before, key) != getattr(other, key)
                for other in (after, current) for key in fields):
            raise ReleaseEvidenceError("file_changed_during_read")
        return raw
    finally:
        os.close(fd)


def _object(raw: bytes) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ReleaseEvidenceError("duplicate_json_key")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ReleaseEvidenceError("nonfinite_json")))
    if not isinstance(value, dict):
        raise ReleaseEvidenceError("metadata_is_not_object")
    return value


def _pin(path: Path, raw: bytes) -> dict[str, Any]:
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "--no-optional-locks", "--no-replace-objects", *arguments],
                            cwd=root, check=True, capture_output=True, text=True, timeout=20)
    if len(result.stdout) > 4096:
        raise ReleaseEvidenceError("git_identity_unbounded")
    return result.stdout.strip()


def _native():
    from integrations.ipfs_datasets.loader import ensure_import_paths
    ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon
    from ipfs_accelerate_py.agent_supervisor.runtime import event_log
    expected = Path(__file__).resolve().parents[2] / "external" / "ipfs_accelerate_py"
    if not all(Path(module.__file__).resolve().is_relative_to(expected) for module in (implementation_daemon, event_log)):
        raise ReleaseEvidenceError("native_import_origin_mismatch")
    return implementation_daemon, event_log


def _campaign_context(root: Path, state: Path, plan_id: str) -> tuple[Path, dict[str, Any]]:
    # The trusted scheduler supplies the existing campaign locator.  Bind it
    # to the actual launcher and Native stores, never a caller's receipt flags.
    _directory(state, private=True)
    launcher = _object(_read(state / "launcher.json"))
    campaign_root = _directory(Path(str(launcher.get("repo_root", ""))))
    if (launcher.get("schema_version") != "complaint-improvement-launcher@1"
            or not (campaign_root / ".git").exists() or launcher.get("plan_id") != plan_id
            or launcher.get("state_dir") != str(state)
            or not isinstance(launcher.get("merge_target"), str) or not launcher["merge_target"]):
        raise ReleaseEvidenceError("campaign_launcher_binding_mismatch")
    # A qualification checkout may differ in path and implementation, but it
    # must use the same reviewed campaign contract and exact task namespace.
    if _read(campaign_root / compiler.SPEC_RELATIVE, source=True) != _read(root / compiler.SPEC_RELATIVE, source=True):
        raise ReleaseEvidenceError("campaign_specification_mismatch")
    if _git(campaign_root, "symbolic-ref", "--short", "HEAD") != launcher["merge_target"].removeprefix("refs/heads/"):
        raise ReleaseEvidenceError("campaign_target_branch_mismatch")
    return campaign_root, launcher


def _read_state(state: Path) -> dict[str, Any]:
    """Project only task metadata from the existing, explicit Native plane."""
    import duckdb
    from ipfs_accelerate_py.agent_supervisor.task_sources.duckdb_state import connect_duckdb_with_policy
    # This is Native implicit_portal_database's layout with the campaign's
    # explicit orchestration root.  No environment-selected/global catalog is
    # opened, and neither Native load(create=True) nor a daemon is constructed.
    scope = hashlib.sha256(str(state).encode()).hexdigest()[:20]
    database = state / "control-plane" / scope / "lanes" / "complaint_intake_task_state.duckdb"
    _readable_database(database, private_root=state)
    fields = ("completed_task_ids", "assumed_completed_task_ids", "task_identities", "task_statuses",
              "blocked_task_ids", "implementation_in_progress", "active_task_id")
    columns = ", ".join("json_extract(body_json, '$." + field + "')" for field in fields)
    connection = connect_duckdb_with_policy(duckdb, database, read_only=True)
    try:
        rows = connection.execute("SELECT " + columns + " FROM portal_task_state WHERE lane_key=?",
                                  ["complaint_intake_task_state"]).fetchall()
    finally:
        connection.close()
    if len(rows) != 1:
        raise ReleaseEvidenceError("native_state_row_missing")
    result = {}
    for key, value in zip(fields, rows[0]):
        if value is not None and len(str(value)) > 2_000_000:
            raise ReleaseEvidenceError("native_state_projection_unbounded")
        result[key] = json.loads(value) if isinstance(value, str) else value
    return result


def _readable_database(path: Path, *, private_root: Path) -> None:
    # Native creates its lane catalog with the operator's group umask. Its
    # enclosing campaign is private, so group file bits confer no access.
    # Bind that boundary explicitly rather than changing existing Native files.
    boundary = _directory(private_root, private=True)
    if path.resolve(strict=True) != path or not path.is_relative_to(boundary):
        raise ReleaseEvidenceError("aliased_database")
    for parent in path.parents:
        _directory(parent)
        if parent == boundary:
            break
    value = path.lstat()
    if (not stat.S_ISREG(value.st_mode) or value.st_uid != os.getuid()
            or value.st_nlink != 1 or value.st_mode & 0o002 or value.st_size <= 0):
        raise ReleaseEvidenceError("unowned_database")


def _queue_bindings(campaign_root: Path, state: Path, branch: str) -> dict[str, set[str]]:
    """Run Native versioned completion rules over its existing read-only store."""
    import duckdb
    from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import checkout_repository_id
    from ipfs_accelerate_py.agent_supervisor.merge.merge_queue import MergeQueue
    from ipfs_accelerate_py.agent_supervisor.task_sources.duckdb_state import DuckDBCursor, connect_duckdb_with_policy
    database = state / "merge-queue" / "merge_queue.duckdb"
    _readable_database(database, private_root=state)

    class ReadOnlyConnection:
        def __enter__(self):
            self.connection = connect_duckdb_with_policy(duckdb, database, read_only=True)
            count = self.connection.execute("SELECT count(*) FROM merge_requests").fetchone()[0]
            if not 0 <= count <= 256:
                self.connection.close()
                raise ReleaseEvidenceError("native_merge_queue_unbounded")
            return self

        def execute(self, sql, parameters=()):
            return DuckDBCursor(self.connection.execute(sql, parameters))

        def __exit__(self, *_args):
            self.connection.close()

    # Native MergeQueue.__init__ creates/migrates catalogs; only adapt transport.
    queue = object.__new__(MergeQueue)
    queue.target_repository_id = checkout_repository_id(campaign_root)
    queue.target_branch = branch
    queue.require_target_binding = True
    queue._connect = ReadOnlyConnection
    return queue.completed_task_cid_bindings()


def _sidecar(state: Path, value: Any) -> Any:
    if not isinstance(value, dict) or value.get("schema") != "ipfs_accelerate_py.agent_supervisor.event-sidecar-blob@1":
        return value
    digest = value.get("digest")
    if (set(value) != {"schema", "bytes", "digest"} or type(value.get("bytes")) is not int
            or not 0 < value["bytes"] <= MAX_METADATA or not isinstance(digest, str)
            or not digest.startswith("sha256:") or _HEX.fullmatch(digest[7:]) is None):
        raise ReleaseEvidenceError("invalid_native_sidecar")
    path = state / "complaint_intake_events.jsonl.artifacts" / digest[7:]
    raw = _read(path, maximum=MAX_METADATA, source=True)
    if len(raw) != value["bytes"] or hashlib.sha256(raw).hexdigest() != digest[7:]:
        raise ReleaseEvidenceError("native_sidecar_digest_mismatch")
    return json.loads(raw)


def _legacy_command_digest(command: Any) -> str:
    """Bind a declared command without retaining historical delivery paths."""
    import shlex
    if not isinstance(command, str) or not 0 < len(command) <= 32_768:
        raise ReleaseEvidenceError("legacy_native_command_invalid")
    try:
        tokens = shlex.split(command)
    except ValueError:
        raise ReleaseEvidenceError("legacy_native_command_invalid") from None
    # The pre-adapter campaign delivered its source path with this one exact
    # prefix. Do not accept arbitrary shell prefixes as command equivalence.
    if tokens and tokens[0] == "export":
        if (len(tokens) < 4 or not tokens[1].startswith("PYTHONPATH=") or tokens[2] != "&&"
                or any(character in tokens[1] for character in ("$", "`", "\n", "\r"))):
            raise ReleaseEvidenceError("legacy_native_command_invalid")
        tokens = tokens[3:]
    if not tokens:
        raise ReleaseEvidenceError("legacy_native_command_invalid")
    return hashlib.sha256(json.dumps(tokens, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _legacy_native_validation(validation: Mapping[str, Any]) -> dict[str, Any]:
    """Verify original pre-adapter Native metadata, then discard opaque data.

    Native's pure receipt parser rederives DAG identity and declared coverage.
    Original output/cache environment are absent from these old journal rows;
    their result digests can be bound to the authenticated DAG, not recomputed.
    """
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import (
        VALIDATION_DAG_RECEIPT_SCHEMA, ValidationDAGReceipt,
    )
    results, raw_dag = validation.get("results"), validation.get("validation_dag_receipt")
    if (validation.get("attempted") is not True or validation.get("passed") is not True
            or type(validation.get("returncode")) is not int or validation["returncode"] != 0
            or validation.get("coverage_errors") != []
            or not isinstance(results, list) or not 0 < len(results) <= 32
            or not isinstance(raw_dag, dict) or raw_dag.get("schema") != VALIDATION_DAG_RECEIPT_SCHEMA
            or _HEX.fullmatch(str(raw_dag.get("receipt_id", ""))) is None
            or raw_dag.get("passed") is not True or raw_dag.get("coverage_complete") is not True
            or raw_dag.get("uncovered_impact") is not False
            or not isinstance(raw_dag.get("nodes"), list) or not 0 < len(raw_dag["nodes"]) <= 256):
        raise ReleaseEvidenceError("legacy_native_validation_invalid")
    try:
        dag = ValidationDAGReceipt.from_dict(raw_dag)
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ReleaseEvidenceError("legacy_native_dag_invalid") from None
    if (not dag.passed or not dag.coverage_complete or dag.uncovered_impact
            or not dag.required_validation_ids or not dag.selected_node_ids
            or dag.repository_tree_id != validation.get("target_commit")):
        raise ReleaseEvidenceError("legacy_native_dag_invalid")
    selected = {node.validation_id: node for node in dag.nodes if node.selected}
    if len(selected) != len(dag.selected_node_ids) or set(selected) != set(dag.required_validation_ids):
        raise ReleaseEvidenceError("legacy_native_result_binding_invalid")
    projected, ordinals, identities = [], set(), set()
    for result in results:
        if not isinstance(result, dict):
            raise ReleaseEvidenceError("legacy_native_result_invalid")
        identity, ordinal = result.get("validation_id"), result.get("ordinal")
        digest, cache_key = result.get("validation_result_digest"), result.get("cache_key")
        if (not isinstance(identity, str) or not 0 < len(identity) <= 512 or identity in identities
                or type(ordinal) is not int or ordinal in ordinals
                or type(result.get("returncode")) is not int or result["returncode"] != 0
                or result.get("timed_out") is not False or result.get("cache_hit") is not False
                or type(result.get("attempt_number")) is not int or result["attempt_number"] < 1
                or _HEX.fullmatch(str(digest or "")) is None or _HEX.fullmatch(str(cache_key or "")) is None):
            raise ReleaseEvidenceError("legacy_native_result_invalid")
        node = selected.get(identity)
        command_digest = _legacy_command_digest(result.get("command"))
        if (node is None or not node.mandatory or node.disposition.value != "succeeded"
                or node.returncode != 0 or node.result_digest != digest
                or _legacy_command_digest(node.command) != command_digest):
            raise ReleaseEvidenceError("legacy_native_result_binding_invalid")
        launcher = result.get("validation_python_launcher")
        if (not isinstance(launcher, dict) or launcher.get("sealed") is not True
                or launcher.get("mode") != "linux:sealed-memfd"
                or any(_HEX.fullmatch(str(launcher.get(field, ""))) is None for field in (
                    "content_sha256", "interpreter_sha256", "policy_sha256"))
                or not isinstance(launcher.get("interpreter_stat"), str)
                or not 0 < len(launcher["interpreter_stat"]) <= 4096):
            raise ReleaseEvidenceError("legacy_native_launcher_invalid")
        try:
            interpreter = _object(launcher["interpreter_stat"].encode())
        except (ValueError, TypeError):
            raise ReleaseEvidenceError("legacy_native_launcher_invalid") from None
        if (any(type(interpreter.get(field)) is not int or interpreter[field] < 0
                for field in ("device", "inode", "mode", "mtime_ns", "size"))
                or not interpreter["inode"] or not interpreter["size"]
                or not isinstance(interpreter.get("path"), str) or not Path(interpreter["path"]).is_absolute()):
            raise ReleaseEvidenceError("legacy_native_launcher_invalid")
        projected.append({"validation_id": identity, "ordinal": ordinal, "command_sha256": command_digest,
            "validation_result_digest": digest, "cache_key": cache_key,
            "validation_python_launcher": {**{field: launcher[field] for field in (
                "mode", "sealed", "content_sha256", "interpreter_sha256", "policy_sha256")},
                "interpreter_stat_sha256": hashlib.sha256(launcher["interpreter_stat"].encode()).hexdigest()}})
        identities.add(identity)
        ordinals.add(ordinal)
    binding = validation.get("validation_plan_binding")
    if (ordinals != set(range(len(results))) or identities != set(selected)
            or not isinstance(binding, dict) or binding.get("command_count") != len(results)
            or binding.get("graph_id") != dag.graph_id
            or not isinstance(binding.get("validation_ids"), list)
            or len(binding["validation_ids"]) != len(results) or set(binding["validation_ids"]) != identities):
        raise ReleaseEvidenceError("legacy_native_result_binding_invalid")
    candidate, proposal = validation.get("candidate_binding"), validation.get("proposal_gate")
    if (not isinstance(candidate, dict) or candidate.get("verified") is not True
            or not isinstance(candidate.get("validated_workspace"), dict)
            or candidate["validated_workspace"].get("verified") is not True
            or not isinstance(candidate.get("expected_fingerprint"), str)
            or not candidate["expected_fingerprint"].startswith("sha256:")
            or _HEX.fullmatch(candidate["expected_fingerprint"][7:]) is None
            or candidate.get("current_fingerprint") != candidate["expected_fingerprint"]
            or not isinstance(proposal, dict) or proposal.get("accepted") is not True
            or proposal.get("attempted") is not True or proposal.get("reason_codes") != []
            or not isinstance(proposal.get("proposal_id"), str) or not 0 < len(proposal["proposal_id"]) <= 512
            or candidate.get("proposal_id") != proposal["proposal_id"]
            or proposal.get("receipt_id") != dag.proposal_receipt_id
            or proposal.get("repository_tree_id") != dag.repository_tree_id):
        raise ReleaseEvidenceError("legacy_native_candidate_binding_invalid")
    return {"schema": "complaint-legacy-native-validation@1", "results": sorted(projected, key=lambda item: item["ordinal"]),
            "dag_receipt_id": dag.receipt_id, "dag_graph_id": dag.graph_id,
            "repository_tree_id": dag.repository_tree_id, "required_validation_ids": list(dag.required_validation_ids),
            "selected_node_ids": list(dag.selected_node_ids), "candidate_fingerprint": candidate["current_fingerprint"],
            "proposal_id": proposal["proposal_id"], "proposal_receipt_id": dag.proposal_receipt_id}


def _journal(state: Path, event_log) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verify every canonical identity; retain only bounded completion fields.

    Other event values are opaque inputs to Native's identity verifier.  No
    provider text, prompts, command arguments, or environment is projected.
    """
    path = state / "complaint_intake_events.jsonl"
    raw = _read(path, maximum=MAX_JOURNAL, source=True)
    lines = raw.splitlines(keepends=True)
    if not lines or len(lines) > MAX_EVENTS or not raw.endswith(b"\n"):
        raise ReleaseEvidenceError("native_journal_incomplete_or_unbounded")
    previous, retained, started = "", [], {}
    stream, snapshot = event_log._event_stream_binding(path)
    for sequence, line in enumerate(lines, 1):
        if len(line) > MAX_METADATA:
            raise ReleaseEvidenceError("native_event_unbounded")
        value = _object(line)
        if (type(value.get("sequence")) is not int or value["sequence"] != sequence
                or value.get("previous_event_id", "") != previous
                or value.get("stream_id") != stream or value.get("snapshot_id") != snapshot
                or value.get("event_id") != event_log._event_identity(value)):
            raise ReleaseEvidenceError("native_journal_chain_invalid")
        previous = value["event_id"]
        task_id = value.get("task_id")
        if value.get("type") == "implementation_started" and isinstance(task_id, str):
            cid, key = value.get("canonical_task_cid"), value.get("canonical_task_key")
            if isinstance(cid, str) and isinstance(key, str) and cid and key:
                started.setdefault((task_id, cid), set()).add(key)
        if value.get("type") != "implementation_finished":
            continue
        validation, merge = value.get("validation_result"), value.get("merge_result")
        if not isinstance(validation, dict) or not isinstance(merge, dict):
            continue
        todo = merge.get("todo_update_result")
        if not isinstance(todo, dict):
            continue
        cid, key = value.get("canonical_task_cid"), value.get("canonical_task_key")
        if not cid or not key:
            cid = value.get("task_cid")
            keys = started.get((task_id, cid), set())
            if (value.get("provider_dispatched") is not False or value.get("attempt_consumed") is not False
                    or not value.get("recovery_key") or len(keys) != 1):
                continue
            key = next(iter(keys))
        modern = "behavioral_evidence" in validation
        evidence = _sidecar(state, validation.get("behavioral_evidence"))
        evidence = [{name: item.get(name) for name in ("admitted", "measurement_record")}
                    if isinstance(item, dict) else None for item in evidence] if isinstance(evidence, list) else None
        legacy = None
        if not modern:
            try:
                legacy = _legacy_native_validation(validation)
            except ReleaseEvidenceError as exc:
                legacy = {"error": str(exc)}
        commit = todo.get("commit_result")
        commit = {name: commit.get(name) for name in ("committed", "commit", "reason", "parent_gitlink_commits")} if isinstance(commit, dict) else None
        retained.append({"task_id": task_id, "canonical_task_cid": cid, "canonical_task_key": key,
                         "sequence": sequence, "event_id": previous,
                         "returncode": value.get("returncode"), "validation_passed": validation.get("passed"),
                         "behavioral_evidence": evidence, "behavioral_evidence_present": modern,
                         "legacy_native_validation": legacy,
                         "implementation_commit": value.get("implementation_commit"),
                         "merge_commit": merge.get("merge_commit"),
                         "merged": merge.get("merged") is True or merge.get("already_merged") is True,
                         "todo": {**{name: todo.get(name) for name in (
                             "updated", "reason", "updated_task_ids", "already_completed_task_ids", "missing_task_ids",
                             "completion_receipts", "durable", "completion_callback_evidence")}, "commit_result": commit}})
    return retained, {"path": str(path), "prefix_sha256": hashlib.sha256(raw).hexdigest(),
                      "prefix_bytes": len(raw), "last_sequence": len(lines), "last_event_id": previous,
                      "chain_verified": True}


def _historical_measurements(state: Path, evidence: Any) -> dict[str, Any]:
    if not isinstance(evidence, list) or not 0 < len(evidence) <= 32:
        raise ReleaseEvidenceError("historical_measurement_missing")
    artifacts, digests = [], []
    for item in evidence:
        if not isinstance(item, dict) or item.get("admitted") is not True:
            raise ReleaseEvidenceError("historical_admission_missing")
        record = item.get("measurement_record")
        if not isinstance(record, dict) or _HEX.fullmatch(str(record.get("sha256", ""))) is None:
            raise ReleaseEvidenceError("historical_measurement_pin_missing")
        path = Path(str(record.get("path", "")))
        if not path.is_relative_to(state / "evidence-runs") or path.name != "measurement.json":
            raise ReleaseEvidenceError("historical_measurement_out_of_scope")
        raw = _read(path, source=True)
        if hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ReleaseEvidenceError("historical_measurement_digest_mismatch")
        measured = _object(raw)
        if (measured.get("schema") != "complaint-owned-behavioral-measurement@1"
                or measured.get("reason") != "" or measured.get("source_unchanged") is not True
                or measured.get("source_before") != measured.get("source_after")):
            raise ReleaseEvidenceError("historical_measurement_rejected")
        source = measured.get("source_after")
        if not isinstance(source, dict) or _HEX.fullmatch(str(source.get("digest", ""))) is None:
            raise ReleaseEvidenceError("historical_source_binding_missing")
        artifacts.append(_pin(path, raw))
        digests.append(source["digest"])
    return {"status": "HISTORICAL", "artifacts": artifacts,
            "source_after_digest": digests[0] if len(digests) == 1 else None,
            "source_after_digests": digests, "current_source_equivalence": False}


def _historical_execution(state: Path, row: Mapping[str, Any], task: Any, journal_pin: Mapping[str, Any]) -> dict[str, Any]:
    # Presence, including null/malformed modern data, forbids legacy fallback.
    if row.get("behavioral_evidence_present", True) is not False:
        return _historical_measurements(state, row.get("behavioral_evidence"))
    legacy = row.get("legacy_native_validation")
    if not isinstance(legacy, dict) or legacy.get("schema") != "complaint-legacy-native-validation@1":
        raise ReleaseEvidenceError(legacy.get("error", "legacy_native_validation_missing")
                                   if isinstance(legacy, dict) else "legacy_native_validation_missing")
    if (journal_pin.get("chain_verified") is not True
            or _HEX.fullmatch(str(journal_pin.get("prefix_sha256", ""))) is None
            or type(journal_pin.get("prefix_bytes")) is not int or journal_pin["prefix_bytes"] <= 0
            or type(row.get("sequence")) is not int
            or type(journal_pin.get("last_sequence")) is not int
            or not 0 < row["sequence"] <= journal_pin["last_sequence"]
            or journal_pin.get("path") != str(state / "complaint_intake_events.jsonl")):
        raise ReleaseEvidenceError("legacy_native_journal_pin_missing")
    expected = [_legacy_command_digest(command) for command in task.validation]
    if not expected or [item["command_sha256"] for item in legacy["results"]] != expected:
        raise ReleaseEvidenceError("legacy_native_contract_mismatch")
    return {"status": "HISTORICAL", "evidence_kind": "legacy_native_executor", "artifacts": [],
            "source_after_digest": None, "source_after_digests": [], "current_source_equivalence": False,
            "journal_prefix": dict(journal_pin), "native_event": {"sequence": row["sequence"], "event_id": row["event_id"]},
            "validation_metadata": legacy,
            "limitations": ["Original result output and cache environment were not retained; result digests are bound to the authenticated journal and Native DAG, not recomputed.",
                            "Historical case counts, AST seals, and skip outcomes are unavailable; current semantic coverage requires fresh mandatory measurements."]}


def _compact_queue_host_measurements(state: Path, validation: Mapping[str, Any], task: Any,
                                     binding: Mapping[str, Any]) -> dict[str, Any]:
    """Observe owned Host seals omitted by Native's bounded queue projection.

    Native's queue producer retains proposal/result identities but deliberately
    omits behavioral_evidence. The fixed admitted Host receipt is usable only
    when its proposal, task, command and measured candidate bytes all join that
    authenticated completed queue/callback. This mints no new admission.
    """
    root = Path(str(binding.get("repo_root", "")))
    candidate, baseline = binding.get("implementation_commit"), binding.get("baseline_ref")
    gate, results = validation.get("proposal_gate"), validation.get("results")
    expected = [_legacy_command_digest(command) for command in task.validation]
    if (not _COMMIT.fullmatch(str(candidate or "")) or not _COMMIT.fullmatch(str(baseline or ""))
            or validation.get("attempted") is not True or validation.get("passed") is not True
            or type(validation.get("returncode")) is not int or validation["returncode"] != 0
            or validation.get("target_commit") != candidate
            or not isinstance(gate, dict) or gate.get("accepted") is not True
            or gate.get("proposal_id") != binding.get("proposal_id")
            or gate.get("repository_tree_id") != baseline
            or _HEX.fullmatch(str(gate.get("proposal_id", ""))) is None
            or _HEX.fullmatch(str(gate.get("receipt_id", ""))) is None
            or not isinstance(results, list) or not 0 < len(results) == len(expected) <= 32):
        raise ReleaseEvidenceError("compact_queue_validation_invalid")
    tree = _git(root, "rev-parse", candidate + "^{tree}")
    if validation.get("target_tree") != tree or validation.get("repository_tree_id") != "git-tree:" + tree:
        raise ReleaseEvidenceError("compact_queue_candidate_mismatch")
    changed = gate.get("changed_paths")
    if (not isinstance(changed, list) or not changed or len(changed) > 256
            or any(not isinstance(path, str) for path in changed)
            or sorted(set(changed)) != sorted(changed)
            or _git(root, "diff", "--name-only", baseline, candidate).splitlines() != sorted(changed)):
        raise ReleaseEvidenceError("compact_queue_changed_paths_mismatch")
    for ordinal, (result, command) in enumerate(zip(results, expected)):
        if (not isinstance(result, dict) or type(result.get("ordinal")) is not int
                or result["ordinal"] != ordinal or type(result.get("returncode")) is not int
                or result["returncode"] != 0 or result.get("timed_out") is not False
                or result.get("cache_hit") is not False
                or result.get("infrastructure_failure") not in (None, False)
                or _HEX.fullmatch(str(result.get("validation_result_digest", ""))) is None
                or _legacy_command_digest(result.get("command")) != command):
            raise ReleaseEvidenceError("compact_queue_result_invalid")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", task.task_id) is None:
        raise ReleaseEvidenceError("compact_queue_task_locator_invalid")
    path = state / "evidence" / task.task_id / "completion.json"
    raw = _read(path, source=True)
    receipt = _object(raw)
    contract = receipt.get("host_task_contract")
    context = contract.get("context") if isinstance(contract, dict) else None
    declared = contract.get("task") if isinstance(contract, dict) else None
    if (receipt.get("schema_version") != "complaint-generator/improvement-evidence@1"
            or receipt.get("task_id") != task.task_id or receipt.get("admitted") is not True
            or receipt.get("completion") is not True or receipt.get("completion_authority") is not False
            or receipt.get("lane") != compiler.COMPLETING_LANE
            or type(receipt.get("exit_status")) is not int or receipt["exit_status"] != 0
            or receipt.get("timed_out") is not False or not isinstance(context, dict)
            or not isinstance(declared, dict) or declared.get("id") != task.task_id
            or declared.get("targets") != list(task.outputs)
            or [_legacy_command_digest(command) for command in declared.get("validation_commands", [])] != expected
            or context.get("task_id") != task.task_id
            or context.get("task_cid") != binding.get("canonical_task_cid")
            or context.get("task_key") != binding.get("canonical_task_key")
            or context.get("proposal_context_id") != binding.get("canonical_task_cid")
            or context.get("proposal_id") != gate["proposal_id"]
            or context.get("repository_tree_id") != baseline
            or context.get("campaign_state_dir") != str(state)
            or sorted(context.get("changed_paths", [])) != changed
            or receipt.get("task_contract_digest") != compiler._digest(contract)):
        raise ReleaseEvidenceError("compact_queue_host_contract_mismatch")
    # The fixed receipt only retains one completing command. Multiple-command
    # compact queues need a future immutable per-command Host index; do not
    # infer missing authority from the final command's receipt.
    if len(expected) != 1 or _legacy_command_digest(contract.get("declared_command")) != expected[0]:
        raise ReleaseEvidenceError("compact_queue_host_population_unavailable")
    history = _historical_measurements(state, [receipt])
    record = receipt["measurement_record"]
    measured = _object(_read(Path(record["path"]), source=True))
    observed = measured.get("observation_binding")
    source = receipt.get("source_binding")
    if (receipt.get("host_measurement") != measured
            or measured.get("task_contract_digest") != receipt["task_contract_digest"]
            or not isinstance(observed, dict) or observed.get("source_binding") != source
            or observed.get("exit_status") != 0 or observed.get("timed_out") is not False
            or not isinstance(source, dict) or source.get("missing") != [] or source.get("empty") != []
            or source.get("unbounded") is not False
            or set(source.get("files", {})) != set(task.outputs)
            or measured.get("output_paths") != list(task.outputs)):
        raise ReleaseEvidenceError("compact_queue_host_measurement_mismatch")
    files = measured["source_after"].get("files", {})
    for relative, item in source["files"].items():
        name = Path(relative)
        if (name.is_absolute() or ".." in name.parts or name.as_posix() != relative
                or not isinstance(item, dict) or item.get("present") is not True
                or item.get("kind") != "file" or item.get("empty") is not False
                or _HEX.fullmatch(str(item.get("sha256", ""))) is None
                or not isinstance(files.get(relative), dict)
                or files[relative].get("sha256") != item["sha256"]):
            raise ReleaseEvidenceError("compact_queue_source_binding_invalid")
        # Git bytes, not current mutable worktree files, bind the old source
        # seal to the immutable candidate Native actually integrated.
        result = subprocess.run(["git", "--no-replace-objects", "--no-optional-locks", "-c", "core.hooksPath=/dev/null", "show", candidate + ":" + relative],
            cwd=root, env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "GIT_CONFIG_GLOBAL": "/dev/null",
                           "GIT_CONFIG_SYSTEM": "/dev/null"}, capture_output=True, timeout=30, check=False)
        if result.returncode or len(result.stdout) > MAX_METADATA or hashlib.sha256(result.stdout).hexdigest() != item["sha256"]:
            raise ReleaseEvidenceError("compact_queue_candidate_source_mismatch")
    return {**history, "evidence_kind": "compact_native_queue_and_owned_host_measurement",
        "host_receipt": _pin(path, raw), "proposal_id": gate["proposal_id"],
        "implementation_commit": candidate, "native_result_digests": [row["validation_result_digest"] for row in results],
        "limitations": ["This is historical execution, not current semantic coverage or a new completion admission."]}


def historical_queue_validation(state: Path, validation: Mapping[str, Any], task: Any,
                                journal_pin: Mapping[str, Any], *, callback_sequence: int,
                                callback_event_id: str,
                                callback_binding: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Read the same historical seals from an actual completed queue proof.

    This is a distinct queue/callback observation, never a synthesized Native
    implementation_finished event. Malformed modern data cannot use legacy.
    """
    if "behavioral_evidence" in validation:
        raw = _sidecar(state, validation.get("behavioral_evidence"))
        selected = ([{name: item.get(name) for name in ("admitted", "measurement_record")}
                     if isinstance(item, dict) else None for item in raw]
                    if isinstance(raw, list) else None)
        history = _historical_measurements(state, selected)
    elif ("schema" not in validation and "validation_dag_receipt" not in validation
          and "target_tree" in validation and "proposal_gate" in validation):
        if not isinstance(callback_binding, Mapping):
            raise ReleaseEvidenceError("compact_queue_callback_binding_missing")
        history = _compact_queue_host_measurements(state, validation, task, callback_binding)
    else:
        # Reuse the exact existing Native DAG/command/launcher checks. This
        # projection labels the genuine callback event as its provenance.
        legacy = _legacy_native_validation(validation)
        history = _historical_execution(state, {"behavioral_evidence_present": False,
            "legacy_native_validation": legacy, "sequence": callback_sequence,
            "event_id": callback_event_id}, task, journal_pin)
    return {**history, "observation_provenance": "completed_queue_validation_and_durable_callback",
            "native_finish_event_synthesized": False}


def _callback(row: Mapping[str, Any], task: Any, native) -> tuple[dict[str, Any], str]:
    if (type(row.get("returncode")) is not int or row["returncode"] != 0
            or row.get("validation_passed") is not True or row.get("merged") is not True
            or row.get("canonical_task_cid") != task.canonical_task_cid
            or row.get("canonical_task_key") != task.canonical_task_key):
        raise ReleaseEvidenceError("native_finish_not_successful")
    todo = row["todo"]
    if todo.get("durable") is False:
        raise ReleaseEvidenceError("native_callback_not_durable")
    updated, already = todo.get("updated_task_ids") or [], todo.get("already_completed_task_ids") or []
    if (not isinstance(updated, list) or not isinstance(already, list)
            or any(not isinstance(value, str) or not value for value in updated + already)
            or len(set(updated + already)) != len(updated + already)):
        raise ReleaseEvidenceError("native_callback_members_malformed")
    if (todo.get("updated") is not True and todo.get("reason") != "already_completed") or task.task_id not in updated + already:
        raise ReleaseEvidenceError("native_callback_not_applied")
    if todo.get("missing_task_ids"):
        raise ReleaseEvidenceError("native_callback_has_missing_members")
    receipts = todo.get("completion_receipts")
    if not isinstance(receipts, list) or not 0 < len(receipts) <= 58:
        raise ReleaseEvidenceError("native_member_receipt_missing")
    if (any(not isinstance(receipt, dict) or receipt.get("schema") != "ipfs_accelerate_py.agent_supervisor.member_completion_receipt@1"
            or receipt.get("status") != "succeeded" for receipt in receipts)
            or len({receipt.get("task_id") for receipt in receipts}) != len(receipts)
            or {receipt.get("task_id") for receipt in receipts} != set(updated + already)):
        raise ReleaseEvidenceError("native_callback_all_member_receipts_mismatch")
    matches = [receipt for receipt in receipts if isinstance(receipt, dict)
               and receipt.get("schema") == "ipfs_accelerate_py.agent_supervisor.member_completion_receipt@1"
               and receipt.get("status") == "succeeded" and receipt.get("task_id") == task.task_id
               and receipt.get("canonical_task_cid") == task.canonical_task_cid
               and receipt.get("canonical_task_key") == task.canonical_task_key]
    if len(matches) != 1:
        raise ReleaseEvidenceError("native_member_revision_receipt_mismatch")
    callback = todo.get("completion_callback_evidence")
    if callback is not None:
        # Existing static Native content identity; never synthesize a callback
        # expectation or a lifecycle event from this audit's task list.
        if (not isinstance(callback, dict) or callback.get("succeeded") is not True
                or callback.get("evidence_id") != native.content_identity({key: value for key, value in callback.items() if key != "evidence_id"})):
            raise ReleaseEvidenceError("native_callback_evidence_invalid")
    commit = todo.get("commit_result")
    if (not isinstance(commit, dict) or commit.get("committed") is not True
            or not native.PortalImplementationDaemon._generated_file_commit_result_trusted(commit)
            or not _COMMIT.fullmatch(str(commit.get("commit", "")))):
        raise ReleaseEvidenceError("native_callback_commit_missing")
    # Legacy genuine journal entries carry the successful member/CAS receipt
    # and committed board result rather than a separate callback expectation.
    return {key: matches[0][key] for key in ("schema", "task_id", "canonical_task_key", "canonical_task_cid", "status")}, commit["commit"]


def _requirement_maps(plan: Any, result: dict[str, Any]) -> None:
    """Derive coverage from the contract, without asserting goal lifecycles."""
    for kind, records, identifier in (("goals", plan.goals, "goal_id"), ("subgoals", plan.subgoals, "subgoal_id")):
        for record in records:
            requirement_ids = list(record.evidence_requirement_ids)
            task_ids = [value.removeprefix("test.") for value in requirement_ids]
            if not requirement_ids or any("test." + task_id != requirement or task_id not in result["tasks"]
                    for requirement, task_id in zip(requirement_ids, task_ids)):
                raise ReleaseEvidenceError("goal_requirement_mapping_mismatch")
            result[kind][getattr(record, identifier)] = {"evidence_requirement_ids": requirement_ids,
                "task_ids": task_ids, **({"goal_id": record.goal_id} if kind == "subgoals" else {}),
                "native_completion_satisfied": all(result["tasks"][task_id]["native_completed"]
                    and result["tasks"][task_id]["callback_verified"] and result["tasks"][task_id]["integration_verified"] for task_id in task_ids),
                "current_source_semantic_coverage": {"status": "UNVERIFIED"},
                "native_goal_lifecycle_claimed": False, "completion_authority": False}


def collect_native_release_evidence(repo_root: Path | str, spec_path: Path | str,
                                    campaign_state_dir: Path | str, *, phase: str) -> dict[str, Any]:
    """Return bounded historical Native proof and unverified current coverage.

    ``pre-admission`` permits only REL03 itself to remain pending.  No arbitrary
    JSON receipt argument, caller-provided source hash, or completion flag can
    replace the existing campaign's journal, versioned queue, and control plane.
    All failures remain explicit and fail closed.
    """
    result: dict[str, Any] = {"schema": SCHEMA, "phase": phase, "completion_authority": False,
        "native_completion_satisfied": False, "tasks": {}, "goals": {}, "subgoals": {}, "issues": [],
        "integration_proof": {"verified": False, "status": "UNVERIFIED"},
        "current_source_semantic_coverage": {"status": "UNVERIFIED", "completion_authority": False}}

    def issue(code: str, kind: str, task_id: str | None = None):
        result["issues"].append({"code": code, "kind": kind, **({"task_id": task_id} if task_id else {})})

    if phase not in {"pre-admission", "post-completion"}:
        issue("unknown_release_phase", "unknown")
        return result
    try:
        root, state = _directory(Path(repo_root)), Path(campaign_state_dir)
        spec_file = Path(spec_path)
        if spec_file != root / compiler.SPEC_RELATIVE:
            raise ReleaseEvidenceError("noncanonical_specification_path")
        spec_raw = _read(spec_file, source=True)
        spec = compiler.validate_spec(_object(spec_raw))
        native, event_log = _native()
        plan = compiler.build_improvement_work_plan(spec)
        result.update(plan_id=plan.plan_id, expected_task_count=58, expected_goal_count=10, expected_subgoal_count=29)
        if (len(plan.tasks), len(plan.goals), len(plan.subgoals), len(plan.evidence_requirements)) != (58, 10, 29, 58):
            raise ReleaseEvidenceError("reviewed_plan_shape_mismatch")
        stored_plan = _object(_read(root / compiler.PLAN_RELATIVE, source=True))
        if stored_plan != {**plan.to_dict(), "plan_id": plan.plan_id}:
            raise ReleaseEvidenceError("formal_plan_contract_mismatch")
        campaign_root, launcher = _campaign_context(root, state, plan.plan_id)
        board_raw = _read(root / compiler.BOARD_RELATIVE, source=True)
        if board_raw.decode().count(f"<!-- plan_id: {plan.plan_id} -->") != 1:
            raise ReleaseEvidenceError("native_board_plan_binding_mismatch")
        tasks = native.parse_task_text(board_raw.decode(), path=root / compiler.BOARD_RELATIVE, task_header_prefix=TASK_PREFIX)
        by_id = {task.task_id: task for task in tasks}
        if len(tasks) != 58 or set(by_id) != {task["id"] for task in spec["tasks"]}:
            raise ReleaseEvidenceError("native_board_task_set_mismatch")
        campaign_tasks = native.parse_task_text(_read(campaign_root / compiler.BOARD_RELATIVE, source=True).decode(),
            path=campaign_root / compiler.BOARD_RELATIVE, task_header_prefix=TASK_PREFIX)
        campaign_by_id = {task.task_id: task for task in campaign_tasks}
        if (len(campaign_tasks) != 58 or set(campaign_by_id) != set(by_id)
                or any(campaign_by_id[task_id].canonical_task_cid != task.canonical_task_cid
                       for task_id, task in by_id.items())):
            raise ReleaseEvidenceError("campaign_current_task_revision_mismatch")
        for item in spec["tasks"]:
            task = by_id[item["id"]]
            if (task.title != item["title"] or task.acceptance != " ".join(item["acceptance"])
                    or task.outputs != item["targets"] or task.validation != item["validation_commands"]
                    or task.depends_on != item["depends_on"] or task.metadata.get("goal") != item["goal_id"]
                    or task.metadata.get("subgoal") != item["subgoal_id"]
                    or task.metadata.get("provider role") != "grok-only" or task.metadata.get("model") != "grok-4.7"):
                raise ReleaseEvidenceError("native_board_contract_mismatch")
        head, tree = _git(root, "rev-parse", "HEAD"), _git(root, "rev-parse", "HEAD^{tree}")
        result["source_checkout"] = {"path": str(root), "head": head, "tree": tree,
                                     "specification": _pin(spec_file, spec_raw),
                                     "board": _pin(root / compiler.BOARD_RELATIVE, board_raw),
                                     "scope": "Git identities; current uncommitted semantics require separate measurement"}
        for task_id, task in by_id.items():
            result["tasks"][task_id] = {"canonical_task_cid": task.canonical_task_cid, "native_completed": False,
                "callback_verified": False, "integration_verified": False,
                "required_in_phase": phase == "post-completion" or task_id != SELF_TASK,
                "historical_evidence": {"status": "MISSING", "artifacts": [], "current_source_equivalence": False},
                "current_source_semantic_coverage": {"status": "UNVERIFIED"}}
        _requirement_maps(plan, result)
        projection = _read_state(state)
        bindings = _queue_bindings(campaign_root, state, launcher["merge_target"])
        finishes, journal_pin = _journal(state, event_log)
        result["native_journal"] = journal_pin
        completed = projection.get("completed_task_ids")
        identities = projection.get("task_identities")
        statuses = projection.get("task_statuses")
        if not isinstance(completed, list) or not isinstance(identities, dict) or not isinstance(statuses, dict):
            raise ReleaseEvidenceError("native_state_projection_malformed")
        if projection.get("assumed_completed_task_ids"):
            issue("assumed_completions_are_not_actual_callbacks", "unknown")
        if len(set(completed)) != len(completed) or not set(completed) <= set(by_id):
            issue("native_completed_task_namespace_mismatch", "unknown")
        active = projection.get("active_task_id")
        if projection.get("implementation_in_progress") and (phase != "pre-admission" or active != SELF_TASK):
            issue("native_required_implementation_still_active", "held", active if isinstance(active, str) else None)
        for task_id, task in by_id.items():
            required = phase == "post-completion" or task_id != SELF_TASK
            task_row = result["tasks"][task_id]
            if not required:
                if (task_id in completed or task.canonical_task_cid in bindings.get(task_id, set())
                        or campaign_by_id[task_id].status == "completed"):
                    issue("pre_admission_self_already_completed", "unknown", task_id)
                continue
            if task_id in (projection.get("blocked_task_ids") or []) or statuses.get(task_id) in {"blocked", "paused", "waiting_user", "manual_hold"}:
                issue("native_task_held", "held", task_id)
                continue
            if (task_id not in completed or statuses.get(task_id) != "completed"
                    or campaign_by_id[task_id].status != "completed"
                    or identities.get(task_id, {}).get("canonical_task_cid") != task.canonical_task_cid
                    or task.canonical_task_cid not in bindings.get(task_id, set())):
                issue("actual_native_revision_completion_missing", "missing", task_id)
                continue
            task_row["native_completed"] = True
            candidates = [row for row in finishes if row.get("task_id") == task_id and row.get("canonical_task_cid") == task.canonical_task_cid]
            if not candidates:
                issue("native_callback_history_missing", "missing", task_id)
                continue
            try:
                row = candidates[-1]
                receipt, callback_commit = _callback(row, task, native)
                task_row["callback_verified"] = True
                task_row["callback"] = {"sequence": row["sequence"], "event_id": row["event_id"],
                                        "member_receipt": receipt, "board_commit": callback_commit}
                task_row["historical_evidence"] = _historical_execution(state, row, task, journal_pin)
                commits = [row["implementation_commit"], row["merge_commit"], callback_commit]
                if any(not _COMMIT.fullmatch(str(commit or "")) for commit in commits):
                    raise ReleaseEvidenceError("native_integration_commit_missing")
                for commit in dict.fromkeys(commits):
                    _git(campaign_root, "merge-base", "--is-ancestor", commit, "HEAD")
                task_row["integration_verified"] = True
                task_row["historical_integration_commits"] = commits
            except (ReleaseEvidenceError, OSError, ValueError, subprocess.SubprocessError) as exc:
                issue(str(exc) if isinstance(exc, ReleaseEvidenceError) else "native_callback_or_integration_unavailable", "unavailable", task_id)
        required_rows = [row for row in result["tasks"].values() if row["required_in_phase"]]
        result["native_completion_satisfied"] = not result["issues"] and all(
            row["native_completed"] and row["callback_verified"] and row["integration_verified"]
            and row["historical_evidence"]["status"] == "HISTORICAL" for row in required_rows)
        result["integration_proof"] = {"verified": result["native_completion_satisfied"],
            "status": "VERIFIED" if result["native_completion_satisfied"] else "UNVERIFIED",
            "campaign_repo_root": str(campaign_root), "campaign_head": _git(campaign_root, "rev-parse", "HEAD"),
            "scope": "Historical Native implementation, merge and board callback ancestry"}
        _requirement_maps(plan, result)
    except Exception as exc:
        issue(str(exc) if isinstance(exc, ReleaseEvidenceError) else "native_release_evidence_unavailable", "unavailable")
        result["native_completion_satisfied"] = False
        result["integration_proof"] = {"verified": False, "status": "UNVERIFIED"}
    return result


# Current-source qualification is independent of the historical Native join.
_CURRENT_BINDING_NAME = "complaint-release-current-qualification.json"
_CURRENT_BINDING_SCHEMA = "complaint-release-current-host-binding@1"
_CURRENT_QUALIFICATION_SCHEMA = "complaint-release-current-source-qualification@1"
_CURRENT_MAX_SHARDS = 83
_CURRENT_MODULES_PER_SHARD = 4
_CURRENT_BUDGET = 900


def _current_need(condition, reason):
    if not condition:
        raise ReleaseEvidenceError("current_qualification_" + reason)


def _current_private(path):
    path = _directory(Path(path), private=True)
    _current_need(stat.S_IMODE(path.stat().st_mode) == 0o700, "directory_not_private")
    return path


def _current_file(path, *, maximum=MAX_METADATA, source=False):
    """Stable no-follow reads; installed source may also be owned by root."""
    path = Path(path)
    _current_need(path.is_absolute() and path.resolve(strict=True) == path, "file_alias")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        allowed_owners = {0, os.getuid()} if source else {os.getuid()}
        _current_need(stat.S_ISREG(before.st_mode) and before.st_uid in allowed_owners
            and before.st_nlink == 1 and not before.st_mode & (0o002 if source else 0o077)
            and (0 if source else 1) <= before.st_size <= maximum, "file_custody_or_bound")
        chunks, remaining = [], before.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
        _current_need(len(raw) == before.st_size and all(
            getattr(before, name) == getattr(other, name)
            for other in (os.fstat(descriptor), path.lstat()) for name in fields), "file_changed")
        return raw
    finally:
        os.close(descriptor)


def _current_pin(row, *, within=None, maximum=MAX_METADATA, source=False):
    _current_need(isinstance(row, dict) and set(row) == {"path", "sha256"}
        and isinstance(row["path"], str) and isinstance(row["sha256"], str)
        and _HEX.fullmatch(row["sha256"]) is not None, "invalid_artifact_pin")
    path = Path(row["path"])
    if within is not None:
        _current_need(path.is_relative_to(within), "artifact_outside_producer")
        for parent in path.parents:
            _current_private(parent)
            if parent == within:
                break
    raw = _current_file(path, maximum=maximum, source=source)
    _current_need(hashlib.sha256(raw).hexdigest() == row["sha256"], "artifact_digest_mismatch")
    return path, raw


def _current_checker(root):
    """Load the actual source contract, without a scripts-package lookup."""
    import importlib.util
    import sys
    path = root / "scripts/validate_complaint_intake.py"
    raw = _current_file(path, source=True)
    guard = sys.modules.get("integrations.ipfs_accelerate.release_guard")
    existing = getattr(guard, "checker", None)
    if existing is not None and Path(existing.__file__).resolve() == path:
        # In guarded pytest children the already loaded checker owns the audit
        # hook. Compare the functions actually consumed here with fresh code
        # objects compiled from these bytes; do not install another audit hook.
        import types
        expected = {item.co_name: item for item in compile(raw, str(path), "exec").co_consts
                    if isinstance(item, types.CodeType)}
        _current_need(all(getattr(existing, name).__code__ == expected[name]
            for name in ("mandatory_manifest", "source_bindings", "module_case_population")), "loaded_checker_changed")
        return existing
    _current_need(not os.environ.get("COMPLAINT_INTAKE_RELEASE_GUARD_DIR"), "checker_guard_context_unavailable")
    name = "_complaint_current_qualification_contract_" + hashlib.sha256(raw).hexdigest()
    specification = importlib.util.spec_from_file_location(name, path)
    _current_need(specification is not None and specification.loader is not None, "checker_unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    _current_need(Path(module.__file__).resolve() == path, "checker_origin")
    return module


def _current_native_source(module, root):
    """Allow installed first-party APIs only when candidate Native bytes agree."""
    actual = Path(module.__file__).resolve(strict=True)
    installed = Path(__file__).resolve().parents[2]
    origins = (root / "external/ipfs_accelerate_py", installed / "external/ipfs_accelerate_py")
    matched = next((origin for origin in origins if actual.is_relative_to(origin)), None)
    _current_need(matched is not None, "native_source_origin")
    expected = root / "external/ipfs_accelerate_py" / actual.relative_to(matched)
    _current_need(_current_file(actual, source=True) == _current_file(expected, source=True), "native_source_changed")


def _current_runtime_identity(root, checker, *, validation_environment=None, recorded_runtime=None):
    """Pin the interpreter, Native policy and approved distribution metadata.

    The distribution fingerprint describes installed metadata, not a claim
    that all third-party package files were executed or independently sealed.
    """
    import importlib.metadata
    import sys
    from .improvement_runner import _native_modules
    _native_modules(root)
    from ipfs_accelerate_py.agent_supervisor.validation import validation_runtime as runtime
    _current_native_source(runtime, root)
    # The checked Source helper retains approved distribution roots from an
    # immutable inherited Native launcher even in a raw-no-site consumer. Do
    # not rediscover a different environment from that child's sys.prefix.
    if recorded_runtime is None:
        # A host caller may supply only the actual trusted environment which
        # it is about to pass to the canonical Native executor. This optional
        # in-process argument is not a JSON/CLI source of execution authority.
        environment = (checker._validation_environment(root, root / ".qualification-readonly-context")
                       if validation_environment is None else validation_environment)
        _current_need(isinstance(environment, Mapping), "validation_environment_type")
        python = environment["IPFS_ACCELERATE_VALIDATION_PYTHON_EXECUTABLE"]
        profile = runtime.validation_python_profile(environment)
        mode = runtime._validation_python_launcher_mode(sealed=True, no_site=profile == "raw-no-site")
        policy = runtime._validation_python_launcher_policy_sha256(mode)
        _current_need(environment.get(runtime.VALIDATION_PYTHON_LAUNCHER_MODE_ENV) == mode
            and environment.get(runtime.VALIDATION_PYTHON_LAUNCHER_POLICY_SHA256_ENV) == policy, "validation_environment_policy")
        roots = sorted({part for part in environment["PYTHONPATH"].split(os.pathsep)
                        if Path(part).name in {"site-packages", "dist-packages"}})
        if validation_environment is None:
            # A directory's basename is only a distribution-root filter. Its
            # approval comes from Native's actual environment builder or the
            # exact immutable launcher recipe, independently of this filter.
            source = dict(os.environ)
            built = runtime.build_validation_environment(source)
            approved = {Path(part).resolve(strict=True) for part in built.get("PYTHONPATH", "").split(os.pathsep) if part}
            inherited = checker.native_memfd_approved_paths(source.get("PYTHON", ""), source,
                runtime=runtime, python=python, candidate_root=root)
            approved.update(inherited or ())
            _current_need(all(Path(entry) in approved for entry in roots), "runtime_package_root_unapproved")
    else:
        # Privileged external artifact consumers can reprove the *recorded*
        # environment explicitly. The public fixed-slot reader never selects
        # this mode or substitutes it for its current Native runtime context.
        _current_need(validation_environment is None and isinstance(recorded_runtime, dict), "recorded_runtime_type")
        python, profile = recorded_runtime["python"], recorded_runtime["native_profile"]
        _current_need(profile in {"default", "raw-no-site"}, "recorded_runtime_profile")
        mode = runtime._validation_python_launcher_mode(sealed=True, no_site=profile == "raw-no-site")
        policy = runtime._validation_python_launcher_policy_sha256(mode)
        roots = recorded_runtime["approved_package_roots"]
        _current_need(recorded_runtime["launcher_mode"] == mode
            and recorded_runtime["launcher_policy_sha256"] == policy, "recorded_runtime_policy")
    _current_need(isinstance(roots, list) and 0 < len(roots) <= 64 and roots == sorted(set(roots)), "approved_runtime_distribution_roots_missing")
    for entry in roots:
        _current_need(isinstance(entry, str) and Path(entry).is_absolute()
            and Path(entry).resolve(strict=True) == Path(entry)
            and Path(entry).name in {"site-packages", "dist-packages"}
            and not Path(entry).is_relative_to(root), "runtime_package_root")
        info = Path(entry).stat()
        _current_need(stat.S_ISDIR(info.st_mode) and info.st_uid in {0, os.getuid()}
            and not info.st_mode & 0o002, "runtime_package_root_custody")
        # Native's already-active known package roots may be writable by their
        # owner (ordinary user VENV installations). Reapplying the stricter
        # explicit-path admission check would reject genuine Native contexts.
    digest, details = runtime._validation_python_interpreter_identity(python)
    distributions, total = [], 0
    for distribution in importlib.metadata.distributions(path=roots):
        name, version = distribution.metadata.get("Name"), distribution.version
        _current_need(isinstance(name, str) and isinstance(version, str), "runtime_distribution_identity")
        metadata = (distribution.read_text("METADATA") or distribution.read_text("PKG-INFO") or "").encode()
        record = (distribution.read_text("RECORD") or "").encode()
        total += len(metadata) + len(record)
        _current_need(total <= 64 * 1024 * 1024 and len(distributions) < 4096, "runtime_metadata_bound")
        distributions.append((name, version, hashlib.sha256(metadata).hexdigest(), hashlib.sha256(record).hexdigest()))
    return {"python": str(Path(python).resolve()), "interpreter_sha256": digest, "interpreter_stat": details,
        "native_profile": profile, "launcher_mode": mode, "launcher_policy_sha256": policy,
        "python_version": list(sys.version_info[:3]), "approved_package_roots": roots,
        "distributions": [list(row) for row in sorted(distributions)],
        "distribution_scope": "approved_installed_distribution_metadata_and_RECORD; no_whole_third_party_runtime_reexecution_claim"}


def _current_source_identity(root, checker, *, validation_environment=None, recorded_runtime=None):
    """Bind current implementation bytes, report/spec, and deployed dirt too."""
    from .improvement_runner import _source_freeze
    from .improvement_plan import _digest
    manifest = checker.mandatory_manifest(root)
    _current_need(set(manifest) == {"application", "lifecycle", "replica"}
        and sum(map(len, manifest.values())) == 83, "mandatory_manifest_population")
    modules = [path for paths in manifest.values() for path in paths]
    _current_need(len(set(modules)) == len(modules), "duplicate_manifest_module")
    explicit = sorted(set(checker.BOUND_SOURCE_PATHS) | set(modules)
        | {checker.REPORT_RELATIVE, checker.SPEC_RELATIVE})
    frozen = _source_freeze(root, explicit)
    # Filesystem umasks may differ between equivalent proper clones. Actual
    # measurement snapshots retain their modes; cross-checkout equivalence
    # binds bytes and the committed Git modes from the actual source index.
    index = subprocess.run(["git", "--no-optional-locks", "ls-files", "-z", "--stage"],
        cwd=root, capture_output=True, check=True, timeout=20)
    _current_need(len(index.stdout) <= 16 * 1024 * 1024, "source_index_unbounded")
    modes = {}
    for entry in index.stdout.decode().split("\0"):
        if entry:
            metadata, relative = entry.split("\t", 1)
            mode, _blob, stage = metadata.split()
            _current_need(stage == "0", "unmerged_source")
            modes[relative] = mode
    files = {relative: {"sha256": row["sha256"], "git_mode": modes.get(relative)}
             for relative, row in frozen["files"].items()}
    _current_need(all(row["git_mode"] in {"100644", "100755"} for row in files.values()), "untracked_source")
    deployed = {"external/ipfs_accelerate_py", "external/ipfs_datasets_py", "external/ipfs_kit_py"}
    _current_need(deployed.issubset(frozen["dependencies"]), "dependency_population")
    dependencies = {}
    for relative, row in frozen["dependencies"].items():
        if relative in deployed:
            _current_need(row.get("head") == row.get("gitlink") and _COMMIT.fullmatch(str(row.get("head", ""))), "dependency_head")
            changed = subprocess.run(["git", "--no-optional-locks", "diff", "--ignore-submodules=all", "--binary", "HEAD"],
                cwd=root / relative, capture_output=True, check=True, timeout=30)
            _current_need(len(changed.stdout) <= 32 * 1024 * 1024, "dependency_diff_unbounded")
            nested_index = subprocess.run(["git", "--no-optional-locks", "ls-files", "--stage", "-z"],
                cwd=root / relative, capture_output=True, check=True, timeout=20)
            _current_need(len(nested_index.stdout) <= 16 * 1024 * 1024, "dependency_index_unbounded")
            opaque_nested = {}
            for entry in nested_index.stdout.decode().split("\0"):
                if entry:
                    metadata, name = entry.split("\t", 1)
                    mode, blob, stage = metadata.split()
                    _current_need(stage == "0", "dependency_unmerged_source")
                    if mode == "160000":
                        _current_need(not Path(name).is_absolute() and ".." not in Path(name).parts, "dependency_gitlink_path")
                        opaque_nested[name] = blob
            dependencies[relative] = {**row,
                "functional_tracked_diff_sha256": hashlib.sha256(changed.stdout).hexdigest(),
                "opaque_nested_gitlinks": opaque_nested,
                "nested_gitlink_scope": "committed_identity_only; no_physical_checkout_or_HEAD_equivalence_claim"}
        else:
            dependencies[relative] = {"gitlink": row["gitlink"], "scope": "opaque_gitlink_identity_only"}
    snapshot = {"files": files, "dependencies": dependencies}
    return {"snapshot": snapshot, "digest": _digest(snapshot), "manifest": manifest,
        "report_sha256": hashlib.sha256(_current_file(root / checker.REPORT_RELATIVE, source=True)).hexdigest(),
        "source_bindings": checker.source_bindings(root), "runtime_identity": _current_runtime_identity(root, checker,
            validation_environment=validation_environment, recorded_runtime=recorded_runtime)}


def _current_shard_plan(manifest, evidence_root):
    """One finite, deterministic plan; no test selectors, retries or pruning."""
    import shlex
    _current_need(isinstance(manifest, Mapping) and set(manifest) == {"application", "lifecycle", "replica"}
        and sum(map(len, manifest.values())) == 83, "plan_manifest_population")
    all_modules = [path for paths in manifest.values() for path in paths]
    _current_need(len(set(all_modules)) == len(all_modules) and all(isinstance(path, str)
        and path.startswith("tests/") and path.endswith(".py") and "::" not in path
        and ".." not in Path(path).parts for path in all_modules), "plan_module_identity")
    shards = []
    for group in ("application", "lifecycle", "replica"):
        paths = manifest[group]
        _current_need(paths == sorted(set(paths)) and paths, "manifest_order_or_empty")
        for offset in range(0, len(paths), _CURRENT_MODULES_PER_SHARD):
            selected = paths[offset:offset + _CURRENT_MODULES_PER_SHARD]
            ordinal = len(shards)
            owned = evidence_root / ("shard-%03d" % ordinal)
            command = "python -m pytest -q --run-llm --run-network --run-heavy --basetemp=" + shlex.quote(str(owned / "cases")) + " " + shlex.join(selected)
            shards.append({"id": "shard-%03d" % ordinal, "group": group, "modules": selected,
                "command": command, "budget_seconds": _CURRENT_BUDGET})
    _current_need(0 < len(shards) <= _CURRENT_MAX_SHARDS, "shard_bound")
    return {"schema": "complaint-release-current-shard-plan@1", "shards": shards,
        "max_shards": _CURRENT_MAX_SHARDS, "max_modules_per_shard": _CURRENT_MODULES_PER_SHARD,
        "per_shard_budget_seconds": _CURRENT_BUDGET, "serial": True, "retries": 0,
        "selection": "complete_modules_without_k_or_node_selectors"}


def _current_measurement_snapshot(value, current):
    _current_need(isinstance(value, dict) and isinstance(value.get("files"), dict), "measurement_snapshot")
    expected = current["snapshot"]["files"]
    # The fixed producer names all explicit outputs for every shard. There is
    # no smaller caller-selected measurement scope to accept from disk.
    _current_need(set(value["files"]) == set(expected) and all(
        isinstance(row, dict) and expected[name]["sha256"] == row.get("sha256")
        for name, row in value["files"].items()), "measurement_source_changed")
    _current_need(set(value.get("dependencies", {})) == set(current["snapshot"]["dependencies"]), "measurement_dependency_population")
    for relative, row in value.get("dependencies", {}).items():
        wanted = current["snapshot"]["dependencies"].get(relative)
        _current_need(wanted is not None and row.get("gitlink") == wanted.get("gitlink"), "measurement_dependency_changed")
        if "head" in wanted:
            _current_need(row.get("head") == wanted["head"], "measurement_dependency_head")


def _current_catalog(path, *, collection_only, required, current_root, execution_root, native, closures, hashes):
    import duckdb
    database = duckdb.connect(str(path), read_only=True, config={"threads": 1})
    try:
        nodes = database.execute("SELECT nodeid,seal,file_count,completion_authority FROM pytest_ast_seal").fetchall()
        files = database.execute("SELECT path,mtime_ns,size_bytes,content_hash FROM pytest_ast_file_hash").fetchall()
    finally:
        database.close()
    _current_need(0 < len(files) <= 20000 and len(nodes) <= 20000, "catalog_population_bound")
    _current_need(len({row[0] for row in files}) == len(files), "duplicate_catalog_file")
    observed = {}
    for name, mtime, size, digest in files:
        _current_need(isinstance(name, str) and Path(name).is_relative_to(execution_root)
            and type(mtime) is int and type(size) is int and size >= 0
            and isinstance(digest, str) and _HEX.fullmatch(digest), "catalog_file_contract")
        relative = Path(name).relative_to(execution_root)
        _current_need(not compiler._private_binding_path(relative.as_posix()), "private_catalog_source")
        current = current_root / relative
        if current not in hashes:
            raw = _current_file(current, maximum=32 * 1024 * 1024, source=True)
            hashes[current] = (hashlib.sha256(raw).hexdigest(), len(raw))
        _current_need(hashes[current] == (digest, size), "catalog_source_changed")
        observed[name] = digest
    needed = set()
    for node in required:
        module = node.split("::", 1)[0]
        if module not in closures:
            _current_need(False, "missing_rederived_closure")
        needed.update(str(execution_root / path.relative_to(current_root)) for path in closures[module])
    _current_need(set(observed) == needed, "catalog_closure_population")
    if collection_only:
        _current_need(not nodes, "collection_claimed_case_pass")
        return
    _current_need(len(nodes) == len(required) and len({row[0] for row in nodes}) == len(nodes)
        and {row[0] for row in nodes} == set(required), "run_catalog_case_population")
    for node, digest, count, authority in nodes:
        files_for_module = closures[node.split("::", 1)[0]]
        pairs = [(str(execution_root / item.relative_to(current_root)), hashes[item][0]) for item in files_for_module]
        _current_need(authority is False and type(count) is int and count == len(files_for_module)
            and digest == native.hash_of_hashes(pairs), "run_catalog_seal_mismatch")


def _current_native_phase(phases, result, guard, *, namespace, required, runtime_identity, current_root, execution_root):
    from ipfs_accelerate_py.agent_supervisor.validation import validation_runtime as runtime
    _current_need(phases.get("schema") == "complaint-pytest-observation@1"
        and phases.get("completion_authority") is False and phases.get("nodeids") == required
        and phases.get("exitstatus") == result.get("returncode") == 0
        and not result.get("timed_out") and not result.get("error"), "native_phase_failed")
    launcher = result.get("validation_python_launcher", {})
    mode = launcher.get("mode")
    _current_need(launcher.get("sealed") is True and mode in {
        runtime._validation_python_launcher_mode(sealed=True, no_site=False),
        runtime._validation_python_launcher_mode(sealed=True, no_site=True)}
        and all(isinstance(launcher.get(name), str) and _HEX.fullmatch(launcher[name])
            for name in ("content_sha256", "interpreter_sha256", "policy_sha256"))
        and launcher["policy_sha256"] == runtime._validation_python_launcher_policy_sha256(mode)
        and result.get("owned_process_cleanup") == {"quiescent": True, "canonical_native_delegate": True}, "native_execution_boundary")
    identity_raw = launcher.get("interpreter_stat")
    _current_need(isinstance(identity_raw, str) and len(identity_raw) <= 8192, "interpreter_identity")
    identity = _object(identity_raw.encode())
    executable = Path(str(identity.get("path", "")))
    _current_need(executable.is_absolute() and executable.resolve(strict=True) == executable, "interpreter_locator")
    digest, details = runtime._validation_python_interpreter_identity(executable)
    _current_need(digest == launcher["interpreter_sha256"] == runtime_identity["interpreter_sha256"]
        and details == identity_raw == runtime_identity["interpreter_stat"]
        and mode == runtime_identity["launcher_mode"]
        and launcher["policy_sha256"] == runtime_identity["launcher_policy_sha256"], "interpreter_or_runtime_policy_changed")
    _current_need(guard.get("schema") == "complaint-release-effect-guard@1" and guard.get("exitstatus") == 0
        and guard.get("network_process_dispatch_permitted") is False and guard.get("kernel_network_deny") is True
        and guard.get("provider_process_deny") is True
        and guard.get("guard_load_order") == "explicit_first_plugin_before_product_imports"
        and guard.get("private_namespace") == str(namespace), "effect_guard")
    imported = guard.get("imported_source_hashes")
    _current_need(isinstance(imported, dict) and 0 < len(imported) <= 20000, "runtime_import_population")
    total = 0
    for name, sha256 in imported.items():
        _current_need(isinstance(name, str) and Path(name).is_relative_to(execution_root)
            and isinstance(sha256, str) and _HEX.fullmatch(sha256), "runtime_import_identity")
        relative = Path(name).relative_to(execution_root)
        _current_need(not compiler._private_binding_path(relative.as_posix()), "private_runtime_import")
        raw = _current_file(current_root / relative, maximum=8 * 1024 * 1024, source=True)
        total += len(raw)
        _current_need(total <= 128 * 1024 * 1024, "runtime_import_bytes_bound")
        _current_need(hashlib.sha256(raw).hexdigest() == sha256, "runtime_import_source_changed")
    return launcher


def _current_reprove_global_collection(root, execution_root, evidence_root, row, current, checker, native, closures, hashes):
    _current_need(isinstance(row, dict) and set(row) == {"required_nodeids", "artifacts",
        "source_bindings_before", "source_bindings_after", "completion_authority"}
        and row["completion_authority"] is False
        and row["source_bindings_before"] == row["source_bindings_after"] == current, "global_collection_contract")
    required = row["required_nodeids"]
    _current_need(isinstance(required, list) and 0 < len(required) <= 20000
        and all(isinstance(node, str) and "::" in node for node in required)
        and len(set(required)) == len(required), "global_collection_identity")
    modules = [path for paths in current["manifest"].values() for path in paths]
    _population, reason = checker.module_case_population(modules, required)
    _current_need(not reason, "global_module_population")
    artifacts = {}
    for pin in row["artifacts"]:
        path, raw = _current_pin(pin, within=evidence_root, maximum=128 * 1024 * 1024)
        _current_need(path.parent == evidence_root / "global-collect" and path.name not in artifacts, "global_artifact_path")
        artifacts[path.name] = (path, raw)
    _current_need(set(artifacts) == {"collect.json", "collect.duckdb", "collect-native-result.json", "collect.guard.json"}, "global_artifact_population")
    phases, result, guard = (_object(artifacts[name][1]) for name in ("collect.json", "collect-native-result.json", "collect.guard.json"))
    _current_native_phase(phases, result, guard, namespace=evidence_root / "global-collect", required=required,
        runtime_identity=current["runtime_identity"], current_root=root, execution_root=execution_root)
    _current_need(phases.get("reports") == [], "global_collection_has_execution_reports")
    _current_catalog(artifacts["collect.duckdb"][0], collection_only=True, required=required,
        current_root=root, execution_root=execution_root, native=native, closures=closures, hashes=hashes)
    for pin in row["artifacts"]:
        _current_pin(pin, within=evidence_root, maximum=128 * 1024 * 1024)
    return required


def _current_reprove_shard(root, execution_root, evidence_root, descriptor, shard, current, checker, native, closures, hashes):
    from collections import Counter
    import xml.etree.ElementTree as ET
    path, raw = _current_pin(descriptor, within=evidence_root, maximum=32 * 1024 * 1024)
    measured = _object(raw)
    _current_need(measured.get("schema") == "complaint-owned-behavioral-measurement@1"
        and measured.get("reason") == "" and measured.get("source_unchanged") is True
        and measured.get("source_before") == measured.get("source_after")
        and measured.get("completion_authority") is False, "measurement_rejected")
    _current_measurement_snapshot(measured["source_before"], current)
    _current_need(measured.get("workspace_path") == str(execution_root), "execution_root_mismatch")
    run = Path(measured["run_path"])
    _current_need(path == run / "measurement.json" and run.is_relative_to(evidence_root / shard["id"] / "measurements"), "run_path_mismatch")
    observed = measured["observation_binding"]
    required = observed["required_nodeids"]
    _current_need(isinstance(required, list) and required and len(required) <= 20000
        and all(isinstance(node, str) and "::" in node for node in required)
        and len(set(required)) == len(required) and observed.get("command") == shard["command"]
        and observed.get("collected_count") == len(required) and observed.get("exit_status") == 0
        and observed.get("timed_out") is False and measured.get("required_nodeids") == required
        and measured.get("cases") == observed.get("cases") == [{"nodeid": node, "outcome": "passed"} for node in required], "case_contract")
    population, reason = checker.module_case_population(shard["modules"], required)
    _current_need(not reason, "module_population")
    artifacts = {}
    for row in measured["artifacts"]:
        item, data = _current_pin(row, within=evidence_root, maximum=128 * 1024 * 1024)
        _current_need(item.parent == run and item.name not in artifacts, "artifact_path_or_duplicate")
        artifacts[item.name] = (item, data)
    expected = {"junit.xml"} | {mode + ending for mode in ("collect", "run")
        for ending in (".json", ".duckdb", "-native-result.json", ".guard.json")}
    _current_need(set(artifacts) == expected, "artifact_population")
    results = measured.get("results")
    _current_need(isinstance(results, list) and [row.get("mode") for row in results] == ["collect", "run"], "execution_modes")
    executor = measured.get("trusted_executor", {})
    _current_need(executor.get("qualname") == "_owned_native_runner"
        and executor.get("canonical_native_identity") is False, "producer_delegate")
    for mode in ("collect", "run"):
        phases = _object(artifacts[mode + ".json"][1])
        result = _object(artifacts[mode + "-native-result.json"][1])
        guard = _object(artifacts[mode + ".guard.json"][1])
        launcher = _current_native_phase(phases, result, guard,
            namespace=evidence_root / shard["id"], required=required,
            runtime_identity=current["runtime_identity"], current_root=root, execution_root=execution_root)
        summary = next(item for item in results if item["mode"] == mode)
        _current_need(summary.get("returncode") == 0 and summary.get("timed_out") is False
            and summary.get("validation_python_launcher") == launcher, "measurement_result_mismatch")
        if mode == "collect":
            _current_need(phases.get("reports") == [], "collection_has_execution_reports")
        else:
            expected_reports = Counter((node, when, "passed") for node in required for when in ("setup", "call", "teardown"))
            reports = phases.get("reports")
            _current_need(isinstance(reports, list) and Counter((row["nodeid"], row["when"], row["outcome"]) for row in reports) == expected_reports, "required_phase_failed_skipped_or_duplicate")
        _current_catalog(artifacts[mode + ".duckdb"][0], collection_only=mode == "collect", required=required,
            current_root=root, execution_root=execution_root, native=native, closures=closures, hashes=hashes)
    junit = ET.fromstring(artifacts["junit.xml"][1])
    identities = []
    for case in junit.iter("testcase"):
        values = [item.get("value") for item in case.findall("properties/property") if item.get("name") == "complaint_nodeid"]
        _current_need(len(values) == 1 and not any(case.find(tag) is not None for tag in ("failure", "error", "skipped")), "junit_outcome")
        identities.extend(values)
    _current_need(len(identities) == len(required) and set(identities) == set(required), "junit_population")
    # Recheck all immutable artifact pins after SQLite/DuckDB/XML consumption.
    for row in measured["artifacts"]:
        _current_pin(row, within=evidence_root, maximum=128 * 1024 * 1024)
    _current_pin(descriptor, within=evidence_root, maximum=32 * 1024 * 1024)
    return {"required_nodeids": required, "cases": observed["cases"], "module_case_population": population,
        "measurement_record": descriptor, "artifact_bindings": measured["artifacts"], "completion_authority": False}


def _verify_current_release_qualification(root, descriptor, producer, *, phase,
                                          validation_environment=None, recorded_runtime=False):
    """Pure reproof, called only after a fixed privileged binding is read."""
    _current_need(phase in {"pre-admission", "post-completion"}, "phase")
    _current_need(type(recorded_runtime) is bool, "runtime_reproof_mode")
    path, raw = _current_pin(descriptor, maximum=64 * 1024 * 1024)
    qualification = _object(raw)
    evidence_root = _current_private(path.parent)
    _current_need(set(qualification) == {"schema", "execution_root", "execution_git", "source", "plan", "executions",
        "global_collection", "producer", "completion_authority", "provider_dispatched", "native_task_completion_claimed"}
        and qualification.get("schema") == _CURRENT_QUALIFICATION_SCHEMA
        and qualification.get("completion_authority") is False
        and qualification.get("provider_dispatched") is False
        and qualification.get("native_task_completion_claimed") is False
        and qualification.get("producer") == producer, "qualification_contract")
    _current_pin(producer, maximum=1024 * 1024, source=True)
    execution_root = Path(qualification["execution_root"])
    _current_need(execution_root.is_absolute() and execution_root.resolve(strict=True) == execution_root
        and not evidence_root.is_relative_to(root) and not evidence_root.is_relative_to(execution_root), "producer_location")
    _current_need(qualification.get("execution_git") == {
        "head": _git(execution_root, "rev-parse", "HEAD"),
        "tree": _git(execution_root, "rev-parse", "HEAD^{tree}")}, "execution_git_changed")
    checker = _current_checker(root)
    runtime_record = qualification.get("source", {}).get("runtime_identity") if recorded_runtime else None
    _current_need(not recorded_runtime or isinstance(runtime_record, dict), "recorded_runtime_missing")
    current = _current_source_identity(root, checker, validation_environment=validation_environment, recorded_runtime=runtime_record)
    _current_need(qualification.get("source") == current, "current_source_changed")
    plan = _current_shard_plan(current["manifest"], evidence_root)
    _current_need(qualification.get("plan") == plan, "shard_plan_changed")
    executions = qualification.get("executions")
    _current_need(isinstance(executions, list) and len(executions) == len(plan["shards"])
        and [row.get("id") for row in executions] == [row["id"] for row in plan["shards"]], "execution_population")
    from .improvement_runner import _native_modules
    _native_modules(root)
    from ipfs_accelerate_py.testing import pytest_ast_seal as native
    from .release_guard import _NativeImportEdgeCache
    _current_native_source(native, root)
    cache, closures, hashes = _NativeImportEdgeCache(native), {}, {}
    for paths in current["manifest"].values():
        for module in paths:
            closure = cache.closure(root, root / module)
            _current_need(closure is not None and closure, "native_closure_unavailable")
            closures[module] = closure
    globally_collected = _current_reprove_global_collection(root, execution_root, evidence_root,
        qualification.get("global_collection"), current, checker, native, closures, hashes)
    groups = {name: {"status": "VERIFIED", "reason": "", "manifest": paths, "required_nodeids": [], "cases": [],
        "module_case_population": {}, "measurements": [], "artifact_bindings": [],
        "source_digest": current["digest"], "completion_authority": False}
        for name, paths in current["manifest"].items()}
    all_nodes = set()
    for execution, shard in zip(executions, plan["shards"]):
        _current_need(set(execution) == {"id", "measurement"}, "execution_fields")
        result = _current_reprove_shard(root, execution_root, evidence_root, execution["measurement"], shard,
            current, checker, native, closures, hashes)
        _current_need(not all_nodes.intersection(result["required_nodeids"]), "duplicate_cross_shard_case")
        all_nodes.update(result["required_nodeids"])
        group = groups[shard["group"]]
        for field in ("required_nodeids", "cases", "artifact_bindings"):
            group[field].extend(result[field])
        group["module_case_population"].update(result["module_case_population"])
        group["measurements"].append(result["measurement_record"])
    _current_need(all_nodes and all_nodes == set(globally_collected)
        and all(set(group["module_case_population"]) == set(group["manifest"]) for group in groups.values()), "incomplete_union")
    _current_need(_current_source_identity(root, checker, validation_environment=validation_environment,
        recorded_runtime=runtime_record) == current, "source_changed_during_reproof")
    _current_pin(descriptor, maximum=64 * 1024 * 1024)
    _current_pin(producer, maximum=1024 * 1024, source=True)
    return {"schema": "complaint-release-current-semantic-coverage@1", "status": "VERIFIED", "issues": [],
        "groups": groups, "required_case_count": len(all_nodes), "completion_authority": False,
        "execution_mode": "fixed_host_qualification_reverification", "source_identity": current,
        "qualification": descriptor, "producer": producer,
        "producer_executions": {"shards": len(executions), "collect_commands": len(executions) + 1, "run_commands": len(executions),
            "actual_current_source_case_count": len(all_nodes), "per_shard_budget_seconds": _CURRENT_BUDGET,
            "execution_root": str(execution_root), "serial": True, "no_skips": True,
            "global_collection": qualification["global_collection"]},
        "verification_this_invocation": {"mandatory_case_execution_count": 0, "all_artifacts_reverified": True,
            "current_source_reverified": True, "canonical_native_closures_rederived": True,
            "runtime_context": "recorded_producer_runtime_reproof" if recorded_runtime else "current_canonical_native_validation_environment"},
        "historical_whole_runtime_reexecution_claimed": False}


def _read_current_release_qualification(repo_root, spec_path, campaign_state_dir, *, phase, validation_environment=None):
    """Read only the fixed existing host acceptance slot, never caller JSON.

    None means the fixed slot is absent and the caller must execute its direct
    measurement path. A configured bad/changed slot raises and cannot fall back.
    The host operator's private publication is the provenance trust boundary;
    artifacts alone are not cryptographic proof of past process execution.
    """
    root, state = Path(repo_root), Path(campaign_state_dir)
    directory = state / "host-acceptance"
    path = directory / _CURRENT_BINDING_NAME
    # Absence is a cheap capability probe. Do not import Native, parse a
    # specification or open any stores on the ordinary direct-measurement path.
    if not os.path.lexists(path):
        return None
    _directory(root)
    _current_private(state)
    _current_private(directory)
    raw = _current_file(path, maximum=65536)
    binding = _object(raw)
    _current_need(set(binding) == {"schema", "qualification", "producer"}
        and binding["schema"] == _CURRENT_BINDING_SCHEMA, "host_binding_contract")
    _current_need(Path(spec_path) == root / compiler.SPEC_RELATIVE, "specification_locator")
    spec = compiler.load_spec(spec_path)
    plan = compiler.build_improvement_work_plan(spec)
    _campaign_context(root, state, plan.plan_id)
    proof = _verify_current_release_qualification(root, binding["qualification"], binding["producer"],
        phase=phase, validation_environment=validation_environment)
    _current_need(_current_file(path, maximum=65536) == raw, "host_binding_changed")
    return {**proof, "host_binding": _pin(path, raw), "provenance_boundary": "privileged_fixed_host_operator_publication"}


def read_current_release_qualification(repo_root, spec_path, campaign_state_dir, *, phase, validation_environment=None):
    """Reprove the fixed host slot in the caller's actual Native context.

    validation_environment, when supplied by the trusted host adapter, must be
    the already approved environment passed to that canonical Native executor.
    This function exposes no evidence-file option or JSON capability loader.
    """
    try:
        return _read_current_release_qualification(repo_root, spec_path, campaign_state_dir,
            phase=phase, validation_environment=validation_environment)
    except ReleaseEvidenceError:
        raise
    except Exception as error:
        raise ReleaseEvidenceError("current_qualification_unavailable:" + type(error).__name__) from None
