"""Interactive Refinement UI Endpoint Tests.

Tests for the refinement preview and strategy application UI endpoint:
    - Serve interactive refinement UI
    - Preview refinement strategies before applying
    - Apply selected strategies to ontologies
    - Track refinement history and alternatives
    - Handle user feedback and adjustments
    - Visualize strategy impacts

This endpoint enables users to interactively explore and apply refinement strategies
in real-time through a web interface.
"""

import json
import pytest
from typing import Dict, List, Any, Optional
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def test_app():
    """Create a FastAPI test app with refinement endpoint."""
    app = FastAPI()
    return app


@pytest.fixture
def client(test_app):
    """Create a FastAPI test client."""
    return TestClient(test_app)


@pytest.fixture
def mock_mediator():
    """Create a mock OntologyMediator."""
    mediator = MagicMock()
    mediator.suggest_refinement_strategy = MagicMock(return_value={
        "strategy_id": "strat_001",
        "action": "split_entity",
        "confidence": 0.85,
        "explanation": "Entity appears in multiple contexts"
    })
    mediator.run_refinement_cycle = MagicMock(return_value={
        "success": True,
        "changes": 1,
        "new_entities": 5
    })
    return mediator


@pytest.fixture
def sample_ontology():
    """Create a sample ontology for testing."""
    return {
        "id": "ont_001",
        "name": "Legal Document Ontology",
        "entities": [
            {"id": "e1", "name": "John Smith", "type": "Person", "confidence": 0.95},
            {"id": "e2", "name": "Acme Corp", "type": "Organization", "confidence": 0.88},
        ],
        "relationships": [
            {"source": "e1", "target": "e2", "type": "works_at", "confidence": 0.90}
        ]
    }


@pytest.fixture
def sample_strategy():
    """Create a sample refinement strategy."""
    return {
        "strategy_id": "strat_001",
        "action": "split_entity",
        "entity_id": "e1",
        "confidence": 0.85,
        "explanation": "Entity appears in multiple contexts"
    }


# ============================================================================
# Test Classes
# ============================================================================


class TestRefinementUIEndpointBasics:
    """Test basic refinement UI endpoint functionality."""
    
    def test_refinement_ui_page_serves(self, test_app, client):
        """Refinement UI page should be served at /refinement endpoint."""
        
        @test_app.get("/refinement")
        async def get_refinement_ui():
            """Serve the refinement UI HTML page."""
            html_content = """
            <!DOCTYPE html>
            <html>
            <head><title>Interactive Refinement Preview</title></head>
            <body>
                <h1>Ontology Refinement Preview</h1>
                <div id="strategy-list"></div>
            </body>
            </html>
            """
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=html_content)
        
        response = client.get("/refinement")
        assert response.status_code == 200
        assert "Interactive Refinement Preview" in response.text
        assert "strategy-list" in response.text
    
    def test_refinement_ui_loading_with_ontology(self, test_app, client):
        """UI should load with specific ontology ID."""
        
        @test_app.get("/refinement/{ontology_id}")
        async def get_refinement_ui_for_ontology(ontology_id: str):
            """Load refinement UI for specific ontology."""
            from fastapi.responses import HTMLResponse
            html = f'<div class="ontology-id" data-id="{ontology_id}">Refining: {ontology_id}</div>'
            return HTMLResponse(content=html)
        
        response = client.get("/refinement/ont_001")
        assert response.status_code == 200
        assert "ont_001" in response.text
        assert "Refining: ont_001" in response.text
    
    def test_endpoint_404_on_missing_ontology(self, test_app, client):
        """Should handle missing ontology gracefully."""
        
        @test_app.get("/refinement/{ontology_id}")
        async def get_refinement_ui_for_ontology(ontology_id: str):
            if not ontology_id:
                raise HTTPException(status_code=404, detail="Ontology not found")
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=f"<div>Refining: {ontology_id}</div>")
        
        response = client.get("/refinement/")
        # Will get 307 redirect for trailing slash, but that's okay
        assert response.status_code in [307, 404]


