"""Tests for domain-aware configuration factory in ExtractionConfig.

This module tests the ExtractionConfig.for_domain() classmethod, which creates
optimized configurations based on document domain and benchmarked sentence_window
recommendations from SENTENCE_WINDOW_BENCHMARK_REPORT.md.

Test Coverage:
- Domain-specific sentence_window defaults (legal=2, technical=2, financial=2)
- Case-insensitive domain matching
- Fallback behavior for unrecognized domains
- Field value verification for known domains
- Roundtrip serialization compatibility
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import ExtractionConfig


class TestDomainAwareConfigFactory:
    """Test suite for ExtractionConfig.for_domain() factory method."""

    def test_domain_config_for_legal(self):
        """Test that legal domain config has sentence_window=2."""
        cfg = ExtractionConfig.for_domain("legal")
        assert cfg.sentence_window == 2
        assert isinstance(cfg, ExtractionConfig)

    def test_domain_config_for_technical(self):
        """Test that technical domain config has sentence_window=2."""
        cfg = ExtractionConfig.for_domain("technical")
        assert cfg.sentence_window == 2
        assert isinstance(cfg, ExtractionConfig)

    def test_domain_config_for_financial(self):
        """Test that financial domain config has sentence_window=2."""
        cfg = ExtractionConfig.for_domain("financial")
        assert cfg.sentence_window == 2
        assert isinstance(cfg, ExtractionConfig)

    def test_domain_config_for_finance_alias(self):
        """Test that 'finance' alias also maps to sentence_window=2."""
        cfg = ExtractionConfig.for_domain("finance")
        assert cfg.sentence_window == 2

    def test_domain_config_case_insensitive(self):
        """Test that domain names are case-insensitive."""
        cfg_lower = ExtractionConfig.for_domain("legal")
        cfg_upper = ExtractionConfig.for_domain("LEGAL")
        cfg_mixed = ExtractionConfig.for_domain("LegAl")
        
        assert cfg_lower.sentence_window == cfg_upper.sentence_window == cfg_mixed.sentence_window == 2

    def test_domain_config_handles_whitespace(self):
        """Test that domain names with leading/trailing whitespace are handled."""
        cfg_clean = ExtractionConfig.for_domain("legal")
        cfg_spaces = ExtractionConfig.for_domain("  legal  ")
        
        assert cfg_clean.sentence_window == cfg_spaces.sentence_window == 2

    def test_domain_config_for_unknown_domain_defaults(self):
        """Test that unknown domain falls back to sentence_window=0."""
        cfg = ExtractionConfig.for_domain("unknown_domain")
        assert cfg.sentence_window == 0

    def test_domain_config_for_general_domain_defaults(self):
        """Test that 'general' or 'default' domain defaults to sentence_window=0."""
        cfg_general = ExtractionConfig.for_domain("general")
        cfg_default = ExtractionConfig.for_domain("default")
        
        assert cfg_general.sentence_window == 0
        assert cfg_default.sentence_window == 0

    def test_domain_config_preserves_other_defaults(self):
        """Test that domain config uses standard defaults for non-domain fields."""
        cfg = ExtractionConfig.for_domain("legal")
        
        # Check standard defaults
        assert cfg.confidence_threshold == 0.5
        assert cfg.max_entities == 0
        assert cfg.max_relationships == 0
        assert cfg.window_size == 5
        assert cfg.include_properties is True
        assert cfg.llm_fallback_threshold == 0.0
        assert cfg.min_entity_length == 2
        assert cfg.max_confidence == 1.0
        assert cfg.enable_parallel_inference is False
        assert cfg.max_workers == 4

    def test_domain_config_empty_collections(self):
        """Test that domain config has empty collections for vocabs, rules, etc."""
        cfg = ExtractionConfig.for_domain("technical")
        
        assert cfg.domain_vocab == {}
        assert cfg.custom_rules == []
        assert cfg.stopwords == []
        assert cfg.allowed_entity_types == []

    def test_domain_config_serialization_roundtrip(self):
        """Test that domain config serializes and deserializes correctly."""
        cfg_original = ExtractionConfig.for_domain("legal")
        
        # Roundtrip through dict
        cfg_dict = cfg_original.to_dict()
        cfg_restored = ExtractionConfig.from_dict(cfg_dict)
        
        assert cfg_restored.sentence_window == 2
        assert cfg_restored == cfg_original

    def test_domain_config_json_roundtrip(self):
        """Test that domain config survives JSON serialization."""
        cfg_original = ExtractionConfig.for_domain("financial")
        
        json_str = cfg_original.to_json()
        cfg_restored = ExtractionConfig.from_json(json_str)
        
        assert cfg_restored.sentence_window == 2
        assert cfg_restored.confidence_threshold == 0.5
        assert cfg_restored == cfg_original

    def test_domain_config_merge_with_overrides(self):
        """Test that domain config can be merged with overrides."""
        domain_cfg = ExtractionConfig.for_domain("legal")
        override_cfg = ExtractionConfig(confidence_threshold=0.8)
        
        merged = domain_cfg.merge(override_cfg)
        
        assert merged.sentence_window == 2  # From domain
        assert merged.confidence_threshold == 0.8  # From override

    def test_domain_config_is_different_from_defaults(self):
        """Test that domain-specific configs differ from plain defaults where appropriate."""
        domain_cfg = ExtractionConfig.for_domain("legal")
        default_cfg = ExtractionConfig()
        
        # Legal should have sentence_window=2, default has 0
        assert domain_cfg.sentence_window == 2
        assert default_cfg.sentence_window == 0
        assert domain_cfg.sentence_window != default_cfg.sentence_window

    def test_domain_config_all_domains_are_extractable(self):
        """Test that all known domains can be created without error."""
        domains = ["legal", "technical", "financial", "finance", "general", "default"]
        
        for domain in domains:
            cfg = ExtractionConfig.for_domain(domain)
            assert isinstance(cfg, ExtractionConfig)
            assert cfg.sentence_window >= 0

    def test_domain_config_legal_variant_consistency(self):
        """Test that different case/whitespace variants of 'legal' produce identical configs."""
        variants = ["legal", "LEGAL", "Legal", "  legal  ", "LE GAL".replace(" ", "")]
        
        window_values = [ExtractionConfig.for_domain(v).sentence_window for v in variants]
        
        assert all(w == 2 for w in window_values), "All legal variants should have window=2"

    def test_domain_config_validates_on_creation(self):
        """Test that domain config passes validation."""
        cfg = ExtractionConfig.for_domain("technical")
        
        # Should not raise any errors
        cfg.validate()

    def test_domain_config_with_enable_parallel(self):
        """Test that domain config can be manually enabled for parallelization."""
        import dataclasses as _dc
        
        cfg = ExtractionConfig.for_domain("legal")
        assert cfg.enable_parallel_inference is False
        
        # User can enable it if desired
        cfg_parallel = _dc.replace(cfg, enable_parallel_inference=True)
        assert cfg_parallel.enable_parallel_inference is True
        assert cfg_parallel.sentence_window == 2  # Still has domain optimization

    def test_domain_config_performance_note_coverage(self):
        """Verify that domains with documented performance improvements are in the map."""
        # From SENTENCE_WINDOW_BENCHMARK_REPORT.md:
        # - Legal domain: 7-35% improvement with sentence_window=2
        # - Technical domain: 34% improvement with sentence_window=2
        # - Financial domain: 25% improvement with sentence_window=2
        
        domains_with_improvement = ["legal", "technical", "financial"]
        
        for domain in domains_with_improvement:
            cfg = ExtractionConfig.for_domain(domain)
            assert cfg.sentence_window == 2, f"{domain} should have window=2 per benchmarks"


class TestDomainConfigIntegration:
    """Integration tests for domain-aware configs with existing patterns."""

    def test_domain_config_with_scale_thresholds(self):
        """Test that domain configs work with scale_thresholds method."""
        cfg = ExtractionConfig.for_domain("legal")
        relaxed = cfg.scale_thresholds(0.9)
        
        assert relaxed.sentence_window == 2  # Unchanged
        assert relaxed.confidence_threshold < cfg.confidence_threshold

    def test_domain_config_with_copy(self):
        """Test that domain configs can be copied."""
        cfg1 = ExtractionConfig.for_domain("technical")
        cfg2 = cfg1.copy()
        
        assert cfg1 == cfg2
        assert cfg1 is not cfg2

    def test_domain_config_diff_from_defaults(self):
        """Test diff() method highlights domain-specific differences."""
        domain_cfg = ExtractionConfig.for_domain("legal")
        default_cfg = ExtractionConfig()
        
        diff = domain_cfg.diff(default_cfg)
        
        assert "sentence_window" in diff
        assert diff["sentence_window"]["self"] == 2
        assert diff["sentence_window"]["other"] == 0

    def test_domain_config_summary(self):
        """Test that domain config generates a meaningful summary."""
        cfg = ExtractionConfig.for_domain("financial")
        summary = cfg.summary()
        
        assert "ExtractionConfig" in summary
        assert isinstance(summary, str)

    def test_domain_config_is_not_strict(self):
        """Test that domain configs use default (non-strict) confidence threshold."""
        cfg = ExtractionConfig.for_domain("legal")
        
        assert cfg.is_strict() is False
        assert cfg.confidence_threshold == 0.5

    def test_domain_config_describe(self):
        """Test that domain config produces a detailed description."""
        cfg = ExtractionConfig.for_domain("technical")
        desc = cfg.describe()
        
        assert isinstance(desc, str)
        assert "threshold=" in desc
        assert "sentence_window" in desc or "sentence" not in desc or "window" in desc


class TestDomainConfigEdgeCases:
    """Test edge cases and error scenarios for domain-aware configs."""

    def test_domain_config_empty_string_domain(self):
        """Test handling of empty string domain."""
        cfg = ExtractionConfig.for_domain("")
        assert cfg.sentence_window == 0  # Falls back to default

    def test_domain_config_numeric_string(self):
        """Test handling of numeric string as domain."""
        cfg = ExtractionConfig.for_domain("12345")
        assert cfg.sentence_window == 0

    def test_domain_config_special_characters(self):
        """Test handling of special characters in domain."""
        cfg = ExtractionConfig.for_domain("legal!@#$%")
        assert cfg.sentence_window == 0  # Doesn't match "legal"

    def test_domain_config_very_long_domain_string(self):
        """Test handling of very long domain string."""
        long_domain = "a" * 10000
        cfg = ExtractionConfig.for_domain(long_domain)
        assert cfg.sentence_window == 0  # Doesn't match any known domain

    def test_domain_config_unicode_domain(self):
        """Test handling of unicode characters in domain."""
        cfg = ExtractionConfig.for_domain("法律")  # "legal" in Chinese
        assert cfg.sentence_window == 0  # Doesn't match English "legal"

    def test_domain_config_multiple_spaces(self):
        """Test handling of multiple spaces in domain name."""
        cfg = ExtractionConfig.for_domain("   legal   ")
        assert cfg.sentence_window == 2  # Should strip and match


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
