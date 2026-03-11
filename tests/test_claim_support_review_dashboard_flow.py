from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi import Response
from fastapi.responses import HTMLResponse

from applications.review_api import attach_claim_support_review_routes
from claim_support_review import (
    ClaimSupportFollowUpExecuteRequest,
    ClaimSupportReviewRequest,
)


def _build_dashboard_app(mediator: Mock) -> FastAPI:
    app = FastAPI()
    attach_claim_support_review_routes(app, mediator)

    @app.get("/claim-support-review", response_class=HTMLResponse)
    async def claim_support_review_page() -> str:
        return Path("templates/claim_support_review.html").read_text()

    return app


def _build_dashboard_mediator() -> Mock:
    mediator = Mock()
    mediator.state = SimpleNamespace(username="dashboard-user", hashed_username=None)
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "total_elements": 2,
                "total_links": 2,
                "total_facts": 3,
                "support_by_kind": {"evidence": 1, "authority": 1},
                "status_counts": {
                    "covered": 1,
                    "partially_supported": 0,
                    "missing": 1,
                },
                "elements": [
                    {
                        "element_text": "Protected activity",
                        "status": "covered",
                        "fact_count": 2,
                        "total_links": 2,
                        "missing_support_kinds": [],
                        "links_by_kind": {
                            "evidence": [
                                {
                                    "support_label": "Timeline email",
                                    "graph_summary": {
                                        "entity_count": 2,
                                        "relationship_count": 1,
                                    },
                                }
                            ]
                        },
                    }
                ],
            }
        }
    }
    mediator.get_claim_overview.return_value = {
        "claims": {
            "retaliation": {
                "missing": [{"element_text": "Causal connection"}],
                "partially_supported": [],
            }
        }
    }
    mediator.get_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 1,
                "blocked_task_count": 0,
                "tasks": [
                    {
                        "claim_element": "Causal connection",
                        "status": "missing",
                        "priority": "high",
                        "recommended_action": "retrieve_more_support",
                        "missing_support_kinds": ["authority"],
                        "blocked_by_cooldown": False,
                        "should_suppress_retrieval": False,
                    }
                ],
            }
        }
    }
    mediator.summarize_claim_support.return_value = {
        "claims": {
            "retaliation": {
                "total_links": 2,
                "support_by_kind": {"evidence": 1, "authority": 1},
            }
        }
    }
    mediator.execute_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 1,
                "tasks": [{"claim_element": "Causal connection"}],
                "skipped_tasks": [],
            }
        }
    }
    return mediator


async def test_claim_support_review_dashboard_flow_serves_page_and_supports_api_round_trip():
    mediator = _build_dashboard_mediator()
    app = _build_dashboard_app(mediator)
    page_route = next(
        route for route in app.routes if getattr(route, "path", None) == "/claim-support-review"
    )
    review_route = next(
        route for route in app.routes if getattr(route, "path", None) == "/api/claim-support/review"
    )
    execute_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/claim-support/execute-follow-up"
    )

    page_html = await page_route.endpoint()

    soup = BeautifulSoup(page_html, "html.parser")
    assert soup.find(id="claim-type") is not None
    assert soup.find(id="required-kinds") is not None
    assert soup.find(id="review-button") is not None
    assert soup.find(id="execute-button") is not None

    review_payload = await review_route.endpoint(
        ClaimSupportReviewRequest(
            claim_type="retaliation",
            required_support_kinds=["evidence", "authority"],
            include_follow_up_plan=True,
            include_support_summary=True,
            include_overview=True,
            execute_follow_up=False,
            follow_up_cooldown_seconds=3600,
            follow_up_max_tasks_per_claim=2,
        ),
        Response(),
    )
    assert review_payload["user_id"] == "dashboard-user"
    assert review_payload["claim_coverage_summary"]["retaliation"]["missing_elements"] == [
        "Causal connection"
    ]
    assert review_payload["follow_up_plan_summary"]["retaliation"]["task_count"] == 1

    execute_payload = await execute_route.endpoint(
        ClaimSupportFollowUpExecuteRequest(
            claim_type="retaliation",
            required_support_kinds=["evidence", "authority"],
            follow_up_support_kind="authority",
            follow_up_max_tasks_per_claim=1,
            follow_up_force=False,
            include_post_execution_review=True,
            include_support_summary=True,
            include_overview=True,
            include_follow_up_plan=True,
        ),
    )
    assert execute_payload["follow_up_execution"]["retaliation"]["task_count"] == 1
    assert execute_payload["post_execution_review"]["claim_coverage_summary"]["retaliation"][
        "missing_elements"
    ] == ["Causal connection"]