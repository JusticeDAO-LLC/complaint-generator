import json
import sys
from threading import Thread
from typing import Any, Dict, List

from adversarial_harness.demo_autopatch import run_adversarial_autopatch_batch

from .cli import CLI
from .review_api import create_review_api_app
from .review_ui import create_review_dashboard_app, create_review_surface_app
from .server import SERVER


_WEB_APPLICATION_TYPES = {
    "server",
    "review-api",
    "review-dashboard",
    "review-surface",
}


def normalize_application_types(type_config: Any) -> List[str]:
    if isinstance(type_config, dict):
        raw_types = list(type_config.values())
    elif isinstance(type_config, list):
        raw_types = type_config
    elif isinstance(type_config, str):
        raw_types = [type_config]
    else:
        raise ValueError(f"unsupported application type configuration: {type(type_config)!r}")

    return [canonicalize_application_type(value) for value in raw_types]


def canonicalize_application_type(app_type: Any) -> str:
    normalized = str(app_type or "").strip().lower().replace("_", "-")
    if normalized in {"cli", "server", "review-api", "review-dashboard", "review-surface", "adversarial-autopatch"}:
        return normalized
    raise ValueError(f"unknown application type: {app_type}")


def create_uvicorn_app_for_type(app_type: str, mediator: Any):
    canonical = canonicalize_application_type(app_type)
    if canonical == "review-api":
        return create_review_api_app(mediator)
    if canonical == "review-dashboard":
        return create_review_dashboard_app()
    if canonical == "review-surface":
        return create_review_surface_app(mediator)
    return None


def _run_uvicorn_app(app: Any, application_config: Dict[str, Any]) -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=application_config.get("host", "0.0.0.0"),
        port=application_config.get("port", 8000),
        reload=bool(application_config.get("reload", False)),
    )


def _run_adversarial_autopatch_app(mediator: Any, application_config: Dict[str, Any]) -> None:
    project_root = application_config.get("project_root")
    if not project_root:
        project_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)

    output_dir = application_config.get("output_dir")
    if not output_dir:
        output_dir = str(__import__("pathlib").Path(project_root) / "tmp" / "launched_adversarial_autopatch")

    payload = run_adversarial_autopatch_batch(
        project_root=project_root,
        output_dir=output_dir,
        target_file=application_config.get("target_file", "adversarial_harness/session.py"),
        num_sessions=int(application_config.get("num_sessions", 1) or 1),
        max_turns=int(application_config.get("max_turns", 2) or 2),
        max_parallel=int(application_config.get("max_parallel", 1) or 1),
        session_state_dir=application_config.get("session_state_dir"),
        marker_prefix=str(application_config.get("marker_prefix", "Launcher autopatch recommendation")),
        demo_backend=bool(application_config.get("demo_backend", False)),
        backends=getattr(mediator, "backends", None),
    )
    warnings = list(((payload.get("runtime") or {}).get("preflight_warnings") or []))
    if warnings:
        print("adversarial-autopatch preflight warnings:", file=sys.stderr)
        for warning in warnings:
            print(f"- {warning}", file=sys.stderr)
    print(json.dumps(payload, indent=2))


def launch_application(
    app_type: str,
    mediator: Any,
    application_config: Dict[str, Any],
    background: bool = False,
) -> None:
    canonical = canonicalize_application_type(app_type)

    if canonical == "cli":
        if background:
            raise ValueError("cli cannot be launched in background mode")
        CLI(mediator)
        return

    if canonical == "adversarial-autopatch":
        if background:
            raise ValueError("adversarial-autopatch cannot be launched in background mode")
        _run_adversarial_autopatch_app(mediator, application_config)
        return

    if canonical == "server":
        target = SERVER
        args = (mediator,)
    else:
        app = create_uvicorn_app_for_type(canonical, mediator)
        target = _run_uvicorn_app
        args = (app, application_config)

    if background:
        thread = Thread(target=target, args=args, daemon=True)
        thread.start()
        return

    target(*args)


def start_configured_applications(mediator: Any, application_config: Dict[str, Any]) -> None:
    application_types = normalize_application_types(application_config.get("type", []))
    web_types = [app_type for app_type in application_types if app_type in _WEB_APPLICATION_TYPES]

    if len(web_types) > 1:
        raise ValueError(
            "multiple web application types are not supported in one process; choose one of "
            "server, review-api, review-dashboard, or review-surface"
        )

    if "cli" in application_types and web_types:
        launch_application(web_types[0], mediator, application_config, background=True)
        launch_application("cli", mediator, application_config, background=False)
        return

    for app_type in application_types:
        launch_application(app_type, mediator, application_config, background=False)