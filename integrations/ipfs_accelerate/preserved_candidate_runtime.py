"""Materialize a Native-preserved candidate for fresh zero-paid validation.

This creates an ordinary Git worktree. It grants no lifecycle, task claim,
validation, callback, completion, or attempt authority.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def materialize(repo_root, spec_path, state_dir, record, daemon, candidate, *, root_base=None, receipt_id=None, receipt_sha256=None):
    """Run only while the caller retains its stopped recovery/checkout guards."""
    from .pending_claim_runtime import _canonical, _need, _read
    from .improvement_runner import _require_resource_capacity, recorded_worktree_root
    from .improvement_plan import load_spec
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.engine import run_command
    from ipfs_accelerate_py.agent_supervisor.merge.workspace_quarantine import mutation
    from ipfs_accelerate_py.agent_supervisor.git_environment import git_subprocess_environment

    root, state = _canonical(repo_root), _canonical(state_dir)
    workroot, _ = recorded_worktree_root(record, state)
    workroot = _canonical(workroot)
    required = {"commit", "rescue_ref", "baseline_ref", "source_root", "original_workspace",
                "original_branch", "task_id", "task_cid", "task_key", "attempt",
                "source_manifest_sha256", "preservation_event_id", "preservation_receipt_path"}
    _need(type(candidate) is dict and required.issubset(candidate), "preserved_candidate_shape")
    _need(all(type(candidate[key]) is str for key in required - {"attempt"}),
          "preserved_candidate_field_types")
    _need(candidate["source_root"] == str(root), "preserved_candidate_foreign_repository")
    for key in ("commit", "baseline_ref"):
        _need(re.fullmatch(r"[a-f0-9]{40}", candidate[key] or "") is not None,
              "preserved_candidate_commit_required")
    _need(re.fullmatch(r"[a-f0-9]{64}", candidate["source_manifest_sha256"] or "") is not None
          and type(candidate["attempt"]) is int and candidate["attempt"] > 0,
          "preserved_candidate_identity_required")
    original = Path(candidate["original_workspace"])
    _need(original.is_absolute() and original.resolve(strict=False) == original
          and original != workroot and original.is_relative_to(workroot),
          "preserved_candidate_foreign_workspace")
    encoded = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":"), allow_nan=False).encode()
    proof_key = hashlib.sha256(encoded({"task_cid": candidate["task_cid"], "attempt": candidate["attempt"]})).hexdigest()
    expected_proof = state / "pending-task-claim-recoveries" / ("candidate-" + proof_key + ".json")
    _need(Path(candidate["preservation_receipt_path"]) == expected_proof,
          "preserved_candidate_foreign_receipt")
    proof = _canonical(expected_proof)
    proof_raw = _read(proof, private=True)
    proof_value = json.loads(proof_raw)
    _need(type(proof_value) is dict, "preserved_candidate_receipt_changed")
    request = proof_value.get("request")
    _need(type(request) is dict and type(request.get("candidate")) is dict and type(request.get("base")) is dict,
          "preserved_candidate_receipt_scope_changed")
    source, base = request["candidate"], request["base"]
    _need(proof_value.get("schema") == "ordinary-preserved-pending-candidate-recovery@1"
          and proof_value.get("phase") == "released"
          and proof_value.get("preserved_candidate") == candidate
          and proof_value.get("receipt_id") == "sha256:" + hashlib.sha256(encoded({
              k: v for k, v in proof_value.items() if k != "receipt_id"})).hexdigest()
          and proof_value.get("receipt_id") == receipt_id
          and hashlib.sha256(proof_raw).hexdigest() == receipt_sha256
          and hashlib.sha256(encoded(source)).hexdigest()
              == candidate["source_manifest_sha256"]
          and all(proof_value.get(k) is False for k in ("completion_authority", "attempt_refunded",
              "provider_callback_settled", "new_attempt_authority")),
          "preserved_candidate_receipt_changed")
    _need(request.get("schema") == "ordinary-preserved-pending-candidate-recovery@1"
          and proof_value.get("operation_id") == "sha256:" + hashlib.sha256(encoded(request)).hexdigest()
          and base.get("repo_root") == str(root) and base.get("state_path") == str(daemon.state_path)
          and base.get("workspace") == str(original) and base.get("baseline_ref") == candidate["baseline_ref"]
          and all(base.get(key) == candidate[key] for key in ("task_id", "task_cid", "task_key", "attempt")),
          "preserved_candidate_receipt_scope_changed")
    tasks = [t for t in daemon._load_tasks() if t.task_id == candidate["task_id"]]
    _need(len(tasks) == 1, "preserved_candidate_current_task_required")
    identity = daemon._identity_for_task(tasks[0])
    _need(identity.canonical_task_cid == candidate["task_cid"]
          and identity.canonical_task_key == candidate["task_key"]
          and identity.board_namespace == base.get("board_namespace"),
          "preserved_candidate_task_changed")
    source_spec = load_spec(spec_path)
    target = [t for t in source_spec["tasks"] if t["id"] == candidate["task_id"]]
    _need(len(target) == 1, "preserved_candidate_current_contract_required")

    def git(where, *args, allowed=(0,), stdin=None):
        value = run_command(("git", "--no-replace-objects", "-c", "core.hooksPath=/dev/null",
                             "-c", "submodule.recurse=false", *args), cwd=where, timeout_seconds=120, stdin=stdin)
        _need(value.returncode in allowed, "preserved_candidate_git_" + args[0] + "_failed")
        return value

    def git_directory(where, option):
        value = Path(git(where, "rev-parse", option).stdout.strip())
        return _canonical(value if value.is_absolute() else where / value)

    commit, baseline = candidate["commit"], candidate["baseline_ref"]
    current_root = git(root, "rev-parse", "HEAD").stdout.strip()
    root_base = current_root if root_base is None else root_base
    _need(current_root == root_base, "preserved_candidate_host_baseline_changed")
    _need(base.get("repo_head") == root_base, "preserved_candidate_host_receipt_baseline_changed")
    ref = candidate["rescue_ref"].removeprefix("refs/heads/")
    _need(ref.startswith("rescue/") and git(root, "check-ref-format", "--branch", ref).ok,
          "preserved_candidate_rescue_ref_required")
    _need(git(root, "rev-parse", ref + "^{commit}").stdout.strip() == commit
          and git(root, "rev-parse", baseline + "^{commit}").stdout.strip() == baseline,
          "preserved_candidate_ref_changed")
    _need(git(root, "rev-list", "--parents", "-n", "1", commit).stdout.split() == [commit, baseline],
          "preserved_candidate_parent_changed")
    changed = set(git(root, "diff", "--name-only", baseline, commit).stdout.splitlines())
    _need(changed and changed.issubset(set(target[0]["targets"]))
          and all(not p.startswith("external/") and not Path(p).is_absolute()
                  and ".." not in Path(p).parts for p in changed),
          "preserved_candidate_output_scope_changed")
    _need(source.get("baseline_ref") == baseline and source.get("changed_paths") == sorted(changed)
          and type(source.get("files")) is dict and set(source["files"]) == set(target[0]["targets"]),
          "preserved_candidate_manifest_scope_changed")
    for relative, pin in source["files"].items():
        _need(type(pin) is dict, "preserved_candidate_manifest_blob_changed")
        _need(type(relative) is str and Path(relative).as_posix() == relative and not Path(relative).is_absolute()
              and not {"..", ".git"}.intersection(Path(relative).parts) and not relative.startswith("external/"),
              "preserved_candidate_manifest_path_unsafe")
        row = git(root, "ls-tree", commit, "--", relative).stdout.strip()
        match = re.fullmatch(r"(100644|100755) blob ([a-f0-9]{40})\t" + re.escape(relative), row)
        _need(match is not None and pin.get("mode") == match[1] and pin.get("blob") == match[2],
              "preserved_candidate_manifest_blob_changed")
        size = int(git(root, "cat-file", "-s", match[2]).stdout.strip())
        _need(0 <= size <= 8_000_000 and pin.get("bytes") == size, "preserved_candidate_manifest_size_changed")
        # Read immutable Git blobs as bytes; all checkout mutations stay in
        # Native's argv runner. Never round-trip binary source through text.
        blob = subprocess.run(["git", "--no-replace-objects", "cat-file", "blob", match[2]], cwd=root,
            env=git_subprocess_environment(None), capture_output=True, timeout=15, check=False)
        _need(blob.returncode == 0 and len(blob.stdout) == size
              and hashlib.sha256(blob.stdout).hexdigest() == pin.get("sha256"),
              "preserved_candidate_manifest_content_changed")
    if root_base != baseline:
        _need(git(root, "merge-base", "--is-ancestor", baseline, root_base, allowed=(0, 1)).returncode == 0,
              "preserved_candidate_host_baseline_diverged")
        _need(not git(root, "diff", "--name-only", baseline, root_base, "--", *sorted(target[0]["targets"])).stdout,
              "preserved_candidate_host_outputs_overlap")
    branch_leaf = candidate["original_branch"].removeprefix("refs/heads/").removeprefix("implementation/")
    _need(re.fullmatch(r"[a-z0-9][a-z0-9._-]*", branch_leaf or "") is not None,
          "preserved_candidate_original_branch_unsafe")
    branch = "rescue/worktree/" + branch_leaf + "-preserved-" + commit[:12] + "-onto-" + root_base[:12]
    path = workroot / ("preserved_" + re.sub(r"[^a-z0-9_]", "_", candidate["task_id"].lower()) + "_" + commit[:12] + "_" + root_base[:12])
    _need(path.resolve(strict=False) == path and path != original,
          "preserved_candidate_materialization_aliased")
    lifecycle_attempt = daemon._worktree_lifecycle_attempt_for_identity(
        task_id=candidate["task_id"], canonical_task_cid=candidate["task_cid"],
        portal_attempt=candidate["attempt"])
    index = daemon.worktree_lifecycle.task_index_path_for(canonical_task_cid=candidate["task_cid"],
        task_id=candidate["task_id"], attempt=lifecycle_attempt)
    _need(not os.path.lexists(index) and daemon.worktree_lifecycle.load_workspace(path) is None,
          "preserved_candidate_terminal_custody_not_retired")
    _require_resource_capacity(root, state, workroot, os.environ, stage="preserved_candidate_materialization")
    with mutation(root, path):
        _need(not os.path.lexists(index) and daemon.worktree_lifecycle.load_workspace(path) is None,
              "preserved_candidate_terminal_custody_not_retired")
        registered = git(root, "worktree", "list", "--porcelain", "-z").stdout.split("\0")
        if os.path.lexists(path):
            _need(_canonical(path) == path and path.stat().st_uid == os.getuid()
                  and ("worktree " + str(path)) in registered,
                  "preserved_candidate_unowned_existing_workspace")
        else:
            present = git(root, "show-ref", "--verify", "--quiet", "refs/heads/" + branch, allowed=(0, 1))
            if present.returncode == 0:
                git(root, "worktree", "add", str(path), branch)
            else:
                git(root, "worktree", "add", "--no-track", "-b", branch, str(path), commit if root_base == baseline else root_base)
        _need(git(path, "branch", "--show-current").stdout.strip() == branch,
              "preserved_candidate_materialization_changed")
        common = git_directory(root, "--git-common-dir")
        directory = git_directory(path, "--git-dir")
        _need(git_directory(path, "--git-common-dir") == common
              and directory.parent == common / "worktrees"
              and git(path, "rev-parse", "--show-toplevel").stdout.strip() == str(path)
              and _read(directory / "gitdir").decode().strip() == str(path / ".git"),
              "preserved_candidate_foreign_worktree_metadata")
        materialized_commit = git(path, "rev-parse", "HEAD").stdout.strip()
        if root_base != baseline and materialized_commit == root_base:
            dirty = set(git(path, "diff", "HEAD", "--name-only").stdout.splitlines())
            dirty.update(git(path, "diff", "--cached", "--name-only").stdout.splitlines())
            dirty.update(git(path, "ls-files", "--others", "--exclude-standard").stdout.splitlines())
            _need(dirty.issubset(changed), "preserved_candidate_transplant_has_foreign_edits")
            for relative in dirty:
                destination = path / relative
                _need(destination.is_file() and not destination.is_symlink(), "preserved_candidate_transplant_unsafe_file")
                observed_blob = git(path, "hash-object", "--", str(destination)).stdout.strip()
                expected_blob = git(root, "rev-parse", commit + ":" + relative).stdout.strip()
                base_blob = git(root, "rev-parse", "--verify", root_base + ":" + relative, allowed=(0, 128))
                _need(observed_blob in {expected_blob, base_blob.stdout.strip() if base_blob.returncode == 0 else ""},
                      "preserved_candidate_transplant_file_changed")
                staged = git(path, "ls-files", "--stage", "--", relative).stdout.strip()
                if staged:
                    metadata, _ = staged.split("\t", 1)
                    mode, indexed_blob, stage = metadata.split()
                    _need(stage == "0" and mode in {"100644", "100755"}
                          and indexed_blob in {expected_blob, base_blob.stdout.strip() if base_blob.returncode == 0 else ""},
                          "preserved_candidate_transplant_index_changed")
            git(path, "checkout", commit, "--", *sorted(changed))
            git(path, "-c", "user.name=Agent Supervisor", "-c", "user.email=agent-supervisor@localhost",
                "commit", "-m", "Revalidate preserved " + candidate["task_id"] + " on current source")
            materialized_commit = git(path, "rev-parse", "HEAD").stdout.strip()
        _need(git(root, "rev-list", "--parents", "-n", "1", materialized_commit).stdout.split()
                  == [materialized_commit, root_base]
              and set(git(root, "diff", "--name-only", root_base, materialized_commit).stdout.splitlines()) == changed,
              "preserved_candidate_materialization_commit_changed")
        for relative in changed:
            _need(git(root, "rev-parse", materialized_commit + ":" + relative).stdout.strip()
                  == git(root, "rev-parse", commit + ":" + relative).stdout.strip(),
                  "preserved_candidate_transplanted_output_changed")
        _need(not git(path, "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=all").stdout,
              "preserved_candidate_materialization_dirty")
        dependencies = {}
        for relative in daemon.worktree_submodule_paths:
            relative_path = Path(relative)
            _need(not relative_path.is_absolute() and ".." not in relative_path.parts,
                  "preserved_candidate_dependency_path_unsafe")
            row = git(root, "ls-tree", materialized_commit, "--", relative).stdout.strip()
            match = re.fullmatch(r"160000 commit ([a-f0-9]{40})\t" + re.escape(relative), row)
            _need(match is not None, "preserved_candidate_dependency_pin_required")
            pin = match[1]
            source, destination = _canonical(root / relative), path / relative
            _need(destination.resolve(strict=False) == destination,
                  "preserved_candidate_dependency_aliased")
            _need(git(source, "rev-parse", "HEAD").stdout.strip() == pin,
                  "preserved_candidate_dependency_source_changed")
            _need(not git(source, "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=all").stdout,
                  "preserved_candidate_dependency_source_dirty")
            if not os.path.lexists(destination / ".git"):
                _need(not os.path.lexists(destination) or destination.is_dir() and not any(destination.iterdir()),
                      "preserved_candidate_dependency_unowned")
                git(path, "clone", "--shared", "--no-checkout", "--no-recurse-submodules", str(source), str(destination))
            _need(_canonical(destination) == destination
                  and (destination / ".git").is_dir()
                  and _canonical(destination / ".git").stat().st_uid == os.getuid()
                  and git_directory(destination, "--git-common-dir") == destination / ".git"
                  and git(destination, "rev-parse", "--show-toplevel").stdout.strip() == str(destination)
                  and git(destination, "rev-parse", "HEAD").stdout.strip() == pin,
                  "preserved_candidate_dependency_checkout_changed")
            index_path = Path(git(destination, "rev-parse", "--git-path", "index").stdout.strip())
            if not index_path.is_absolute():
                index_path = destination / index_path
            observed_origin = git(destination, "remote", "get-url", "origin").stdout.strip()
            origin = git(source, "remote", "get-url", "origin").stdout.strip()
            _need(observed_origin in {str(source), origin}, "preserved_candidate_dependency_origin_changed")
            if not index_path.exists():
                _need(all(entry.name == ".git" for entry in destination.iterdir())
                      and observed_origin == str(source),
                      "preserved_candidate_incomplete_clone_changed")
            else:
                _need(not git(destination, "status", "--porcelain", "--untracked-files=all").stdout,
                      "preserved_candidate_dependency_checkout_changed")
            if observed_origin == str(source):
                # A crash after sparse init can leave an index with package
                # directories still skipped. Inspect present skipped files
                # before expanding; status alone can hide their local edits.
                entries = {}
                for row in git(destination, "ls-files", "--stage", "-z").stdout.split("\0"):
                    if row:
                        metadata, name = row.split("\t", 1); mode, blob, stage = metadata.split()
                        _need(stage == "0", "preserved_candidate_dependency_index_changed")
                        entries[name] = (mode, blob)
                hidden = []
                for row in git(destination, "ls-files", "-t", "-z").stdout.split("\0"):
                    if not row.startswith("S "): continue
                    name = row[2:]; target_path = destination / name
                    if not os.path.lexists(target_path): continue
                    mode, blob = entries[name]
                    if mode == "120000" and target_path.is_symlink():
                        link = os.fsencode(os.readlink(target_path))
                        _need(hashlib.sha1(b"blob " + str(len(link)).encode() + b"\0" + link).hexdigest() == blob,
                              "preserved_candidate_skipped_dependency_file_changed")
                    else:
                        _need(mode in {"100644", "100755"} and target_path.is_file() and not target_path.is_symlink()
                              and target_path.resolve() == target_path and "\n" not in name,
                              "preserved_candidate_skipped_dependency_file_changed")
                        hidden.append(name)
                if hidden:
                    hashes = git(destination, "hash-object", "--no-filters", "--stdin-paths",
                                 stdin="\n".join(hidden) + "\n").stdout.splitlines()
                    _need(hashes == [entries[name][1] for name in hidden],
                          "preserved_candidate_skipped_dependency_file_changed")
                git(destination, "sparse-checkout", "init", "--no-cone")
                # Runtime files are complete; archived documentation is not needed.
                git(destination, "sparse-checkout", "set", "--no-cone", "/*", "!/docs/")
                git(destination, "checkout", "--detach", pin)
            _need(not os.path.lexists(destination / "docs") and all(
                not row.startswith("S ") or row[2:].startswith("docs/")
                for row in git(destination, "ls-files", "-t", "-z").stdout.split("\0")),
                "preserved_candidate_dependency_runtime_incomplete")
            git(destination, "remote", "set-url", "origin", origin)
            _need(_canonical(destination) == destination
                  and git(destination, "rev-parse", "--show-toplevel").stdout.strip() == str(destination)
                  and git(destination, "rev-parse", "HEAD").stdout.strip() == pin
                  and not git(destination, "status", "--porcelain", "--untracked-files=all").stdout,
                  "preserved_candidate_dependency_checkout_changed")
            dependencies[relative] = pin
        _need(not git(path, "status", "--porcelain", "--untracked-files=all").stdout,
              "preserved_candidate_materialization_dirty")
        _need(git(root, "rev-parse", "HEAD").stdout.strip() == root_base
              and _read(proof, private=True) == proof_raw,
              "preserved_candidate_custody_changed_during_materialization")
        _need(not os.path.lexists(index) and daemon.worktree_lifecycle.load_workspace(path) is None,
              "preserved_candidate_terminal_custody_not_retired")
    return {"schema": "complaint-preserved-candidate-materialization@1", "worktree_path": str(path),
            "branch": branch, "commit": materialized_commit, "baseline_ref": root_base,
            "preserved_commit": commit, "preserved_baseline_ref": baseline,
            "dependencies": dependencies, "preservation_event_id": candidate["preservation_event_id"],
            "preservation_receipt_sha256": hashlib.sha256(_read(proof, private=True)).hexdigest(),
            "task_id": candidate["task_id"], "task_cid": candidate["task_cid"],
            "native_admission_claimed": False, "completion_authority": False,
            "attempt_consumed": False, "provider_dispatched": False}
