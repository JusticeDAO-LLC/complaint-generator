"""Tests for response validator type contracts.

This module tests the ValidationErrorDetail TypedDict and ValidationResult
dataclass to ensure proper type safety and structure for validation errors.
"""

import pytest
from typing import cast
from ipfs_datasets_py.optimizers.graphrag.response_validators import (
    ValidationResult,
    ValidationErrorDetail,
    ValidationSeverity,
)


class TestValidationErrorDetailType:
    """Tests for ValidationErrorDetail TypedDict structure."""
    
    def test_validation_error_detail_has_correct_fields(self):
        """Verify ValidationErrorDetail has expected field names."""
        error_detail: ValidationErrorDetail = {
            "severity": "error",
            "field": "entity_id",
            "message": "Required field missing",
            "code": "MISSING_FIELD",
        }
        
        assert "severity" in error_detail
        assert "field" in error_detail
        assert "message" in error_detail
        assert "code" in error_detail
    
    def test_validation_error_detail_field_types(self):
        """Verify field types in ValidationErrorDetail."""
        error_detail: ValidationErrorDetail = {
            "severity": "error",
            "field": "confidence",
            "message": "Value out of range",
            "code": "RANGE_ERROR",
        }
        
        assert isinstance(error_detail["severity"], str)
        assert isinstance(error_detail["field"], (str, type(None)))
        assert isinstance(error_detail["message"], str)
        assert isinstance(error_detail["code"], (str, type(None)))
    
    def test_validation_error_detail_optional_fields(self):
        """Verify field and code are optional in ValidationErrorDetail."""
        # Total=False allows omitted fields
        minimal_error: ValidationErrorDetail = {
            "severity": "warning",
            "message": "Recommended field missing",
        }
        
        assert "severity" in minimal_error
        assert "message" in minimal_error
        assert "field" not in minimal_error
        assert "code" not in minimal_error
    
    def test_severity_values_match_enum(self):
        """Verify severity values correspond to ValidationSeverity enum."""
        for severity_level in ValidationSeverity:
            error_detail: ValidationErrorDetail = {
                "severity": severity_level.value,
                "message": f"Test {severity_level.value} message",
            }
            
            assert error_detail["severity"] == severity_level.value
            assert error_detail["severity"] in ["error", "warning", "info"]


class TestValidationResultErrorHandling:
    """Tests for ValidationResult.add_error and error structure."""
    
    def test_add_error_populates_detailed_errors(self):
        """Verify add_error creates correct DetailedValidationError structure."""
        result = ValidationResult(is_valid=True)
        result.add_error("Field is required", field="entity_id", code="REQUIRED")
        
        assert len(result.detailed_errors) == 1
        error = result.detailed_errors[0]
        
        assert error["severity"] == "error"
        assert error["field"] == "entity_id"
        assert error["message"] == "Field is required"
        assert error["code"] == "REQUIRED"
    
    def test_add_error_without_field_or_code(self):
        """Verify add_error handles missing field/code gracefully."""
        result = ValidationResult(is_valid=True)
        result.add_error("Generic error message")
        
        assert len(result.detailed_errors) == 0  # Not added to detailed_errors
        assert len(result.errors) == 1
        assert result.errors[0] == "Generic error message"
        assert not result.is_valid
    
    def test_add_error_sets_is_valid_false(self):
        """Verify add_error sets is_valid to False."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid
        
        result.add_error("Some error", field="test")
        
        assert not result.is_valid
    
    def test_add_warning_populates_detailed_errors(self):
        """Verify add_warning creates correct DetailedValidationError structure."""
        result = ValidationResult(is_valid=True)
        result.add_warning("Deprecated field used", field="old_field")
        
        assert len(result.detailed_errors) == 1
        warning = result.detailed_errors[0]
        
        assert warning["severity"] == "warning"
        assert warning["field"] == "old_field"
        assert warning["message"] == "Deprecated field used"
        assert "code" not in warning or warning.get("code") is None
    
    def test_add_warning_without_field(self):
        """Verify add_warning without field doesn't add to detailed_errors."""
        result = ValidationResult(is_valid=True)
        result.add_warning("General warning")
        
        assert len(result.detailed_errors) == 0
        assert len(result.warnings) == 1
        assert result.warnings[0] == "General warning"
    
    def test_add_warning_preserves_is_valid(self):
        """Verify add_warning doesn't change is_valid status."""
        result = ValidationResult(is_valid=True)
        result.add_warning("Warning message", field="test")
        
        assert result.is_valid  # Warnings don't invalidate


class TestValidationResultIntegration:
    """Integration tests for ValidationResult with multiple errors/warnings."""
    
    def test_multiple_errors_accumulate(self):
        """Verify multiple errors accumulate correctly."""
        result = ValidationResult(is_valid=True)
        
        result.add_error("Error 1", field="field1", code="ERR1")
        result.add_error("Error 2", field="field2", code="ERR2")
        result.add_error("Error 3", field="field3", code="ERR3")
        
        assert len(result.detailed_errors) == 3
        assert len(result.errors) == 3
        assert not result.is_valid
        
        # Verify all errors present
        fields = [e["field"] for e in result.detailed_errors]
        assert "field1" in fields
        assert "field2" in fields
        assert "field3" in fields
    
    def test_mixed_errors_and_warnings(self):
        """Verify errors and warnings can coexist."""
        result = ValidationResult(is_valid=True)
        
        result.add_error("Critical error", field="id", code="INVALID_ID")
        result.add_warning("Performance warning", field="cache")
        result.add_error("Validation failure", field="confidence", code="OUT_OF_RANGE")
        
        assert not result.is_valid
        assert len(result.errors) == 2
        assert len(result.warnings) == 1
        assert len(result.detailed_errors) == 3
        
        # Verify severity distribution
        severities = [e["severity"] for e in result.detailed_errors]
        assert severities.count("error") == 2
        assert severities.count("warning") == 1
    
    def test_detailed_errors_preserve_order(self):
        """Verify detailed_errors maintains insertion order."""
        result = ValidationResult(is_valid=True)
        
        result.add_error("First", field="a", code="1")
        result.add_warning("Second", field="b")
        result.add_error("Third", field="c", code="3")
        
        messages = [e["message"] for e in result.detailed_errors]
        assert messages == ["First", "Second", "Third"]


