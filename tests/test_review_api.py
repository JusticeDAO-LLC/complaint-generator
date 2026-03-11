from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import Response
from claim_support_review import (
    ClaimSupportFollowUpExecuteRequest,
    ClaimSupportReviewRequest,
    build_claim_support_follow_up_execution_payload,
    build_claim_support_review_payload,
)
from applications.review_api import (
    REVIEW_EXECUTION_SUNSET,
    create_review_api_app,
)


def test_claim_support_review_payload_returns_matrix_and_summary():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "total_elements": 3,
                "total_links": 2,
                "total_facts": 4,
                "support_by_kind": {"evidence": 1, "authority": 1},
                "status_counts": {
                    "covered": 1,
                    "partially_supported": 1,
                    "missing": 1,
                },
                "elements": [],
            }
        }
    }
    mediator.get_claim_overview.return_value = {
        "claims": {
            "retaliation": {
                "missing": [{"element_text": "Causal connection"}],
                "partially_supported": [{"element_text": "Adverse action"}],
            }
        }
    }
    mediator.summarize_claim_support.return_value = {
        "claims": {
            "retaliation": {
                "support_by_kind": {"evidence": 1, "authority": 1},
                "total_links": 2,
            }
        }
    }
    mediator.get_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 2,
                "blocked_task_count": 1,
                "tasks": [
                    {
                        "claim_element": "Causal connection",
                        "recommended_action": "retrieve_more_support",
                        "has_graph_support": True,
                        "should_suppress_retrieval": False,
                        "graph_support": {
                            "summary": {
                                "semantic_cluster_count": 2,
                                "semantic_duplicate_count": 3,
                            }
                        },
                    },
                    {
                        "claim_element": "Adverse action",
                        "recommended_action": "target_missing_support_kind",
                        "has_graph_support": False,
                        "should_suppress_retrieval": True,
                        "graph_support": {"summary": {}},
                    },
                ],
            }
        }
    }
    mediator.execute_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 1,
                "tasks": [
                    {
                        "claim_element": "Causal connection",
                        "graph_support": {
                            "summary": {
                                "semantic_cluster_count": 1,
                                "semantic_duplicate_count": 2,
                            }
                        },
                    }
                ],
                "skipped_tasks": [
                    {
                        "claim_element": "Adverse action",
                        "graph_support": {
                            "summary": {
                                "semantic_cluster_count": 2,
                                "semantic_duplicate_count": 1,
                            }
                        },
                        "skipped": {
                            "suppressed": {"reason": "existing_support_high_duplication"}
                        },
                    },
                    {
                        "claim_element": "Protected activity",
                        "graph_support": {
                            "summary": {
                                "semantic_cluster_count": 0,
                                "semantic_duplicate_count": 1,
                            }
                        },
                        "skipped": {
                            "authority": {"reason": "duplicate_within_cooldown"}
                        },
                    },
                ],
            }
        }
    }

    payload = build_claim_support_review_payload(
        mediator,
        ClaimSupportReviewRequest(
            claim_type="retaliation",
            execute_follow_up=True,
            follow_up_support_kind="authority",
            follow_up_max_tasks_per_claim=2,
        ),
    )

    assert payload["user_id"] == "state-user"
    assert payload["claim_coverage_matrix"]["retaliation"]["status_counts"]["covered"] == 1
    assert payload["claim_coverage_summary"]["retaliation"]["missing_elements"] == [
        "Causal connection"
    ]
    assert payload["claim_coverage_summary"]["retaliation"][
        "partially_supported_elements"
    ] == ["Adverse action"]
    assert payload["support_summary"]["retaliation"]["total_links"] == 2
    assert payload["claim_overview"]["retaliation"]["missing"][0]["element_text"] == (
        "Causal connection"
    )
    assert payload["follow_up_plan"]["retaliation"]["task_count"] == 2
    assert payload["follow_up_plan_summary"]["retaliation"]["blocked_task_count"] == 1
    assert payload["follow_up_plan_summary"]["retaliation"]["suppressed_task_count"] == 1
    assert payload["follow_up_plan_summary"]["retaliation"]["semantic_cluster_count"] == 2
    assert payload["follow_up_plan_summary"]["retaliation"]["recommended_actions"] == {
        "retrieve_more_support": 1,
        "target_missing_support_kind": 1,
    }
    assert payload["follow_up_execution"]["retaliation"]["task_count"] == 1
    assert payload["follow_up_execution_summary"]["retaliation"]["executed_task_count"] == 1
    assert payload["follow_up_execution_summary"]["retaliation"]["skipped_task_count"] == 2
    assert payload["follow_up_execution_summary"]["retaliation"]["suppressed_task_count"] == 1
    assert payload["follow_up_execution_summary"]["retaliation"]["cooldown_skipped_task_count"] == 1
    assert payload["follow_up_execution_summary"]["retaliation"]["semantic_cluster_count"] == 3
    assert payload["follow_up_execution_summary"]["retaliation"]["semantic_duplicate_count"] == 4
    mediator.get_claim_coverage_matrix.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
        required_support_kinds=["evidence", "authority"],
    )
    mediator.get_claim_follow_up_plan.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
        required_support_kinds=["evidence", "authority"],
        cooldown_seconds=3600,
    )
    mediator.execute_claim_follow_up_plan.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
        support_kind="authority",
        max_tasks_per_claim=2,
        cooldown_seconds=3600,
    )


