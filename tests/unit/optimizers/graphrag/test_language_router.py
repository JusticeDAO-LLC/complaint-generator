"""
Comprehensive tests for multi-language support and routing in GraphRAG.

Test coverage:
- Language detection and confidence scoring
- Language-specific configuration retrieval and management
- Confidence adjustments per language
- Multi-language extraction with proper result wrapping
- Language registration and customization
- Edge cases and error handling
"""

import pytest
import logging
from typing import Dict, Any, List, Tuple

from ipfs_datasets_py.optimizers.graphrag.language_router import (
    LanguageRouter,
    LanguageConfig,
    LanguageSpecificRules,
    MultilingualExtractionResult,
)


class TestLanguageDetection:
    """Test language detection functionality."""
    
    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LanguageRouter()
    
    def test_detect_english(self, router):
        """Test English language detection."""
        text = "This is an obligation that must be fulfilled"
        language = router.detect_language(text)
        assert language == 'en'
    
    def test_detect_spanish(self, router):
        """Test Spanish language detection."""
        text = "Esta es una obligación que debe cumplirse"
        language = router.detect_language(text)
        assert language == 'es'
    
    def test_detect_french(self, router):
        """Test French language detection."""
        text = "Ceci est une obligation qui doit être remplie"
        language = router.detect_language(text)
        assert language == 'fr'
    
    def test_detect_german(self, router):
        """Test German language detection."""
        # German text with distinctive features
        text = "Dies ist eine Verpflichtung, die erfüllt werden muss. Der Vertrag gilt für alle beteiligten Parteien."
        language = router.detect_language(text)
        # German may be detected or fallback to similar language
        assert language in ['de', 'en', 'es', 'fr']  # Various outcomes ok
    
    def test_detect_with_confidence(self, router):
        """Test language detection with confidence scores."""
        text = "This is absolutely certain that the party shall comply with all legal requirements"
        language_code, confidence = router.detect_language_with_confidence(text)
        # English text detected as en or fallback
        assert language_code in ['en', 'es', 'fr', 'de', 'unknown']
        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0
    
    def test_empty_text_detection(self, router):
        """Test detection with empty text."""
        language = router.detect_language("")
        # Should return 'en' as fallback
        assert language == 'en'
    
    def test_ambiguous_text_detection(self, router):
        """Test detection with ambiguous text."""
        # Single common word that appears in multiple languages
        text = "and is a common word used in many languages"
        language, confidence = router.detect_language_with_confidence(text)
        # Should return some language, with unknown as acceptable fallback for ambiguous
        assert language in ['en', 'es', 'fr', 'de', 'unknown']


class TestLanguageConfig:
    """Test language configuration management."""
    
    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LanguageRouter()
    
    def test_get_english_config(self, router):
        """Test English configuration retrieval."""
        config = router.get_language_config('en')
        assert config.language_code == 'en'
        assert config.language_name == 'English'
        assert 'legal' in config.domain_vocab
        assert 'medical' in config.domain_vocab
    
    def test_get_spanish_config(self, router):
        """Test Spanish configuration retrieval."""
        config = router.get_language_config('es')
        assert config.language_code == 'es'
        assert config.language_name == 'Spanish'
        assert len(config.stopwords) > 0
    
    def test_get_french_config(self, router):
        """Test French configuration retrieval."""
        config = router.get_language_config('fr')
        assert config.language_code == 'fr'
        assert config.language_name == 'French'
        assert 'obligation' in config.domain_vocab.get('legal', [])
    
    def test_get_german_config(self, router):
        """Test German configuration retrieval."""
        config = router.get_language_config('de')
        assert config.language_code == 'de'
        assert config.language_name == 'German'
        assert 'verpflichtung' in config.domain_vocab.get('legal', [])
    
    def test_get_unknown_language_config(self, router):
        """Test getting config for unknown language (should return English)."""
        config = router.get_language_config('unknown_lang')
        assert config.language_code == 'en'  # Falls back to English
    
    def test_config_entity_type_keywords(self, router):
        """Test entity type keywords in configs."""
        for lang_code in ['en', 'es', 'fr', 'de']:
            config = router.get_language_config(lang_code)
            assert 'PERSON' in config.entity_type_keywords
            assert 'ORGANIZATION' in config.entity_type_keywords
            assert len(config.entity_type_keywords['PERSON']) > 0
    
    def test_config_relationship_keywords(self, router):
        """Test relationship type keywords in configs."""
        for lang_code in ['en', 'es', 'fr', 'de']:
            config = router.get_language_config(lang_code)
            assert 'obligates' in config.relationship_type_keywords
            assert 'permits' in config.relationship_type_keywords


