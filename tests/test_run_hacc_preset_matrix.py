import importlib.util
import sys
from types import ModuleType
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_hacc_preset_matrix.py"
SPEC = importlib.util.spec_from_file_location("run_hacc_preset_matrix", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_compact_claim_selection_summary_formats_tags_exhibits_and_rationale():
    summary = [
        {
            "title": "Accommodation Theory",
            "selection_tags": ["reasonable_accommodation", "contact"],
            "selected_exhibits": [{"exhibit_id": "Exhibit B", "label": "ADMINISTRATIVE PLAN"}],
            "selection_rationale": "selected for stronger accommodation contact-language",
        }
    ]

    overview = MODULE._compact_claim_selection_summary(summary)

    assert "Accommodation Theory" in overview
    assert "tags=reasonable_accommodation,contact" in overview
    assert "exhibits=Exhibit B: ADMINISTRATIVE PLAN" in overview
    assert "rationale=selected for stronger accommodation contact-language" in overview


def test_compact_relief_selection_summary_formats_families_role_and_related_claims():
    summary = [
        {
            "text": "Corrective action requiring clear notice, fair review, and non-retaliation safeguards.",
            "strategic_families": ["process"],
            "strategic_role": "shared_baseline",
            "related_claims": ["Administrative Fair Housing Process Failure"],
            "strategic_note": "This relief item tracks the shared process baseline that appeared in both the selected preset and the runner-up.",
        }
    ]

    overview = MODULE._compact_relief_selection_summary(summary)

    assert "Corrective action requiring clear notice" in overview
    assert "families=process" in overview
    assert "role=shared_baseline" in overview
    assert "related=Administrative Fair Housing Process Failure" in overview


def test_markdown_report_includes_claim_selection_snapshots(tmp_path):
    report_path = tmp_path / "preset_matrix_summary.md"
    rows = [
        {
            "preset": "accommodation_focus",
            "backend_id": "llm-router-codex",
            "hacc_search_mode": "hybrid",
            "effective_hacc_search_mode": "lexical_only",
            "hacc_search_fallback_note": "Requested hybrid search, but vector support is unavailable; using lexical results instead.",
            "average_score": 0.75,
            "successful_sessions": 3,
            "total_sessions": 3,
            "anchor_coverage": 1.0,
            "router_status": "available",
            "top_missing_sections": "",
            "top_intake_gaps": "anchor_appeal_rights (0/1)",
            "remediation_focus": "anchor=appeal_rights; intake=anchor_appeal_rights",
            "missing_sections": "",
            "output_dir": "/tmp/accommodation_focus",
            "claim_selection_overview": (
                "Accommodation Theory [tags=reasonable_accommodation,contact; "
                "exhibits=Exhibit B: ADMINISTRATIVE PLAN; "
                "rationale=selected for stronger accommodation contact-language]"
            ),
            "relief_selection_overview": (
                "Corrective action requiring clear notice, fair review, and non-retaliation safeguards. "
                "[families=process; role=shared_baseline]"
            ),
            "claim_theory_families": ["accommodation", "process"],
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
        }
    ]
    recommendations = {
        "best_overall": {
            "preset": "accommodation_focus",
            "claim_theory_families": ["accommodation", "process"],
            "strategy_summary": "Best for accommodation framing + process framing.",
            "claim_posture_note": "The winner added stronger accommodation framing theories.",
            "relief_posture_note": "Relief posture was materially similar across the winner and runner-up, so the selection difference was driven mainly by claim posture.",
        },
        "best_anchor_coverage": {"preset": "accommodation_focus"},
        "best_balanced": {"preset": "accommodation_focus"},
    }

    MODULE._write_markdown_report(report_path, rows, recommendations)
    report = report_path.read_text(encoding="utf-8")

    assert "- Unified winner: `accommodation_focus` (accommodation, process) - Best for accommodation framing + process framing" in report
    assert "- Applies to: best overall, best anchor coverage, best balanced" in report
    assert "### Unified Winner Snapshot" in report
    assert "## Runner-Up Snapshot" not in report
    assert "## Claim Selection Snapshots" not in report
    assert "### accommodation_focus" not in report
    assert "- Overview: Accommodation Theory [tags=reasonable_accommodation,contact;" in report
    assert "- Search mode: requested=hybrid; effective=lexical_only" in report
    assert "- Search fallback: Requested hybrid search, but vector support is unavailable; using lexical results instead." in report
    assert "- Coverage remediation: anchor=appeal_rights; intake=anchor_appeal_rights" in report
    assert "- Strategy summary: Best for accommodation framing + process framing." in report
    assert "- Claim posture note: The winner added stronger accommodation framing theories." not in report
    assert "- Relief posture note: Relief posture was materially similar across the winner and runner-up, so the selection difference was driven mainly by claim posture." not in report
    assert "- Relief overview: Corrective action requiring clear notice, fair review, and non-retaliation safeguards." in report
    assert "- Complaint synthesis: `/tmp/accommodation_focus/complaint_synthesis`" in report
    assert "| Preset | Backend | Avg Score | Success | Anchor Coverage | Router | Top Missing Sections | Top Intake Gaps | Remediation Focus | Missing Sections | Output Dir |" in report


def test_rebuild_batch_result_recovers_effective_search_mode_from_run_summary(tmp_path, monkeypatch):
    preset_dir = tmp_path / "accommodation_focus"
    preset_dir.mkdir()
    (preset_dir / "adversarial_results.json").write_text(
        __import__("json").dumps({"results": []}, indent=2),
        encoding="utf-8",
    )
    (preset_dir / "optimizer_report.json").write_text(
        __import__("json").dumps({}, indent=2),
        encoding="utf-8",
    )
    (preset_dir / "run_summary.json").write_text(
        __import__("json").dumps(
            {
                "hacc_search_mode": "hybrid",
                "runtime": {},
                "router_report": {"status": "available"},
                "search_summary": {
                    "requested_search_mode": "hybrid",
                    "effective_search_mode": "lexical_only",
                    "fallback_note": "Requested hybrid search, but vector support is unavailable; using lexical results instead.",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        MODULE,
        '_synthesize_claim_selection_snapshot',
        lambda **kwargs: {
            'claim_selection_summary': [],
            'claim_selection_overview': '',
            'relief_selection_summary': [],
            'relief_selection_overview': '',
            'claim_theory_families': [],
            'synthesis_output_dir': str(preset_dir / 'complaint_synthesis'),
        },
    )

    result = MODULE._rebuild_batch_result_from_preset_dir(
        preset='accommodation_focus',
        preset_dir=preset_dir,
        backend_id='llm-router-codex',
        selected_backend_healthy=True,
        backend_probe_attempts=[],
        synthesis_filing_forum='hud',
    )

    assert result['hacc_search_mode'] == 'hybrid'
    assert result['effective_hacc_search_mode'] == 'lexical_only'
    assert result['hacc_search_fallback_note'] == (
        'Requested hybrid search, but vector support is unavailable; using lexical results instead.'
    )


def test_main_uses_rebuild_helper_when_rebuild_existing_is_set(tmp_path, monkeypatch):
    fake_adversarial_harness = ModuleType("adversarial_harness")
    fake_adversarial_harness.HACC_QUERY_PRESETS = {"accommodation_focus": {"query": "stub"}}
    monkeypatch.setitem(sys.modules, "adversarial_harness", fake_adversarial_harness)

    monkeypatch.setattr(MODULE, "_load_config", lambda path: {"BACKENDS": [], "MEDIATOR": {"backends": []}})
    monkeypatch.setattr(
        MODULE,
        "_select_llm_router_backend_config",
        lambda config, backend_id: ("llm-router-codex", {"id": "llm-router-codex"}, [], True),
    )

    calls = {"rebuild": [], "run": 0, "write": None}

    def fake_rebuild(**kwargs):
        calls["rebuild"].append(kwargs)
        preset_dir = kwargs["preset_dir"]
        return {
            "preset": kwargs["preset"],
            "backend_id": kwargs["backend_id"],
            "hacc_search_mode": "package",
            "effective_hacc_search_mode": "package",
            "hacc_search_fallback_note": "",
            "selected_backend_healthy": True,
            "average_score": 0.81,
            "successful_sessions": 1,
            "total_sessions": 1,
            "anchor_coverage": 1.0,
            "top_missing_sections": "",
            "top_intake_gaps": "",
            "remediation_focus": "maintain full intake coverage",
            "coverage_remediation": {
                "anchor_sections": {"missing_sections": [], "recommended_actions": []},
                "intake_priorities": {"uncovered_objectives": [], "recommended_actions": []},
            },
            "missing_sections": "",
            "output_dir": str(preset_dir),
            "router_status": "available",
            "backend_probe_attempts": [],
            "router_report": {},
            "runtime": {},
            "search_summary": {
                "requested_search_mode": "package",
                "effective_search_mode": "package",
                "fallback_note": "",
            },
            "statistics": {},
            "optimizer_report": {},
            "claim_selection_summary": [],
            "claim_selection_overview": "winner overview",
            "relief_selection_summary": [],
            "relief_selection_overview": "relief overview",
            "claim_theory_families": ["accommodation"],
            "synthesis_output_dir": str(preset_dir / "complaint_synthesis"),
        }

    def fake_run(**kwargs):
        calls["run"] += 1
        raise AssertionError("_run_preset_batch should not be called when --rebuild-existing is set")

    def fake_write(**kwargs):
        calls["write"] = kwargs

    monkeypatch.setattr(MODULE, "_rebuild_batch_result_from_preset_dir", fake_rebuild)
    monkeypatch.setattr(MODULE, "_run_preset_batch", fake_run)
    monkeypatch.setattr(MODULE, "_write_matrix_outputs", fake_write)
    monkeypatch.setattr(
        MODULE.sys,
        "argv",
        [
            "run_hacc_preset_matrix.py",
            "--config",
            str(tmp_path / "config.json"),
            "--presets",
            "accommodation_focus",
            "--rebuild-existing",
            "--output-dir",
            str(tmp_path / "matrix_output"),
        ],
    )

    exit_code = MODULE.main()

    assert exit_code == 0
    assert calls["run"] == 0
    assert len(calls["rebuild"]) == 1
    assert calls["rebuild"][0]["preset"] == "accommodation_focus"
    assert calls["rebuild"][0]["preset_dir"] == (tmp_path / "matrix_output" / "accommodation_focus").resolve()
    assert calls["write"] is not None
    assert calls["write"]["requested_presets"] == ["accommodation_focus"]
    assert calls["write"]["matrix_rows"][0]["preset"] == "accommodation_focus"
    assert calls["write"]["matrix_rows"][0]["hacc_search_mode"] == "package"
    assert calls["write"]["full_results"][0]["search_summary"]["requested_search_mode"] == "package"


def test_main_continue_on_error_records_failed_preset_and_writes_partial_matrix(tmp_path, monkeypatch):
    fake_adversarial_harness = ModuleType("adversarial_harness")
    fake_adversarial_harness.HACC_QUERY_PRESETS = {
        "accommodation_focus": {"query": "stub"},
        "core_hacc_policies": {"query": "stub"},
    }
    monkeypatch.setitem(sys.modules, "adversarial_harness", fake_adversarial_harness)

    monkeypatch.setattr(MODULE, "_load_config", lambda path: {"BACKENDS": [], "MEDIATOR": {"backends": []}})
    monkeypatch.setattr(
        MODULE,
        "_select_llm_router_backend_config",
        lambda config, backend_id: ("llm-router-codex", {"id": "llm-router-codex"}, [], True),
    )

    calls = {"run": [], "write": None}

    def fake_run(**kwargs):
        calls["run"].append(kwargs["preset"])
        if kwargs["preset"] == "accommodation_focus":
            raise RuntimeError("quota exceeded")
        preset_dir = kwargs["preset_dir"]
        return {
            "preset": kwargs["preset"],
            "backend_id": kwargs["backend_id"],
            "hacc_search_mode": "package",
            "effective_hacc_search_mode": "package",
            "hacc_search_fallback_note": "",
            "selected_backend_healthy": True,
            "average_score": 0.73,
            "successful_sessions": 1,
            "total_sessions": 1,
            "anchor_coverage": 1.0,
            "top_missing_sections": "",
            "top_intake_gaps": "",
            "remediation_focus": "maintain full intake coverage",
            "coverage_remediation": {
                "anchor_sections": {"missing_sections": [], "recommended_actions": []},
                "intake_priorities": {"uncovered_objectives": [], "recommended_actions": []},
            },
            "missing_sections": "",
            "output_dir": str(preset_dir),
            "router_status": "available",
            "backend_probe_attempts": [],
            "router_report": {},
            "runtime": {},
            "search_summary": {
                "requested_search_mode": "package",
                "effective_search_mode": "package",
                "fallback_note": "",
            },
            "statistics": {},
            "optimizer_report": {},
            "claim_selection_summary": [],
            "claim_selection_overview": "winner overview",
            "relief_selection_summary": [],
            "relief_selection_overview": "relief overview",
            "claim_theory_families": ["process"],
            "synthesis_output_dir": str(preset_dir / "complaint_synthesis"),
        }

    def fake_write(**kwargs):
        calls["write"] = kwargs

    monkeypatch.setattr(MODULE, "_run_preset_batch", fake_run)
    monkeypatch.setattr(MODULE, "_write_matrix_outputs", fake_write)
    monkeypatch.setattr(
        MODULE.sys,
        "argv",
        [
            "run_hacc_preset_matrix.py",
            "--config",
            str(tmp_path / "config.json"),
            "--presets",
            "accommodation_focus,core_hacc_policies",
            "--continue-on-error",
            "--output-dir",
            str(tmp_path / "matrix_output"),
        ],
    )

    exit_code = MODULE.main()

    assert exit_code == 0
    assert calls["run"] == ["accommodation_focus", "core_hacc_policies"]
    assert calls["write"] is not None
    assert [row["preset"] for row in calls["write"]["matrix_rows"]] == ["core_hacc_policies"]
    assert [item["preset"] for item in calls["write"]["full_results"]] == ["core_hacc_policies"]
    assert calls["write"]["preset_errors"][0]["preset"] == "accommodation_focus"
    assert calls["write"]["preset_errors"][0]["error"] == "quota exceeded"
    assert "RuntimeError: quota exceeded" in calls["write"]["preset_errors"][0]["traceback"]


def test_runner_up_snapshot_uses_role_based_heading(tmp_path):
    report_path = tmp_path / "preset_matrix_summary.md"
    rows = [
        {
            "preset": "accommodation_focus",
            "backend_id": "llm-router-codex",
            "average_score": 0.75,
            "successful_sessions": 3,
            "total_sessions": 3,
            "anchor_coverage": 1.0,
            "router_status": "available",
            "top_missing_sections": "",
            "missing_sections": "",
            "output_dir": "/tmp/accommodation_focus",
            "claim_selection_overview": "winner overview",
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
        },
        {
            "preset": "administrative_plan_retaliation",
            "backend_id": "llm-router-codex",
            "average_score": 0.70,
            "successful_sessions": 3,
            "total_sessions": 3,
            "anchor_coverage": 0.9,
            "router_status": "available",
            "top_missing_sections": "",
            "missing_sections": "",
            "output_dir": "/tmp/administrative_plan_retaliation",
            "claim_selection_overview": "runner overview",
            "synthesis_output_dir": "/tmp/administrative_plan_retaliation/complaint_synthesis",
        },
    ]
    recommendations = {
        "best_overall": {"preset": "accommodation_focus", "strategy_summary": "Best for accommodation framing."},
        "best_anchor_coverage": {"preset": "accommodation_focus"},
        "best_balanced": {"preset": "accommodation_focus"},
    }

    MODULE._write_markdown_report(report_path, rows, recommendations)
    report = report_path.read_text(encoding="utf-8")

    assert "## Runner-Up Snapshot" in report
    assert "### Runner-Up: administrative_plan_retaliation" in report


def test_recommendation_groups_collapses_duplicate_presets():
    recommendations = {
        "best_overall": {"preset": "accommodation_focus"},
        "best_anchor_coverage": {"preset": "accommodation_focus"},
        "best_balanced": {"preset": "accommodation_focus"},
    }

    groups = MODULE._recommendation_groups(recommendations)

    assert groups == [(
        ["best_overall", "best_anchor_coverage", "best_balanced"],
        {"preset": "accommodation_focus"},
    )]


def test_attach_recommendation_claim_snapshots_enriches_best_overall():
    rows = [
        {
            "preset": "accommodation_focus",
            "claim_selection_overview": "Accommodation Theory [tags=reasonable_accommodation,contact]",
            "relief_selection_overview": "Corrective action requiring clear notice [families=process]",
            "claim_theory_families": ["accommodation", "process"],
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
            "hacc_search_mode": "hybrid",
            "effective_hacc_search_mode": "lexical_only",
            "hacc_search_fallback_note": "Requested hybrid search, but vector support is unavailable; using lexical results instead.",
            "top_intake_gaps": "anchor_appeal_rights (0/1)",
            "remediation_focus": "anchor=appeal_rights; intake=anchor_appeal_rights",
            "coverage_remediation": {
                "anchor_sections": {"missing_sections": ["appeal_rights"]},
                "intake_priorities": {"uncovered_objectives": ["anchor_appeal_rights"]},
            },
        }
    ]
    recommendations = {
        "best_overall": {"preset": "accommodation_focus", "average_score": 0.75, "anchor_coverage": 1.0},
    }

    enriched = MODULE._attach_recommendation_claim_snapshots(recommendations, rows)

    assert enriched["best_overall"]["claim_selection_overview"] == "Accommodation Theory [tags=reasonable_accommodation,contact]"
    assert enriched["best_overall"]["relief_selection_overview"] == "Corrective action requiring clear notice [families=process]"
    assert enriched["best_overall"]["claim_theory_families"] == ["accommodation", "process"]
    assert enriched["best_overall"]["synthesis_output_dir"] == "/tmp/accommodation_focus/complaint_synthesis"
    assert enriched["best_overall"]["hacc_search_mode"] == "hybrid"
    assert enriched["best_overall"]["effective_hacc_search_mode"] == "lexical_only"
    assert enriched["best_overall"]["hacc_search_fallback_note"] == (
        "Requested hybrid search, but vector support is unavailable; using lexical results instead."
    )
    assert enriched["best_overall"]["top_intake_gaps"] == "anchor_appeal_rights (0/1)"
    assert enriched["best_overall"]["remediation_focus"] == (
        "anchor=appeal_rights; intake=anchor_appeal_rights"
    )
    assert enriched["best_overall"]["coverage_remediation"]["anchor_sections"]["missing_sections"] == [
        "appeal_rights"
    ]


def test_remediation_helpers_rank_intake_gaps_and_focus():
    remediation = {
        "anchor_sections": {"missing_sections": ["appeal_rights", "grievance_hearing"]},
        "intake_priorities": {
            "uncovered_objectives": ["anchor_appeal_rights", "anchor_grievance_hearing"],
            "recommended_actions": [
                {
                    "objective": "anchor_appeal_rights",
                    "covered": 0,
                    "expected": 2,
                    "uncovered": 2,
                    "coverage_rate": 0.0,
                },
                {
                    "objective": "anchor_grievance_hearing",
                    "covered": 1,
                    "expected": 2,
                    "uncovered": 1,
                    "coverage_rate": 0.5,
                },
            ],
        },
    }

    assert MODULE._top_uncovered_objectives(remediation) == (
        "anchor_appeal_rights (0/2), anchor_grievance_hearing (1/2)"
    )
    assert MODULE._coverage_remediation_focus(remediation) == (
        "anchor=appeal_rights, grievance_hearing; intake=anchor_appeal_rights, anchor_grievance_hearing"
    )


def test_attach_recommendation_tradeoff_notes_enriches_winner():
    recommendations = {
        "best_overall": {"preset": "accommodation_focus"},
        "best_anchor_coverage": {"preset": "administrative_plan_retaliation"},
    }
    delta = {
        "winner_preset": "accommodation_focus",
        "winner_only_theory_families": ["accommodation", "protected_basis"],
        "runner_up_only_theory_families": ["retaliation"],
    }

    enriched = MODULE._attach_recommendation_tradeoff_notes(recommendations, delta)

    assert enriched["best_overall"]["tradeoff_note"] == (
        "best for accommodation framing + protected-basis framing; "
        "runner-up is stronger on retaliation-heavy framing"
    )
    assert enriched["best_overall"]["claim_posture_note"] == (
        "The winner added stronger accommodation framing + protected-basis framing theories, "
        "while the runner-up leaned more heavily on retaliation-heavy framing theories."
    )
    assert "relief_posture_note" not in enriched["best_overall"]
    assert enriched["best_overall"]["strategy_summary"] == (
        "Best for accommodation framing + protected-basis framing; runner-up is stronger on retaliation-heavy framing. "
        "The winner added stronger accommodation framing + protected-basis framing theories, while the runner-up leaned more heavily on retaliation-heavy framing theories."
    )
    assert "tradeoff_note" not in enriched["best_anchor_coverage"]


def test_attach_recommendation_tradeoff_notes_enriches_relief_posture_when_relevant():
    recommendations = {
        "best_overall": {"preset": "accommodation_focus"},
    }
    delta = {
        "winner_preset": "accommodation_focus",
        "winner_relief_overview": "same relief overview",
        "runner_up_relief_overview": "same relief overview",
        "winner_only_relief": [],
        "runner_up_only_relief": [],
        "winner_only_relief_families": [],
        "runner_up_only_relief_families": [],
    }

    enriched = MODULE._attach_recommendation_tradeoff_notes(recommendations, delta)

    assert enriched["best_overall"]["relief_posture_note"] == (
        "Relief posture was materially similar across the winner and runner-up, "
        "so the selection difference was driven mainly by claim posture."
    )
    assert enriched["best_overall"]["strategy_summary"] == (
        "Relief posture was materially similar across the winner and runner-up, "
        "so the selection difference was driven mainly by claim posture."
    )


def test_recommendation_strategy_summary_combines_notes_cleanly():
    payload = {
        "tradeoff_note": "best for accommodation framing + protected-basis framing; runner-up is stronger on retaliation-heavy framing",
        "claim_posture_note": "The winner added stronger accommodation framing + protected-basis framing theories, while the runner-up leaned more heavily on retaliation-heavy framing theories.",
        "relief_posture_note": "Relief posture was materially similar across the winner and runner-up, so the selection difference was driven mainly by claim posture.",
    }

    summary = MODULE._recommendation_strategy_summary(payload)

    assert summary == (
        "Best for accommodation framing + protected-basis framing; runner-up is stronger on retaliation-heavy framing. "
        "The winner added stronger accommodation framing + protected-basis framing theories, while the runner-up leaned more heavily on retaliation-heavy framing theories. "
        "Relief posture was materially similar across the winner and runner-up, so the selection difference was driven mainly by claim posture."
    )


def test_claim_posture_note_compares_winner_to_runner_up():
    delta = {
        "winner_only_theory_families": ["accommodation", "protected_basis"],
        "runner_up_only_theory_families": ["retaliation"],
    }

    note = MODULE._claim_posture_note(delta)

    assert note == (
        "The winner added stronger accommodation framing + protected-basis framing theories, "
        "while the runner-up leaned more heavily on retaliation-heavy framing theories."
    )


def test_meaningful_shared_relief_families_drops_other_placeholder():
    assert MODULE._meaningful_shared_relief_families(["other"]) == []
    assert MODULE._meaningful_shared_relief_families(["process", "other"]) == ["process"]


def test_relief_posture_note_detects_materially_similar_relief():
    delta = {
        "winner_relief_overview": "same relief overview",
        "runner_up_relief_overview": "same relief overview",
        "winner_only_relief": [],
        "runner_up_only_relief": [],
        "winner_only_relief_families": [],
        "runner_up_only_relief_families": [],
    }

    note = MODULE._relief_posture_note(delta)

    assert note == (
        "Relief posture was materially similar across the winner and runner-up, "
        "so the selection difference was driven mainly by claim posture."
    )
def test_claim_selection_theory_families_collects_unique_semantic_labels():
    summary = [
        {"title": "Administrative Fair Housing Process Failure", "selection_tags": ["notice", "hearing"]},
        {"title": "Fair Housing Act / Section 504 Accommodation Theory", "selection_tags": ["reasonable_accommodation", "contact"]},
        {"title": "Retaliation for Protected Fair Housing Activity", "selection_tags": []},
    ]

    families = MODULE._claim_selection_theory_families(summary)

    assert families == ["accommodation", "process", "retaliation"]


def test_recommendation_use_note_reads_like_decision_aid():
    assert MODULE._recommendation_use_note(["accommodation", "process"]) == "best for accommodation framing + process framing"
    assert MODULE._recommendation_use_note(["retaliation"]) == "best for retaliation-heavy framing"
def test_recommendation_tradeoff_note_compares_winner_to_runner_up():
    delta = {
        "winner_only_theory_families": ["accommodation", "protected_basis"],
        "runner_up_only_theory_families": ["retaliation"],
    }

    note = MODULE._recommendation_tradeoff_note(delta)

    assert note == "best for accommodation framing + protected-basis framing; runner-up is stronger on retaliation-heavy framing"
def test_build_claim_snapshot_delta_identifies_winner_only_and_changed_shared_claims():
    rows = [
        {"preset": "accommodation_focus", "average_score": 0.9, "anchor_coverage": 1.0},
        {"preset": "administrative_plan_retaliation", "average_score": 0.7, "anchor_coverage": 0.9},
    ]
    details = [
        {
            "preset": "accommodation_focus",
            "claim_selection_overview": "winner overview",
            "relief_selection_overview": "winner relief overview",
            "claim_selection_summary": [
                {
                    "title": "Accommodation Theory",
                    "selection_tags": ["reasonable_accommodation", "contact"],
                    "selected_exhibits": [{"exhibit_id": "Exhibit B", "label": "ADMINISTRATIVE PLAN"}],
                },
                {
                    "title": "Protected-Basis Administrative Theory",
                    "selection_tags": ["protected_basis"],
                    "selected_exhibits": [{"exhibit_id": "Exhibit B", "label": "ADMINISTRATIVE PLAN"}],
                },
            ],
            "relief_selection_summary": [
                {
                    "text": "Corrective action requiring clear notice.",
                    "strategic_families": ["process"],
                    "strategic_role": "winner_unique_strength",
                },
                {
                    "text": "Protected-basis remedies.",
                    "strategic_families": ["protected_basis"],
                    "strategic_role": "winner_unique_strength",
                },
            ],
        },
        {
            "preset": "administrative_plan_retaliation",
            "claim_selection_overview": "runner overview",
            "relief_selection_overview": "runner relief overview",
            "claim_selection_summary": [
                {
                    "title": "Accommodation Theory",
                    "selection_tags": ["reasonable_accommodation"],
                    "selected_exhibits": [{"exhibit_id": "Exhibit A", "label": "ACOP"}],
                },
                {
                    "title": "Retaliation for Protected Fair Housing Activity",
                    "selection_tags": ["retaliation"],
                    "selected_exhibits": [{"exhibit_id": "Exhibit A", "label": "ADMINISTRATIVE PLAN"}],
                },
            ],
            "relief_selection_summary": [
                {
                    "text": "Corrective action requiring clear notice.",
                    "strategic_families": ["process", "retaliation"],
                    "strategic_role": "runner_up_emphasis",
                },
                {
                    "text": "Retaliation remedies.",
                    "strategic_families": ["retaliation"],
                    "strategic_role": "runner_up_emphasis",
                },
            ],
        },
    ]
    recommendations = {"best_overall": {"preset": "accommodation_focus"}}

    delta = MODULE._build_claim_snapshot_delta(rows, details, recommendations)

    assert delta["winner_preset"] == "accommodation_focus"
    assert delta["runner_up_preset"] == "administrative_plan_retaliation"
    assert delta["winner_only_claims"] == ["Protected-Basis Administrative Theory"]
    assert delta["runner_up_only_claims"] == ["Retaliation for Protected Fair Housing Activity"]
    assert delta["winner_only_theory_families"] == ["protected_basis"]
    assert delta["runner_up_only_theory_families"] == ["retaliation"]
    assert delta["shared_theory_families"] == ["accommodation"]
    assert delta["winner_relief_overview"] == "winner relief overview"
    assert delta["runner_up_relief_overview"] == "runner relief overview"
    assert delta["winner_only_relief"] == ["Protected-basis remedies."]
    assert delta["runner_up_only_relief"] == ["Retaliation remedies."]
    assert delta["winner_only_relief_families"] == ["protected_basis"]
    assert delta["runner_up_only_relief_families"] == ["retaliation"]
    assert delta["shared_relief_families"] == ["process"]
    assert delta["changed_shared_relief"][0]["text"] == "Corrective action requiring clear notice."
    assert delta["changed_shared_relief"][0]["winner_families"] == ["process"]
    assert delta["changed_shared_relief"][0]["runner_up_families"] == ["process", "retaliation"]
    assert delta["changed_shared_claims"][0]["title"] == "Accommodation Theory"
    assert delta["changed_shared_claims"][0]["winner_exhibits"] == ["Exhibit B: ADMINISTRATIVE PLAN"]
    assert delta["changed_shared_claims"][0]["runner_up_exhibits"] == ["Exhibit A: ACOP"]


def test_markdown_report_includes_champion_claim_snapshot(tmp_path):
    report_path = tmp_path / "preset_matrix_summary.md"
    rows = [
        {
            "preset": "accommodation_focus",
            "backend_id": "llm-router-codex",
            "average_score": 0.75,
            "successful_sessions": 3,
            "total_sessions": 3,
            "anchor_coverage": 1.0,
            "router_status": "available",
            "top_missing_sections": "",
            "missing_sections": "",
            "output_dir": "/tmp/accommodation_focus",
            "claim_selection_overview": "Accommodation Theory [tags=reasonable_accommodation,contact]",
            "relief_selection_overview": "Corrective action requiring clear notice [families=process]",
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
        }
    ]
    recommendations = {
        "best_overall": {
            "preset": "accommodation_focus",
            "claim_selection_overview": "Accommodation Theory [tags=reasonable_accommodation,contact]",
            "relief_selection_overview": "Corrective action requiring clear notice [families=process]",
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
        },
        "best_anchor_coverage": {"preset": "accommodation_focus"},
        "best_balanced": {"preset": "accommodation_focus"},
    }
    champion_challenger = {
        "top_k_rerun": 2,
        "num_sessions": 8,
        "recommendations": {
            "best_overall": {
                "preset": "accommodation_focus",
                "claim_selection_overview": "Accommodation Theory [tags=reasonable_accommodation,contact]",
                "relief_selection_overview": "Corrective action requiring clear notice [families=process]",
                "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
            },
            "best_anchor_coverage": {"preset": "accommodation_focus"},
            "best_balanced": {"preset": "accommodation_focus"},
        },
    }

    MODULE._write_markdown_report(report_path, rows, recommendations, champion_challenger)
    report = report_path.read_text(encoding="utf-8")

    assert "### Unified Winner Snapshot" in report
    assert "## Champion Challenger" in report
    assert "- Reran top 2 presets with 8 sessions each." in report
    assert "- Unified champion: `accommodation_focus`" in report
    assert "- Applies to: best overall, best anchor coverage, best balanced" in report
    assert "### Unified Champion Snapshot" in report
    assert "- Overview: Accommodation Theory [tags=reasonable_accommodation,contact]" in report
    assert "- Relief overview: Corrective action requiring clear notice [families=process]" in report


def test_markdown_report_includes_winner_vs_runner_up_delta(tmp_path):
    report_path = tmp_path / "preset_matrix_summary.md"
    rows = [
        {
            "preset": "accommodation_focus",
            "backend_id": "llm-router-codex",
            "average_score": 0.75,
            "successful_sessions": 3,
            "total_sessions": 3,
            "anchor_coverage": 1.0,
            "router_status": "available",
            "top_missing_sections": "",
            "missing_sections": "",
            "output_dir": "/tmp/accommodation_focus",
            "claim_selection_overview": "winner overview",
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
        },
        {
            "preset": "administrative_plan_retaliation",
            "backend_id": "llm-router-codex",
            "average_score": 0.70,
            "successful_sessions": 3,
            "total_sessions": 3,
            "anchor_coverage": 0.9,
            "router_status": "available",
            "top_missing_sections": "",
            "missing_sections": "",
            "output_dir": "/tmp/administrative_plan_retaliation",
            "claim_selection_overview": "runner overview",
            "synthesis_output_dir": "/tmp/administrative_plan_retaliation/complaint_synthesis",
        },
    ]
    recommendations = {
        "best_overall": {"preset": "accommodation_focus"},
        "best_anchor_coverage": {"preset": "accommodation_focus"},
        "best_balanced": {"preset": "accommodation_focus"},
    }
    winner_delta = {
        "winner_preset": "accommodation_focus",
        "runner_up_preset": "administrative_plan_retaliation",
        "winner_only_theory_families": ["protected_basis"],
        "runner_up_only_theory_families": ["retaliation"],
        "shared_theory_families": ["accommodation"],
        "winner_relief_overview": "winner relief overview",
        "runner_up_relief_overview": "runner relief overview",
        "winner_only_relief_families": ["protected_basis"],
        "runner_up_only_relief_families": ["retaliation"],
        "shared_relief_families": ["process"],
        "winner_only_claims": ["Protected-Basis Administrative Theory"],
        "runner_up_only_claims": ["Retaliation for Protected Fair Housing Activity"],
        "winner_only_relief": ["Protected-basis remedies."],
        "runner_up_only_relief": ["Retaliation remedies."],
        "changed_shared_claims": [
            {
                "title": "Accommodation Theory",
                "winner_tags": ["reasonable_accommodation", "contact"],
                "runner_up_tags": ["reasonable_accommodation"],
                "winner_exhibits": ["Exhibit B: ADMINISTRATIVE PLAN"],
                "runner_up_exhibits": ["Exhibit A: ACOP"],
            }
        ],
        "changed_shared_relief": [
            {
                "text": "Corrective action requiring clear notice.",
                "winner_families": ["process"],
                "runner_up_families": ["process", "retaliation"],
                "winner_role": "shared_baseline",
                "runner_up_role": "runner_up_emphasis",
            }
        ],
    }

    MODULE._write_markdown_report(report_path, rows, recommendations, None, winner_delta)
    report = report_path.read_text(encoding="utf-8")

    assert "### Winner Vs Runner-Up" in report
    assert "- Winner: `accommodation_focus`" in report
    assert "- Runner-up: `administrative_plan_retaliation`" in report
    assert "- Winner-only theory families: protected_basis" in report
    assert "- Runner-up-only theory families: retaliation" in report
    assert "- Shared theory families: accommodation" in report
    assert "- Claim posture note: The winner added stronger protected-basis framing theories, while the runner-up leaned more heavily on retaliation-heavy framing theories." in report
    assert "- Winner relief overview: winner relief overview" in report
    assert "- Runner-up relief overview: runner relief overview" in report
    assert "- Winner-only relief families: protected_basis" in report
    assert "- Runner-up-only relief families: retaliation" in report
    assert "- Shared relief families: process" in report
    assert "- Winner-only claims: Protected-Basis Administrative Theory" in report
    assert "- Runner-up-only claims: Retaliation for Protected Fair Housing Activity" in report
    assert "- Winner-only relief items: Protected-basis remedies." in report
    assert "- Runner-up-only relief items: Retaliation remedies." in report
    assert "Shared claim changed: Accommodation Theory | winner tags=reasonable_accommodation, contact" in report
    assert "Shared relief changed: Corrective action requiring clear notice. | winner families=process | runner-up families=process, retaliation" in report


def test_markdown_report_suppresses_shared_relief_other_placeholder(tmp_path):
    report_path = tmp_path / "preset_matrix_summary.md"
    rows = [
        {
            "preset": "accommodation_focus",
            "backend_id": "llm-router-codex",
            "average_score": 0.75,
            "successful_sessions": 1,
            "total_sessions": 1,
            "anchor_coverage": 1.0,
            "router_status": "available",
            "top_missing_sections": "",
            "missing_sections": "",
            "output_dir": "/tmp/accommodation_focus",
        },
        {
            "preset": "administrative_plan_retaliation",
            "backend_id": "llm-router-codex",
            "average_score": 0.70,
            "successful_sessions": 1,
            "total_sessions": 1,
            "anchor_coverage": 0.9,
            "router_status": "available",
            "top_missing_sections": "",
            "missing_sections": "",
            "output_dir": "/tmp/administrative_plan_retaliation",
        },
    ]
    recommendations = {
        "best_overall": {"preset": "accommodation_focus"},
        "best_anchor_coverage": {"preset": "accommodation_focus"},
        "best_balanced": {"preset": "accommodation_focus"},
    }
    winner_delta = {
        "winner_preset": "accommodation_focus",
        "runner_up_preset": "administrative_plan_retaliation",
        "winner_only_theory_families": ["accommodation"],
        "runner_up_only_theory_families": ["retaliation"],
        "shared_theory_families": ["process"],
        "shared_relief_families": ["other"],
    }

    MODULE._write_markdown_report(report_path, rows, recommendations, None, winner_delta)
    report = report_path.read_text(encoding="utf-8")

    assert "- Claim posture note: The winner added stronger accommodation framing theories, while the runner-up leaned more heavily on retaliation-heavy framing theories." in report
    assert "- Shared relief families:" not in report


def test_markdown_report_collapses_identical_relief_overviews_into_relief_posture_note(tmp_path):
    report_path = tmp_path / "preset_matrix_summary.md"
    rows = [
        {
            "preset": "accommodation_focus",
            "backend_id": "llm-router-codex",
            "average_score": 0.75,
            "successful_sessions": 1,
            "total_sessions": 1,
            "anchor_coverage": 1.0,
            "router_status": "available",
            "top_missing_sections": "",
            "missing_sections": "",
            "output_dir": "/tmp/accommodation_focus",
        },
        {
            "preset": "administrative_plan_retaliation",
            "backend_id": "llm-router-codex",
            "average_score": 0.70,
            "successful_sessions": 1,
            "total_sessions": 1,
            "anchor_coverage": 0.9,
            "router_status": "available",
            "top_missing_sections": "",
            "missing_sections": "",
            "output_dir": "/tmp/administrative_plan_retaliation",
        },
    ]
    recommendations = {
        "best_overall": {"preset": "accommodation_focus"},
        "best_anchor_coverage": {"preset": "accommodation_focus"},
        "best_balanced": {"preset": "accommodation_focus"},
    }
    winner_delta = {
        "winner_preset": "accommodation_focus",
        "runner_up_preset": "administrative_plan_retaliation",
        "winner_only_theory_families": ["accommodation", "protected_basis"],
        "runner_up_only_theory_families": ["retaliation"],
        "shared_theory_families": ["process"],
        "winner_relief_overview": "same relief overview",
        "runner_up_relief_overview": "same relief overview",
        "winner_only_relief": [],
        "runner_up_only_relief": [],
        "winner_only_relief_families": [],
        "runner_up_only_relief_families": [],
        "shared_relief_families": ["other"],
    }

    MODULE._write_markdown_report(report_path, rows, recommendations, None, winner_delta)
    report = report_path.read_text(encoding="utf-8")

    assert "- Relief posture note: Relief posture was materially similar across the winner and runner-up, so the selection difference was driven mainly by claim posture." in report
    assert "- Winner relief overview:" not in report
    assert "- Runner-up relief overview:" not in report


def test_summary_json_can_record_partial_preset_errors(tmp_path):
    summary_path = tmp_path / "preset_matrix_summary.json"
    payload = {
        "timestamp": "2026-03-16T00:00:00+00:00",
        "presets": ["accommodation_focus", "administrative_plan_retaliation"],
        "recommendations": {"best_overall": {"preset": "accommodation_focus"}},
        "winner_delta": {},
        "rows": [{"preset": "accommodation_focus"}],
        "details": [{"preset": "accommodation_focus"}],
        "champion_challenger": None,
        "errors": [{"preset": "administrative_plan_retaliation", "error": "quota exceeded"}],
    }

    summary_path.write_text(__import__("json").dumps(payload, indent=2), encoding="utf-8")
    loaded = __import__("json").loads(summary_path.read_text(encoding="utf-8"))

    assert loaded["errors"][0]["preset"] == "administrative_plan_retaliation"
    assert loaded["errors"][0]["error"] == "quota exceeded"


def test_write_matrix_outputs_persists_remediation_fields(tmp_path):
    matrix_rows = [
        {
            "preset": "accommodation_focus",
            "backend_id": "llm-router-codex",
            "hacc_search_mode": "hybrid",
            "effective_hacc_search_mode": "lexical_only",
            "hacc_search_fallback_note": "fallback",
            "average_score": 0.8,
            "successful_sessions": 2,
            "total_sessions": 2,
            "anchor_coverage": 0.9,
            "router_status": "available",
            "top_missing_sections": "appeal_rights (1)",
            "top_intake_gaps": "anchor_appeal_rights (0/1)",
            "remediation_focus": "anchor=appeal_rights; intake=anchor_appeal_rights",
            "coverage_remediation": {
                "anchor_sections": {"missing_sections": ["appeal_rights"]},
                "intake_priorities": {"uncovered_objectives": ["anchor_appeal_rights"]},
            },
            "missing_sections": "appeal_rights",
            "output_dir": "/tmp/accommodation_focus",
            "claim_selection_overview": "winner overview",
            "relief_selection_overview": "relief overview",
            "claim_theory_families": ["accommodation"],
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
        }
    ]
    full_results = [
        {
            "preset": "accommodation_focus",
            "optimizer_report": {
                "coverage_remediation": {
                    "anchor_sections": {"missing_sections": ["appeal_rights"]},
                    "intake_priorities": {"uncovered_objectives": ["anchor_appeal_rights"]},
                }
            },
            "coverage_remediation": {
                "anchor_sections": {"missing_sections": ["appeal_rights"]},
                "intake_priorities": {"uncovered_objectives": ["anchor_appeal_rights"]},
            },
        }
    ]
    recommendations = {
        "best_overall": {
            "preset": "accommodation_focus",
            "hacc_search_mode": "hybrid",
            "effective_hacc_search_mode": "lexical_only",
            "hacc_search_fallback_note": "fallback",
        }
    }

    MODULE._write_matrix_outputs(
        output_dir=tmp_path,
        requested_presets=["accommodation_focus"],
        matrix_rows=matrix_rows,
        full_results=full_results,
        recommendations=recommendations,
        winner_delta={},
        challenger_summary=None,
        preset_errors=[],
    )

    summary = __import__("json").loads((tmp_path / "preset_matrix_summary.json").read_text(encoding="utf-8"))
    csv_text = (tmp_path / "preset_matrix_summary.csv").read_text(encoding="utf-8")
    markdown = (tmp_path / "preset_matrix_summary.md").read_text(encoding="utf-8")
    persisted_full_results = summary.get("details") or summary.get("full_results") or []

    assert summary["rows"][0]["top_intake_gaps"] == "anchor_appeal_rights (0/1)"
    assert summary["rows"][0]["remediation_focus"] == "anchor=appeal_rights; intake=anchor_appeal_rights"
    assert summary["rows"][0]["coverage_remediation"]["anchor_sections"]["missing_sections"] == ["appeal_rights"]
    assert persisted_full_results[0]["coverage_remediation"]["intake_priorities"]["uncovered_objectives"] == [
        "anchor_appeal_rights"
    ]
    assert summary["recommendations"]["best_overall"]["hacc_search_mode"] == "hybrid"
    assert summary["recommendations"]["best_overall"]["effective_hacc_search_mode"] == "lexical_only"
    assert summary["recommendations"]["best_overall"]["hacc_search_fallback_note"] == "fallback"
    assert "top_intake_gaps,remediation_focus" in csv_text
    assert "anchor_appeal_rights (0/1)" in markdown
    assert "anchor=appeal_rights; intake=anchor_appeal_rights" in markdown
