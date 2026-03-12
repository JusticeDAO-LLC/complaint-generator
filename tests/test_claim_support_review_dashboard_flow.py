from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi import Response

from applications.review_api import attach_claim_support_review_routes
from applications.review_ui import attach_claim_support_review_ui_routes
from claim_support_review import (
    ClaimSupportFollowUpExecuteRequest,
    ClaimSupportManualReviewResolveRequest,
    ClaimSupportReviewRequest,
)


pytestmark = pytest.mark.no_auto_network


def _build_dashboard_app(mediator: Mock) -> FastAPI:
    app = FastAPI()
    attach_claim_support_review_routes(app, mediator)
    attach_claim_support_review_ui_routes(app)
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
                "support_packet_summary": {
                    "total_packet_count": 3,
                    "fact_packet_count": 3,
                    "link_only_packet_count": 0,
                    "historical_capture_count": 2,
                    "content_origin_counts": {
                        "historical_archive_capture": 2,
                        "authority_reference_fallback": 1,
                    },
                    "capture_source_counts": {
                        "archived_domain_scrape": 2,
                    },
                    "fallback_mode_counts": {
                        "citation_title_only": 1,
                    },
                    "content_source_field_counts": {
                        "citation_title_fallback": 1,
                    },
                },
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
                        "support_packet_summary": {
                            "total_packet_count": 3,
                            "fact_packet_count": 3,
                            "link_only_packet_count": 0,
                            "historical_capture_count": 2,
                            "content_origin_counts": {
                                "historical_archive_capture": 2,
                                "authority_reference_fallback": 1,
                            },
                            "fallback_mode_counts": {
                                "citation_title_only": 1,
                            },
                        },
                        "support_packets": [
                            {
                                "support_kind": "evidence",
                                "support_ref": "QmTimelineEmail",
                                "support_label": "Timeline email",
                                "fact": {
                                    "fact_id": "fact:timeline-email",
                                    "text": "Employee preserved the retaliation timeline in an archived email.",
                                    "confidence": 0.98,
                                },
                                "lineage_summary": {
                                    "content_origin": "historical_archive_capture",
                                    "historical_capture": True,
                                    "capture_source": "archived_domain_scrape",
                                    "archive_url": "https://web.archive.org/web/20240101120000/https://example.com/timeline-email",
                                    "original_url": "https://example.com/timeline-email",
                                    "fallback_mode": "",
                                    "content_source_field": "content",
                                },
                            },
                            {
                                "support_kind": "authority",
                                "support_ref": "42 U.S.C. § 2000e-3",
                                "support_label": "Retaliation citation",
                                "fact": {
                                    "fact_id": "fact:retaliation-citation",
                                    "text": "Title and citation fallback preserved the retaliation authority reference.",
                                    "confidence": 0.91,
                                },
                                "lineage_summary": {
                                    "content_origin": "authority_reference_fallback",
                                    "historical_capture": False,
                                    "capture_source": "",
                                    "archive_url": "",
                                    "original_url": "",
                                    "fallback_mode": "citation_title_only",
                                    "content_source_field": "citation_title_fallback",
                                },
                            },
                        ],
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
    mediator.get_recent_claim_follow_up_execution.return_value = {
        "claims": {
            "retaliation": [
                {
                    "execution_id": 21,
                    "claim_type": "retaliation",
                    "claim_element_id": "retaliation:2",
                    "claim_element_text": "Adverse action",
                    "support_kind": "manual_review",
                    "query_text": "manual_review::retaliation::retaliation:2::resolve_contradiction",
                    "status": "skipped_manual_review",
                    "timestamp": "2026-03-12T12:35:00",
                    "execution_mode": "manual_review",
                    "follow_up_focus": "contradiction_resolution",
                    "query_strategy": "standard_gap_targeted",
                    "resolution_applied": "",
                },
                {
                    "execution_id": 44,
                    "claim_type": "retaliation",
                    "claim_element_id": "retaliation:2",
                    "claim_element_text": "Causal connection",
                    "support_kind": "authority",
                    "query_text": '"retaliation" "Causal connection" statute',
                    "status": "executed",
                    "timestamp": "2026-03-12T12:30:00",
                    "execution_mode": "retrieve_support",
                    "follow_up_focus": "parse_quality_improvement",
                    "query_strategy": "quality_gap_targeted",
                    "resolution_applied": "manual_review_resolved",
                }
            ]
        }
    }
    mediator.resolve_claim_follow_up_manual_review.return_value = {
        "recorded": True,
        "status": "resolved_manual_review",
        "execution_id": 91,
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
                        "recommended_action": "improve_parse_quality",
                        "follow_up_focus": "parse_quality_improvement",
                        "query_strategy": "quality_gap_targeted",
                        "missing_support_kinds": ["authority"],
                        "blocked_by_cooldown": False,
                        "should_suppress_retrieval": False,
                        "resolution_applied": "manual_review_resolved",
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
                "tasks": [
                    {
                        "claim_element": "Causal connection",
                        "follow_up_focus": "parse_quality_improvement",
                        "query_strategy": "quality_gap_targeted",
                    }
                ],
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
    resolve_route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/claim-support/resolve-manual-review"
    )

    page_html = await page_route.endpoint()

    soup = BeautifulSoup(page_html, "html.parser")
    assert soup.find(id="claim-type") is not None
    assert soup.find(id="required-kinds") is not None
    assert soup.find(id="review-button") is not None
    assert soup.find(id="execute-button") is not None
    assert soup.find(id="resolve-button") is not None
    assert soup.find(id="clear-resolution-button") is not None
    assert soup.find(id="resolution-element-id") is not None
    assert soup.find(id="resolution-notes") is not None
    assert soup.find(id="resolution-result-card") is not None
    assert soup.find(id="resolution-result-status") is not None
    assert soup.find(id="resolution-result-chips") is not None
    assert soup.find(id="execution-result-card") is not None
    assert soup.find(id="execution-result-status") is not None
    assert soup.find(id="signal-plan-normalized") is not None
    assert soup.find(id="signal-history-normalized") is not None
    assert soup.find(id="signal-archive-captures") is not None
    assert soup.find(id="signal-fallback-authorities") is not None
    assert soup.find(id="signal-low-quality-records") is not None
    assert soup.find(id="signal-parse-quality-tasks") is not None
    assert soup.find(id="history-list") is not None
    assert soup.find(id="history-summary-chips") is not None
    assert "View lineage packets" in page_html
    assert "packet-details" in page_html
    assert "All packets" in page_html
    assert "Archived only" in page_html
    assert "Fallback only" in page_html
    assert "data-packet-filter-button" in page_html
    assert "packet-filter-count" in page_html
    assert "data-packet-filter-summary" in page_html
    assert "data-packet-url-action" in page_html
    assert "supportPackets.length" in page_html
    assert "archivedPacketCount" in page_html
    assert "fallbackPacketCount" in page_html
    assert "Showing ${supportPackets.length} of ${supportPackets.length} packets" in page_html
    assert "Showing ${visibleCount} of ${totalCount} packets" in page_html
    assert "Open archive" in page_html
    assert "Copy archive" in page_html
    assert "Open original" in page_html
    assert "Copy original" in page_html
    assert "copyPacketUrl" in page_html
    assert "openPacketUrl" in page_html
    assert "data-packet-action-feedback" in page_html
    assert "setPacketActionFeedback" in page_html
    assert "packetSortRank" in page_html
    assert "sortSupportPackets" in page_html

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
    assert review_payload["claim_coverage_summary"]["retaliation"]["support_packet_summary"] == {
        "total_packet_count": 3,
        "fact_packet_count": 3,
        "link_only_packet_count": 0,
        "historical_capture_count": 2,
        "content_origin_counts": {
            "historical_archive_capture": 2,
            "authority_reference_fallback": 1,
        },
        "capture_source_counts": {
            "archived_domain_scrape": 2,
        },
        "fallback_mode_counts": {
            "citation_title_only": 1,
        },
        "content_source_field_counts": {
            "citation_title_fallback": 1,
        },
    }
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["support_packets"][0]["lineage_summary"]["archive_url"] == "https://web.archive.org/web/20240101120000/https://example.com/timeline-email"
    assert review_payload["claim_coverage_matrix"]["retaliation"]["elements"][0]["support_packets"][1]["lineage_summary"]["fallback_mode"] == "citation_title_only"
    assert review_payload["follow_up_plan_summary"]["retaliation"]["task_count"] == 1
    assert review_payload["follow_up_plan_summary"]["retaliation"]["parse_quality_task_count"] == 1
    assert review_payload["follow_up_plan_summary"]["retaliation"]["quality_gap_targeted_task_count"] == 1
    assert review_payload["follow_up_plan_summary"]["retaliation"]["resolution_applied_counts"] == {
        "manual_review_resolved": 1,
    }
    assert review_payload["follow_up_history_summary"]["retaliation"]["manual_review_entry_count"] == 1
    assert any(
        entry.get("resolution_applied") == "manual_review_resolved"
        for entry in review_payload["follow_up_history"]["retaliation"]
    )
    assert review_payload["follow_up_history_summary"]["retaliation"]["resolution_applied_counts"] == {
        "manual_review_resolved": 1,
    }

    resolution_payload = await resolve_route.endpoint(
        ClaimSupportManualReviewResolveRequest(
            claim_type="retaliation",
            claim_element_id="retaliation:2",
            claim_element="Adverse action",
            resolution_status="resolved_supported",
            resolution_notes="Operator reconciled the contradiction from the dashboard.",
            related_execution_id=21,
        ),
    )
    assert resolution_payload["resolution_result"]["status"] == "resolved_manual_review"
    assert resolution_payload["post_resolution_review"]["follow_up_history_summary"]["retaliation"]["resolution_applied_counts"] == {
        "manual_review_resolved": 1,
    }

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
    assert execute_payload["execution_quality_summary"]["retaliation"]["quality_improvement_status"] == "unchanged"
    assert execute_payload["execution_quality_summary"]["retaliation"]["parse_quality_task_count"] == 1
    assert execute_payload["post_execution_review"]["claim_coverage_summary"]["retaliation"][
        "missing_elements"
    ] == ["Causal connection"]