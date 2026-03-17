"""Tests for pipeline_json_logger type contracts.

This module tests the PipelineErrorDict and PipelineMetricsDict TypedDict
contracts to ensure proper type safety for pipeline logging structures.
"""

import pytest
import time
from typing import cast
from ipfs_datasets_py.optimizers.graphrag.pipeline_json_logger import (
    LogContext,
    PipelineErrorDict,
    PipelineMetricsDict,
    PipelineJSONLogger,
)


class TestPipelineErrorDictType:
    """Tests for PipelineErrorDict TypedDict structure."""
    
    def test_pipeline_error_has_correct_fields(self):
        """Verify PipelineErrorDict has expected field names."""
        error: PipelineErrorDict = {
            "stage": "extraction",
            "type": "ValueError",
            "message": "Invalid entity format",
        }
        
        assert "stage" in error
        assert "type" in error
        assert "message" in error
    
    def test_pipeline_error_field_types(self):
        """Verify field types in PipelineErrorDict."""
        error: PipelineErrorDict = {
            "stage": "evaluation",
            "type": "RuntimeError",
            "message": "Evaluation failed",
        }
        
        assert isinstance(error["stage"], str)
        assert isinstance(error["type"], str)
        assert isinstance(error["message"], str)
    
    def test_pipeline_error_optional_fields(self):
        """Verify all fields are optional in PipelineErrorDict (total=False)."""
        # Can create with subset of fields
        partial_error: PipelineErrorDict = {
            "message": "Generic error",
        }
        
        assert "message" in partial_error
        assert "stage" not in partial_error
        assert "type" not in partial_error
    
    def test_pipeline_error_empty_is_valid(self):
        """Verify empty PipelineErrorDict is valid (total=False)."""
        empty_error: PipelineErrorDict = {}
        
        assert isinstance(empty_error, dict)
        assert len(empty_error) == 0


class TestPipelineMetricsDictType:
    """Tests for PipelineMetricsDict TypedDict structure."""
    
    def test_pipeline_metrics_has_correct_fields(self):
        """Verify PipelineMetricsDict has expected field names."""
        metrics: PipelineMetricsDict = {
            "entity_count": 50,
            "relationship_count": 75,
            "overall_score": 0.85,
        }
        
        assert "entity_count" in metrics
        assert "relationship_count" in metrics
        assert "overall_score" in metrics
    
    def test_pipeline_metrics_field_types(self):
        """Verify field types in PipelineMetricsDict."""
        metrics: PipelineMetricsDict = {
            "entity_count": 100,
            "relationship_count": 200,
            "overall_score": 0.92,
        }
        
        assert isinstance(metrics["entity_count"], int)
        assert isinstance(metrics["relationship_count"], int)
        assert isinstance(metrics["overall_score"], float)
    
    def test_pipeline_metrics_optional_fields(self):
        """Verify fields are optional in PipelineMetricsDict (total=False)."""
        # Can have just entity_count
        partial_metrics: PipelineMetricsDict = {
            "entity_count": 25,
        }
        
        assert "entity_count" in partial_metrics
        assert "relationship_count" not in partial_metrics
        assert "overall_score" not in partial_metrics
    
    def test_pipeline_metrics_empty_is_valid(self):
        """Verify empty PipelineMetricsDict is valid (total=False)."""
        empty_metrics: PipelineMetricsDict = {}
        
        assert isinstance(empty_metrics, dict)
        assert len(empty_metrics) == 0
    
    def test_pipeline_metrics_partial_population(self):
        """Verify PipelineMetricsDict can be partially populated."""
        # Start empty
        metrics: PipelineMetricsDict = {}
        
        # Add entity_count
        metrics["entity_count"] = 10
        assert len(metrics) == 1
        
        # Add relationship_count
        metrics["relationship_count"] = 15
        assert len(metrics) == 2
        
        # Add overall_score
        metrics["overall_score"] = 0.9
        assert len(metrics) == 3


