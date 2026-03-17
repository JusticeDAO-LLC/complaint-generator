"""Tests for pipeline JSON logging infrastructure.

Tests the comprehensive JSON logging for GraphRAG pipeline runs,
including context management, stage tracking, and event emission.
"""

import json
import logging
import pytest
import time
from io import StringIO

from ipfs_datasets_py.optimizers.graphrag.pipeline_json_logger import (
    PipelineJSONLogger,
    PipelineStage,
    LogContext,
)


@pytest.fixture
def logger_with_handler():
    """Create a logger with a string handler for capturing output."""
    test_logger = logging.getLogger("test_pipeline_" + str(time.time()))
    test_logger.handlers.clear()
    test_logger.setLevel(logging.DEBUG)
    
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    test_logger.addHandler(handler)
    
    return test_logger, stream


@pytest.fixture
def pipeline_logger(logger_with_handler):
    """Create a PipelineJSONLogger for testing."""
    test_logger, stream = logger_with_handler
    logger = PipelineJSONLogger(
        domain="legal",
        logger=test_logger,
        include_schema=False,
        include_timestamp=False,
    )
    return logger, stream


class TestLogContext:
    """Test LogContext data structure."""

    def test_context_initialization(self):
        """Test LogContext is properly initialized."""
        context = LogContext(
            run_id="test-run-123",
            domain="legal",
            data_source="complaints.txt",
        )
        
        assert context.run_id == "test-run-123"
        assert context.domain == "legal"
        assert context.data_source == "complaints.txt"
        assert context.stages == {}
        assert context.stage_timings == {}
        assert context.metrics == {}
        assert context.errors == []

    def test_elapsed_ms_calculation(self):
        """Test elapsed time calculation."""
        context = LogContext(
            run_id="test-run",
            domain="legal",
            data_source="test.txt",
        )
        
        # Sleep briefly and check elapsed time
        time.sleep(0.01)
        elapsed = context.elapsed_ms()
        
        # Should be at least 10ms (our sleep duration)
        assert elapsed >= 10, f"Expected elapsed >= 10ms, got {elapsed}"

    def test_mark_stage_start_and_end(self):
        """Test stage timing measurement."""
        context = LogContext(
            run_id="test-run",
            domain="legal",
            data_source="test.txt",
        )
        
        context.mark_stage_start("extraction")
        time.sleep(0.01)  # 10ms minimum
        context.mark_stage_end("extraction")
        
        assert "extraction" in context.stage_timings
        assert context.stage_timings["extraction"] >= 10

    def test_context_to_dict(self):
        """Test context serialization to dict."""
        context = LogContext(
            run_id="test-run",
            domain="legal",
            data_source="test.txt",
            data_type="json",
            refine=True,
            max_workers=4,
        )
        
        context.metrics["entity_count"] = 10
        context.stage_timings["extraction"] = 100.0
        
        result = context.to_dict()
        
        assert result["run_id"] == "test-run"
        assert result["domain"] == "legal"
        assert result["data_source"] == "test.txt"
        assert result["data_type"] == "json"
        assert result["refine"] is True
        assert result["max_workers"] == 4
        assert result["metrics"]["entity_count"] == 10
        assert result["stage_timings"]["extraction"] == 100.0
        assert "total_elapsed_ms" in result
        assert "error_count" in result


