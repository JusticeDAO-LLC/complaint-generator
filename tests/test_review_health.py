from applications.review_ui import create_review_dashboard_app, create_review_surface_app


async def test_review_dashboard_health_endpoint_returns_surface_metadata():
    app = create_review_dashboard_app()
    health_route = next(
        route for route in app.routes if getattr(route, "path", None) == "/health"
    )

    payload = await health_route.endpoint()

    assert payload["status"] == "healthy"
    assert payload["surface"] == "review-dashboard"
    assert payload["timestamp"]


async def test_review_surface_health_endpoint_returns_surface_metadata():
    app = create_review_surface_app(mediator=object())
    health_route = next(
        route for route in app.routes if getattr(route, "path", None) == "/health"
    )

    payload = await health_route.endpoint()

    assert payload["status"] == "healthy"
    assert payload["surface"] == "review-surface"
    assert payload["timestamp"]