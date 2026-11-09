"""Formal work plan for the complaint-generator alignment program.

The document uses the ipfs_accelerate_py agent-supervisor contracts
(formal-work-plan@1): goals, subgoals, and tasks, with satisfaction formulas
taken from the reviewed logic vocabulary. Free-form titles live in metadata.

Runtime status stays on the execution board. Putting status into this plan
would change its content identity on every claim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


PLAN_RELATIVE = "docs/task_boards/complaint_alignment_formal_work_plan.json"
BOARD_RELATIVE = "docs/task_boards/complaint_alignment_execution_board.json"
STATE_RELATIVE = ".complaint_workspace/supervisor/alignment_execution_state.json"

_ACTOR_ID = "actor.watchdog"
_OPERATOR_ID = "actor.operator"


def _task(task_id: str, title: str, *, depends_on: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"task_id": task_id, "title": title, "depends_on": depends_on}


def _subgoal(
    subgoal_id: str,
    title: str,
    tasks: tuple[dict[str, Any], ...],
    *,
    depends_on: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "subgoal_id": subgoal_id,
        "title": title,
        "depends_on": depends_on,
        "tasks": tasks,
    }


def _goal(
    goal_id: str,
    title: str,
    domain: str,
    subgoals: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    return {
        "goal_id": goal_id,
        "title": title,
        "domain": domain,
        "subgoals": subgoals,
    }


# Machine-checkable alignment work. Publishing the connector on a public
# address stays with the operator and is recorded on the human actor, not as
# a task this board has to close.
ALIGNMENT_GOALS: tuple[dict[str, Any], ...] = (
    _goal(
        "goal.mike_connector",
        "Mike registers the complaint connector through the current MCP handshake.",
        "mike",
        (
            _subgoal(
                "subgoal.mike_handshake",
                "The Streamable HTTP handshake echoes a supported protocol version and lists the four connector tools.",
                (
                    _task(
                        "task.mike_protocol_versions",
                        "Negotiate MCP protocol versions 2024-11-05, 2025-03-26, and 2025-06-18.",
                    ),
                    _task(
                        "task.mike_connector_tools",
                        "Publish the four complaint connector tool names.",
                        depends_on=("task.mike_protocol_versions",),
                    ),
                    _task(
                        "task.mike_http_route_gate",
                        "Serve one stateless JSON-RPC POST with an optional bearer gate, off the supervisor job path.",
                        depends_on=("task.mike_connector_tools",),
                    ),
                ),
            ),
            _subgoal(
                "subgoal.mike_stamp",
                "The Mike monkey patch remains a compatibility stamp for the connector.",
                (
                    _task(
                        "task.mike_compatibility_stamp",
                        "Keep mike-llm-router-patch-v1 as a compatibility-only connector stamp.",
                        depends_on=("task.mike_http_route_gate",),
                    ),
                    _task(
                        "task.mike_registration_text",
                        "Tell the operator that Mike needs a public https connector URL and the same bearer.",
                        depends_on=("task.mike_compatibility_stamp",),
                    ),
                ),
                depends_on=("subgoal.mike_handshake",),
            ),
        ),
    ),
    _goal(
        "goal.datasets_modules",
        "Multimedia, knowledge graphs, legal datasets, and logic stay behind the datasets adapters.",
        "ipfs_datasets",
        (
            _subgoal(
                "subgoal.datasets_multimedia",
                "Attachment text goes through the multimedia adapter.",
                (
                    _task(
                        "task.multimedia_attachment_adapter",
                        "Route attachment text through processors.multimedia.attachment_text_extractor.",
                    ),
                ),
            ),
            _subgoal(
                "subgoal.datasets_graphs",
                "Graph snapshots use the knowledge-graph client.",
                (
                    _task(
                        "task.graph_client_persist",
                        "Persist graph snapshots through knowledge_graphs.Client.",
                    ),
                ),
            ),
            _subgoal(
                "subgoal.datasets_legal",
                "Legal dataset symbols load through the adapter.",
                (
                    _task(
                        "task.legal_symbol_loader",
                        "Load legal symbols lazily through load_legal_symbol.",
                    ),
                    _task(
                        "task.operator_scripts_use_adapter",
                        "Keep operator scripts off direct processors.legal_data imports.",
                        depends_on=("task.legal_symbol_loader",),
                    ),
                ),
            ),
            _subgoal(
                "subgoal.datasets_logic",
                "Logic checks use the logic adapter and leave theorem export local.",
                (
                    _task(
                        "task.logic_adapter_paths",
                        "Select logic.fol, logic.deontic, and the local theorem exporter.",
                    ),
                ),
            ),
        ),
    ),
    _goal(
        "goal.kit_storage",
        "ipfs_kit_py owns storage only when the kit gate is enabled.",
        "ipfs_kit",
        (
            _subgoal(
                "subgoal.kit_gate",
                "The default storage path stays on the datasets router and the local cache.",
                (
                    _task(
                        "task.kit_gate_default_off",
                        "Enable IPFSSimpleAPI only when COMPLAINT_GENERATOR_ENABLE_IPFS_KIT is set.",
                    ),
                    _task(
                        "task.storage_fallback_order",
                        "Store bytes through an injected backend, then kit, then the datasets router, then the local cache.",
                        depends_on=("task.kit_gate_default_off",),
                    ),
                ),
            ),
        ),
    ),
    _goal(
        "goal.inference_routers",
        "Accelerate llm, embedding, and multimodal routers own inference.",
        "inference",
        (
            _subgoal(
                "subgoal.routers",
                "The complaint facade loads the three accelerate routers.",
                (
                    _task(
                        "task.llm_router_facade",
                        "Load generate_text from the accelerate llm router.",
                    ),
                    _task(
                        "task.embedding_router_facade",
                        "Load embedding calls from the accelerate embeddings router.",
                        depends_on=("task.llm_router_facade",),
                    ),
                    _task(
                        "task.multimodal_router_facade",
                        "Load multimodal calls from the accelerate multimodal router.",
                        depends_on=("task.embedding_router_facade",),
                    ),
                ),
            ),
        ),
    ),
    _goal(
        "goal.supervisor_autonomy",
        "Supervisor jobs stay off the request path, and the watchdog can finish this board.",
        "agent_supervisor",
        (
            _subgoal(
                "subgoal.supervisor_jobs",
                "Evidence, draft repair, and graph refresh run as local jobs.",
                (
                    _task(
                        "task.supervisor_jobs_off_request_path",
                        "Keep the three supervisor jobs out of the HTTP route.",
                    ),
                    _task(
                        "task.supervisor_cli_has_three_operations",
                        "Expose the three jobs through the off-request-path CLI.",
                        depends_on=("task.supervisor_jobs_off_request_path",),
                    ),
                ),
            ),
            _subgoal(
                "subgoal.watchdog_repair",
                "The watchdog repairs a stalled or blocked board and advances ready tasks.",
                (
                    _task(
                        "task.watchdog_repairs_board",
                        "Repair stalled claims, dead owners, and dependency blocks on the execution board.",
                        depends_on=("task.supervisor_cli_has_three_operations",),
                    ),
                    _task(
                        "task.watchdog_cli_off_control_plane",
                        "Run the watchdog loop without constructing a control-plane request.",
                        depends_on=("task.watchdog_repairs_board",),
                    ),
                ),
                depends_on=("subgoal.supervisor_jobs",),
            ),
        ),
    ),
)


def alignment_task_ids() -> tuple[str, ...]:
    """Return every plan task id in declaration order."""

    identifiers: list[str] = []
    for goal in ALIGNMENT_GOALS:
        for subgoal in goal["subgoals"]:
            for task in subgoal["tasks"]:
                identifiers.append(task["task_id"])
    return tuple(identifiers)


def build_alignment_work_plan() -> Any:
    """Construct a FormalWorkPlan whose content identity the supervisor can reload."""

    from integrations.ipfs_datasets.loader import ensure_import_paths

    ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import (
        Actor,
        ActorKind,
        EvidenceRequirement,
        EvidenceRequirementKind,
        FormalWorkPlan,
        Goal,
        PlanTask,
        RefinementMode,
        Subgoal,
    )
    from ipfs_accelerate_py.agent_supervisor.proof.formal_logic_vocabulary import (
        LOGIC_VOCABULARY_VERSION,
        ReviewedPredicate,
        TermSort,
        atom,
        constant,
        subgoal_satisfied,
    )

    actors = (
        Actor(
            actor_id=_ACTOR_ID,
            kind=ActorKind.SERVICE,
            principal_id="complaint-generator",
            capabilities=("board_repair", "local_verification"),
            metadata={"title": "Complaint alignment watchdog"},
        ),
        Actor(
            actor_id=_OPERATOR_ID,
            kind=ActorKind.HUMAN,
            principal_id="operator",
            capabilities=("public_connector_registration",),
            metadata={
                "title": "Operator",
                "boundary": "Publishes the connector URL. That registration is not a task on this plan.",
            },
        ),
    )

    formulas: list[Any] = []
    goals: list[Goal] = []
    subgoals: list[Subgoal] = []
    tasks: list[PlanTask] = []
    requirements: list[EvidenceRequirement] = []

    for goal_spec in ALIGNMENT_GOALS:
        goal_id = goal_spec["goal_id"]
        goal_formula = atom(
            ReviewedPredicate.GOAL_SATISFIED,
            constant(TermSort.GOAL, goal_id),
        )
        formulas.append(goal_formula)
        requirement_id = "evidence." + goal_id.removeprefix("goal.")
        requirements.append(
            EvidenceRequirement(
                requirement_id=requirement_id,
                kind=EvidenceRequirementKind.PLAN_CHECK,
                subject_ids=(goal_id,),
                metadata={"title": goal_spec["title"]},
            )
        )
        goals.append(
            Goal(
                goal_id=goal_id,
                owner_actor_id=_ACTOR_ID,
                satisfaction_formula_id=goal_formula.formula_id,
                evidence_requirement_ids=(requirement_id,),
                source_ids=("complaint-generator",),
                metadata={"title": goal_spec["title"], "domain": goal_spec["domain"]},
            )
        )
        for subgoal_spec in goal_spec["subgoals"]:
            subgoal_id = subgoal_spec["subgoal_id"]
            subgoal_formula = subgoal_satisfied(subgoal_id)
            formulas.append(subgoal_formula)
            subgoals.append(
                Subgoal(
                    subgoal_id=subgoal_id,
                    goal_id=goal_id,
                    parent_id=goal_id,
                    refinement_mode=RefinementMode.SUFFICIENT,
                    satisfaction_formula_id=subgoal_formula.formula_id,
                    depends_on=subgoal_spec["depends_on"],
                    evidence_requirement_ids=(requirement_id,),
                    metadata={"title": subgoal_spec["title"]},
                )
            )
            for task_spec in subgoal_spec["tasks"]:
                tasks.append(
                    PlanTask(
                        task_id=task_spec["task_id"],
                        goal_id=goal_id,
                        subgoal_id=subgoal_id,
                        actor_ids=(_ACTOR_ID,),
                        depends_on=task_spec["depends_on"],
                        evidence_requirement_ids=(requirement_id,),
                        metadata={"title": task_spec["title"], "domain": goal_spec["domain"]},
                    )
                )

    return FormalWorkPlan(
        vocabulary_profile_id="supervisor-reviewed",
        vocabulary_version=LOGIC_VOCABULARY_VERSION,
        source_ids=(
            "complaint-generator",
            PLAN_RELATIVE,
        ),
        repository_tree_id="complaint-alignment",
        trace_bound=1,
        actors=actors,
        goals=tuple(goals),
        subgoals=tuple(subgoals),
        tasks=tuple(tasks),
        events=(),
        fluents=(),
        preconditions=(),
        effects=(),
        norms=(),
        temporal_constraints=(),
        evidence_requirements=tuple(requirements),
        formulas=tuple(formulas),
        metadata={
            "title": "Complaint-generator alignment with Mike, datasets, kit, and accelerate",
            "autonomy": (
                "The complaint watchdog completes these tasks with local file checks. "
                "It does not start a control-plane plan."
            ),
        },
    )


def plan_document(plan: Any) -> dict[str, Any]:
    """Return the ingestible object, including the non-recursive plan id."""

    document = plan.to_dict()
    document["plan_id"] = plan.plan_id
    return document


def _matching_execution_board(path: Path, plan: Any) -> dict[str, Any] | None:
    """Read a structurally valid snapshot for this exact plan."""

    from integrations.ipfs_accelerate.watchdog import EXECUTION_SCHEMA

    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(board, dict) or board.get("schema_version") != EXECUTION_SCHEMA:
        return None
    if board.get("plan_id") != plan.plan_id or not isinstance(board.get("supervisor"), dict):
        return None
    tasks = board.get("tasks")
    if not isinstance(tasks, dict) or set(tasks) != {task.task_id for task in plan.tasks}:
        return None
    for task in plan.tasks:
        record = tasks[task.task_id]
        if not isinstance(record, dict):
            return None
        status = record.get("status")
        if not isinstance(status, str) or status not in {"ready", "blocked", "in_progress", "completed", "failed", "cancelled"}:
            return None
        if record.get("depends_on") != list(task.depends_on) or not isinstance(record.get("receipts"), list):
            return None
    return board


def publish_alignment_execution_board(
    repo_root: Path | None = None,
    *,
    plan_path: Path | None = None,
    state_path: Path | None = None,
) -> Path | None:
    """Publish the standard runtime snapshot without exporting custom runs.

    Share the runtime ownership lock so a second publisher cannot replace a
    newer projection with an older snapshot. A live monitor owns publication
    until it releases that lock.
    """

    from integrations.ipfs_accelerate.watchdog import _state_lock, load_formal_plan, save_state

    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    standard_plan = (root / PLAN_RELATIVE).resolve()
    standard_state = (root / STATE_RELATIVE).resolve()
    if Path(plan_path or standard_plan).resolve() != standard_plan:
        return None
    if Path(state_path or standard_state).resolve() != standard_state:
        return None
    with _state_lock(standard_state) as owned:
        if not owned:
            return None
        plan = load_formal_plan(standard_plan)
        board = _matching_execution_board(standard_state, plan)
        if board is None:
            return None
        target = root / BOARD_RELATIVE
        save_state(target, board)
        return target


def write_alignment_artifacts(
    repo_root: Path | None = None,
    *,
    plan: Any | None = None,
) -> Mapping[str, Any]:
    """Write the formal plan and preserve matching execution progress."""

    root = Path(repo_root or Path(__file__).resolve().parents[2])
    built = plan or build_alignment_work_plan()
    plan_path = root / PLAN_RELATIVE
    board_path = root / BOARD_RELATIVE
    document = plan_document(built)

    from integrations.ipfs_accelerate.watchdog import _state_lock, initial_execution_board, save_state

    with _state_lock(root / STATE_RELATIVE) as owned:
        if not owned:
            raise RuntimeError("alignment artifacts are owned by a running watchdog")
        board = (
            _matching_execution_board(root / STATE_RELATIVE, built)
            or _matching_execution_board(board_path, built)
            or initial_execution_board(built)
        )
        save_state(plan_path, document)
        save_state(board_path, board)
    return {"plan_path": plan_path, "board_path": board_path, "plan_id": built.plan_id}