def test_claim_support_review_endpoint_allows_explicit_user_and_optional_sections():
    mediator = Mock()
    mediator.state = SimpleNamespace(username=None, hashed_username="hashed-user")
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {
            "civil rights": {
                "claim_type": "civil rights",
                "total_elements": 1,
                "total_links": 1,
                "total_facts": 1,
                "support_by_kind": {"authority": 1},
                "status_counts": {
                    "covered": 0,
                    "partially_supported": 1,
                    "missing": 0,
                },
                "elements": [],
            }
        }
    }
    mediator.get_claim_overview.return_value = {
        "claims": {
            "civil rights": {
                "missing": [],
                "partially_supported": [{"element_text": "Protected activity"}],
            }
        }
    }
    mediator.get_claim_follow_up_plan.return_value = {"claims": {}}

    payload = build_claim_support_review_payload(
        mediator,
        ClaimSupportReviewRequest(
            user_id="api-user",
            claim_type="civil rights",
            required_support_kinds=["authority"],
            include_support_summary=False,
            include_overview=False,
            include_follow_up_plan=False,
        ),
    )

    assert payload["user_id"] == "api-user"
    assert payload["required_support_kinds"] == ["authority"]
    assert "support_summary" not in payload
    assert "claim_overview" not in payload
    assert "follow_up_plan" not in payload
    assert "follow_up_plan_summary" not in payload
    assert "follow_up_execution" not in payload
    assert "follow_up_execution_summary" not in payload
    assert payload["claim_coverage_summary"]["civil rights"][
        "partially_supported_elements"
    ] == ["Protected activity"]
    mediator.summarize_claim_support.assert_not_called()
    mediator.get_claim_follow_up_plan.assert_not_called()
    mediator.execute_claim_follow_up_plan.assert_not_called()
    mediator.get_claim_overview.assert_called_once_with(
        claim_type="civil rights",
        user_id="api-user",
        required_support_kinds=["authority"],
    )


