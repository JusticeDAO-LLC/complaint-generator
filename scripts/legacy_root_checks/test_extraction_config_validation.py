"""Tests for ExtractionConfig field validation."""

import sys
sys.path.insert(0, '/home/barberb/complaint-generator/ipfs_datasets_py')

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import ExtractionConfig


class TestExtractionConfigValidation:
    """Tests for ExtractionConfig field validation."""

    def test_confidence_threshold_valid_range(self):
        """Test that confidence_threshold must be between 0 and 1."""
        # Valid values
        config = ExtractionConfig(confidence_threshold=0.0)
        assert config.confidence_threshold == 0.0
        
        config = ExtractionConfig(confidence_threshold=0.5)
        assert config.confidence_threshold == 0.5
        
        config = ExtractionConfig(confidence_threshold=1.0)
        assert config.confidence_threshold == 1.0

    def test_confidence_threshold_invalid_range(self):
        """Test that confidence_threshold validation rejects out-of-range values."""
        config = ExtractionConfig(confidence_threshold=1.5)
        # validate() should catch this
        with pytest.raises(ValueError):
            config.validate()
        
        config = ExtractionConfig(confidence_threshold=-0.1)
        with pytest.raises(ValueError):
            config.validate()

    def test_max_confidence_valid_range(self):
        """Test that max_confidence must be between 0 and 1."""
        config = ExtractionConfig(max_confidence=0.0)
        assert config.max_confidence == 0.0
        
        config = ExtractionConfig(max_confidence=0.95)
        assert config.max_confidence == 0.95
        
        config = ExtractionConfig(max_confidence=1.0)
        assert config.max_confidence == 1.0

    def test_max_confidence_invalid_range(self):
        """Test that max_confidence validation rejects out-of-range values."""
        config = ExtractionConfig(max_confidence=1.5)
        with pytest.raises(ValueError):
            config.validate()
        
        config = ExtractionConfig(max_confidence=-0.5)
        with pytest.raises(ValueError):
            config.validate()

    def test_llm_fallback_threshold_valid_range(self):
        """Test that llm_fallback_threshold must be between 0 and 1."""
        config = ExtractionConfig(llm_fallback_threshold=0.0)
        assert config.llm_fallback_threshold == 0.0
        
        config = ExtractionConfig(llm_fallback_threshold=0.5)
        assert config.llm_fallback_threshold == 0.5
        
        config = ExtractionConfig(llm_fallback_threshold=1.0)
        assert config.llm_fallback_threshold == 1.0

    def test_llm_fallback_threshold_invalid_range(self):
        """Test that llm_fallback_threshold validation rejects out-of-range values."""
        config = ExtractionConfig(llm_fallback_threshold=1.5)
        with pytest.raises(ValueError):
            config.validate()
        
        config = ExtractionConfig(llm_fallback_threshold=-0.1)
        with pytest.raises(ValueError):
            config.validate()

    def test_max_entities_non_negative(self):
        """Test that max_entities must be non-negative (0 = unlimited)."""
        config = ExtractionConfig(max_entities=0)
        assert config.max_entities == 0
        
        config = ExtractionConfig(max_entities=100)
        assert config.max_entities == 100
        
        config = ExtractionConfig(max_entities=10000)
        assert config.max_entities == 10000

    def test_max_entities_negative_invalid(self):
        """Test that negative max_entities is invalid."""
        config = ExtractionConfig(max_entities=-1)
        with pytest.raises(ValueError):
            config.validate()

    def test_max_relationships_non_negative(self):
        """Test that max_relationships must be non-negative."""
        config = ExtractionConfig(max_relationships=0)
        assert config.max_relationships == 0
        
        config = ExtractionConfig(max_relationships=50)
        assert config.max_relationships == 50

    def test_max_relationships_negative_invalid(self):
        """Test that negative max_relationships is invalid."""
        config = ExtractionConfig(max_relationships=-1)
        with pytest.raises(ValueError):
            config.validate()

    def test_min_entity_length_positive(self):
        """Test that min_entity_length must be positive."""
        config = ExtractionConfig(min_entity_length=1)
        assert config.min_entity_length == 1
        
        config = ExtractionConfig(min_entity_length=10)
        assert config.min_entity_length == 10

    def test_min_entity_length_zero_invalid(self):
        """Test that zero min_entity_length is invalid."""
        config = ExtractionConfig(min_entity_length=0)
        with pytest.raises(ValueError):
            config.validate()

    def test_min_entity_length_negative_invalid(self):
        """Test that negative min_entity_length is invalid."""
        config = ExtractionConfig(min_entity_length=-5)
        with pytest.raises(ValueError):
            config.validate()

    def test_window_size_positive(self):
        """Test that window_size must be positive."""
        config = ExtractionConfig(window_size=1)
        assert config.window_size == 1
        
        config = ExtractionConfig(window_size=256)
        assert config.window_size == 256

    def test_window_size_zero_invalid(self):
        """Test that zero window_size is invalid."""
        config = ExtractionConfig(window_size=0)
        with pytest.raises(ValueError):
            config.validate()

    def test_window_size_negative_invalid(self):
        """Test that negative window_size is invalid."""
        config = ExtractionConfig(window_size=-100)
        with pytest.raises(ValueError):
            config.validate()

    def test_include_properties_boolean(self):
        """Test that include_properties must be boolean."""
        config = ExtractionConfig(include_properties=True)
        assert config.include_properties is True
        
        config = ExtractionConfig(include_properties=False)
        assert config.include_properties is False

    def test_domain_vocab_dict_type(self):
        """Test that domain_vocab must be a dict."""
        config = ExtractionConfig(domain_vocab={})
        assert config.domain_vocab == {}
        
        config = ExtractionConfig(domain_vocab={'legal': ['court', 'attorney']})
        assert config.domain_vocab == {'legal': ['court', 'attorney']}

    def test_domain_vocab_values_are_lists(self):
        """Test that domain_vocab values must be lists of strings."""
        config = ExtractionConfig(domain_vocab={'tech': ['API', 'database']})
        assert isinstance(config.domain_vocab['tech'], list)
        assert all(isinstance(v, str) for v in config.domain_vocab['tech'])

    def test_custom_rules_list_type(self):
        """Test that custom_rules must be a list."""
        config = ExtractionConfig(custom_rules=[])
        assert config.custom_rules == []
        
        config = ExtractionConfig(custom_rules=[('pattern', 'action')])
        assert len(config.custom_rules) == 1

    def test_stopwords_list_type(self):
        """Test that stopwords must be a list."""
        config = ExtractionConfig(stopwords=[])
        assert config.stopwords == []
        
        config = ExtractionConfig(stopwords=['the', 'a', 'an'])
        assert config.stopwords == ['the', 'a', 'an']

    def test_stopwords_string_elements(self):
        """Test that stopwords must contain strings."""
        config = ExtractionConfig(stopwords=['the', 'a', 'an'])
        assert all(isinstance(sw, str) for sw in config.stopwords)

    def test_allowed_entity_types_list_type(self):
        """Test that allowed_entity_types must be a list."""
        config = ExtractionConfig(allowed_entity_types=[])
        assert config.allowed_entity_types == []
        
        config = ExtractionConfig(allowed_entity_types=['PERSON', 'ORG', 'LOCATION'])
        assert config.allowed_entity_types == ['PERSON', 'ORG', 'LOCATION']

    def test_allowed_entity_types_string_elements(self):
        """Test that allowed_entity_types must contain strings."""
        config = ExtractionConfig(allowed_entity_types=['PERSON', 'ORG'])
        assert all(isinstance(t, str) for t in config.allowed_entity_types)

    def test_validate_passes_for_default_config(self):
        """Test that default config passes validation."""
        config = ExtractionConfig()
        # Should not raise
        config.validate()

    def test_validate_passes_for_custom_valid_config(self):
        """Test that custom valid config passes validation."""
        config = ExtractionConfig(
            confidence_threshold=0.7,
            max_entities=100,
            max_relationships=50,
            window_size=256,
            include_properties=True,
            min_entity_length=2,
            llm_fallback_threshold=0.5,
            max_confidence=0.95,
            stopwords=['the', 'a'],
            domain_vocab={'tech': ['API']},
            allowed_entity_types=['PERSON', 'ORG'],
            custom_rules=[('pattern', 'action')]
        )
        # Should not raise
        config.validate()

    def test_thresholds_consistency(self):
        """Test that confidence_threshold should typically be < max_confidence."""
        config = ExtractionConfig(
            confidence_threshold=0.8,
            max_confidence=0.95
        )
        # confidence_threshold should be less than max_confidence
        assert config.confidence_threshold < config.max_confidence
        config.validate()

    def test_llm_fallback_threshold_meaning(self):
        """Test reasonable llm_fallback_threshold values."""
        # If confidence < llm_fallback_threshold, use LLM
        config = ExtractionConfig(
            confidence_threshold=0.5,
            llm_fallback_threshold=0.6
        )
        assert config.llm_fallback_threshold >= config.confidence_threshold
        config.validate()

    def test_empty_stopwords_allowed(self):
        """Test that empty stopwords list is allowed."""
        config = ExtractionConfig(stopwords=[])
        config.validate()
        assert config.stopwords == []

    def test_empty_domain_vocab_allowed(self):
        """Test that empty domain_vocab dict is allowed."""
        config = ExtractionConfig(domain_vocab={})
        config.validate()
        assert config.domain_vocab == {}

    def test_empty_allowed_entity_types_allowed(self):
        """Test that empty allowed_entity_types list is allowed."""
        config = ExtractionConfig(allowed_entity_types=[])
        config.validate()
        assert config.allowed_entity_types == []

    def test_large_max_entities(self):
        """Test that large max_entities values are allowed."""
        config = ExtractionConfig(max_entities=1000000)
        config.validate()
        assert config.max_entities == 1000000

    def test_large_window_size(self):
        """Test that large window_size values are allowed."""
        config = ExtractionConfig(window_size=8192)
        config.validate()
        assert config.window_size == 8192

    def test_very_small_min_entity_length(self):
        """Test that min_entity_length=1 is valid (minimum)."""
        config = ExtractionConfig(min_entity_length=1)
        config.validate()
        assert config.min_entity_length == 1

    def test_high_min_entity_length(self):
        """Test that high min_entity_length values are allowed."""
        config = ExtractionConfig(min_entity_length=100)
        config.validate()
        assert config.min_entity_length == 100


