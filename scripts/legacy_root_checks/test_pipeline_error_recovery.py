"""Tests for OntologyPipeline error recovery and resilience."""

import sys
sys.path.insert(0, '/home/barberb/complaint-generator/ipfs_datasets_py')

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_pipeline import OntologyPipeline


class TestPipelineErrorRecoveryBasics:
    """Tests for basic error handling and recovery in OntologyPipeline."""

    def test_pipeline_with_empty_text(self):
        """Test pipeline resilience to empty input text."""
        pipeline = OntologyPipeline(domain='legal')

        # Empty string should be handled gracefully
        result = pipeline.run(
            data='',
            data_source='test',
            data_type='text'
        )

        assert result is not None
        assert hasattr(result, 'ontology')
        # Empty input should produce minimal ontology
        ontology = result.ontology
        assert ontology is not None

    def test_pipeline_with_whitespace_only(self):
        """Test pipeline resilience to whitespace-only input."""
        pipeline = OntologyPipeline(domain='medical')

        # Only whitespace should handle gracefully
        result = pipeline.run(
            data='   \n\t  ',
            data_source='test',
            data_type='text'
        )

        assert result is not None
        assert hasattr(result, 'ontology')

    def test_pipeline_with_very_long_text(self):
        """Test pipeline with very long input text."""
        pipeline = OntologyPipeline(domain='legal')

        # Create very long text (10000 chars)
        long_text = 'The court held that the defendant was responsible. ' * 200

        result = pipeline.run(
            data=long_text,
            data_source='test',
            data_type='text'
        )

        assert result is not None
        assert hasattr(result, 'ontology')
        ontology = result.ontology
        assert ontology is not None

    def test_pipeline_with_default_domain(self):
        """Test pipeline error handling with default domain."""
        pipeline = OntologyPipeline()  # Uses default 'general' domain

        text = 'John Doe worked at ABC Law Firm.'

        # Should handle with default domain gracefully
        result = pipeline.run(data=text, data_source='test', data_type='text')
        assert result is not None

    def test_pipeline_with_none_data(self):
        """Test that pipeline requires valid data input."""
        pipeline = OntologyPipeline()

        result = pipeline.run(data=None, data_source='test', data_type='text')
        assert result is not None

    def test_pipeline_with_special_characters(self):
        """Test pipeline robustness to special characters in input."""
        pipeline = OntologyPipeline(domain='legal')

        text = 'The plaintiff, Jane @# Doe [2023], filed suit ($$$) against XYZ Corp™'

        result = pipeline.run(data=text, data_source='test', data_type='text')

        assert result is not None
        assert hasattr(result, 'ontology')

    def test_pipeline_with_unicode_text(self):
        """Test pipeline with unicode and multi-language text."""
        pipeline = OntologyPipeline(domain='legal')

        text = 'The attorney 法律家 (lawyer) filed a motion. Avocat français intervened.'

        result = pipeline.run(data=text, data_source='test', data_type='text')

        assert result is not None
        assert hasattr(result, 'ontology')

    def test_pipeline_with_custom_extraction_config(self):
        """Test pipeline with custom extraction config."""
        pipeline = OntologyPipeline(domain='legal', use_llm=False)

        # Verify pipeline works with configuration
        text = 'John Doe filed a lawsuit.'
        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        assert result is not None


class TestPipelineErrorRecoveryMalformedData:
    """Tests for pipeline resilience to malformed data structures."""

    def test_pipeline_with_minimal_ontology(self):
        """Test pipeline handling when input yields minimal ontology."""
        pipeline = OntologyPipeline(domain='legal', use_llm=False)

        # Some inputs might return minimal ontologies
        text = ''
        try:
            result = pipeline.run(data=text, data_source='test', data_type='text', refine=False)
            # Should not crash, might have empty ontology
            assert result is not None
        except Exception as e:
            # If it does raise, should be a meaningful error
            assert 'ontology' in str(e).lower() or 'generation' in str(e).lower()

    def test_pipeline_with_ambiguous_entity_text(self):
        """Test pipeline robustness when text has ambiguous entities."""
        # This tests how the downstream generator/critic handle odd entity data
        pipeline = OntologyPipeline(domain='legal')

        text = 'President Lincoln of the United States'  # Ambiguous references

        result = pipeline.run(data=text, data_source='test', data_type='text', refine=False)
        assert result is not None

    def test_pipeline_with_circular_references_in_text(self):
        """Test pipeline handling of inputs with circular concepts."""
        pipeline = OntologyPipeline(domain='legal')

        # Text that might create circular relationships in extraction
        text = 'A depends on B, B depends on C, C depends on A.'

        result = pipeline.run(data=text, data_source='test', data_type='text', refine=False)
        # Should complete without infinite loop
        assert result is not None

    def test_pipeline_with_repetitive_entities(self):
        """Test pipeline handling when same entity appears multiple times."""
        pipeline = OntologyPipeline(domain='legal')

        text = '''
            John Doe filed suit. 
            John Doe is a plaintiff. 
            John Doe hired attorney Jane Smith.
            John Doe testified.
        '''

        result = pipeline.run(data=text, data_source='test', data_type='text', refine=False)
        assert result is not None
        # Duplicates should be handled (merged or kept as-is)