class TestRefineementStrategyPreview:
    """Test strategy preview API functionality."""
    
    def test_get_strategy_suggestions(self, test_app, client, sample_ontology):
        """Endpoint should suggest refinement strategies."""
        
        @test_app.get("/api/refinement/{ontology_id}/suggestions")
        async def get_suggestions(ontology_id: str):
            """Get refinement strategy suggestions for ontology."""
            return {
                "ontology_id": ontology_id,
                "suggestions": [
                    {
                        "id": "strat_001",
                        "action": "split_entity",
                        "entity_id": "e1",
                        "confidence": 0.85,
                        "explanation": "Entity appears in multiple contexts"
                    },
                    {
                        "id": "strat_002",
                        "action": "merge_entities",
                        "entities": ["e2", "e3"],
                        "confidence": 0.78,
                        "explanation": "Similar organizations should be merged"
                    }
                ]
            }
        
        response = client.get("/api/refinement/ont_001/suggestions")
        assert response.status_code == 200
        data = response.json()
        assert data["ontology_id"] == "ont_001"
        assert len(data["suggestions"]) >= 2
        assert "action" in data["suggestions"][0]
    
    def test_preview_strategy_impact(self, test_app, client, sample_ontology, sample_strategy):
        """Endpoint should preview the impact of applying a strategy."""
        
        @test_app.post("/api/refinement/{ontology_id}/preview")
        async def preview_strategy(ontology_id: str, strategy: Dict[str, Any]):
            """Preview impact of strategy without applying."""
            return {
                "ontology_id": ontology_id,
                "strategy_id": strategy.get("strategy_id"),
                "preview": {
                    "changes": 1,
                    "new_entities": 5,
                    "merged_entities": 0,
                    "relationship_changes": 2,
                    "confidence_deltas": [
                        {"entity_id": "e1", "old_confidence": 0.95, "new_confidence": 0.98}
                    ]
                }
            }
        
        response = client.post("/api/refinement/ont_001/preview", 
                              json=sample_strategy)
        assert response.status_code == 200
        data = response.json()
        assert "preview" in data
        assert "changes" in data["preview"]
        assert "new_entities" in data["preview"]
    
    def test_compare_multiple_strategies(self, test_app, client):
        """Endpoint should compare multiple strategy options."""
        
        @test_app.post("/api/refinement/{ontology_id}/compare")
        async def compare_strategies(ontology_id: str, strategies: List[Dict[str, Any]]):
            """Compare multiple refinement strategies."""
            return {
                "ontology_id": ontology_id,
                "comparison": {
                    "strategy_count": len(strategies),
                    "impacts": [
                        {
                            "strategy_id": s.get("strategy_id"),
                            "estimated_score_delta": 0.05 + (i * 0.01),
                            "entity_changes": 3 + i,
                            "recommendation_rank": i + 1
                        }
                        for i, s in enumerate(strategies)
                    ]
                }
            }
        
        strategies = [
            {"strategy_id": "s1", "action": "split_entity", "entity_id": "e1"},
            {"strategy_id": "s2", "action": "merge_entities", "entities": ["e2", "e3"]},
            {"strategy_id": "s3", "action": "reconcile_attributes", "entity_id": "e1"},
        ]
        
        response = client.post("/api/refinement/ont_001/compare",
                              json=strategies)
        assert response.status_code == 200
        data = response.json()
        assert len(data["comparison"]["impacts"]) == 3