class TestLogContextIntegration:
    """Tests for LogContext using typed fields."""
    
    def test_log_context_initializes_with_empty_dicts(self):
        """Verify LogContext initializes with empty typed dicts."""
        context = LogContext(
            run_id="test-run-1",
            domain="test",
            data_source="test.txt",
        )
        
        assert context.metrics == {}
        assert context.errors == []
        assert isinstance(context.metrics, dict)
        assert isinstance(context.errors, list)
    
    def test_log_context_metrics_population(self):
        """Verify LogContext.metrics can be populated with valid fields."""
        context = LogContext(
            run_id="test-run-2", 
            domain="legal",
            data_source="complaints.json",
        )
        
        # Populate metrics
        context.metrics["entity_count"] = 100
        context.metrics["relationship_count"] = 150
        context.metrics["overall_score"] = 0.88
        
        assert context.metrics["entity_count"] == 100
        assert context.metrics["relationship_count"] == 150
        assert context.metrics["overall_score"] == 0.88
    
    def test_log_context_errors_append(self):
        """Verify LogContext.errors can accumulate error dicts."""
        context = LogContext(
            run_id="test-run-3",
            domain="medical",
            data_source="records.csv",
        )
        
        # Add errors
        context.errors.append({
            "stage": "extraction",
            "type": "ValueError",
            "message": "Invalid format",
        })
        
        context.errors.append({
            "stage": "evaluation",
            "type": "RuntimeError",
            "message": "Timeout",
        })
        
        assert len(context.errors) == 2
        assert context.errors[0]["stage"] == "extraction"
        assert context.errors[1]["stage"] == "evaluation"
    
    def test_log_context_to_dict_includes_typed_fields(self):
        """Verify LogContext.to_dict() includes metrics and error_count."""
        context = LogContext(
            run_id="test-run-4",
            domain="finance",
            data_source="transactions.json",
        )
        
        context.metrics["entity_count"] = 50
        context.errors.append({
            "stage": "extraction",
            "type": "KeyError",
            "message": "Missing field",
        })
        
        result = context.to_dict()
        
        assert "metrics" in result
        assert result["metrics"]["entity_count"] == 50
        assert "error_count" in result
        assert result["error_count"] == 1


class TestPipelineJSONLoggerIntegration:
    """Integration tests with PipelineJSONLogger."""
    
    def test_logger_extraction_completed_populates_metrics(self):
        """Verify log_extraction_completed populates typed metrics."""
        logger = PipelineJSONLogger(domain="test")
        logger.start_run(
            run_id="integration-1",
            data_source="test_data.txt",
        )
        
        logger.log_extraction_completed(
            entity_count=75,
            relationship_count=100,
        )
        
        assert logger._context is not None
        assert logger._context.metrics.get("entity_count") == 75
        assert logger._context.metrics.get("relationship_count") == 100
    
    def test_logger_evaluation_completed_populates_score(self):
        """Verify log_evaluation_completed populates overall_score metric."""
        logger = PipelineJSONLogger(domain="test")
        logger.start_run(
            run_id="integration-2",
            data_source="test.json",
        )
        
        logger.log_evaluation_completed(score=0.92)
        
        assert logger._context is not None
        assert logger._context.metrics.get("overall_score") == 0.92
    
    def test_logger_error_populates_errors_list(self):
        """Verify log_error populates typed errors list."""
        logger = PipelineJSONLogger(domain="test")
        logger.start_run(
            run_id="integration-3",
            data_source="test.csv",
        )
        
        logger.log_error(
            stage="extraction",
            error_type="ValueError",
            error_message="Invalid entity",
        )
        
        assert logger._context is not None
        assert len(logger._context.errors) == 1
        
        error = logger._context.errors[0]
        assert error["stage"] == "extraction"
        assert error["type"] == "ValueError"
        assert error["message"] == "Invalid entity"
    
    def test_logger_multiple_errors_accumulate(self):
        """Verify multiple errors accumulate correctly."""
        logger = PipelineJSONLogger(domain="test")
        logger.start_run(
            run_id="integration-4",
            data_source="test.txt",
        )
        
        logger.log_error("extraction", "TypeError", "Type mismatch")
        logger.log_error("evaluation", "RuntimeError", "Timeout")
        logger.log_error("refinement", "ValidationError", "Invalid schema")
        
        assert logger._context is not None
        assert len(logger._context.errors) == 3
        
        stages = [e["stage"] for e in logger._context.errors]
        assert stages == ["extraction", "evaluation", "refinement"]