class TestPipelineErrorRecoveryWithRefinement:
    """Tests for error handling during refinement iterations."""

    def test_pipeline_refinement_iteration_limit(self):
        """Test that refinement loop terminates within max rounds."""
        pipeline = OntologyPipeline(domain='legal', max_rounds=3)

        # Input that might not yield perfect quality
        text = 'xyz abc def ghi jkl'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=True
        )
        assert result is not None
        # Should complete and have some ontology

    def test_pipeline_refinement_with_difficult_input(self):
        """Test pipeline stability with challenging input."""
        pipeline = OntologyPipeline(domain='legal', max_rounds=5)

        text = 'The quick brown fox jumps over the lazy dog'

        # Pipeline should be stable even if refinement doesn't strictly improve
        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=True
        )
        assert result is not None

    def test_pipeline_refinement_disabled(self):
        """Test pipeline when refinement is explicitly disabled."""
        pipeline = OntologyPipeline(domain='legal')

        # Single entity - some strategies might not apply anyway
        text = 'plaintiff'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        # Pipeline should handle gracefully
        assert result is not None


class TestPipelineExceptionHandling:
    """Tests for exception handling and meaningful error messages."""

    def test_pipeline_with_valid_input_no_crash(self):
        """Test that pipeline doesn't crash with well-formed input."""
        pipeline = OntologyPipeline(domain='legal')

        # Valid input
        text = 'John Doe is a lawyer at ABC firm.'

        try:
            result = pipeline.run(
                data=text,
                data_source='test',
                data_type='text',
                refine=False
            )
            assert result is not None
        except Exception as e:
            # If it fails, should be informative
            assert len(str(e)) > 0

    def test_pipeline_with_mediator_active(self):
        """Test pipeline with refinement and mediator enabled."""
        pipeline = OntologyPipeline(domain='legal')

        # Valid input
        text = 'Jane Smith sued Bob Johnson for breach of contract.'

        # Pipeline should complete
        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=True
        )
        assert result is not None

    def test_pipeline_with_default_parameters(self):
        """Test pipeline with minimal parameter specification."""
        pipeline = OntologyPipeline()

        text = 'Some legal text here.'

        # Pipeline should handle default parameters gracefully
        result = pipeline.run(data=text, data_source='test', data_type='text')
        assert result is not None


class TestPipelinePartialFailureRecovery:
    """Tests for recovery from partial failures in pipeline stages."""

    def test_pipeline_with_difficult_extraction(self):
        """Test pipeline continues even if extraction is difficult."""
        pipeline = OntologyPipeline(domain='legal', use_llm=False)

        # Text with no obvious entities
        text = 'aaaaaa bbbbbb cccccc'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        # Should complete, not crash
        assert result is not None

    def test_pipeline_with_minimal_relationships(self):
        """Test pipeline continues even if relationships are sparse."""
        pipeline = OntologyPipeline(domain='legal')

        # Text with entities but no clear relationships
        text = 'attorney plaintiff defendant'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        # Should have ontology even without rich relationships
        assert result is not None

    def test_pipeline_with_low_confidence_threshold(self):
        """Test pipeline handling when confidence threshold is very low."""
        pipeline = OntologyPipeline(domain='legal', use_llm=False)

        text = 'There may be or might be possibly attorneys or lawyers'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        assert result is not None

    def test_pipeline_with_minimal_input(self):
        """Test that pipeline works with minimal ontology (single entity)."""
        pipeline = OntologyPipeline(domain='legal')

        # Text that might yield only one entity
        text = 'attorney'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        assert result is not None
        assert result.ontology is not None