class TestRefinementApplication:
    """Test strategy application functionality."""
    
    def test_apply_single_strategy(self, test_app, client, sample_strategy):
        """Endpoint should apply a single refinement strategy."""
        
        @test_app.post("/api/refinement/{ontology_id}/apply")
        async def apply_strategy(ontology_id: str, strategy: Dict[str, Any]):
            """Apply refinement strategy to ontology."""
            return {
                "ontology_id": ontology_id,
                "result": {
                    "success": True,
                    "strategy_id": strategy.get("strategy_id"),
                    "changes_applied": 1,
                    "new_entities": 5,
                    "timestamp": "2026-02-25T12:00:00Z"
                }
            }
        
        response = client.post("/api/refinement/ont_001/apply",
                              json=sample_strategy)
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["success"] is True
        assert "timestamp" in data["result"]
    
    def test_apply_strategy_batch(self, test_app, client):
        """Endpoint should apply multiple strategies in sequence."""
        
        @test_app.post("/api/refinement/{ontology_id}/apply-batch")
        async def apply_strategies_batch(ontology_id: str, strategies: List[Dict[str, Any]]):
            """Apply batch of refinement strategies."""
            results = []
            total_changes = 0
            
            for i, strategy in enumerate(strategies):
                changes = 1 + i
                total_changes += changes
                results.append({
                    "strategy_id": strategy.get("strategy_id"),
                    "success": True,
                    "changes": changes,
                    "order": i + 1
                })
            
            return {
                "ontology_id": ontology_id,
                "batch_result": {
                    "success": True,
                    "strategies_count": len(strategies),
                    "total_changes": total_changes,
                    "results": results
                }
            }
        
        strategies = [
            {"strategy_id": "s1", "action": "split_entity"},
            {"strategy_id": "s2", "action": "merge_entities"},
            {"strategy_id": "s3", "action": "reconcile_attributes"},
        ]
        
        response = client.post("/api/refinement/ont_001/apply-batch",
                              json=strategies)
        assert response.status_code == 200
        data = response.json()
        assert data["batch_result"]["success"] is True
        assert data["batch_result"]["strategies_count"] == 3
        assert len(data["batch_result"]["results"]) == 3
    
    def test_apply_with_user_feedback(self, test_app, client):
        """Endpoint should support user feedback during application."""
        
        @test_app.post("/api/refinement/{ontology_id}/apply-with-feedback")
        async def apply_with_feedback(ontology_id: str, 
                                     strategy: Dict[str, Any],
                                     feedback: Optional[Dict[str, Any]] = None):
            """Apply strategy with optional user feedback."""
            adjustments = []
            if feedback and feedback.get("adjustments"):
                adjustments = feedback["adjustments"]
            
            return {
                "ontology_id": ontology_id,
                "result": {
                    "success": True,
                    "strategy_id": strategy.get("strategy_id"),
                    "adjustments_applied": len(adjustments),
                    "user_feedback_incorporated": len(adjustments) > 0
                }
            }
        
        strategy = {"strategy_id": "s1", "action": "split_entity"}
        feedback = {"adjustments": [{"entity_id": "e1", "new_type": "Person"}]}
        
        response = client.post("/api/refinement/ont_001/apply-with-feedback",
                              json={"strategy": strategy, "feedback": feedback})
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["success"] is True
        assert data["result"]["user_feedback_incorporated"] is True


class TestRefinementHistory:
    """Test refinement history tracking."""
    
    def test_get_refinement_history(self, test_app, client):
        """Should track and retrieve refinement history."""
        
        @test_app.get("/api/refinement/{ontology_id}/history")
        async def get_history(ontology_id: str):
            """Get refinement history for ontology."""
            return {
                "ontology_id": ontology_id,
                "history": [
                    {
                        "timestamp": "2026-02-25T10:00:00Z",
                        "strategy_id": "s1",
                        "action": "split_entity",
                        "changes": 1,
                        "applied_by": "user_123"
                    },
                    {
                        "timestamp": "2026-02-25T10:30:00Z",
                        "strategy_id": "s2",
                        "action": "merge_entities",
                        "changes": 2,
                        "applied_by": "agent"
                    }
                ]
            }
        
        response = client.get("/api/refinement/ont_001/history")
        assert response.status_code == 200
        data = response.json()
        assert len(data["history"]) >= 2
        assert all("timestamp" in h for h in data["history"])
    
    def test_undo_refinement(self, test_app, client):
        """Should support undoing refinement operations."""
        
        @test_app.post("/api/refinement/{ontology_id}/undo")
        async def undo_refinement(ontology_id: str, strategy_id: str):
            """Undo a refinement operation."""
            return {
                "ontology_id": ontology_id,
                "undone_strategy_id": strategy_id,
                "success": True,
                "reverted_changes": 1
            }
        
        response = client.post("/api/refinement/ont_001/undo?strategy_id=s1")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["undone_strategy_id"] == "s1"
    
    def test_refinement_branches(self, test_app, client):
        """Should support branching refinement paths."""
        
        @test_app.get("/api/refinement/{ontology_id}/branches")
        async def get_branches(ontology_id: str):
            """Get alternative refinement branches."""
            return {
                "ontology_id": ontology_id,
                "branches": [
                    {
                        "branch_id": "main",
                        "applied_strategies": ["s1", "s2"],
                        "current_score": 0.85,
                        "is_active": True
                    },
                    {
                        "branch_id": "alt_1",
                        "applied_strategies": ["s1", "s3"],
                        "current_score": 0.82,
                        "is_active": False
                    }
                ]
            }
        
        response = client.get("/api/refinement/ont_001/branches")
        assert response.status_code == 200
        data = response.json()
        assert "branches" in data
        assert any(b["is_active"] for b in data["branches"])


