"""Immutable artifact locations for independent implementation campaigns."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping


@dataclass(frozen=True)
class CampaignArtifacts:
    spec_relative: str = "docs/task_boards/complaint_intake_improvement_spec.json"
    plan_relative: str = "docs/task_boards/complaint_intake_formal_work_plan.json"
    board_relative: str = "docs/task_boards/complaint_intake_task_board.md"
    board_namespace: str = "complaint-intake-improvement"

    @property
    def protected_paths(self) -> tuple[str, ...]:
        if self == DEFAULT_ARTIFACTS:
            return ()
        return self.spec_relative, self.plan_relative, self.board_relative

    def validate_source(self, repo_root: Path, spec_path: Path) -> None:
        if self == DEFAULT_ARTIFACTS:
            return
        root, source = Path(repo_root).resolve(), Path(spec_path).absolute()
        if source != source.resolve() or source != root / self.spec_relative:
            raise ValueError("campaign spec path differs from its declared source")
        for relative in (self.spec_relative, self.plan_relative, self.board_relative):
            path = root / relative
            if path.resolve(strict=False) != path:
                raise ValueError("campaign artifact path traverses a symlink")


DEFAULT_ARTIFACTS = CampaignArtifacts()


def campaign_artifacts(spec: Mapping[str, Any]) -> CampaignArtifacts:
    if "campaign" not in spec:
        return DEFAULT_ARTIFACTS
    value = spec["campaign"]
    fields = {"spec_relative", "plan_relative", "board_relative", "board_namespace"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("campaign must declare exactly its spec, plan, board and namespace")
    for field, suffix in (("spec_relative", ".json"), ("plan_relative", ".json"), ("board_relative", ".md")):
        path = value[field]
        if (not isinstance(path, str) or len(path) > 256
                or re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)+", path) is None
                or any(part in {".", "..", ".git"} for part in PurePosixPath(path).parts)
                or not path.startswith("docs/task_boards/") or not path.endswith(suffix)):
            raise ValueError("campaign artifact paths must be safe task-board-relative files")
    paths = [value[field] for field in ("spec_relative", "plan_relative", "board_relative")]
    legacy = {DEFAULT_ARTIFACTS.spec_relative, DEFAULT_ARTIFACTS.plan_relative, DEFAULT_ARTIFACTS.board_relative}
    if len(set(paths)) != 3 or set(paths) & legacy:
        raise ValueError("new campaign artifacts must not replace the original intake artifacts")
    namespace = value["board_namespace"]
    if (not isinstance(namespace, str) or re.fullmatch(r"[a-z][a-z0-9-]{0,63}", namespace) is None
            or namespace == DEFAULT_ARTIFACTS.board_namespace):
        raise ValueError("new campaign requires a distinct canonical board namespace")
    return CampaignArtifacts(**value)