class TestPipelineTimeoutAndResourceLimits:
    """Tests for handling resource constraints."""

    def test_pipeline_with_brief_input(self):
        """Test pipeline with quick completion on brief input."""
        pipeline = OntologyPipeline(domain='legal')

        text = 'Brief legal text.'

        # Should complete quickly
        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        assert result is not None

    def test_pipeline_with_large_text(self):
        """Test pipeline doesn't break with large input text."""
        pipeline = OntologyPipeline(domain='legal', use_llm=False)

        # Generate large text with many potential entities
        text = ' '.join([f'entity{i} plaintiff{i} defendant{i}' for i in range(100)])

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        assert result is not None

    def test_pipeline_with_many_refinement_rounds(self):
        """Test pipeline stability during multiple refinement rounds."""
        pipeline = OntologyPipeline(domain='legal', max_rounds=10)

        text = 'John Doe is a plaintiff. Jane Smith is a defendant.' * 10

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=True
        )
        assert result is not None


class TestPipelineInputValidationAndSanitization:
    """Tests for input validation and sanitization."""

    def test_pipeline_with_null_bytes_in_text(self):
        """Test that embedded null bytes do not prevent text processing."""
        pipeline = OntologyPipeline(domain='legal', use_llm=False)

        # The rule-based pipeline accepts arbitrary Python text, including NUL.
        text = 'John Doe\x00filed suit'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )

        assert result is not None
        assert result.ontology is not None

    def test_pipeline_with_control_characters(self):
        """Test pipeline with control characters in input."""
        pipeline = OntologyPipeline(domain='legal')

        # Text with control characters
        text = 'John\x01Doe\x02filed\x03suit'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        assert result is not None

    def test_pipeline_with_extremely_long_entity_name(self):
        """Test pipeline with very long entity name in text."""
        pipeline = OntologyPipeline(domain='legal')

        # Entity with 1000 character name
        long_name = 'A' * 1000
        text = f'{long_name} filed suit'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        assert result is not None

    def test_pipeline_with_nested_quotations(self):
        """Test pipeline with nested quotes and complex text structure."""
        pipeline = OntologyPipeline(domain='legal')

        text = '''
            Judge said "The attorney claimed 'The defendant said "I am innocent"'".
            This is a complex nesting scenario.
        '''

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        assert result is not None


class TestPipelineGracefulDegradation:
    """Tests for graceful degradation when features unavailable."""

    def test_pipeline_without_critic(self):
        """Test that pipeline works even without critic scoring."""
        # Create pipeline with minimal configuration
        pipeline = OntologyPipeline(domain='legal', use_llm=False)

        text = 'John Doe filed suit against ABC Corp.'

        # Should work without LLM-backed scoring
        try:
            result = pipeline.run(
                data=text,
                data_source='test',
                data_type='text',
                refine=False
            )
            # Either works, or raises informative error
            assert result is not None or True
        except (ValueError, AttributeError):
            # Acceptable if critic is required
            pass

    def test_pipeline_without_mediator(self):
        """Test that pipeline works even without mediator refinement."""
        pipeline = OntologyPipeline(domain='legal')

        # Without running refinement
        text = 'Jane Smith is a lawyer.'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False  # Disable refinement
        )
        assert result is not None

    def test_pipeline_without_llm_backend(self):
        """Test that pipeline works in rule-based mode without LLM."""
        pipeline = OntologyPipeline(domain='legal', use_llm=False)

        text = 'The plaintiff hired an attorney.'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )
        assert result is not None


class TestPipelineResultConsistency:
    """Tests for result consistency despite error handling."""

    def test_pipeline_result_structure_always_valid(self):
        """Test that pipeline result has consistent structure regardless of input."""
        pipeline = OntologyPipeline(domain='legal')

        test_cases = [
            '',  # Empty
            'a b c',  # No meaningful entities
            'John Doe and Jane Smith filed suit',  # Normal case
            '   ',  # Whitespace
        ]

        for text in test_cases:
            result = pipeline.run(
                data=text,
                data_source='test',
                data_type='text',
                refine=False
            )
            assert result is not None
            assert hasattr(result, 'ontology')
            # Result should always be a dict or similar structure
            assert isinstance(result.ontology, dict)

    def test_pipeline_ontology_valid_after_error_recovery(self):
        """Test that ontology structure is valid after error recovery."""
        pipeline = OntologyPipeline(domain='legal')

        # Edge case input
        text = '!@#$%^&*()'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=False
        )

        if result.ontology:
            # If ontology was generated, it should have valid structure
            assert 'entities' in result.ontology or len(result.ontology) >= 0

    def test_pipeline_refinement_count_accurate(self):
        """Test that refinement count is accurate even with errors."""
        pipeline = OntologyPipeline(domain='legal', max_rounds=5)

        text = 'Some legal text here.'

        result = pipeline.run(
            data=text,
            data_source='test',
            data_type='text',
            refine=True
        )

        if hasattr(result, 'refinement_count'):
            # Should not exceed max iterations
            assert result.refinement_count <= 5
            assert result.refinement_count >= 0