class TestExtractionConfigValidationEdgeCases:
    """Edge case tests for ExtractionConfig validation."""

    def test_float_threshold_precision(self):
        """Test that floating-point precision doesn't break validation."""
        config = ExtractionConfig(confidence_threshold=0.1 + 0.2)  # Float precision issue
        # Should validate despite floating-point representation
        config.validate()

    def test_unicode_in_stopwords(self):
        """Test that unicode strings in stopwords are allowed."""
        config = ExtractionConfig(stopwords=['the', 'é', 'café', '日本'])
        config.validate()
        assert 'é' in config.stopwords
        assert '日本' in config.stopwords

    def test_unicode_in_entity_types(self):
        """Test that unicode strings in allowed_entity_types are allowed."""
        config = ExtractionConfig(allowed_entity_types=['PERSON', '人物'])
        config.validate()
        assert '人物' in config.allowed_entity_types

    def test_special_characters_in_stopwords(self):
        """Test that special characters in stopwords are allowed."""
        config = ExtractionConfig(stopwords=['...', '---', '***', '()', '[]'])
        config.validate()
        assert '...' in config.stopwords

    def test_domain_vocab_complex_nesting(self):
        """Test domain_vocab with multiple domains and entities."""
        config = ExtractionConfig(
            domain_vocab={
                'legal': ['court', 'attorney', 'plaintiff', 'defendant'],
                'medical': ['diagnosis', 'treatment', 'patient'],
                'technical': ['API', 'database', 'server', 'client']
            }
        )
        config.validate()
        assert len(config.domain_vocab) == 3
        assert len(config.domain_vocab['legal']) == 4

    def test_duplicate_stopwords_allowed(self):
        """Test that duplicate entries in stopwords list are allowed (just inefficient)."""
        config = ExtractionConfig(stopwords=['the', 'a', 'the', 'a'])
        config.validate()
        assert config.stopwords.count('the') == 2

    def test_duplicate_entity_types_allowed(self):
        """Test that duplicate entries in allowed_entity_types are allowed."""
        config = ExtractionConfig(allowed_entity_types=['PERSON', 'ORG', 'PERSON'])
        config.validate()
        assert config.allowed_entity_types.count('PERSON') == 2

    def test_empty_string_in_stopwords(self):
        """Test that empty string in stopwords is technically allowed (but unusual)."""
        config = ExtractionConfig(stopwords=['', 'the', 'a'])
        config.validate()
        assert '' in config.stopwords

    def test_very_long_stopword(self):
        """Test that very long stopwords are allowed."""
        long_stopword = 'a' * 1000
        config = ExtractionConfig(stopwords=[long_stopword])
        config.validate()
        assert long_stopword in config.stopwords

    def test_many_stopwords(self):
        """Test that large stopwords lists are allowed."""
        stopwords = [f'word{i}' for i in range(1000)]
        config = ExtractionConfig(stopwords=stopwords)
        config.validate()
        assert len(config.stopwords) == 1000


