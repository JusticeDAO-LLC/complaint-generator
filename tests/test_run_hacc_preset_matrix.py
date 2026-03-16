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
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
        }
    ]
    recommendations = {
        "best_overall": {"preset": "accommodation_focus"},
        "best_anchor_coverage": {"preset": "accommodation_focus"},
        "best_balanced": {"preset": "accommodation_focus"},
    }

    MODULE._write_markdown_report(report_path, rows, recommendations)
    report = report_path.read_text(encoding="utf-8")

    assert "## Claim Selection Snapshots" in report
    assert "### accommodation_focus" in report
    assert "- Overview: Accommodation Theory [tags=reasonable_accommodation,contact;" in report
    assert "- Complaint synthesis: `/tmp/accommodation_focus/complaint_synthesis`" in report


def test_attach_recommendation_claim_snapshots_enriches_best_overall():
    rows = [
        {
            "preset": "accommodation_focus",
            "claim_selection_overview": "Accommodation Theory [tags=reasonable_accommodation,contact]",
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
        }
    ]
    recommendations = {
        "best_overall": {"preset": "accommodation_focus", "average_score": 0.75, "anchor_coverage": 1.0},
    }

    enriched = MODULE._attach_recommendation_claim_snapshots(recommendations, rows)

    assert enriched["best_overall"]["claim_selection_overview"] == "Accommodation Theory [tags=reasonable_accommodation,contact]"
    assert enriched["best_overall"]["synthesis_output_dir"] == "/tmp/accommodation_focus/complaint_synthesis"


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