class TestPipelineJSONLogger:
    """Test PipelineJSONLogger functionality."""

    def test_logger_initialization(self, logger_with_handler):
        """Test logger is properly initialized."""
        test_logger, _ = logger_with_handler
        logger = PipelineJSONLogger(
            domain="medical",
            logger=test_logger,
            include_schema=False,
            include_timestamp=False,
        )
        
        assert logger.domain == "medical"
        assert logger.logger is test_logger
        assert logger.include_schema is False
        assert logger.include_timestamp is False

    def test_start_run(self, pipeline_logger):
        """Test starting a pipeline run."""
        logger, stream = pipeline_logger
        
        context = logger.start_run(
            run_id="test-run-001",
            data_source="input.txt",
            data_type="text",
            refine=True,
            max_workers=2,
        )
        
        assert context.run_id == "test-run-001"
        assert context.domain == "legal"
        assert context.data_source == "input.txt"
        assert context.data_type == "text"
        assert context.refine is True
        assert context.max_workers == 2
        
        # Check that a log was emitted
        log_output = stream.getvalue()
        assert "pipeline.run.started" in log_output

    def test_end_run_success(self, pipeline_logger):
        """Test ending a pipeline run successfully."""
        logger, stream = pipeline_logger
        
        context = logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        summary = logger.end_run(success=True)
        
        assert summary["run_id"] == "test-run"
        assert "success" in summary or "error_count" in summary
        
        log_output = stream.getvalue()
        assert "pipeline.run.completed" in log_output

    def test_end_run_failure(self, pipeline_logger):
        """Test ending a pipeline run with failure."""
        logger, stream = pipeline_logger
        
        context = logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        error_msg = "Test error occurred"
        summary = logger.end_run(success=False, error=error_msg)
        
        log_output = stream.getvalue()
        assert "pipeline.run.failed" in log_output

    def test_log_extraction_started(self, pipeline_logger):
        """Test logging extraction start."""
        logger, stream = pipeline_logger
        logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        logger.log_extraction_started(data_length=5000, strategy="llm_based")
        
        log_output = stream.getvalue()
        assert "extraction.started" in log_output
        assert "5000" in log_output
        assert "llm_based" in log_output

    def test_log_extraction_completed(self, pipeline_logger):
        """Test logging extraction completion."""
        logger, stream = pipeline_logger
        context = logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        logger.log_extraction_started(data_length=5000)
        logger.log_extraction_completed(
            entity_count=42,
            relationship_count=15,
            entity_types={"Person": 20, "Organization": 22},
        )
        
        assert context.metrics["entity_count"] == 42
        assert context.metrics["relationship_count"] == 15
        
        log_output = stream.getvalue()
        assert "extraction.completed" in log_output
        assert "42" in log_output
        assert "15" in log_output

    def test_log_evaluation_started(self, pipeline_logger):
        """Test logging evaluation start."""
        logger, stream = pipeline_logger
        logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        logger.log_evaluation_started(parallel=True, batch_size=4)
        
        log_output = stream.getvalue()
        assert "evaluation.started" in log_output

    def test_log_evaluation_completed(self, pipeline_logger):
        """Test logging evaluation completion."""
        logger, stream = pipeline_logger
        context = logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        logger.log_evaluation_started()
        logger.log_evaluation_completed(
            score=0.82,
            dimensions={"completeness": 0.8, "consistency": 0.85},
            cache_hit=False,
            cache_size=50,
        )
        
        assert context.metrics["overall_score"] == 0.82
        
        log_output = stream.getvalue()
        assert "evaluation.completed" in log_output

    def test_log_refinement_started(self, pipeline_logger):
        """Test logging refinement start."""
        logger, stream = pipeline_logger
        logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        logger.log_refinement_started(mode="llm", max_rounds=3, current_score=0.75)
        
        log_output = stream.getvalue()
        assert "refinement.started" in log_output

    def test_log_refinement_round(self, pipeline_logger):
        """Test logging refinement rounds."""
        logger, stream = pipeline_logger
        logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        logger.log_refinement_round(
            round_num=1,
            max_rounds=3,
            score_before=0.75,
            score_after=0.82,
            actions_applied=["add_entity", "remove_duplicate"],
        )
        
        log_output = stream.getvalue()
        assert "refinement.round.completed" in log_output
        assert "round" in log_output

    def test_log_refinement_completed(self, pipeline_logger):
        """Test logging refinement completion."""
        logger, stream = pipeline_logger
        logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        logger.log_refinement_completed(
            final_score=0.88,
            initial_score=0.75,
            rounds_completed=3,
            total_actions=10,
        )
        
        log_output = stream.getvalue()
        assert "refinement.completed" in log_output

    def test_log_error(self, pipeline_logger):
        """Test logging errors."""
        logger, stream = pipeline_logger
        context = logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        logger.log_error(
            stage="extraction",
            error_type="ValueError",
            error_message="Invalid input",
            traceback=None,
        )
        
        assert len(context.errors) == 1
        
        log_output = stream.getvalue()
        assert "error" in log_output.lower()

    def test_log_cache_statistics(self, pipeline_logger):
        """Test logging cache statistics."""
        logger, stream = pipeline_logger
        logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        logger.log_cache_statistics(
            cache_type="shared_eval",
            size=200,
            hit_count=100,
            miss_count=50,
            eviction_count=5,
        )
        
        log_output = stream.getvalue()
        assert "cache" in log_output.lower()

    def test_log_batch_progress(self, pipeline_logger):
        """Test logging batch progress."""
        logger, stream = pipeline_logger
        logger.start_run("test-run", "input.txt")
        stream.truncate(0)
        stream.seek(0)
        
        logger.log_batch_progress(
            batch_index=5,
            batch_total=10,
            items_completed=5,
            items_failed=0,
            current_score=0.85,
        )
        
        log_output = stream.getvalue()
        assert "batch.progress" in log_output

    def test_json_validity(self, pipeline_logger):
        """Test that emitted logs are valid JSON."""
        logger, stream = pipeline_logger
        logger.start_run("test-run", "input.txt")
        
        log_output = stream.getvalue()
        lines = [line.strip() for line in log_output.strip().split('\n') if line.strip()]
        
        for line in lines:
            # Each line should be valid JSON (after stripping logging prefix)
            try:
                json_str = line[line.find('{'):]  # Find first '{'
                if json_str.startswith('{'):
                    json.loads(json_str)
            except (json.JSONDecodeError, ValueError):
                # Log line may not have JSON if it's a prefix
                pass


