from pathlib import Path

from applications.review_ui import create_review_dashboard_app, create_review_surface_app


def test_claim_support_review_template_exists_and_targets_review_endpoints():
    template_path = Path("templates/claim_support_review.html")

    assert template_path.exists()
    content = template_path.read_text()
    assert "/api/claim-support/review" in content
    assert "/api/claim-support/execute-follow-up" in content
    assert "/api/claim-support/resolve-manual-review" in content
    assert "Load Review" in content
    assert "Execute Follow-Up" in content
    assert "resolution-result-card" in content


def test_landing_pages_link_to_claim_support_review_dashboard():
    index_content = Path("templates/index.html").read_text()
    home_content = Path("templates/home.html").read_text()

    assert "/claim-support-review" in index_content
    assert "/claim-support-review" in home_content


def test_review_dashboard_app_registers_claim_support_review_page():
    app = create_review_dashboard_app()

    assert any(
        route.path == "/claim-support-review" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/health" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )


def test_review_surface_app_registers_dashboard_and_api_routes():
    app = create_review_surface_app(mediator=object())

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
        route.path == "/health" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )