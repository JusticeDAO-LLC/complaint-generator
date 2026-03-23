from types import SimpleNamespace

import pytest

from adversarial_harness import Optimizer, UIUXOptimizationBundle


pytestmark = [pytest.mark.no_auto_network]


def test_build_ui_ux_optimization_bundle_wraps_iterative_review_workflow(monkeypatch, tmp_path):
    optimizer = Optimizer()
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"

    def fake_iterative(**kwargs):
        assert str(kwargs["screenshot_dir"]) == str(screenshot_dir)
        assert str(kwargs["output_dir"]) == str(output_dir)
        return {
            "iterations": 2,
            "screenshot_dir": str(screenshot_dir),
            "output_dir": str(output_dir),
            "runs": [
                {
                    "iteration": 1,
                    "review_markdown_path": str(output_dir / "iteration-01-review.md"),
                    "review_json_path": str(output_dir / "iteration-01-review.json"),
                },
                {
                    "iteration": 2,
                    "review_markdown_path": str(output_dir / "iteration-02-review.md"),
                    "review_json_path": str(output_dir / "iteration-02-review.json"),
                },
            ],
        }

    monkeypatch.setattr("complaint_generator.ui_ux_workflow.run_iterative_ui_ux_workflow", fake_iterative)
    monkeypatch.setattr(
        optimizer,
        "_read_ui_ux_review_json",
        lambda path: {"review": "# Top Risks\n- Improve evidence affordances."},
    )

    bundle = optimizer.build_ui_ux_optimization_bundle(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target="playwright/tests/navigation.spec.js",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
    )

    assert isinstance(bundle, UIUXOptimizationBundle)
    payload = bundle.to_dict()
    assert payload["iterations"] == 2
    assert payload["review_runs"]
    assert payload["task"]["target_files"]
    assert "templates/workspace.html" in payload["target_files"]


def test_run_agentic_ui_ux_autopatch_executes_optimizer_against_ui_task(monkeypatch, tmp_path):
    optimizer = Optimizer()
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"

    monkeypatch.setattr(
        optimizer,
        "build_ui_ux_optimization_bundle",
        lambda **kwargs: UIUXOptimizationBundle(
            timestamp="2026-03-23T00:00:00+00:00",
            screenshot_dir=str(screenshot_dir),
            output_dir=str(output_dir),
            iterations=1,
            pytest_target="playwright/tests/navigation.spec.js",
            target_files=["templates/workspace.html"],
            review_runs=[
                {
                    "iteration": 1,
                    "review_markdown_path": str(output_dir / "iteration-01-review.md"),
                    "review_json_path": str(output_dir / "iteration-01-review.json"),
                }
            ],
            latest_review_markdown_path=str(output_dir / "iteration-01-review.md"),
            latest_review_json_path=str(output_dir / "iteration-01-review.json"),
            task={},
        ),
    )
    monkeypatch.setattr(
        optimizer,
        "_read_ui_ux_review_json",
        lambda path: {"review": "# High-Impact UX Fixes\n- Keep the MCP SDK path shared."},
    )

    captured = {}

    class FakeUIOptimizer:
        def __init__(self, *, agent_id, llm_router):
            captured["agent_id"] = agent_id
            captured["llm_router"] = llm_router
            self._last_generation_diagnostics = [{"file": "templates/workspace.html", "status": "ok"}]

        def optimize(self, task):
            captured["task"] = task
            return SimpleNamespace(status="applied", metadata={"changed_files": ["templates/workspace.html"]})

    result = optimizer.run_agentic_ui_ux_autopatch(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target="playwright/tests/navigation.spec.js",
        llm_router=object(),
        components=None,
        optimizer=FakeUIOptimizer(agent_id="ui-ux-agent", llm_router=object()),
    )

    assert result["bundle"]["target_files"] == ["templates/workspace.html"]
    assert result["task"]["target_files"] == ["templates/workspace.html"]
    assert captured["task"].metadata["workflow_type"] == "ui_ux_autopatch"


def test_run_agentic_ui_ux_feedback_loop_revalidates_and_stops_when_reviews_stabilize(monkeypatch, tmp_path):
    optimizer = Optimizer()
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"

    call_counter = {"count": 0}
    review_by_path = {}

    def fake_workflow(**kwargs):
        call_counter["count"] += 1
        round_index = call_counter["count"]
        review_json_path = tmp_path / f"review-{round_index}.json"
        if round_index == 2:
            review_text = "# Top Risks\n- Calmer intake language still needed."
        elif round_index == 4:
            review_text = "# Top Risks\n- Calmer intake language still needed."
        else:
            review_text = f"# Top Risks\n- Review pass {round_index}."
        review_by_path[str(review_json_path)] = {"review": review_text}
        return {
            "iterations": 1,
            "screenshot_dir": str(kwargs["screenshot_dir"]),
            "output_dir": str(kwargs["output_dir"]),
            "latest_review": review_text,
            "latest_review_json_path": str(review_json_path),
            "runs": [
                {
                    "iteration": 1,
                    "review_markdown_path": str(tmp_path / f"review-{round_index}.md"),
                    "review_json_path": str(review_json_path),
                }
            ],
        }

    monkeypatch.setattr("complaint_generator.ui_ux_workflow.run_iterative_ui_ux_workflow", fake_workflow)
    monkeypatch.setattr(
        optimizer,
        "_read_ui_ux_review_json",
        lambda path: review_by_path.get(str(path), {}),
    )

    class FakeLoopOptimizer:
        def __init__(self, *, agent_id, llm_router):
            self._last_generation_diagnostics = [{"status": "ok"}]

        def optimize(self, task):
            return SimpleNamespace(
                success=True,
                status="applied",
                patch_path=str(tmp_path / "round.patch"),
                metadata={"changed_files": [str(task.target_files[0])]},
            )

    result = optimizer.run_agentic_ui_ux_feedback_loop(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target="playwright/tests/navigation.spec.js",
        max_rounds=3,
        review_iterations=1,
        llm_router=object(),
        optimizer=FakeLoopOptimizer(agent_id="ui-loop", llm_router=object()),
        components=None,
    )

    assert result["workflow_type"] == "ui_ux_closed_loop"
    assert result["rounds_executed"] == 2
    assert result["stop_reason"] == "validation_review_stable"
    assert result["cycles"][0]["optimizer_result"]["changed_files"]
    assert "actor_critic_summary" in result