def test_claim_support_follow_up_execution_payload_returns_post_execution_review():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.execute_claim_follow_up_plan.return_value = {
        "claims": {
            "retaliation": {
                "task_count": 1,
                "tasks": [
                    {
                        "claim_element": "Causal connection",
                        "graph_support": {
                            "summary": {
                                "semantic_cluster_count": 1,
                                "semantic_duplicate_count": 0,
                            }
                        },
                    }
                ],
                "skipped_tasks": [],
            }
        }
    }
    mediator.get_claim_coverage_matrix.return_value = {
        "claims": {
            "retaliation": {
                "claim_type": "retaliation",
                "total_elements": 3,
                "total_links": 3,
                "total_facts": 5,
                "support_by_kind": {"evidence": 2, "authority": 1},
                "status_counts": {
                    "covered": 2,
                    "partially_supported": 0,
                    "missing": 1,
                },
                "elements": [],
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
                "tasks": [],
            }
        }
    }
    mediator.summarize_claim_support.return_value = {
        "claims": {
            "retaliation": {
                "total_links": 3,
                "support_by_kind": {"evidence": 2, "authority": 1},
            }
        }
    }

    payload = build_claim_support_follow_up_execution_payload(
        mediator,
        ClaimSupportFollowUpExecuteRequest(
            claim_type="retaliation",
            follow_up_support_kind="evidence",
            follow_up_max_tasks_per_claim=1,
            follow_up_force=True,
        ),
    )

    assert payload["user_id"] == "state-user"
    assert payload["follow_up_support_kind"] == "evidence"
    assert payload["follow_up_force"] is True
    assert payload["follow_up_execution"]["retaliation"]["task_count"] == 1
    assert payload["follow_up_execution_summary"]["retaliation"]["executed_task_count"] == 1
    assert payload["post_execution_review"]["claim_coverage_summary"]["retaliation"]["status_counts"]["covered"] == 2
    mediator.execute_claim_follow_up_plan.assert_called_once_with(
        claim_type="retaliation",
        user_id="state-user",
        support_kind="evidence",
        max_tasks_per_claim=1,
        cooldown_seconds=3600,
        force=True,
    )


def test_claim_support_follow_up_execution_payload_can_skip_post_review():
    mediator = Mock()
    mediator.state = SimpleNamespace(username=None, hashed_username="hashed-user")
    mediator.execute_claim_follow_up_plan.return_value = {"claims": {}}

    payload = build_claim_support_follow_up_execution_payload(
        mediator,
        ClaimSupportFollowUpExecuteRequest(
            user_id="api-user",
            claim_type="civil rights",
            include_post_execution_review=False,
        ),
    )

    assert payload["user_id"] == "api-user"
    assert "post_execution_review" not in payload
    mediator.get_claim_coverage_matrix.assert_not_called()
    mediator.get_claim_overview.assert_not_called()
    mediator.get_claim_follow_up_plan.assert_not_called()


def test_claim_support_review_endpoint_is_registered_on_app():
    mediator = Mock()

    app = create_review_api_app(mediator)

    assert any(
        route.path == "/api/claim-support/review" and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )
    assert any(
        route.path == "/api/claim-support/execute-follow-up"
        and "POST" in route.methods
        for route in app.routes
        if hasattr(route, "methods")
    )


async def test_claim_support_review_route_marks_execute_follow_up_as_deprecated():
    mediator = Mock()
    mediator.state = SimpleNamespace(username="state-user", hashed_username=None)
    mediator.get_claim_coverage_matrix.return_value = {"claims": {}}
    mediator.get_claim_overview.return_value = {"claims": {}}
    mediator.get_claim_follow_up_plan.return_value = {"claims": {}}
    mediator.execute_claim_follow_up_plan.return_value = {"claims": {}}
    mediator.summarize_claim_support.return_value = {"claims": {}}

    app = create_review_api_app(mediator)
    review_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/claim-support/review"
    )
    response = Response()

    payload = await review_route.endpoint(
        ClaimSupportReviewRequest(claim_type="retaliation", execute_follow_up=True),
        response,
    )

    assert payload["compatibility_notice"]["deprecated"] is True
    assert (
        payload["compatibility_notice"]["replacement_route"]
        == "/api/claim-support/execute-follow-up"
    )
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Sunset"] == REVIEW_EXECUTION_SUNSET
    assert response.headers["Link"] == (
        '</api/claim-support/execute-follow-up>; rel="successor-version"'
    )
    assert "execute_follow_up on /api/claim-support/review is deprecated" in response.headers[
        "Warning"
    ]