class TestValidationResultInitialization:
    """Tests for ValidationResult initialization and defaults."""
    
    def test_default_initialization(self):
        """Verify ValidationResult initializes with empty collections."""
        result = ValidationResult(is_valid=True)
        
        assert result.is_valid
        assert result.data is None
        assert result.errors == []
        assert result.warnings == []
        assert result.detailed_errors == []
    
    def test_initialization_with_data(self):
        """Verify ValidationResult can be initialized with data."""
        test_data = {"entity_id": "e1", "text": "ACME Corp"}
        result = ValidationResult(is_valid=True, data=test_data)
        
        assert result.is_valid
        assert result.data == test_data
    
    def test_initialization_invalid_state(self):
        """Verify ValidationResult can be initialized as invalid."""
        result = ValidationResult(
            is_valid=False,
            errors=["Preexisting error"],
        )
        
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.errors[0] == "Preexisting error"


class TestValidationErrorDetailStructure:
    """Tests for ValidationErrorDetail structure compliance."""
    
    def test_error_detail_from_add_error(self):
        """Verify error detail from add_error matches TypedDict structure."""
        result = ValidationResult(is_valid=True)
        result.add_error(
            "Invalid confidence value",
            field="confidence",
            code="VALUE_ERROR",
        )
        
        error_detail = result.detailed_errors[0]
        
        # Verify structure matches ValidationErrorDetail
        assert set(error_detail.keys()) == {"severity", "field", "message", "code"}
        assert all(isinstance(k, str) for k in error_detail.keys())
    
    def test_warning_detail_from_add_warning(self):
        """Verify warning detail from add_warning matches TypedDict structure."""
        result = ValidationResult(is_valid=True)
        result.add_warning("Deprecated field", field="old_name")
        
        warning_detail = result.detailed_errors[0]
        
        # Verify structure (no 'code' field expected)
        assert "severity" in warning_detail
        assert "field" in warning_detail
        assert "message" in warning_detail
        assert warning_detail["severity"] == "warning"
    
    def test_all_severity_levels_create_valid_errors(self):
        """Verify all ValidationSeverity levels create valid error details."""
        result = ValidationResult(is_valid=True)
        
        # Test ERROR severity (via add_error)
        result.add_error("Error message", field="f1", code="E1")
        assert result.detailed_errors[0]["severity"] == ValidationSeverity.ERROR.value
        
        # Test WARNING severity (via add_warning)
        result.add_warning("Warning message", field="f2")
        assert result.detailed_errors[1]["severity"] == ValidationSeverity.WARNING.value
        
        # INFO would need a custom method if implemented
        # Verify both are valid severity values
        for detail in result.detailed_errors:
            assert detail["severity"] in ["error", "warning", "info"]


class TestValidationResultRealWorldScenarios:
    """Real-world scenario tests for ValidationResult."""
    
    def test_entity_extraction_validation_scenario(self):
        """Simulate entity extraction validation with multiple issues."""
        result = ValidationResult(is_valid=True)
        
        # Missing required field
        result.add_error("Entity ID is required", field="id", code="MISSING_REQUIRED")
        
        # Invalid confidence range
        result.add_error("Confidence must be 0-1", field="confidence", code="RANGE_ERROR")
        
        # Deprecated type usage (warning)
        result.add_warning("Entity type 'Person' is deprecated", field="type")
        
        # Malformed text field
        result.add_error("Text field cannot be empty", field="text", code="EMPTY_FIELD")
        
        assert not result.is_valid
        assert len(result.errors) == 3
        assert len(result.warnings) == 1
        assert len(result.detailed_errors) == 4
        
        # Verify error distribution
        error_details = {e["code"] for e in result.detailed_errors if "code" in e}
        assert "MISSING_REQUIRED" in error_details
        assert "RANGE_ERROR" in error_details
        assert "EMPTY_FIELD" in error_details
    
    def test_relationship_validation_scenario(self):
        """Simulate relationship validation with field-specific errors."""
        result = ValidationResult(is_valid=True, data=None)
        
        result.add_error("Source entity not found", field="source", code="INVALID_REF")
        result.add_error("Target entity not found", field="target", code="INVALID_REF")
        result.add_warning("Relationship type not in ontology", field="type")
        
        assert not result.is_valid
        assert len([e for e in result.detailed_errors if e["field"] == "source"]) == 1
        assert len([e for e in result.detailed_errors if e["field"] == "target"]) == 1
        assert len([e for e in result.detailed_errors if e["field"] == "type"]) == 1
    
    def test_successful_validation_scenario(self):
        """Verify successful validation with no errors."""
        test_data = {"id": "e1", "text": "Apple Inc", "type": "Organization", "confidence": 0.95}
        result = ValidationResult(is_valid=True, data=test_data)
        
        # No errors added
        assert result.is_valid
        assert result.data == test_data
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        assert len(result.detailed_errors) == 0
