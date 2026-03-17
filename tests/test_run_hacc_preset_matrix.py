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
            "relief_selection_overview": (
                "Corrective action requiring clear notice, fair review, and non-retaliation safeguards. "
                "[families=process; role=shared_baseline]"
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
    assert "- Relief overview: Corrective action requiring clear notice, fair review, and non-retaliation safeguards." in report
    assert "- Complaint synthesis: `/tmp/accommodation_focus/complaint_synthesis`" in report


def test_attach_recommendation_claim_snapshots_enriches_best_overall():
    rows = [
        {
            "preset": "accommodation_focus",
            "claim_selection_overview": "Accommodation Theory [tags=reasonable_accommodation,contact]",
            "relief_selection_overview": "Corrective action requiring clear notice [families=process]",
            "claim_theory_families": ["accommodation", "process"],
            "synthesis_output_dir": "/tmp/accommodation_focus/complaint_synthesis",
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
    assert "tradeoff_note" not in enriched["best_anchor_coverage"]


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

    assert "### Best Overall Claim Snapshot" in report
    assert "## Champion Challenger" in report
    assert "- Reran top 2 presets with 8 sessions each." in report
    assert "### Champion Claim Snapshot" in report
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