class TestPipelineMetricsRealWorldScenario:
    """Real-world scenario tests for pipeline metrics."""
    
    def test_extraction_only_metrics(self):
        """Simulate extraction-only workflow with partial metrics."""
        logger = PipelineJSONLogger(domain="legal")
        logger.start_run(run_id="scenario-1", data_source="complaints.txt")
        
        # Only extraction performed
        logger.log_extraction_completed(
            entity_count=150,
            relationship_count=200,
        )
        
        assert logger._context.metrics.get("entity_count") == 150
        assert logger._context.metrics.get("relationship_count") == 200
        assert "overall_score" not in logger._context.metrics
    
    def test_full_pipeline_all_metrics(self):
        """Simulate full pipeline with all metrics populated."""
        logger = PipelineJSONLogger(domain="medical")
        logger.start_run(run_id="scenario-2", data_source="records.json")
        
        # Extraction
        logger.log_extraction_completed(
            entity_count=500,
            relationship_count=750,
        )
        
        # Evaluation
        logger.log_evaluation_completed(score=0.95)
        
        # Verify all metrics present
        assert logger._context.metrics["entity_count"] == 500
        assert logger._context.metrics["relationship_count"] == 750
        assert logger._context.metrics["overall_score"] == 0.95
    
    def test_error_tracking_across_stages(self):
        """Simulate errors occurring across multiple pipeline stages."""
        logger = PipelineJSONLogger(domain="finance")
        logger.start_run(run_id="scenario-3", data_source="transactions.csv")
        
        # Errors in different stages
        logger.log_error("extraction", "ValueError", "Missing required field 'amount'")
        logger.log_error("extraction", "KeyError", "Entity ID not found")
        logger.log_error("evaluation", "TimeoutError", "Evaluation timeout after 30s")
        
        errors = logger._context.errors
        assert len(errors) == 3
        
        extraction_errors = [e for e in errors if e["stage"] == "extraction"]
        evaluation_errors = [e for e in errors if e["stage"] == "evaluation"]
        
        assert len(extraction_errors) == 2
        assert len(evaluation_errors) == 1


class TestPipelineErrorDictStructure:
    """Tests verifying PipelineErrorDict structure compliance."""
    
    def test_error_dict_from_log_error(self):
        """Verify error dict from log_error matches PipelineErrorDict structure."""
        logger = PipelineJSONLogger(domain="test")
        logger.start_run(run_id="structure-1", data_source="test.txt")
        
        logger.log_error(
            stage="refinement",
            error_type="ValidationError",
            error_message="Schema validation failed",
        )
        
        error = logger._context.errors[0]
        
        # Verify structure matches PipelineErrorDict
        assert set(error.keys()) == {"stage", "type", "message"}
        assert all(isinstance(v, str) for v in error.values())
    
    def test_log_context_end_run_summary(self):
        """Verify end_run includes error_count from typed errors list."""
        logger = PipelineJSONLogger(domain="test")
        logger.start_run(run_id="summary-1", data_source="test.json")
        
        logger.log_extraction_completed(entity_count=100, relationship_count=150)
        logger.log_evaluation_completed(score=0.88)
        logger.log_error("extraction", "ValueError", "Error 1")
        logger.log_error("evaluation", "RuntimeError", "Error 2")
        
        summary = logger.end_run(success=False)
        
        assert summary["error_count"] == 2
        assert summary["metrics"]["entity_count"] == 100
        assert summary["metrics"]["overall_score"] == 0.88
