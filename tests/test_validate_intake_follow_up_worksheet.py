import json
import subprocess
import sys
import tempfile
from pathlib import Path


def test_validate_intake_follow_up_worksheet_script_normalizes_statuses_and_writes_output():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "validate_intake_follow_up_worksheet.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        worksheet_path = tmp_path / "intake_follow_up_worksheet.json"
        output_path = tmp_path / "normalized_intake_follow_up_worksheet.json"
        worksheet_path.write_text(
            json.dumps(
                {
                    "follow_up_items": [
                        {
                            "id": "follow_up_01",
                            "question": "When did the key events happen?",
                            "answer": "January 15, 2026.",
                            "status": "open",
                        },
                        {
                            "id": "follow_up_02",
                            "question": "Who at HACC made the decision?",
                            "answer": "",
                            "status": "answered",
                        },
                        {
                            "id": "follow_up_03",
                            "question": "",
                            "answer": "",
                            "status": "open",
                        },
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, str(script_path), str(worksheet_path), "--output", str(output_path)],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        assert result.returncode == 0, (
            f"validator failed with code {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        assert "Intake worksheet validation passed" in result.stdout
        assert output_path.is_file()

        payload = json.loads(output_path.read_text(encoding="utf-8"))
        items = list(payload.get("follow_up_items") or [])
        assert items[0]["status"] == "answered"
        assert items[1]["status"] == "open"
        assert items[2]["status"] == "invalid"
        summary = dict(payload.get("validation_summary") or {})
        assert summary["item_count"] == 3
        assert summary["status_counts"]["answered"] == 1
        assert summary["status_counts"]["open"] == 1
        assert summary["status_counts"]["invalid"] == 1


def test_validate_intake_follow_up_worksheet_require_complete_fails_for_open_items():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "validate_intake_follow_up_worksheet.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        worksheet_path = tmp_path / "intake_follow_up_worksheet.json"
        worksheet_path.write_text(
            json.dumps(
                {
                    "follow_up_items": [
                        {
                            "id": "follow_up_01",
                            "question": "When did the key events happen?",
                            "answer": "",
                            "status": "open",
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, str(script_path), str(worksheet_path), "--require-complete"],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        assert result.returncode == 2
        assert "Worksheet is not complete enough for rerun preflight" in result.stderr


def test_validate_intake_follow_up_worksheet_require_complete_passes_when_all_answered():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "validate_intake_follow_up_worksheet.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        worksheet_path = tmp_path / "intake_follow_up_worksheet.json"
        worksheet_path.write_text(
            json.dumps(
                {
                    "follow_up_items": [
                        {
                            "id": "follow_up_01",
                            "question": "When did the key events happen?",
                            "answer": "January 15, 2026.",
                            "status": "open",
                        },
                        {
                            "id": "follow_up_02",
                            "question": "Who at HACC made the decision?",
                            "answer": "A housing specialist named in the notice.",
                            "status": "open",
                        },
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, str(script_path), str(worksheet_path), "--require-complete"],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "Intake worksheet validation passed" in result.stdout