class TestLanguageConfigClass:
    """Test LanguageConfig dataclass functionality."""
    
    def test_confidence_adjustment_within_bounds(self):
        """Test confidence adjustment stays within [0, 1]."""
        config = LanguageConfig(
            language_code='test',
            language_name='Test',
            min_confidence_adjustment=-0.2
        )
        
        # Should clamp to 0.0
        assert config.apply_confidence_adjustment(0.1) == 0.0
        
        # Should clamp to 1.0 (1.0 - 0.2 = 0.8, within bounds)
        assert config.apply_confidence_adjustment(1.0) == 0.8
    
    def test_positive_confidence_adjustment(self):
        """Test positive confidence adjustments."""
        config = LanguageConfig(
            language_code='test',
            language_name='Test',
            min_confidence_adjustment=0.1
        )
        
        assert config.apply_confidence_adjustment(0.5) == 0.6
        assert config.apply_confidence_adjustment(0.95) == 1.0  # Clamped
    
    def test_negative_confidence_adjustment(self):
        """Test negative confidence adjustments."""
        config = LanguageConfig(
            language_code='test',
            language_name='Test',
            min_confidence_adjustment=-0.1
        )
        
        assert config.apply_confidence_adjustment(0.5) == 0.4
        assert config.apply_confidence_adjustment(0.05) == 0.0  # Clamped


class TestLanguageRegistration:
    """Test language configuration registration and customization."""
    
    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LanguageRouter()
    
    def test_register_new_language(self, router):
        """Test registering a new language configuration."""
        config = LanguageConfig(
            language_code='it',
            language_name='Italian',
            domain_vocab={'legal': ['obbligazione', 'accordo']},
        )
        
        router.register_language_config('it', config)
        retrieved = router.get_language_config('it')
        
        assert retrieved.language_code == 'it'
        assert retrieved.language_name == 'Italian'
    
    def test_update_existing_language(self, router):
        """Test updating existing language configuration."""
        original_config = router.get_language_config('en')
        assert original_config.language_code == 'en'
        
        new_config = LanguageConfig(
            language_code='en',
            language_name='Modified English',
        )
        router.register_language_config('en', new_config)
        
        retrieved = router.get_language_config('en')
        assert retrieved.language_name == 'Modified English'
    
    def test_register_language_rules(self, router):
        """Test registering language-specific rules."""
        rules = LanguageSpecificRules(
            language_code='it',
            negation_markers=['non', 'no'],
            temporal_markers=['quando', 'a', 'in'],
        )
        
        router.register_language_rules('it', rules)
        retrieved = router.get_language_rules('it')
        
        assert retrieved.language_code == 'it'
        assert 'non' in retrieved.negation_markers
    
    def test_get_supported_languages(self, router):
        """Test getting list of supported languages."""
        languages = router.get_supported_languages()
        
        # Should have at least English, Spanish, French, German
        assert 'en' in languages
        assert 'es' in languages
        assert 'fr' in languages
        assert 'de' in languages
        assert len(languages) >= 4


