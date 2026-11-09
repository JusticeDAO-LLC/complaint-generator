"""Compile reviewed improvement specifications into native supervisor plans.

Compilation checks intended work. It executes no validation commands, produces
no implementation evidence, and never changes an existing task board's status.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Mapping, Sequence

from .campaign import DEFAULT_ARTIFACTS, campaign_artifacts


SPEC_RELATIVE = "docs/task_boards/complaint_intake_improvement_spec.json"
PLAN_RELATIVE = "docs/task_boards/complaint_intake_formal_work_plan.json"
BOARD_RELATIVE = "docs/task_boards/complaint_intake_task_board.md"
_ACTOR_ID = "actor.complaint_improvement"
_PROVIDER = {
    "router": "ipfs_accelerate_py.llm_router",
    "provider": "grok_cli",
    "model": "grok-4.7",
    "allow_fallback": False,
}


def _text(value: Any, context: str, *, multiline: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a nonempty string")
    if not multiline and ("\n" in value or "\r" in value):
        raise ValueError(f"{context} must be one line")
    return value.strip()


def _strings(value: Any, context: str, *, empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not empty):
        raise ValueError(f"{context} must be a {'possibly empty ' if empty else 'nonempty '}list")
    result = [_text(item, context) for item in value]
    if len(set(result)) != len(result):
        raise ValueError(f"{context} contains duplicates")
    return result


def validate_spec(spec: Any) -> dict[str, Any]:
    """Validate metadata and the complete task DAG before loading native code."""

    if not isinstance(spec, dict):
        raise ValueError("spec must be an object")
    _text(spec.get("schema_version"), "schema_version")
    _text(spec.get("title"), "title")
    campaign_artifacts(spec)
    if spec.get("provider") != _PROVIDER or spec["provider"].get("allow_fallback") is not False:
        raise ValueError("provider must use grok-4.7 through llm_router with fallback disabled")
    if not isinstance(spec.get("execution_policy"), dict) or not spec["execution_policy"]:
        raise ValueError("execution_policy must be a nonempty object")
    if not isinstance(spec.get("findings", []), list):
        raise ValueError("findings must be a list")
    goals = spec.get("goals")
    tasks = spec.get("tasks")
    if not isinstance(goals, list) or not goals or not isinstance(tasks, list) or not tasks:
        raise ValueError("goals and tasks must be nonempty lists")
    identifiers: set[str] = set()
    subgoal_parents: dict[str, str] = {}
    goal_ids: set[str] = set()

    def identify(record: Any, context: str) -> str:
        if not isinstance(record, dict):
            raise ValueError(f"{context} must be an object")
        identifier = _text(record.get("id"), f"{context}.id")
        if identifier != record["id"] or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", identifier):
            raise ValueError(f"{context}.id is not a stable identifier")
        if identifier in identifiers:
            raise ValueError(f"duplicate identifier: {identifier}")
        identifiers.add(identifier)
        _text(record.get("title"), f"{identifier}.title")
        return identifier

    for goal in goals:
        goal_id = identify(goal, "goal")
        goal_ids.add(goal_id)
        children = goal.get("subgoals")
        if not isinstance(children, list) or not children:
            raise ValueError(f"{goal_id}.subgoals must be nonempty")
        for subgoal in children:
            subgoal_parents[identify(subgoal, "subgoal")] = goal_id
    task_ids: set[str] = set()
    dependencies: dict[str, list[str]] = {}
    populated_subgoals: set[str] = set()
    for task in tasks:
        task_id = identify(task, "task")
        if not task_id.startswith("CIMP-"):
            raise ValueError("task identifiers must begin CIMP-")
        task_ids.add(task_id)
        goal_id = _text(task.get("goal_id"), f"{task_id}.goal_id")
        subgoal_id = _text(task.get("subgoal_id"), f"{task_id}.subgoal_id")
        if goal_id not in goal_ids or subgoal_parents.get(subgoal_id) != goal_id:
            raise ValueError(f"{task_id} has an unknown or mismatched goal/subgoal")
        populated_subgoals.add(subgoal_id)
        if _text(task.get("priority"), f"{task_id}.priority") not in {"P0", "P1", "P2", "P3"}:
            raise ValueError(f"{task_id}.priority must be P0, P1, P2 or P3")
        for field in ("targets", "acceptance", "validation_commands"):
            _strings(task.get(field), f"{task_id}.{field}")
        submodules = _strings(task.get("submodules", []), f"{task_id}.submodules", empty=True)
        if len(submodules) > 16:
            raise ValueError(f"{task_id}.submodules exceeds the sixteen-path bound")
        for path in submodules:
            if (len(path) > 256 or path != path.strip() or path.startswith("-")
                    or re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", path) is None
                    or any(part in {".", "..", ".git"} for part in path.split("/"))):
                raise ValueError(f"{task_id}.submodules must contain safe repository-relative paths")
        dependencies[task_id] = _strings(task.get("depends_on"), f"{task_id}.depends_on", empty=True)
        _text(task.get("implementation_prompt"), f"{task_id}.implementation_prompt", multiline=True)
    if populated_subgoals != set(subgoal_parents):
        raise ValueError("every subgoal must contain at least one implementation task")
    for task_id, upstream in dependencies.items():
        if task_id in upstream or not set(upstream) <= task_ids:
            raise ValueError(f"{task_id} has an unknown or self dependency")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError(f"task dependency cycle at {task_id}")
        if task_id not in visited:
            visiting.add(task_id)
            for upstream in dependencies[task_id]:
                visit(upstream)
            visiting.remove(task_id)
            visited.add(task_id)

    for task_id in dependencies:
        visit(task_id)
    # A JSON round trip also rejects unexpected nonserializable metadata.
    return json.loads(json.dumps(spec, allow_nan=False))


def load_spec(path: Path | str) -> dict[str, Any]:
    return validate_spec(json.loads(Path(path).read_text(encoding="utf-8")))


def build_improvement_work_plan(spec: Mapping[str, Any]) -> Any:
    """Build canonical contracts with behavior-test evidence, without executing it."""

    spec = validate_spec(dict(spec))
    artifacts = campaign_artifacts(spec)
    from integrations.ipfs_datasets.loader import ensure_import_paths

    ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import (
        Actor, ActorKind, EvidenceRequirement, EvidenceRequirementKind,
        FormalWorkPlan, Goal, PlanTask, RefinementMode, Subgoal,
    )
    from ipfs_accelerate_py.agent_supervisor.proof.formal_logic_vocabulary import (
        LOGIC_VOCABULARY_VERSION, ReviewedPredicate, TermSort,
        atom, constant, subgoal_satisfied,
    )

    requirements = tuple(
        EvidenceRequirement(
            requirement_id=f"test.{task['id']}",
            kind=EvidenceRequirementKind.TEST,
            subject_ids=(task["id"], task["subgoal_id"], task["goal_id"]),
            fallback_check_ids=tuple(task["validation_commands"]),
            metadata={
                "acceptance": task["acceptance"],
                "validation_commands": task["validation_commands"],
                "required_evidence": "Behavioral assertions at the tested source revision; skipped or unexecuted checks do not satisfy this requirement.",
            },
        ) for task in spec["tasks"]
    )
    formulas = []
    goals = []
    subgoals = []
    for goal in spec["goals"]:
        formula = atom(ReviewedPredicate.GOAL_SATISFIED, constant(TermSort.GOAL, goal["id"]))
        formulas.append(formula)
        goals.append(Goal(
            goal_id=goal["id"], owner_actor_id=_ACTOR_ID,
            satisfaction_formula_id=formula.formula_id,
            evidence_requirement_ids=tuple(f"test.{task['id']}" for task in spec["tasks"] if task["goal_id"] == goal["id"]),
            source_ids=(artifacts.spec_relative,), metadata={"title": goal["title"]},
        ))
        for subgoal in goal["subgoals"]:
            formula = subgoal_satisfied(subgoal["id"])
            formulas.append(formula)
            subgoals.append(Subgoal(
                subgoal_id=subgoal["id"], goal_id=goal["id"], parent_id=goal["id"],
                refinement_mode=RefinementMode.SUFFICIENT,
                satisfaction_formula_id=formula.formula_id,
                evidence_requirement_ids=tuple(f"test.{task['id']}" for task in spec["tasks"] if task["subgoal_id"] == subgoal["id"]),
                metadata={"title": subgoal["title"]},
            ))
    tasks = tuple(PlanTask(
        task_id=task["id"], goal_id=task["goal_id"], subgoal_id=task["subgoal_id"],
        actor_ids=(_ACTOR_ID,), depends_on=tuple(task["depends_on"]),
        evidence_requirement_ids=(f"test.{task['id']}",),
        metadata={
            **{key: task[key] for key in ("title", "priority", "targets", "acceptance", "validation_commands", "implementation_prompt")},
            **({"submodules": task["submodules"]} if "submodules" in task else {}),
            "outputs": task["targets"], "provider": dict(_PROVIDER),
            "implementation_provider": "grok", "provider_role": "grok-only", "model": _PROVIDER["model"],
            "completion": "validation",
        },
    ) for task in spec["tasks"])
    return FormalWorkPlan(
        vocabulary_profile_id="supervisor-reviewed", vocabulary_version=LOGIC_VOCABULARY_VERSION,
        source_ids=("complaint-generator", artifacts.spec_relative), repository_tree_id="",
        trace_bound=1,
        actors=(Actor(actor_id=_ACTOR_ID, kind=ActorKind.AGENT, principal_id="complaint-generator",
                      capabilities=("implementation", "behavioral_validation"), metadata={"provider": dict(_PROVIDER)}),),
        goals=tuple(goals), subgoals=tuple(subgoals), tasks=tasks,
        events=(), fluents=(), preconditions=(), effects=(), norms=(), temporal_constraints=(),
        evidence_requirements=requirements, formulas=tuple(formulas),
        metadata={"title": spec["title"], "provider": dict(_PROVIDER),
                  "execution_policy": spec["execution_policy"],
                  "spec_sha256": hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                  "evidence_policy": "Ingestion and bounded consistency are not execution or task completion."},
    )


def _render_board(spec: Mapping[str, Any], plan_id: str) -> str:
    lines = [f"# {spec['title']}", "", f"<!-- plan_id: {plan_id} -->", "",
             "Implementation tasks begin pending. Completion requires behavioral validation evidence.", ""]
    for task in spec["tasks"]:
        lines.extend([
            f"## {task['id']} {task['title']}", "",
            "- Status: todo", "- Completion: validation", "- No-change completion: allowed",
            f"- Priority: {task['priority']}",
            f"- Goal: {task['goal_id']}", f"- Subgoal: {task['subgoal_id']}",
            f"- Depends on: {', '.join(task['depends_on'])}",
            f"- Outputs: {', '.join(task['targets'])}",
            f"- Submodules: {', '.join(task.get('submodules', []))}",
            f"- Validation: {'; '.join(task['validation_commands'])}",
            f"- Acceptance: {' '.join(task['acceptance'])}",
            "- Implementation provider: grok", "- Provider role: grok-only", "- Model: grok-4.7",
            "- Router: ipfs_accelerate_py.llm_router", "- Provider fallback: disabled",
            "- Runtime guidance: " + " ".join(task["implementation_prompt"].splitlines()), "",
            "Implementation instructions:", "",
            *("> " + line for line in task["implementation_prompt"].splitlines()), "",
        ])
    return "\n".join(lines)


_TASK_HEADER_PREFIX = "## CIMP-"
_CONTRACT_METADATA = (
    "goal", "subgoal", "submodules", "implementation provider", "provider role",
    "model", "router", "provider fallback",
)


def _parsed_projection(text: str, root: Path, *, board_relative: str = BOARD_RELATIVE) -> dict[str, Any]:
    """Parse with the production board path so semantic identities stay path-bound."""

    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import parse_task_text

    parsed = parse_task_text(text, path=root / board_relative, task_header_prefix=_TASK_HEADER_PREFIX)
    tasks: dict[str, Any] = {}
    for task in parsed:
        if task.task_id in tasks:
            raise ValueError("existing task board differs from this plan; preserve it and migrate explicitly")
        tasks[task.task_id] = task
    return tasks


def _projection_drift(existing: Any, expected: Any) -> list[str]:
    """Return contract fields that differ. Runtime status and notes are not contract."""

    drifted = []
    if (existing.canonical_task_cid != expected.canonical_task_cid
            or existing.canonical_task_key != expected.canonical_task_key):
        drifted.append("semantic identity")
    if tuple(existing.outputs) != tuple(expected.outputs):
        drifted.append("outputs")
    if existing.acceptance != expected.acceptance:
        drifted.append("acceptance")
    if tuple(existing.depends_on) != tuple(expected.depends_on):
        drifted.append("dependencies")
    if tuple(existing.validation) != tuple(expected.validation):
        drifted.append("validation")
    if existing.completion != expected.completion or existing.completion != "validation":
        drifted.append("completion")
    for key in _CONTRACT_METADATA:
        if existing.metadata.get(key, "") != expected.metadata.get(key, ""):
            drifted.append(key)
    return drifted


def _require_matching_projection(existing_text: str, spec: Mapping[str, Any], plan_id: str, root: Path) -> None:
    expected_text = _render_board(spec, plan_id)
    relative = campaign_artifacts(spec).board_relative
    existing, expected = (_parsed_projection(existing_text, root, board_relative=relative),
                          _parsed_projection(expected_text, root, board_relative=relative))
    planned = {task["id"] for task in spec["tasks"]}
    if set(existing) != planned or set(expected) != planned:
        raise ValueError("existing task board differs from this plan; preserve it and migrate explicitly")
    drifted = {task_id: _projection_drift(existing[task_id], expected[task_id]) for task_id in sorted(planned)}
    drifted = {task_id: fields for task_id, fields in drifted.items() if fields}
    if drifted:
        detail = "; ".join(f"{task_id}: {', '.join(fields)}" for task_id, fields in drifted.items())
        raise ValueError(
            "existing task board contract differs from this plan "
            f"({detail}); preserve it and migrate explicitly"
        )



def _require_emitted_projection(text: str, spec: Mapping[str, Any], root: Path) -> None:
    """Validate the actual native projection before publishing a new board."""
    tasks = _parsed_projection(text, root, board_relative=campaign_artifacts(spec).board_relative)
    if set(tasks) != {item["id"] for item in spec["tasks"]}:
        raise ValueError("rendered native projection differs from the specification")
    for item in spec["tasks"]:
        task = tasks[item["id"]]
        metadata = {
            "goal": item["goal_id"], "subgoal": item["subgoal_id"],
            "submodules": ", ".join(item.get("submodules", [])),
            "implementation provider": "grok", "provider role": "grok-only",
            "model": _PROVIDER["model"], "router": _PROVIDER["router"],
            "provider fallback": "disabled",
            "no-change completion": "allowed",
        }
        if (task.title != item["title"] or task.priority != item["priority"]
                or task.outputs != item["targets"] or task.depends_on != item["depends_on"]
                or task.validation != item["validation_commands"]
                or task.acceptance != " ".join(item["acceptance"])
                or task.completion != "validation"
                or any(task.metadata.get(key, "") != value for key, value in metadata.items())):
            raise ValueError(f"rendered native projection differs for {item['id']}")


def _atomic_create(path: Path, content: str) -> bool:
    """Publish complete bytes only if another creator has not won the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        return True
    finally:
        Path(temporary).unlink(missing_ok=True)


