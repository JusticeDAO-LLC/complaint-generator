from applications.launcher import (
    canonicalize_application_type,
    create_uvicorn_app_for_type,
    normalize_application_types,
)


def test_normalize_application_types_supports_legacy_object_config():
    assert normalize_application_types({"review": "review-surface"}) == ["review-surface"]


def test_canonicalize_application_type_supports_underscore_alias():
    assert canonicalize_application_type("review_surface") == "review-surface"


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