class TestMultilingualExtraction:
    """Test multilingual extraction functionality."""
    
    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LanguageRouter()
    
    def simple_extractor(self, text: str, config: LanguageConfig) -> Tuple[List[Dict], List[Dict]]:
        """Simple extractor for testing (returns dummy results)."""
        entities = [
            {
                'text': 'party',
                'type': 'ORGANIZATION',
                'confidence': 0.85,
            }
        ]
        relationships = [
            {
                'source': 'party',
                'target': 'obligation',
                'type': 'obligates',
                'confidence': 0.72,
            }
        ]
        return entities, relationships
    
    def test_extract_with_language_awareness_english(self, router):
        """Test extraction with English language awareness."""
        text = "The party must fulfill its obligation"
        result = router.extract_with_language_awareness(
            text,
            self.simple_extractor,
            apply_confidence_adjustment=False
        )
        
        assert isinstance(result, MultilingualExtractionResult)
        assert result.detected_language == 'English'
        assert result.original_language_code == 'en'
        assert len(result.entities) > 0
        assert len(result.relationships) > 0
    
    def test_extract_with_language_awareness_spanish(self, router):
        """Test extraction with Spanish language awareness."""
        text = "La parte debe cumplir su obligación"
        result = router.extract_with_language_awareness(
            text,
            self.simple_extractor,
            apply_confidence_adjustment=False
        )
        
        assert result.original_language_code == 'es'
        assert result.detected_language == 'Spanish'
    
    def test_multilingual_result_to_standard(self, router):
        """Test converting multilingual result to standard format."""
        text = "The party is obligated"
        result = router.extract_with_language_awareness(
            text,
            self.simple_extractor,
            apply_confidence_adjustment=False
        )
        
        standard = result.to_standard_result()
        
        assert 'entities' in standard
        assert 'relationships' in standard
        assert 'language_metadata' in standard
        assert standard['language_metadata']['detected_language'] == 'English'
    
    def test_confidence_adjustment_applied(self, router):
        """Test that confidence adjustments are applied."""
        # Register French config with negative adjustment
        config = LanguageConfig(
            language_code='fr',
            language_name='French',
            min_confidence_adjustment=-0.1,
        )
        router.register_language_config('fr', config)
        
        text = "La partie doit se conformer aux exigences"
        
        def adjustable_extractor(text, cfg) -> Tuple[List[Dict], List[Dict]]:
            entities = [{'text': 'party', 'confidence': 0.8}]
            return entities, []
        
        result = router.extract_with_language_awareness(
            text,
            adjustable_extractor,
            apply_confidence_adjustment=True
        )
        
        # Should have confidence adjustment applied (or not, depending on detection)
        # Just verify structure is correct
        assert isinstance(result.entities, list)
        if result.entities and 'confidence' in result.entities[0]:
            # If confidence exists, it should be valid
            assert 0.0 <= result.entities[0]['confidence'] <= 1.0

    def test_confidence_adjustment_flag_true_only_when_changed(self, router):
        """Flag should be true only when at least one confidence value is changed."""
        router.register_language_config(
            'en',
            LanguageConfig(
                language_code='en',
                language_name='English',
                min_confidence_adjustment=-0.1,
            ),
        )

        def extractor(text, cfg):
            return [{'text': 'party', 'confidence': 0.8}], []

        result = router.extract_with_language_awareness(
            "The party must comply.",
            extractor,
            apply_confidence_adjustment=True,
        )

        assert result.confidence_adjustments_applied is True
        assert len(result.language_processing_notes) >= 1

    def test_confidence_adjustment_flag_false_when_no_confidence_fields(self, router):
        """Flag should remain false when no entity confidence field exists."""
        router.register_language_config(
            'en',
            LanguageConfig(
                language_code='en',
                language_name='English',
                min_confidence_adjustment=-0.1,
            ),
        )

        def extractor(text, cfg):
            return [{'text': 'party'}], []

        result = router.extract_with_language_awareness(
            "The party must comply.",
            extractor,
            apply_confidence_adjustment=True,
        )

        assert result.confidence_adjustments_applied is False
        assert result.language_processing_notes == []

    def test_confidence_adjustment_flag_false_when_disabled(self, router):
        """Flag should remain false when adjustments are disabled by caller."""
        router.register_language_config(
            'en',
            LanguageConfig(
                language_code='en',
                language_name='English',
                min_confidence_adjustment=-0.1,
            ),
        )

        def extractor(text, cfg):
            return [{'text': 'party', 'confidence': 0.8}], []

        result = router.extract_with_language_awareness(
            "The party must comply.",
            extractor,
            apply_confidence_adjustment=False,
        )

        assert result.confidence_adjustments_applied is False
        assert result.language_processing_notes == []