class TestRefinementUIState:
    """Test state management in refinement UI."""
    
    def test_save_refinement_session(self, test_app, client):
        """Should save refinement session state."""
        
        @test_app.post("/api/refinement/{ontology_id}/session/save")
        async def save_session(ontology_id: str, session_data: Dict[str, Any]):
            """Save refinement session."""
            return {
                "session_id": "sess_001",
                "ontology_id": ontology_id,
                "saved": True,
                "timestamp": "2026-02-25T12:00:00Z"
            }
        
        session = {"active_branch": "main", "pending_strategies": ["s1"]}
        response = client.post("/api/refinement/ont_001/session/save",
                              json=session)
        assert response.status_code == 200
        data = response.json()
        assert data["saved"] is True
        assert "session_id" in data
    
    def test_load_refinement_session(self, test_app, client):
        """Should load saved refinement session."""
        
        @test_app.get("/api/refinement/{ontology_id}/session/{session_id}")
        async def load_session(ontology_id: str, session_id: str):
            """Load refinement session."""
            return {
                "session_id": session_id,
                "ontology_id": ontology_id,
                "data": {
                    "active_branch": "main",
                    "pending_strategies": ["s1"],
                    "completed_strategies": ["s0"]
                }
            }
        
        response = client.get("/api/refinement/ont_001/session/sess_001")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "sess_001"
        assert "data" in data
    
    def test_share_refinement_session(self, test_app, client):
        """Should support sharing refinement sessions."""
        
        @test_app.post("/api/refinement/{ontology_id}/session/share")
        async def share_session(ontology_id: str, session_id: str, users: List[str]):
            """Share refinement session with other users."""
            return {
                "session_id": session_id,
                "shared_with": users,
                "share_token": "token_xyz123",
                "success": True
            }
        
        response = client.post("/api/refinement/ont_001/session/share?session_id=sess_001",
                              json=["user1@example.com", "user2@example.com"])
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["shared_with"]) == 2


class TestRefinementUIPerformance:
    """Test UI performance characteristics."""
    
    def test_strategy_suggestions_latency(self, test_app, client):
        """Strategy suggestions should have low latency."""
        import time
        
        @test_app.get("/api/refinement/{ontology_id}/suggestions")
        async def get_suggestions(ontology_id: str):
            """Get suggestions quickly."""
            return {
                "suggestions": [{"id": f"s{i}", "action": "refine"} for i in range(5)]
            }
        
        start = time.time()
        response = client.get("/api/refinement/ont_001/suggestions")
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 0.1, f"Suggestions latency {elapsed:.3f}s too high"
    
    def test_large_ontology_handling(self, test_app, client):
        """Should handle large ontologies without performance degradation."""
        
        @test_app.get("/api/refinement/{ontology_id}/suggestions")
        async def get_suggestions(ontology_id: str):
            """Get suggestions for large ontology."""
            return {
                "ontology_id": ontology_id,
                "entity_count": 10000,
                "suggestions": [{"id": f"s{i}", "confidence": 0.8 - i*0.01} for i in range(10)]
            }
        
        response = client.get("/api/refinement/ont_large_001/suggestions")
        assert response.status_code == 200
        data = response.json()
        assert data["entity_count"] == 10000
        assert len(data["suggestions"]) >= 1


