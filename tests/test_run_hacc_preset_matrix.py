import importlib.util
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


def test_markdown_report_includes_claim_selection_snapshots(tmp_path):
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
            "claim_selection_overview": (
                "Accommodation Theory [tags=reasonable_accommodation,contact; "
                "exhibits=Exhibit B: ADMINISTRATIVE PLAN; "
                "rationale=selected for stronger accommodation contact-language]"
            ),
            "claim_theory_families": ["accommodation", "process"],
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
        }
    ]
    recommendations = {
        "best_overall": {"preset": "accommodation_focus", "claim_theory_families": ["accommodation", "process"]},
        "best_anchor_coverage": {"preset": "accommodation_focus"},
        "best_balanced": {"preset": "accommodation_focus"},
    }

    MODULE._write_markdown_report(report_path, rows, recommendations)
    report = report_path.read_text(encoding="utf-8")

    assert "- Best overall: `accommodation_focus` (accommodation, process) - best for accommodation framing + process framing" in report
    assert "## Claim Selection Snapshots" in report
    assert "### accommodation_focus" in report
    assert "- Overview: Accommodation Theory [tags=reasonable_accommodation,contact;" in report
    assert "- Complaint synthesis: `/tmp/accommodation_focus/complaint_synthesis`" in report


def test_attach_recommendation_claim_snapshots_enriches_best_overall():
    rows = [
        {
            "preset": "accommodation_focus",
            "claim_selection_overview": "Accommodation Theory [tags=reasonable_accommodation,contact]",
            "claim_theory_families": ["accommodation", "process"],
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
        }
    ]
    recommendations = {
        "best_overall": {"preset": "accommodation_focus", "average_score": 0.75, "anchor_coverage": 1.0},
    }

    enriched = MODULE._attach_recommendation_claim_snapshots(recommendations, rows)

    assert enriched["best_overall"]["claim_selection_overview"] == "Accommodation Theory [tags=reasonable_accommodation,contact]"
    assert enriched["best_overall"]["claim_theory_families"] == ["accommodation", "process"]
    assert enriched["best_overall"]["synthesis_output_dir"] == "/tmp/accommodation_focus/complaint_synthesis"


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


def test_build_claim_snapshot_delta_identifies_winner_only_and_changed_shared_claims():
    rows = [
        {"preset": "accommodation_focus", "average_score": 0.9, "anchor_coverage": 1.0},
        {"preset": "administrative_plan_retaliation", "average_score": 0.7, "anchor_coverage": 0.9},
    ]
    details = [
        {
            "preset": "accommodation_focus",
            "claim_selection_overview": "winner overview",
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
        },
        {
            "preset": "administrative_plan_retaliation",
            "claim_selection_overview": "runner overview",
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
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
        }
    ]
    recommendations = {
        "best_overall": {
            "preset": "accommodation_focus",
            "claim_selection_overview": "Accommodation Theory [tags=reasonable_accommodation,contact]",
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
                "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
            },
            "best_anchor_coverage": {"preset": "accommodation_focus"},
            "best_balanced": {"preset": "accommodation_focus"},
        },
    }

    MODULE._write_markdown_report(report_path, rows, recommendations, champion_challenger)
    report = report_path.read_text(encoding="utf-8")

    assert "### Best Overall Claim Snapshot" in report
    assert "## Champion Challenger" in report
    assert "- Reran top 2 presets with 8 sessions each." in report
    assert "### Champion Claim Snapshot" in report
    assert "- Overview: Accommodation Theory [tags=reasonable_accommodation,contact]" in report


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
        "winner_only_claims": ["Protected-Basis Administrative Theory"],
        "runner_up_only_claims": ["Retaliation for Protected Fair Housing Activity"],
        "changed_shared_claims": [
            {
                "title": "Accommodation Theory",
                "winner_tags": ["reasonable_accommodation", "contact"],
                "runner_up_tags": ["reasonable_accommodation"],
                "winner_exhibits": ["Exhibit B: ADMINISTRATIVE PLAN"],
                "runner_up_exhibits": ["Exhibit A: ACOP"],
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
    assert "- Winner-only claims: Protected-Basis Administrative Theory" in report
    assert "- Runner-up-only claims: Retaliation for Protected Fair Housing Activity" in report
    assert "Shared claim changed: Accommodation Theory | winner tags=reasonable_accommodation, contact" in report