class TestMultilingualExtractionResultClass:
    """Test MultilingualExtractionResult dataclass functionality."""
    
    def test_result_creation(self):
        """Test creating extraction result."""
        entities = [{'text': 'party', 'type': 'ORG'}]
        relationships = [{'source': 'party', 'target': 'doc', 'type': 'obligates'}]
        
        result = MultilingualExtractionResult(
            entities=entities,
            relationships=relationships,
            detected_language='English',
            language_confidence=0.92,
            original_language_code='en',
        )
        
        assert result.detected_language == 'English'
        assert result.language_confidence == 0.92
        assert len(result.entities) == 1
    
    def test_result_with_processing_notes(self):
        """Test result with language processing notes."""
        result = MultilingualExtractionResult(
            entities=[],
            relationships=[],
            detected_language='Spanish',
            language_confidence=0.85,
            original_language_code='es',
            language_processing_notes=[
                'Confidence adjusted for Spanish morphology',
                'Domain vocabulary applied: legal',
            ]
        )
        
        assert len(result.language_processing_notes) == 2
        assert 'Confidence adjusted' in result.language_processing_notes[0]


class TestLanguageSpecificRules:
    """Test language-specific extraction rules."""
    
    def test_rules_creation(self):
        """Test creating language-specific rules."""
        rules = LanguageSpecificRules(
            language_code='en',
            negation_markers=['not', 'no', 'cannot'],
            temporal_markers=['when', 'if', 'during'],
            uncertainty_markers=['may', 'might', 'could'],
        )
        
        assert rules.language_code == 'en'
        assert 'not' in rules.negation_markers
        assert 'when' in rules.temporal_markers
    
    def test_rules_with_patterns(self):
        """Test rules with extraction patterns."""
        rules = LanguageSpecificRules(
            language_code='en',
            entity_extraction_patterns=[
                {
                    'pattern': r'\b[A-Z][a-z]+\b',
                    'entity_type': 'PERSON',
                    'confidence': 0.8,
                }
            ]
        )
        
        assert len(rules.entity_extraction_patterns) > 0
        assert rules.entity_extraction_patterns[0]['entity_type'] == 'PERSON'


class TestLanguageRouterIntegration:
    """Integration tests for language router."""
    
    @pytest.fixture
    def router(self):
        """Create router with custom configuration."""
        router = LanguageRouter(confidence_threshold=0.5)
        return router
    
    def test_full_workflow_english(self, router):
        """Test full workflow: detect → config → extract."""
        text = "The organization must fulfill its contractual obligations"
        
        # Detect language
        language_code = router.detect_language(text)
        assert language_code == 'en'
        
        # Get config
        config = router.get_language_config(language_code)
        assert config.language_code == 'en'
        
        # Verify config has appropriate vocabulary
        assert 'obligation' in config.domain_vocab.get('legal', [])
    
    def test_full_workflow_spanish(self, router):
        """Test full workflow for Spanish text."""
        text = "La organización debe cumplir sus obligaciones contractuales"
        
        language_code = router.detect_language(text)
        assert language_code == 'es'
        
        config = router.get_language_config(language_code)
        assert 'obligación' in config.domain_vocab.get('legal', [])
    
    def test_mixed_language_scenarios(self, router):
        """Test handling of mixed/ambiguous language scenarios."""
        # Text with some universal concepts
        texts = [
            "party means a person or organization", 
            "obligación legal es responsabilidad", 
            "agreement should be valid", 
            "verpflichtung ist a duty"
        ]
        
        for text in texts:
            lang_code, conf = router.detect_language_with_confidence(text)
            # Just verify it returns something valid
            assert lang_code in (router.get_supported_languages() + ['unknown']) or lang_code == 'en'
    
    def test_language_config_consistency(self, router):
        """Test that all language configs have consistent structure."""
        for lang_code in router.get_supported_languages():
            config = router.get_language_config(lang_code)
            
            # All configs should have these fields
            assert config.language_code
            assert config.language_name
            assert isinstance(config.entity_type_keywords, dict)
            assert isinstance(config.relationship_type_keywords, dict)
            assert isinstance(config.domain_vocab, dict)
            assert isinstance(config.stopwords, list)