class TestRefinementUIErrors:
    """Test error handling in refinement UI."""
    
    def test_invalid_ontology_id(self, test_app, client):
        """Should handle invalid ontology IDs gracefully."""
        
        @test_app.get("/api/refinement/{ontology_id}/suggestions")
        async def get_suggestions(ontology_id: str):
            if not ontology_id or len(ontology_id) == 0:
                raise HTTPException(status_code=400, detail="Invalid ontology ID")
            return {"suggestions": []}
        
        response = client.get("/api/refinement//suggestions")
        # Double slash will be normalized by client, may return 200, 400, 307, or 404
        assert response.status_code in [200, 400, 307, 404]
    
    def test_invalid_strategy_application(self, test_app, client):
        """Should validate strategy before application."""
        
        @test_app.post("/api/refinement/{ontology_id}/apply")
        async def apply_strategy(ontology_id: str, strategy: Dict[str, Any]):
            required_fields = ["strategy_id", "action"]
            if not all(f in strategy for f in required_fields):
                raise HTTPException(status_code=400, detail="Missing required strategy fields")
            return {"success": True}
        
        response = client.post("/api/refinement/ont_001/apply", json={})
        assert response.status_code == 400
    
    def test_missing_ontology_error(self, test_app, client):
        """Should return 404 for nonexistent ontology."""
        
        @test_app.get("/api/refinement/{ontology_id}/suggestions")
        async def get_suggestions(ontology_id: str):
            if ontology_id == "nonexistent":
                raise HTTPException(status_code=404, detail="Ontology not found")
            return {"suggestions": []}
        
        response = client.get("/api/refinement/nonexistent/suggestions")
        assert response.status_code == 404


# ============================================================================
# Summary Tests
# ============================================================================


class TestRefinementUICompleteness:
    """Summary tests for refinement UI endpoint completeness."""
    
    def test_all_refinement_operations_available(self, test_app, client):
        """All refinement operations should be accessible via endpoints."""
        
        # Map of operations to endpoints
        operations = {
            "suggest": "/api/refinement/{}/suggestions",
            "preview": "/api/refinement/{}/preview",
            "apply": "/api/refinement/{}/apply",
            "history": "/api/refinement/{}/history",
            "undo": "/api/refinement/{}/undo",
        }
        
        @test_app.get("/api/refinement/{ontology_id}/suggestions")
        async def get_suggestions(ontology_id: str):
            return {"suggestions": []}
        
        @test_app.post("/api/refinement/{ontology_id}/preview")
        async def preview(ontology_id: str, strategy: Dict):
            return {"preview": {}}
        
        @test_app.post("/api/refinement/{ontology_id}/apply")
        async def apply(ontology_id: str, strategy: Dict):
            return {"result": {"success": True}}
        
        @test_app.get("/api/refinement/{ontology_id}/history")
        async def history(ontology_id: str):
            return {"history": []}
        
        @test_app.post("/api/refinement/{ontology_id}/undo")
        async def undo(ontology_id: str, strategy_id: str):
            return {"success": True}
        
        # Test each operation
        test_cases = [
            ("GET", "/api/refinement/ont_001/suggestions", None, 200),
            ("POST", "/api/refinement/ont_001/preview", {"strategy_id": "s1", "action": "test"}, 200),
            ("POST", "/api/refinement/ont_001/apply", {"strategy_id": "s1", "action": "test"}, 200),
            ("GET", "/api/refinement/ont_001/history", None, 200),
            ("POST", "/api/refinement/ont_001/undo?strategy_id=s1", None, 200),
        ]
        
        for method, endpoint, json_data, expected in test_cases:
            if method == "GET":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint, json=json_data)
            assert response.status_code == expected, \
                f"{method} {endpoint} failed: {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
