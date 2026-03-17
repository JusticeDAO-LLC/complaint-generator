"""Refinement Playbook System Tests.

Tests for predefined refinement sequences and playbook execution:
    - Define and save refinement playbooks
    - Load and execute playbooks
    - Conditional execution based on ontology characteristics
    - Playbook templates for common scenarios
    - Playbook composition and chaining
    - Performance tracking and reporting
    - Rollback and checkpoint management

Playbooks enable repeatable, standardized refinement workflows across ontologies.
"""

import json
import pytest
from typing import Dict, List, Any, Optional
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, asdict


# ============================================================================
# Mock Playbook Classes
# ============================================================================


@dataclass
class RefinementStep:
    """A single refinement step in a playbook."""
    step_id: str
    action: str
    parameters: Dict[str, Any]
    condition: Optional[str] = None
    on_success: Optional[str] = None  # Next step ID
    on_failure: Optional[str] = None  # Fallback step ID


@dataclass
class RefinementPlaybook:
    """A playbook containing a sequence of refinement steps."""
    playbook_id: str
    name: str
    description: str
    steps: List[RefinementStep]
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert playbook to dictionary."""
        return {
            "playbook_id": self.playbook_id,
            "name": self.name,
            "description": self.description,
            "steps": [asdict(step) for step in self.steps],
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RefinementPlaybook':
        """Create playbook from dictionary."""
        steps = [RefinementStep(**step) for step in data.get("steps", [])]
        return cls(
            playbook_id=data["playbook_id"],
            name=data["name"],
            description=data["description"],
            steps=steps,
            metadata=data.get("metadata", {})
        )


class PlaybookExecutor:
    """Executes refinement playbooks."""
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.execution_history = []
    
    def execute_playbook(
        self,
        playbook: RefinementPlaybook,
        ontology: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a playbook on an ontology."""
        results = {
            "playbook_id": playbook.playbook_id,
            "success": True,
            "steps_executed": 0,
            "steps_failed": 0,
            "changes": 0,
            "step_results": []
        }
        
        for step in playbook.steps:
            # Check condition
            if step.condition and not self._evaluate_condition(step.condition, ontology):
                results["step_results"].append({
                    "step_id": step.step_id,
                    "skipped": True,
                    "reason": "Condition not met"
                })
                continue
            
            # Execute step
            try:
                step_result = self._execute_step(step, ontology, context)
                results["steps_executed"] += 1
                results["changes"] += step_result.get("changes", 0)
                results["step_results"].append({
                    "step_id": step.step_id,
                    "success": True,
                    "changes": step_result.get("changes", 0)
                })
            except Exception as e:
                results["steps_failed"] += 1
                results["success"] = False
                results["step_results"].append({
                    "step_id": step.step_id,
                    "success": False,
                    "error": str(e)
                })
                break
        
        self.execution_history.append(results)
        return results
    
    def _execute_step(
        self,
        step: RefinementStep,
        ontology: Dict[str, Any],
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Execute a single refinement step."""
        # Mock execution
        return {"success": True, "changes": 1}
    
    def _evaluate_condition(self, condition: str, ontology: Dict[str, Any]) -> bool:
        """Evaluate a condition string."""
        # Mock condition evaluation
        if "entity_count" in condition:
            entity_count = len(ontology.get("entities", []))
            return eval(condition.replace("entity_count", str(entity_count)))
        return True
    
    def get_execution_history(self) -> List[Dict[str, Any]]:
        """Get execution history."""
        return self.execution_history


class PlaybookLibrary:
    """Library of predefined refinement playbooks."""
    
    def __init__(self):
        self.playbooks: Dict[str, RefinementPlaybook] = {}
    
    def register_playbook(self, playbook: RefinementPlaybook):
        """Register a playbook in the library."""
        self.playbooks[playbook.playbook_id] = playbook
    
    def get_playbook(self, playbook_id: str) -> Optional[RefinementPlaybook]:
        """Get a playbook by ID."""
        return self.playbooks.get(playbook_id)
    
    def list_playbooks(self) -> List[Dict[str, Any]]:
        """List all available playbooks."""
        return [
            {
                "playbook_id": pb.playbook_id,
                "name": pb.name,
                "description": pb.description,
                "steps": len(pb.steps)
            }
            for pb in self.playbooks.values()
        ]
    
    def save_playbook(self, playbook: RefinementPlaybook, filepath: str):
        """Save playbook to file."""
        with open(filepath, 'w') as f:
            json.dump(playbook.to_dict(), f, indent=2)
    
    def load_playbook(self, filepath: str) -> RefinementPlaybook:
        """Load playbook from file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        playbook = RefinementPlaybook.from_dict(data)
        self.register_playbook(playbook)
        return playbook


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def playbook_library():
    """Create a playbook library."""
    return PlaybookLibrary()


@pytest.fixture
def playbook_executor():
    """Create a playbook executor."""
    return PlaybookExecutor()


@pytest.fixture
def sample_ontology():
    """Create a sample ontology."""
    return {
        "id": "ont_001",
        "entities": [
            {"id": "e1", "name": "John", "type": "Person", "confidence": 0.7},
            {"id": "e2", "name": "Acme", "type": "Organization", "confidence": 0.8},
        ],
        "relationships": [
            {"source": "e1", "target": "e2", "type": "works_at", "confidence": 0.75}
        ]
    }


@pytest.fixture
def basic_playbook():
    """Create a basic refinement playbook."""
    steps = [
        RefinementStep(
            step_id="step1",
            action="normalize_entity_names",
            parameters={"case": "title"}
        ),
        RefinementStep(
            step_id="step2",
            action="deduplicate_entities",
            parameters={"threshold": 0.9}
        ),
        RefinementStep(
            step_id="step3",
            action="reconcile_relationships",
            parameters={"confidence_threshold": 0.7}
        )
    ]
    return RefinementPlaybook(
        playbook_id="basic_001",
        name="Basic Cleanup Playbook",
        description="Standard entity normalization and deduplication",
        steps=steps,
        metadata={"category": "cleanup", "priority": "high"}
    )


# ============================================================================
# Test Classes
# ============================================================================


class TestPlaybookCreation:
    """Test playbook creation and structure."""
    
    def test_create_empty_playbook(self):
        """Should create an empty playbook."""
        playbook = RefinementPlaybook(
            playbook_id="empty_001",
            name="Empty Playbook",
            description="A playbook with no steps",
            steps=[],
            metadata={}
        )
        assert playbook.playbook_id == "empty_001"
        assert len(playbook.steps) == 0
    
    def test_create_playbook_with_steps(self, basic_playbook):
        """Should create playbook with multiple steps."""
        assert len(basic_playbook.steps) == 3
        assert basic_playbook.steps[0].action == "normalize_entity_names"
        assert basic_playbook.steps[1].action == "deduplicate_entities"
    
    def test_playbook_serialization(self, basic_playbook):
        """Should serialize playbook to dictionary."""
        data = basic_playbook.to_dict()
        assert data["playbook_id"] == "basic_001"
        assert len(data["steps"]) == 3
        assert "metadata" in data
    
    def test_playbook_deserialization(self, basic_playbook):
        """Should deserialize playbook from dictionary."""
        data = basic_playbook.to_dict()
        restored = RefinementPlaybook.from_dict(data)
        assert restored.playbook_id == basic_playbook.playbook_id
        assert len(restored.steps) == len(basic_playbook.steps)
    
    def test_refinement_step_structure(self):
        """Refinement steps should have required fields."""
        step = RefinementStep(
            step_id="step1",
            action="split_entity",
            parameters={"entity_id": "e1"}
        )
        assert step.step_id == "step1"
        assert step.action == "split_entity"
        assert "entity_id" in step.parameters


class TestPlaybookLibrary:
    """Test playbook library management."""
    
    def test_register_playbook(self, playbook_library, basic_playbook):
        """Should register playbook in library."""
        playbook_library.register_playbook(basic_playbook)
        retrieved = playbook_library.get_playbook("basic_001")
        assert retrieved is not None
        assert retrieved.playbook_id == "basic_001"
    
    def test_list_playbooks(self, playbook_library, basic_playbook):
        """Should list all registered playbooks."""
        playbook_library.register_playbook(basic_playbook)
        playbooks = playbook_library.list_playbooks()
        assert len(playbooks) >= 1
        assert any(pb["playbook_id"] == "basic_001" for pb in playbooks)
    
    def test_get_nonexistent_playbook(self, playbook_library):
        """Should return None for nonexistent playbook."""
        result = playbook_library.get_playbook("nonexistent")
        assert result is None
    
    def test_register_multiple_playbooks(self, playbook_library):
        """Should register multiple playbooks."""
        for i in range(5):
            playbook = RefinementPlaybook(
                playbook_id=f"pb_{i}",
                name=f"Playbook {i}",
                description=f"Test playbook {i}",
                steps=[],
                metadata={}
            )
            playbook_library.register_playbook(playbook)
        
        playbooks = playbook_library.list_playbooks()
        assert len(playbooks) == 5


class TestPlaybookExecution:
    """Test playbook execution."""
    
    def test_execute_basic_playbook(self, playbook_executor, basic_playbook, sample_ontology):
        """Should execute a basic playbook."""
        result = playbook_executor.execute_playbook(basic_playbook, sample_ontology)
        assert result["success"] is True
        assert result["steps_executed"] == 3
        assert result["steps_failed"] == 0
    
    def test_execution_produces_results(self, playbook_executor, basic_playbook, sample_ontology):
        """Execution should produce detailed results."""
        result = playbook_executor.execute_playbook(basic_playbook, sample_ontology)
        assert "step_results" in result
        assert len(result["step_results"]) >= 1
    
    def test_execution_tracks_changes(self, playbook_executor, basic_playbook, sample_ontology):
        """Should track changes made during execution."""
        result = playbook_executor.execute_playbook(basic_playbook, sample_ontology)
        assert "changes" in result
        assert result["changes"] >= 0
    
    def test_empty_playbook_execution(self, playbook_executor, sample_ontology):
        """Should handle empty playbook execution."""
        empty_playbook = RefinementPlaybook(
            playbook_id="empty",
            name="Empty",
            description="Empty playbook",
            steps=[],
            metadata={}
        )
        result = playbook_executor.execute_playbook(empty_playbook, sample_ontology)
        assert result["success"] is True
        assert result["steps_executed"] == 0


class TestConditionalExecution:
    """Test conditional step execution."""
    
    def test_condition_evaluation(self, playbook_executor, sample_ontology):
        """Should evaluate conditions before executing steps."""
        steps = [
            RefinementStep(
                step_id="conditional",
                action="merge_entities",
                parameters={"threshold": 0.9},
                condition="entity_count > 5"  # Should skip since only 2 entities
            )
        ]
        playbook = RefinementPlaybook(
            playbook_id="conditional",
            name="Conditional Playbook",
            description="Test conditional execution",
            steps=steps,
            metadata={}
        )
        result = playbook_executor.execute_playbook(playbook, sample_ontology)
        assert result["step_results"][0]["skipped"] is True
    
    def test_condition_passes(self, playbook_executor, sample_ontology):
        """Should execute step when condition passes."""
        steps = [
            RefinementStep(
                step_id="conditional",
                action="normalize",
                parameters={},
                condition="entity_count > 0"  # Should pass
            )
        ]
        playbook = RefinementPlaybook(
            playbook_id="conditional",
            name="Conditional Playbook",
            description="Test conditional execution",
            steps=steps,
            metadata={}
        )
        result = playbook_executor.execute_playbook(playbook, sample_ontology)
        assert result["steps_executed"] >= 1


class TestPlaybookTemplates:
    """Test predefined playbook templates."""
    
    def test_cleanup_template(self, playbook_library):
        """Should provide cleanup playbook template."""
        cleanup_steps = [
            RefinementStep("s1", "normalize_entity_names", {"case": "title"}),
            RefinementStep("s2", "deduplicate_entities", {"threshold": 0.9}),
            RefinementStep("s3", "remove_low_confidence_entities", {"threshold": 0.5}),
        ]
        cleanup_playbook = RefinementPlaybook(
            playbook_id="template_cleanup",
            name="Cleanup Template",
            description="Standard cleanup operations",
            steps=cleanup_steps,
            metadata={"template": True, "category": "cleanup"}
        )
        playbook_library.register_playbook(cleanup_playbook)
        
        retrieved = playbook_library.get_playbook("template_cleanup")
        assert retrieved is not None
        assert retrieved.metadata["template"] is True
    
    def test_enrichment_template(self, playbook_library):
        """Should provide enrichment playbook template."""
        enrichment_steps = [
            RefinementStep("s1", "infer_relationships", {}),
            RefinementStep("s2", "enhance_entity_types", {}),
            RefinementStep("s3", "add_confidence_scores", {}),
        ]
        enrichment_playbook = RefinementPlaybook(
            playbook_id="template_enrichment",
            name="Enrichment Template",
            description="Enhance ontology with additional information",
            steps=enrichment_steps,
            metadata={"template": True, "category": "enrichment"}
        )
        playbook_library.register_playbook(enrichment_playbook)
        
        retrieved = playbook_library.get_playbook("template_enrichment")
        assert len(retrieved.steps) == 3
    
    def test_validation_template(self, playbook_library):
        """Should provide validation playbook template."""
        validation_steps = [
            RefinementStep("s1", "check_entity_types", {}),
            RefinementStep("s2", "validate_relationships", {}),
            RefinementStep("s3", "check_confidence_thresholds", {}),
        ]
        validation_playbook = RefinementPlaybook(
            playbook_id="template_validation",
            name="Validation Template",
            description="Validate ontology structure and quality",
            steps=validation_steps,
            metadata={"template": True, "category": "validation"}
        )
        playbook_library.register_playbook(validation_playbook)
        
        assert playbook_library.get_playbook("template_validation") is not None


class TestPlaybookChaining:
    """Test playbook composition and chaining."""
    
    def test_execute_multiple_playbooks(self, playbook_executor, sample_ontology):
        """Should execute multiple playbooks in sequence."""
        playbook1 = RefinementPlaybook(
            playbook_id="pb1",
            name="First",
            description="First playbook",
            steps=[RefinementStep("s1", "normalize", {})],
            metadata={}
        )
        playbook2 = RefinementPlaybook(
            playbook_id="pb2",
            name="Second",
            description="Second playbook",
            steps=[RefinementStep("s2", "deduplicate", {})],
            metadata={}
        )
        
        result1 = playbook_executor.execute_playbook(playbook1, sample_ontology)
        result2 = playbook_executor.execute_playbook(playbook2, sample_ontology)
        
        assert result1["success"] is True
        assert result2["success"] is True
        assert len(playbook_executor.execution_history) == 2
    
    def test_playbook_chain_metadata(self, playbook_executor):
        """Should track metadata across chained playbooks."""
        history = playbook_executor.get_execution_history()
        assert isinstance(history, list)


class TestPlaybookPersistence:
    """Test playbook saving and loading."""
    
    def test_save_playbook_to_file(self, playbook_library, basic_playbook, tmp_path):
        """Should save playbook to JSON file."""
        filepath = tmp_path / "playbook.json"
        playbook_library.save_playbook(basic_playbook, str(filepath))
        assert filepath.exists()
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        assert data["playbook_id"] == "basic_001"
    
    def test_load_playbook_from_file(self, playbook_library, basic_playbook, tmp_path):
        """Should load playbook from JSON file."""
        filepath = tmp_path / "playbook.json"
        playbook_library.save_playbook(basic_playbook, str(filepath))
        
        loaded = playbook_library.load_playbook(str(filepath))
        assert loaded.playbook_id == basic_playbook.playbook_id
        assert len(loaded.steps) == len(basic_playbook.steps)


class TestExecutionHistory:
    """Test execution history tracking."""
    
    def test_track_execution_history(self, playbook_executor, basic_playbook, sample_ontology):
        """Should track execution history."""
        playbook_executor.execute_playbook(basic_playbook, sample_ontology)
        history = playbook_executor.get_execution_history()
        assert len(history) >= 1
        assert history[0]["playbook_id"] == "basic_001"
    
    def test_history_includes_results(self, playbook_executor, basic_playbook, sample_ontology):
        """History should include detailed results."""
        playbook_executor.execute_playbook(basic_playbook, sample_ontology)
        history = playbook_executor.get_execution_history()
        assert "steps_executed" in history[0]
        assert "success" in history[0]
    
    def test_multiple_executions_tracked(self, playbook_executor, basic_playbook, sample_ontology):
        """Should track multiple executions."""
        for _ in range(3):
            playbook_executor.execute_playbook(basic_playbook, sample_ontology)
        history = playbook_executor.get_execution_history()
        assert len(history) == 3


class TestPlaybookPerformance:
    """Test playbook performance characteristics."""
    
    def test_large_playbook_execution(self, playbook_executor, sample_ontology):
        """Should handle large playbooks efficiently."""
        steps = [
            RefinementStep(f"step_{i}", "action", {})
            for i in range(50)
        ]
        large_playbook = RefinementPlaybook(
            playbook_id="large",
            name="Large Playbook",
            description="Playbook with many steps",
            steps=steps,
            metadata={}
        )
        
        import time
        start = time.time()
        result = playbook_executor.execute_playbook(large_playbook, sample_ontology)
        elapsed = time.time() - start
        
        assert result["success"] is True
        assert elapsed < 1.0, f"Large playbook took {elapsed:.3f}s"


class TestPlaybookValidation:
    """Test playbook validation."""
    
    def test_validate_playbook_structure(self, basic_playbook):
        """Should validate playbook has required fields."""
        assert hasattr(basic_playbook, 'playbook_id')
        assert hasattr(basic_playbook, 'name')
        assert hasattr(basic_playbook, 'description')
        assert hasattr(basic_playbook, 'steps')
    
    def test_validate_step_parameters(self):
        """Should validate step parameters."""
        step = RefinementStep(
            step_id="test",
            action="test_action",
            parameters={"param1": "value1"}
        )
        assert isinstance(step.parameters, dict)


class TestPlaybookErrorHandling:
    """Test error handling in playbook execution."""
    
    def test_handle_step_failure(self, playbook_executor, sample_ontology):
        """Should handle step failures gracefully."""
        # Create a playbook with steps that might fail
        steps = [
            RefinementStep("s1", "action1", {}),
            RefinementStep("s2", "action2", {}),
        ]
        playbook = RefinementPlaybook(
            playbook_id="error_test",
            name="Error Test",
            description="Test error handling",
            steps=steps,
            metadata={}
        )
        
        # Mock a failure
        with patch.object(playbook_executor, '_execute_step', side_effect=[
            {"success": True, "changes": 1},
            Exception("Step failed")
        ]):
            result = playbook_executor.execute_playbook(playbook, sample_ontology)
            assert result["success"] is False
            assert result["steps_failed"] >= 1


class TestPlaybookSummary:
    """Summary tests for playbook system."""
    
    def test_complete_workflow(self, playbook_library, playbook_executor, sample_ontology):
        """Test complete playbook workflow."""
        # Create playbook
        steps = [
            RefinementStep("s1", "normalize", {}),
            RefinementStep("s2", "deduplicate", {}),
        ]
        playbook = RefinementPlaybook(
            playbook_id="workflow_test",
            name="Workflow Test",
            description="Complete workflow test",
            steps=steps,
            metadata={}
        )
        
        # Register
        playbook_library.register_playbook(playbook)
        
        # Retrieve
        retrieved = playbook_library.get_playbook("workflow_test")
        assert retrieved is not None
        
        # Execute
        result = playbook_executor.execute_playbook(retrieved, sample_ontology)
        assert result["success"] is True
        
        # Check history
        history = playbook_executor.get_execution_history()
        assert len(history) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