def _atomic_write(path: Path, content: str) -> None:
    """Publish changed bytes without replacing an unchanged protected file.

    Only a stable, canonical, owned document can take the no-write path.
    Other leaf types retain atomic replacement without opening their target.
    """
    path = Path(path).absolute()
    if path.parent.resolve(strict=False) != path.parent:
        raise ValueError("plan artifact parent traverses an alias")
    path.parent.mkdir(parents=True, exist_ok=True)
    expected = content.encode("utf-8")
    try:
        before = path.lstat()
    except FileNotFoundError:
        before = None
    if (before is not None and stat.S_ISREG(before.st_mode)
            and before.st_uid == os.getuid() and before.st_nlink == 1
            and stat.S_IMODE(before.st_mode) in {0o600, 0o640, 0o644, 0o660, 0o664}
            and before.st_size == len(expected)
            and path.resolve(strict=True) == path
            and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_NONBLOCK")):
        fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid",
                  "st_size", "st_mtime_ns", "st_ctime_ns")

        def identity(value):
            return tuple(getattr(value, field) for field in fields)

        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_NOATIME", 0))
        try:
            if identity(os.fstat(fd)) != identity(before):
                raise ValueError("plan artifact changed while opening")
            data = bytearray()
            while len(data) <= len(expected):
                chunk = os.read(fd, min(1024 * 1024, len(expected) + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if (identity(os.fstat(fd)) != identity(before) or identity(path.lstat()) != identity(before)
                    or path.resolve(strict=True) != path):
                raise ValueError("plan artifact changed while comparing")
            if data == expected:
                return
        finally:
            os.close(fd)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def generate(spec_path: Path | str, repo_root: Path | str) -> dict[str, Any]:
    """Write native artifacts and return an honest, non-execution ingestion receipt.

    Existing matching Markdown is left byte-for-byte intact, including unknown
    runtime fields and states. A changed specification requires explicit board
    migration rather than resetting potentially active tasks to todo.
    """

    spec_path = Path(spec_path).resolve()
    root = Path(repo_root).resolve()
    spec = load_spec(spec_path)
    artifacts = campaign_artifacts(spec)
    artifacts.validate_source(root, spec_path)
    plan = build_improvement_work_plan(spec)
    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import FormalWorkPlan
    from ipfs_accelerate_py.agent_supervisor.planning.formal_plan_validator import FormalPlanValidator

    document = {**plan.to_dict(), "plan_id": plan.plan_id}
    restored = FormalWorkPlan.from_dict(document)
    if restored.plan_id != plan.plan_id:
        raise ValueError("native plan round trip changed identity")
    validation = FormalPlanValidator().validate(restored)
    rendered = _render_board(spec, plan.plan_id)
    _require_emitted_projection(rendered, spec, root)
    plan_path, board_path = root / artifacts.plan_relative, root / artifacts.board_relative
    marker = f"<!-- plan_id: {plan.plan_id} -->"
    board_preserved = board_path.exists()
    if not board_preserved:
        # Hard-link publication is atomic and cannot replace a concurrent
        # creator's held/owned board. Validate that winner before writing plan.
        board_preserved = not _atomic_create(board_path, rendered)
    if board_preserved:
        existing = board_path.read_text(encoding="utf-8")
        headings = re.findall(r"^## (CIMP-[A-Za-z0-9_.:-]+)(?:\s|$)", existing, re.MULTILINE)
        if marker not in existing or len(headings) != len(set(headings)) or set(headings) != {task["id"] for task in spec["tasks"]}:
            raise ValueError("existing task board differs from this plan; preserve it and migrate explicitly")
        # Same plan marker and headings are not a contract. Compare the native
        # parse before any artifact write so a drifted active board is neither
        # rewritten nor given an ingestion receipt.
        _require_matching_projection(existing, spec, plan.plan_id, root)
    # Keep both existing board state and identical formal-plan identity intact;
    # Native crash fences observe inode/mode/timestamps as well as content.
    _atomic_write(plan_path, json.dumps(document, indent=2, sort_keys=True) + "\n")
    receipt = {
        "schema_version": "complaint-generator/improvement-plan-ingestion@1",
        "plan_id": plan.plan_id, "native_roundtrip": True, "native_contract_ingested": True,
        "admission_status": "native_contract_ingested_open_plan", "consistency_claimed": False,
        "task_count": len(plan.tasks), "goal_count": len(plan.goals), "subgoal_count": len(plan.subgoals),
        "provider": dict(_PROVIDER), "board_preserved": board_preserved,
        "execution_started": False, "tasks_completed_by_ingestion": 0,
        "validations_executed": [], "native_validation": validation.to_record(),
        "trace_scope": "Open, unexecuted implementation plan; no terminal runtime events or test evidence are asserted.",
        "scope": "Native contract ingestion and bounded consistency only; no task implementation, test execution, provider invocation or completion evidence.",
    }
    return {"spec_path": str(spec_path), "plan_path": str(plan_path), "board_path": str(board_path), "receipt": receipt}


EVIDENCE_SCHEMA = "complaint-generator/improvement-evidence@1"
READINESS_SCHEMA = "complaint-generator/improvement-readiness@1"
EVIDENCE_LANES = ("unit_fake", "local_node_integration", "optional_real_provider_smoke")
COMPLETING_LANE = "local_node_integration"
SEALED_ENVIRONMENT_POLICY = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin",
    "python": "/usr/bin/python3.12",
    "home_directory_prefix": "ipfs-accelerate-validation-home-",
    "xdg_cache_home": "$HOME/.cache",
    "xdg_config_home": "$HOME/.config",
    "xdg_data_home": "$HOME/.local/share",
    "xdg_state_home": "$HOME/.local/state",
}
_PASSING = "passed"
_SKIPPED_OUTCOMES = {"skipped", "xfailed"}
_FAILED_OUTCOMES = {"failed", "error", "xpassed"}
_MAX_BIND_FILES = 256


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def canonical_model_policy() -> dict[str, Any]:
    """Return the only model policy that behavioral completion may bind."""

    return {"router": _PROVIDER["router"], "provider": _PROVIDER["provider"],
            "model": _PROVIDER["model"], "allow_fallback": False}


def source_generation(spec: Mapping[str, Any]) -> str:
    """Identity of the exact specification bytes a campaign observation may bind."""

    spec = validate_spec(dict(spec))
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def campaign_observation_binding(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Bind a separate campaign to its plan, source generation, and historical intake paths.

    Compilation does not execute validation, start a provider, or rewrite the
    completed intake artifacts. Those paths stay a historical baseline.
    """

    spec = validate_spec(dict(spec))
    artifacts = campaign_artifacts(spec)
    plan = build_improvement_work_plan(spec)
    generation = plan.metadata["spec_sha256"]
    if generation != source_generation(spec):
        raise ValueError("campaign source generation differs from its specification")
    return {
        "plan_id": plan.plan_id,
        "source_generation": generation,
        "board_namespace": artifacts.board_namespace,
        "spec_relative": artifacts.spec_relative,
        "plan_relative": artifacts.plan_relative,
        "board_relative": artifacts.board_relative,
        "distinct_from_historical_intake": artifacts != DEFAULT_ARTIFACTS,
        "historical_baseline": {
            "spec_relative": SPEC_RELATIVE,
            "plan_relative": PLAN_RELATIVE,
            "board_relative": BOARD_RELATIVE,
            "immutable": True,
            "completion_authority": False,
        },
        "provider": canonical_model_policy(),
        "completion_authority": False,
    }


_PRIVATE_BINDING_ROOTS = frozenset({"data", "output", "statefiles", "exports", ".complaint_workspace", "secrets", "evidence", "uploads", "attachments", "private", "sessions"})


def _private_binding_path(relative: str) -> bool:
    path = Path(relative)
    return bool(path.parts and (path.parts[0] in _PRIVATE_BINDING_ROOTS or
                any(part.startswith(".env") or part.endswith((".key", ".pem")) for part in path.parts)))


def _safe_relative(root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        return None
    relative = Path(value)
    if _private_binding_path(value):
        return None
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in {"", ".", "./"}:
        return None
    root = root.resolve()
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return None
    candidate = (root / relative).resolve()
    try:
        resolved_relative = candidate.relative_to(root)
        if _private_binding_path(resolved_relative.as_posix()):
            return None
    except ValueError:
        return None
    return candidate


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bind_sources(repo_root: Path | str, relative_paths: Sequence[str]) -> dict[str, Any]:
    """Hash declared outputs. Missing and empty paths stay explicit and unbound."""

    root = Path(repo_root).resolve()
    files: dict[str, Any] = {}
    missing: list[str] = []
    empty: list[str] = []
    unbounded = False
    for raw in relative_paths:
        key = raw if isinstance(raw, str) else ""
        path = _safe_relative(root, raw)
        if path is None or not path.exists():
            missing.append(key or "<invalid>")
            files[key or "<invalid>"] = {"present": False, "sha256": "", "kind": "missing"}
            continue
        if path.is_file():
            size = path.stat().st_size
            if size <= 0:
                empty.append(key)
                files[key] = {"present": True, "sha256": "", "kind": "file", "empty": True}
            else:
                files[key] = {"present": True, "sha256": _hash_file(path), "kind": "file", "empty": False}
            continue
        if not path.is_dir():
            missing.append(key)
            files[key] = {"present": False, "sha256": "", "kind": "missing"}
            continue
        members: list[tuple[str, str]] = []
        count = 0
        unsafe = False
        for child in sorted(path.rglob("*")):
            if _safe_relative(root, child.relative_to(root).as_posix()) is None:
                unsafe = True
                break
            if not child.is_file():
                continue
            count += 1
            if count > _MAX_BIND_FILES:
                unbounded = True
                break
            if child.stat().st_size <= 0:
                continue
            members.append((child.relative_to(path).as_posix(), _hash_file(child)))
        if unsafe:
            missing.append(key)
            files[key] = {"present": False, "sha256": "", "kind": "unsafe_alias"}
            continue
        if unbounded:
            files[key] = {"present": True, "sha256": "", "kind": "directory", "unbounded": True}
            break
        if not members:
            empty.append(key)
            files[key] = {"present": True, "sha256": "", "kind": "directory", "empty": True}
        else:
            files[key] = {"present": True, "sha256": _digest(members), "kind": "directory", "empty": False,
                          "file_count": len(members)}
    body = {"files": files, "missing": missing, "empty": empty, "unbounded": unbounded}
    return {**body, "digest": "" if missing or empty or unbounded else _digest(files)}


def _case_rows(value: Any) -> tuple[list[dict[str, str]] | None, str]:
    if not isinstance(value, list):
        return None, "required_case_results_missing"
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            return None, "required_case_results_malformed"
        nodeid = item.get("nodeid")
        outcome = item.get("outcome")
        if not isinstance(nodeid, str) or not nodeid.strip() or len(nodeid) > 500 or any(c in nodeid for c in "\n\r"):
            return None, "required_test_identity_malformed"
        if not isinstance(outcome, str) or outcome not in {_PASSING, *_SKIPPED_OUTCOMES, *_FAILED_OUTCOMES}:
            return None, "required_case_outcome_malformed"
        if nodeid in seen:
            return None, "duplicate_required_test_identity"
        seen.add(nodeid)
        rows.append({"nodeid": nodeid, "outcome": outcome})
    return rows, ""


def _environment_mismatch(observed: Any) -> str:
    if not isinstance(observed, dict):
        return "environment_policy_missing"
    for key, expected in SEALED_ENVIRONMENT_POLICY.items():
        if observed.get(key) != expected:
            return "environment_policy_mismatch"
    home = observed.get("HOME")
    prefix = SEALED_ENVIRONMENT_POLICY["home_directory_prefix"]
    if not isinstance(home, str) or Path(home).name.startswith(prefix) is False or home != home.strip():
        return "environment_policy_mismatch"
    return ""


def _claimed_binding_stale(claimed: Any, fresh: Mapping[str, Any]) -> bool:
    if claimed is None:
        return False
    if not isinstance(claimed, dict):
        return True
    files = claimed.get("files", claimed)
    if not isinstance(files, dict):
        return True
    current = fresh.get("files", {})
    if set(files) != set(current):
        return True
    for key, record in files.items():
        expected = record.get("sha256") if isinstance(record, dict) else record
        if not isinstance(expected, str) or expected != current[key].get("sha256"):
            return True
    return False


def assess_behavioral_evidence(task: Mapping[str, Any], observation: Mapping[str, Any], *,
                               source_binding: Mapping[str, Any],
                               model_policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Assess measured admission evidence. Native callback alone completes a task.

    Only a current-source local-node integration run can complete a task.
    Unit fakes and optional real-provider smoke are recorded as different
    lanes and never become completion.
    """

    policy = canonical_model_policy() if model_policy is None else dict(model_policy)
    lane = observation.get("lane")
    command = observation.get("command") if isinstance(observation.get("command"), str) else ""
    cases, case_reason = _case_rows(observation.get("cases", []))
    artifacts = observation.get("artifacts", [])
    receipt: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "task_id": str(task.get("id") or ""),
        "lane": lane if isinstance(lane, str) else "",
        "admitted": False,
        "completion": False,
        "repairable": True,
        "reason": "",
        "command": command,
        "environment_policy": {
            "required": dict(SEALED_ENVIRONMENT_POLICY),
            "observed": observation.get("environment") if isinstance(observation.get("environment"), dict) else {},
        },
        "model_policy": policy,
        "source_binding": dict(source_binding),
        "exit_status": observation.get("exit_status"),
        "timed_out": bool(observation.get("timed_out")),
        "collected_count": observation.get("collected_count"),
        "required_cases": cases or [],
        "artifacts": artifacts if isinstance(artifacts, list) else [],
        "native_validation": {},
        "completion_authority": False,
        "enforcement": "admission_evidence_only_native_callback_completes",
    }

    def reject(reason: str) -> dict[str, Any]:
        receipt["reason"] = reason
        return receipt

    if lane not in EVIDENCE_LANES:
        return reject("unknown_evidence_lane")
    declared = task.get("validation_commands")
    if not isinstance(declared, list) or command not in declared:
        return reject("command_not_declared")
    try:
        from integrations.ipfs_datasets.loader import ensure_import_paths
        ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
        from ipfs_accelerate_py.agent_supervisor.validation.validation_commands import (
            classify_validation_command,
        )
        classified = classify_validation_command(command)
    except Exception as exc:
        receipt["native_validation"] = {"available": False, "error_type": type(exc).__name__}
        return reject("native_validation_classifier_unavailable")
    receipt["native_validation"] = {
        "available": True,
        "stage": classified.stage.label,
        "verdict_kind": classified.effective_verdict_kind.value,
        "command": classified.command,
    }
    release_companion = (task.get("id") == "CIMP-REL-03" and command == "python scripts/validate_complaint_intake.py --phase pre-admission"
        and isinstance(observation, _MeasuredEvidence) and observation.get("host_measurement", {}).get("behavioral_companion") == "tests/test_intake_release_gate.py")
    if classified.effective_verdict_kind.value != "test" and not release_companion:
        return reject("command_not_behavioral_test")
    if policy != canonical_model_policy():
        return reject("model_policy_rejected")
    if lane != "unit_fake" and not isinstance(observation, _MeasuredEvidence):
        mismatch = _environment_mismatch(observation.get("environment"))
        if mismatch:
            return reject(mismatch)
    if isinstance(observation, _MeasuredEvidence) and observation["host_measurement"].get("reason"):
        return reject(observation["host_measurement"]["reason"])
    if receipt["timed_out"] is True:
        return reject("subprocess_timeout")
    exit_status = observation.get("exit_status")
    if not isinstance(exit_status, int) or isinstance(exit_status, bool):
        return reject("missing_exit_status")
    if source_binding.get("unbounded") is True:
        return reject("source_binding_unbounded")
    if source_binding.get("missing") or source_binding.get("empty") or not source_binding.get("digest"):
        return reject("missing_output")
    if _claimed_binding_stale(observation.get("source_binding"), source_binding):
        return reject("stale_source_hash")
    if not isinstance(artifacts, list) or not artifacts:
        return reject("missing_output")
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("present") is not True or not artifact.get("sha256"):
            return reject("missing_output")
        claimed = artifact.get("claimed_sha256")
        if claimed is not None and claimed != artifact.get("sha256"):
            return reject("stale_source_hash")
    if cases is None:
        return reject(case_reason or "required_case_results_missing")
    collected = observation.get("collected_count")
    if not isinstance(collected, int) or isinstance(collected, bool) or collected <= 0 or not cases:
        return reject("zero_test_collection")
    if collected != len(cases):
        return reject("collection_identity_mismatch")
    required = observation.get("required_nodeids")
    if not isinstance(required, list) or not required:
        return reject("missing_required_test_identities")
    if any(not isinstance(item, str) or not item for item in required) or len(set(required)) != len(required):
        return reject("required_test_identity_malformed")
    observed_ids = [row["nodeid"] for row in cases]
    if any(item not in observed_ids for item in required):
        return reject("missing_required_test_identity")
    skipped = [row["nodeid"] for row in cases if row["outcome"] in _SKIPPED_OUTCOMES]
    if skipped:
        receipt["skipped_nodeids"] = skipped
        return reject("skipped_required_case")
    failed = [row["nodeid"] for row in cases if row["outcome"] in _FAILED_OUTCOMES]
    if failed or exit_status != 0:
        receipt["failed_nodeids"] = failed
        return reject("failed_assertion")
    if lane == "unit_fake":
        return reject("unit_fake_is_not_current_source_completion")
    if lane == "optional_real_provider_smoke":
        return reject("optional_real_provider_smoke_is_not_completion")
    measurement_reason = _host_evidence_reason(observation, task)
    if measurement_reason:
        return reject(measurement_reason)
    if task.get("id") == "CIMP-TUI-12":
        from .supervisor_terminal_acceptance import terminal_measurement_reason
        terminal_reason = terminal_measurement_reason(observation, task)
        if terminal_reason:
            return reject(terminal_reason)
    receipt["host_measurement"] = observation["host_measurement"]
    receipt["measurement_record"] = observation.measurement_record
    receipt["task_contract_digest"] = observation["host_measurement"]["task_contract_digest"]
    receipt["admitted"] = True
    receipt["completion"] = True
    receipt["repairable"] = False
    receipt["reason"] = "current_source_behavioral_evidence"
    return receipt


# This in-process capability is minted only after an owned host command has run.
# Serialized receipts remain observations and can never recreate this capability.
_MEASURED = object()
_HOST_MEASUREMENT_RECORDS = {}


def _pin_measurement(observation, path, sha256):
    import weakref
    key = id(observation)
    def release(reference):
        entry = _HOST_MEASUREMENT_RECORDS.get(key)
        if entry is not None and entry[0] is reference:
            _HOST_MEASUREMENT_RECORDS.pop(key, None)
    _HOST_MEASUREMENT_RECORDS[key] = (weakref.ref(observation, release), (str(path), str(sha256)))


def _measurement_record(observation):
    entry = _HOST_MEASUREMENT_RECORDS.get(id(observation))
    if entry is None or entry[0]() is not observation:
        return None
    return {"path": entry[1][0], "sha256": entry[1][1]}


class _MeasuredEvidence(dict):
    def __init__(self, value, *, capability=None):
        if capability is not _MEASURED:
            raise ValueError("host_measurement_required")
        super().__init__(value)
        self.capability = capability

    @property
    def measurement_record(self):
        # A returned dict is descriptive; changing it cannot rebind the host pin.
        return _measurement_record(self)

    def copy(self):
        copied = _MeasuredEvidence(self, capability=self.capability)
        pin = _measurement_record(self)
        if pin is not None:
            _pin_measurement(copied, pin["path"], pin["sha256"])
        return copied


def _host_evidence_reason(observation, task):
    if not isinstance(observation, _MeasuredEvidence) or observation.capability is not _MEASURED:
        return "host_measurement_required"
    try:
        record = _measurement_record(observation)
        if not isinstance(record, dict) or _hash_file(Path(record["path"])) != record["sha256"]:
            return "stale_measurement_record"
        measured = json.loads(Path(record["path"]).read_text())
        if measured != observation["host_measurement"]:
            return "measurement_record_mismatch"
        if measured.get("reason"):
            return measured["reason"]
        expected = measured["observation_binding"]
        if any(observation.get(key) != value for key, value in expected.items()):
            return "measured_case_identity_mismatch"
        from .improvement_runner import _source_freeze, _task_freeze_inputs, _task_outputs
        inputs = measured.get("freeze_inputs", measured["output_paths"])
        if (measured["output_paths"] != _task_outputs(task)
                or inputs != _task_freeze_inputs(task, context=observation["host_task_contract"].get("context"))):
            return "task_contract_changed"
        if _source_freeze(Path(measured["workspace_path"]), inputs) != measured["source_after"]:
            return "stale_source_hash"
        if observation["host_task_contract"]["task"] != dict(task):
            return "task_contract_changed"
        for artifact in measured["artifacts"]:
            if _hash_file(Path(artifact["path"])) != artifact["sha256"]:
                return "stale_evidence_artifact"
        if measured["reason"]:
            return measured["reason"]
        if not measured["source_unchanged"]:
            return "stale_source_hash"
        for path, digest in measured["imported_sources"].items():
            if _hash_file(Path(path)) != digest:
                return "stale_source_hash"
        if not measured["required_nodeids"] or measured["required_nodeids"] != [r["nodeid"] for r in measured["cases"]]:
            return "collection_identity_mismatch"
        if measured["task_contract_digest"] != _digest(observation["host_task_contract"]):
            return "task_contract_changed"
    except (KeyError, TypeError, ValueError, OSError):
        return "host_measurement_unavailable"
    return ""


# Explicit pytest plugin: the native validation environment filters ambient
# PYTEST_PLUGINS/ADDOPTS, so the host adds this module with `-p` to owned commands.
def pytest_addoption(parser):
    parser.addoption("--complaint-evidence-path", default=None)


def pytest_configure(config):
    path = config.getoption("--complaint-evidence-path")
    if path:
        config._complaint_evidence = {"nodeids": [], "reports": [], "path": path}


def pytest_collection_finish(session):
    state = getattr(session.config, "_complaint_evidence", None)
    if state is not None:
        state["nodeids"] = [item.nodeid for item in session.items]
        for item in session.items:
            item.user_properties.append(("complaint_nodeid", item.nodeid))


class _PhaseObserver:
    def __init__(self, state):
        self.state = state

    def pytest_runtest_logreport(self, report):
        self.state["reports"].append({"nodeid": report.nodeid, "when": report.when,
                                      "outcome": report.outcome})


def pytest_sessionstart(session):
    state = getattr(session.config, "_complaint_evidence", None)
    if state is not None:
        session.config.pluginmanager.register(_PhaseObserver(state), "complaint-evidence-phases")


def pytest_sessionfinish(session, exitstatus):
    state = getattr(session.config, "_complaint_evidence", None)
    if state is None:
        return
    path = Path(state["path"])
    value = {"schema": "complaint-pytest-observation@1", "nodeids": state["nodeids"],
             "reports": state["reports"], "exitstatus": int(exitstatus), "completion_authority": False}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
