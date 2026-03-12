from pathlib import Path

from fastapi.testclient import TestClient

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
    assert "signal-archive-captures" in content
    assert "signal-fallback-authorities" in content
    assert "signal-low-quality-records" in content
    assert "signal-parse-quality-tasks" in content
    assert "signal-supportive-authorities" in content
    assert "signal-adverse-authorities" in content
    assert "execution-result-card" in content
    assert "parse_quality_recommendation" in content
    assert "authority_treatment_summary" in content
    assert "authority_search_program_summary" in content
    assert "authority program ${task.authority_search_program_summary.primary_program_type}" in content
    assert "authority bias ${task.authority_search_program_summary.primary_program_bias}" in content
    assert "rule bias ${task.authority_search_program_summary.primary_program_rule_bias}" in content
    assert "History programs: ${selectedProgramTypes.map(([label, count]) => `${label}=${count}`).join(', ')}" in content
    assert "History biases: ${selectedProgramBiases.map(([label, count]) => `${label}=${count}`).join(', ')}" in content
    assert "History rule biases: ${selectedProgramRuleBiases.map(([label, count]) => `${label}=${count}`).join(', ')}" in content
    assert "program: ${entry.selected_search_program_type}" in content
    assert "recommended_next_action" in content
    assert "Lineage Signals" in content
    assert "Parse Signals" in content
    assert "Authority Signals" in content
    assert "View lineage packets" in content
    assert "packet-details" in content
    assert "All packets" in content
    assert "Archived only" in content
    assert "Fallback only" in content
    assert "data-packet-filter-button" in content
    assert "packet-filter-count" in content
    assert "data-packet-filter-summary" in content
    assert "Showing ${visibleCount} of ${totalCount} packets" in content
    assert "data-packet-url-action" in content
    assert "Open archive" in content
    assert "Copy archive" in content
    assert "Open original" in content
    assert "Copy original" in content
    assert "data-packet-action-feedback" in content
    assert "setPacketActionFeedback" in content
    assert "packetSortRank" in content
    assert "sortSupportPackets" in content


def test_landing_pages_link_to_claim_support_review_dashboard():
    index_content = Path("templates/index.html").read_text()
    home_content = Path("templates/home.html").read_text()

    assert "/claim-support-review" in index_content
    assert "/claim-support-review" in home_content


def test_document_template_exists_and_targets_document_endpoints():
    template_path = Path("templates/document.html")

    assert template_path.exists()
    content = template_path.read_text()
    assert "/api/documents/formal-complaint" in content
    assert "download_url" in content
    assert "Formal Complaint Builder" in content
    assert "Generate Formal Complaint" in content
    assert "Requested Relief Overrides" in content
    assert "Draft Preview" in content


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
        route.path == "/document" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/documents/formal-complaint" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/health" and "GET" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )


def test_review_surface_document_route_serves_builder_template():
	app = create_review_surface_app(mediator=object())
	client = TestClient(app)

	response = client.get("/document")

	assert response.status_code == 200
	assert "Formal Complaint Builder" in response.text
	assert "/api/documents/formal-complaint" in response.text