class TestExtractionConfigFieldDefaults:
    """Tests for ExtractionConfig field default values."""

    def test_confidence_threshold_default(self):
        """Test default confidence_threshold value."""
        config = ExtractionConfig()
        assert config.confidence_threshold == 0.5

    def test_max_entities_default(self):
        """Test default max_entities value (0 = unlimited)."""
        config = ExtractionConfig()
        assert config.max_entities == 0

    def test_max_relationships_default(self):
        """Test default max_relationships value."""
        config = ExtractionConfig()
        assert config.max_relationships == 0

    def test_window_size_default(self):
        """Test default window_size value."""
        config = ExtractionConfig()
        assert config.window_size == 5

    def test_include_properties_default(self):
        """Test default include_properties value."""
        config = ExtractionConfig()
        assert config.include_properties is True

    def test_min_entity_length_default(self):
        """Test default min_entity_length value."""
        config = ExtractionConfig()
        assert config.min_entity_length == 2

    def test_llm_fallback_threshold_default(self):
        """Test default llm_fallback_threshold value."""
        config = ExtractionConfig()
        assert config.llm_fallback_threshold == 0.0

    def test_max_confidence_default(self):
        """Test default max_confidence value."""
        config = ExtractionConfig()
        assert config.max_confidence == 1.0

    def test_domain_vocab_default(self):
        """Test default domain_vocab value (empty dict)."""
        config = ExtractionConfig()
        assert config.domain_vocab == {}

    def test_custom_rules_default(self):
        """Test default custom_rules value (empty list)."""
        config = ExtractionConfig()
        assert config.custom_rules == []

    def test_stopwords_default(self):
        """Test default stopwords value (empty list)."""
        config = ExtractionConfig()
        assert config.stopwords == []

    def test_allowed_entity_types_default(self):
        """Test default allowed_entity_types value (empty list)."""
        config = ExtractionConfig()
        assert config.allowed_entity_types == []