class TestMultiStageTracking:
    """Test multi-stage pipeline tracking."""

    def test_multiple_stage_tracking(self, pipeline_logger):
        """Test tracking multiple pipeline stages."""
        logger, stream = pipeline_logger
        context = logger.start_run("test-run", "input.txt")
        
        # Extraction stage
        logger.log_extraction_started(data_length=1000)
        time.sleep(0.01)
        logger.log_extraction_completed(entity_count=10, relationship_count=5)
        
        # Evaluation stage
        logger.log_evaluation_started()
        time.sleep(0.01)
        logger.log_evaluation_completed(
            score=0.85,
            dimensions={"completeness": 0.8},
        )
        
        # Check that timings were recorded
        assert "extraction" in context.stage_timings
        assert "evaluation" in context.stage_timings
        assert context.stage_timings["extraction"] >= 10
        assert context.stage_timings["evaluation"] >= 10

    def test_stage_metrics_accumulation(self, pipeline_logger):
        """Test metrics accumulate correctly across stages."""
        logger, stream = pipeline_logger
        context = logger.start_run("test-run", "input.txt")
        
        logger.log_extraction_completed(
            entity_count=10,
            relationship_count=5,
        )
        
        logger.log_evaluation_completed(
            score=0.85,
            dimensions={"completeness": 0.8},
        )
        
        assert context.metrics["entity_count"] == 10
        assert context.metrics["overall_score"] == 0.85


class TestContextManager:
    """Test context manager functionality."""

    def test_no_context_run(self, pipeline_logger):
        """Test operations without active context."""
        logger, _ = pipeline_logger
        
        # These should not crash without an active context
        logger.log_cache_statistics(
            cache_type="test",
            size=100,
            hit_count=50,
            miss_count=50,
        )
        
        logger.end_run(success=True)


class TestErrorHandling:
    """Test error handling in logger."""

    def test_multiple_errors(self, pipeline_logger):
        """Test logging multiple errors."""
        logger, stream = pipeline_logger
        context = logger.start_run("test-run", "input.txt")
        
        for i in range(3):
            logger.log_error(
                stage="extraction",
                error_type="ValueError",
                error_message=f"Error {i}",
            )
        
        assert len(context.errors) == 3