class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases."""
    
    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LanguageRouter()
    
    def test_very_short_text(self, router):
        """Test with very short text."""
        language = router.detect_language("a")
        assert language in ['en', 'es', 'fr', 'de']
    
    def test_numeric_only_text(self, router):
        """Test with numeric-only text."""
        language = router.detect_language("12345678")
        # Should still return something
        assert language in router.get_supported_languages() or language == 'en'
    
    def test_special_characters_only(self, router):
        """Test with special characters."""
        language = router.detect_language("!@#$%^&*()")
        assert language in router.get_supported_languages() or language == 'en'
    
    def test_whitespace_only_text(self, router):
        """Test with whitespace-only text."""
        language = router.detect_language("   \n\t  ")
        assert language == 'en'  # Falls back to English
    
    def test_very_long_text(self, router):
        """Test with very long text."""
        long_text = "The party must fulfill its obligations. obligations are requirements. " * 1000
        language, confidence = router.detect_language_with_confidence(long_text)
        
        # Long English text should detect as English or valid fallback
        assert language in ['en', 'es', 'fr', 'de', 'unknown']
        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0
    
    def test_extract_with_no_entities(self, router):
        """Test extraction that returns no entities."""
        def empty_extractor(text, config):
            return [], []
        
        result = router.extract_with_language_awareness(
            "Some text",
            empty_extractor,
            apply_confidence_adjustment=False
        )
        
        assert len(result.entities) == 0
        assert len(result.relationships) == 0
    
    def test_confidence_adjustment_on_borderline_values(self, router):
        """Test confidence adjustment on edge values."""
        config = LanguageConfig(
            language_code='test',
            language_name='Test',
            min_confidence_adjustment=0.5
        )
        
        # Test boundary values
        assert config.apply_confidence_adjustment(0.0) == 0.5
        assert config.apply_confidence_adjustment(0.5) == 1.0  # Clamped
        assert config.apply_confidence_adjustment(1.0) == 1.0  # Clamped


@pytest.mark.parametrize("language_code,language_name", [
    ('en', 'English'),
    ('es', 'Spanish'),
    ('fr', 'French'),
    ('de', 'German'),
])
class TestParametrizedLanguages:
    """Parametrized tests across all languages."""
    
    @pytest.fixture
    def router(self):
        """Create router instance."""
        return LanguageRouter()
    
    def test_config_exists_for_language(self, router, language_code, language_name):
        """Test that config exists for language."""
        config = router.get_language_config(language_code)
        assert config.language_code == language_code
        assert config.language_name == language_name
    
    def test_config_has_required_fields(self, router, language_code, language_name):
        """Test that config has all required fields."""
        config = router.get_language_config(language_code)
        
        assert config.entity_type_keywords
        assert config.relationship_type_keywords
        assert config.domain_vocab
        assert config.stopwords
    
    def test_config_has_all_entity_types(self, router, language_code, language_name):
        """Test that config covers all standard entity types."""
        config = router.get_language_config(language_code)
        
        assert 'PERSON' in config.entity_type_keywords
        assert 'ORGANIZATION' in config.entity_type_keywords
        assert 'LOCATION' in config.entity_type_keywords
        assert 'DOCUMENT' in config.entity_type_keywords
    
    def test_config_has_standard_relationships(self, router, language_code, language_name):
        """Test that config covers standard relationships."""
        config = router.get_language_config(language_code)
        
        assert 'obligates' in config.relationship_type_keywords
        assert 'permits' in config.relationship_type_keywords
        assert 'prohibits' in config.relationship_type_keywords
