from __future__ import annotations

import json
from pathlib import Path

from complaint_generator.email_seed_planner import build_email_seed_plan


def test_build_email_seed_plan_focuses_on_notice_chain(tmp_path: Path) -> None:
    package = {
        "summary": "HACC policy defines a grievance as a tenant dispute concerning HACC action or inaction.",
        "factual_allegations": [
            "Unresolved factual gaps still require exact dates, response timing, and event order.",
            "The notice must contain a brief statement of the reasons for the decision.",
        ],
        "supporting_evidence": [
            "ADMINISTRATIVE PLAN: notice to the applicant and request for informal review.",
        ],
    }
    worksheet = {
        "outstanding_intake_gaps": [
            "Written notice chain is referenced but the sending party/date/source artifact is still missing."
        ],
        "follow_up_items": [
            {
                "objective": "timeline",
                "question": "What written notice, letter, email, or message did you receive, who sent it, and what date is on it?",
                "gap": "written notice chain missing",
            },
            {
                "objective": "timeline",
                "question": "What are the exact dates for each notice, review request, response, and final decision?",
                "gap": "",
            },
        ],
    }
    package_path = tmp_path / "draft.json"
    worksheet_path = tmp_path / "worksheet.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")
    worksheet_path.write_text(json.dumps(worksheet), encoding="utf-8")

    payload = build_email_seed_plan(
        complaint_package_path=package_path,
        worksheet_path=worksheet_path,
    )

    assert "notice" in payload["complaint_email_keywords"]
    assert "hearing" in payload["complaint_email_keywords"] or "review" in payload["complaint_email_keywords"]
    assert payload["complaint_email_query"]
    assert payload["follow_up_questions"]
