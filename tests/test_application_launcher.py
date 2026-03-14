from pathlib import Path
import json

from applications.launcher import (
    _run_adversarial_autopatch_app,
    canonicalize_application_type,
    create_uvicorn_app_for_type,
    launch_application,
    normalize_application_types,
)


def test_normalize_application_types_supports_legacy_object_config():
    assert normalize_application_types({"review": "review-surface"}) == ["review-surface"]


def test_canonicalize_application_type_supports_underscore_alias():
    assert canonicalize_application_type("review_surface") == "review-surface"


def test_canonicalize_application_type_supports_adversarial_autopatch_alias():
    assert canonicalize_application_type("adversarial_autopatch") == "adversarial-autopatch"


def test_create_uvicorn_app_for_review_surface_registers_ui_and_api_routes():
    app = create_uvicorn_app_for_type("review-surface", mediator=object())

    assert any(
        route.path == "/claim-support-review" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/review" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/execute-follow-up" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/documents/formal-complaint" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/documents/download" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/document" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/health" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )


def test_launch_application_uses_uvicorn_runner_for_review_surface(monkeypatch):
    observed = {}

    def _fake_run_uvicorn_app(app, application_config):
        observed["app"] = app
        observed["application_config"] = dict(application_config)

    monkeypatch.setattr("applications.launcher._run_uvicorn_app", _fake_run_uvicorn_app)

    launch_application(
        "review-surface",
        mediator=object(),
        application_config={"host": "127.0.0.1", "port": 8765, "reload": False},
        background=False,
    )

    assert observed["app"].title == "Complaint Generator Review Surface"
    assert observed["application_config"] == {"host": "127.0.0.1", "port": 8765, "reload": False}


def test_launch_application_runs_adversarial_autopatch(monkeypatch):
    observed = {}

    def _fake_run_adversarial_autopatch_app(mediator, application_config):
        observed["application_config"] = dict(application_config)
        observed["mediator"] = mediator

    monkeypatch.setattr("applications.launcher._run_adversarial_autopatch_app", _fake_run_adversarial_autopatch_app)

    launch_application(
        "adversarial-autopatch",
        mediator=object(),
        application_config={"output_dir": "/tmp/autopatch", "num_sessions": 2},
        background=False,
    )

    assert observed["application_config"] == {"output_dir": "/tmp/autopatch", "num_sessions": 2}
    assert observed["mediator"] is not None


def test_run_adversarial_autopatch_app_prints_payload(monkeypatch, capsys):
    monkeypatch.setattr(
        "applications.launcher.run_adversarial_autopatch_batch",
        lambda **kwargs: {
            "num_results": 1,
            "report": {"average_score": 0.7},
            "autopatch": {"success": True, "patch_path": "/tmp/demo.patch", "patch_cid": "cid"},
        },
    )

    _run_adversarial_autopatch_app(object(), {"output_dir": "/tmp/autopatch", "demo_backend": True})

    payload = json.loads(capsys.readouterr().out)
    assert payload["num_results"] == 1
    assert payload["autopatch"]["success"] is True


def test_requirements_declare_uvicorn_for_web_applications():
    requirements_path = Path(__file__).resolve().parent.parent / "requirements.txt"
    requirements_text = requirements_path.read_text(encoding="utf-8")

    assert "uvicorn" in requirements_text