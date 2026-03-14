"""Adversarial harness to autopatch demo.

Runs a small complainant/mediator batch with mock components, analyzes the
results, and emits a patch artifact through the new Optimizer.run_agentic_autopatch
bridge. The patch is not applied automatically; it is written to disk so the
flow can be verified safely.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adversarial_harness import AdversarialHarness, Optimizer


class MockLLMBackend:
    def __init__(self, response_template: str = "Mock response"):
        self.response_template = response_template

    def __call__(self, prompt: str) -> str:
        lower_prompt = prompt.lower()
        if "generate" in lower_prompt and "complaint" in lower_prompt:
            return (
                "I reported discrimination to human resources after my supervisor "
                "denied a promotion and made repeated comments about women not being fit for leadership. "
                "Two days later I was terminated."
            )
        if "scores:" in prompt or "evaluate" in lower_prompt:
            return """SCORES:
question_quality: 0.72
information_extraction: 0.74
empathy: 0.68
efficiency: 0.69
coverage: 0.73

FEEDBACK:
Good coverage, but the mediator can ask more specific timeline and witness questions.

STRENGTHS:
- Clear questioning
- Good coverage of key issues

WEAKNESSES:
- Timeline probing could be more specific
- Witness and documentary evidence follow-ups could be stronger

SUGGESTIONS:
- Add a dedicated timeline probe after the first retaliation allegation
- Ask directly about documentary evidence and witnesses earlier in the loop
"""
        if "when" in lower_prompt or "date" in lower_prompt:
            return "The termination happened on March 5, 2026, two days after I complained to HR."
        if "witness" in lower_prompt:
            return "My coworker Sarah Lee witnessed the retaliation discussion."
        if "document" in lower_prompt or "email" in lower_prompt:
            return "I have the HR complaint email and the termination notice."
        return self.response_template


class MockKnowledgeGraph:
    def summary(self) -> Dict[str, Any]:
        return {"total_entities": 5, "total_relationships": 4}


class MockDependencyGraph:
    def summary(self) -> Dict[str, Any]:
        return {"total_nodes": 4, "total_dependencies": 3}


class MockPhaseManager:
    def get_phase_data(self, phase: Any, key: str) -> Any:
        if key == "knowledge_graph":
            return MockKnowledgeGraph()
        if key == "dependency_graph":
            return MockDependencyGraph()
        return None


class MockMediator:
    def __init__(self):
        self.phase_manager = MockPhaseManager()
        self.questions_asked = 0

    def start_three_phase_process(self, complaint_text: str) -> Dict[str, Any]:
        return {
            "phase": "intake",
            "initial_questions": [
                {"question": "When exactly did the retaliation happen?", "type": "timeline"}
            ],
        }

    def process_denoising_answer(self, question: Dict[str, Any], answer: str) -> Dict[str, Any]:
        self.questions_asked += 1
        if self.questions_asked == 1:
            next_questions = [{"question": "Who witnessed the retaliation or has documents about it?", "type": "evidence"}]
        else:
            next_questions = []
        return {
            "converged": self.questions_asked >= 2,
            "ready_for_evidence_phase": self.questions_asked >= 2,
            "next_questions": next_questions,
        }

    def get_three_phase_status(self) -> Dict[str, Any]:
        return {
            "current_phase": "intake",
            "iteration_count": self.questions_asked,
        }


class DemoPatchOptimizer:
    def __init__(self, *, project_root: Path, output_dir: Path):
        self.project_root = project_root
        self.output_dir = output_dir

    def optimize(self, task: Any) -> Any:
        target_path = Path(task.target_files[0])
        absolute_target = target_path if target_path.is_absolute() else self.project_root / target_path
        original_text = absolute_target.read_text(encoding="utf-8")
        recommendation = ""
        report_summary = task.metadata.get("report_summary") or {}
        recommendations = list(report_summary.get("recommendations") or [])
        if recommendations:
            recommendation = recommendations[0]
        else:
            recommendation = "Improve mediator follow-up specificity based on adversarial optimizer output."

        marker = f"# Demo autopatch recommendation: {recommendation.strip()}"
        if marker in original_text:
            modified_text = original_text
        else:
            modified_text = original_text.rstrip("\n") + "\n\n" + marker + "\n"

        relative_target = absolute_target.relative_to(self.project_root)
        diff_text = "".join(
            difflib.unified_diff(
                original_text.splitlines(keepends=True),
                modified_text.splitlines(keepends=True),
                fromfile=f"a/{relative_target.as_posix()}",
                tofile=f"b/{relative_target.as_posix()}",
            )
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        patch_name = f"adversarial_autopatch_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.patch"
        patch_path = self.output_dir / patch_name
        patch_path.write_text(diff_text, encoding="utf-8")
        patch_cid = "demo-" + hashlib.sha1(diff_text.encode("utf-8")).hexdigest()[:16]
        return SimpleNamespace(
            success=True,
            patch_path=patch_path,
            patch_cid=patch_cid,
            metadata={"demo": True, "patch_size_bytes": patch_path.stat().st_size},
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run adversarial harness batch and emit a demo autopatch artifact")
    parser.add_argument(
        "--target-file",
        default="adversarial_harness/session.py",
        help="Repository file to target when generating the demo patch",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "tmp" / "adversarial_autopatch_demo"),
        help="Directory for session artifacts and the generated patch",
    )
    parser.add_argument("--num-sessions", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=2)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    session_dir = output_dir / "sessions"

    harness = AdversarialHarness(
        llm_backend_complainant=MockLLMBackend(),
        llm_backend_critic=MockLLMBackend(),
        mediator_factory=MockMediator,
        max_parallel=1,
        session_state_dir=str(session_dir),
    )

    results = harness.run_batch(
        num_sessions=args.num_sessions,
        seed_complaints=[
            {
                "type": "employment_discrimination",
                "summary": "Retaliation after reporting discrimination",
                "key_facts": {"employer": "Acme Corp", "action": "termination"},
            }
        ],
        personalities=["cooperative"],
        max_turns_per_session=args.max_turns,
    )

    optimizer = Optimizer()
    report = optimizer.analyze(results)
    autopatch_result = optimizer.run_agentic_autopatch(
        results,
        target_files=[args.target_file],
        method="actor_critic",
        llm_router=object(),
        optimizer=DemoPatchOptimizer(project_root=PROJECT_ROOT, output_dir=output_dir),
        report=report,
    )

    payload = {
        "num_results": len(results),
        "report": report.to_dict(),
        "autopatch": {
            "success": bool(getattr(autopatch_result, "success", False)),
            "patch_path": str(getattr(autopatch_result, "patch_path", "")),
            "patch_cid": str(getattr(autopatch_result, "patch_cid", "")),
            "metadata": dict(getattr(autopatch_result, "metadata", {}) or {}),
        },
    }
    summary_path = output_dir / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(payload, indent=2))
    return 0 if payload["autopatch"]["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())