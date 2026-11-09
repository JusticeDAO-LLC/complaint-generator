"""
Legal Pattern Extraction for Complaints

Extensible framework for extracting complaint-relevant legal provisions from text.
Uses a registry pattern to allow adding new complaint types and legal term patterns.

This module includes default patterns for:
- Fair housing law
- Employment discrimination
- Civil rights violations
- Protected class references
- Legal remedies and relief

New complaint types can be added by registering additional patterns.
"""

import re
from typing import List, Dict, Optional, Any, Union
from datetime import datetime
from .base import BaseLegalPatternExtractor

# Constants for complaint categorization
# Minimum keyword matches required to categorize a complaint as a specific type
DEFAULT_KEYWORD_MATCH_THRESHOLD = 2
# Minimum number of keywords a type must have before applying the threshold
# (types with fewer keywords use threshold of 1 to avoid being too strict)
MIN_KEYWORDS_FOR_THRESHOLD = 10


# Registry for legal term patterns by category
LEGAL_TERMS_REGISTRY: Dict[str, List[str]] = {}

# Temporal rule profile patterns are kept separate from LEGAL_TERMS_REGISTRY so
# legacy "all legal terms" extraction does not change its provision counts.
TEMPORAL_LEGAL_PATTERNS: Dict[str, Dict[str, List[str]]] = {
    'retaliation': {
        'protected_activity': [
            r"\b(protected activity)\b",
            r"\b(reported discrimination|complained to HR|filed a complaint)\b",
            r"\b(whistleblow(?:ing|er)?|opposed unlawful conduct)\b",
        ],
        'adverse_action': [
            r"\b(adverse action|adverse employment action)\b",
            r"\b(terminated|fired|demoted|suspended|reduced hours)\b",
            r"\b(denied promotion|disciplinary action)\b",
        ],
        'causal_connection': [
            r"\b(causal connection|causal link|causation)\b",
            r"\b(temporal proximity|soon after|shortly after)\b",
            r"\b(because of|in response to|retaliated after)\b",
        ],
        'limitations_or_exhaustion': [
            r"\b(EEOC charge|administrative charge|exhaustion)\b",
            r"\b(180 days|300 days|filing deadline|limitations period)\b",
        ],
    },
}

TEMPORAL_LEGAL_PATTERN_ALIASES: Dict[str, str] = {
    'employment_retaliation': 'retaliation',
    'employment_discrimination_retaliation': 'retaliation',
}


def get_temporal_legal_patterns(
    claim_type: Optional[str] = None,
    event_role: Optional[str] = None,
) -> Union[Dict[str, Dict[str, List[str]]], List[str]]:
    """
    Return legal-pattern hints tied to explicit temporal rule profiles.

    This is a data-layer companion to ``temporal_rule_profiles``.  It does not
    register patterns into the legacy extractor by default, so chronology proof
    discovery can evolve without changing broad complaint categorization.
    """
    if claim_type is None:
        return {
            profile_claim_type: {
                role: list(patterns)
                for role, patterns in role_patterns.items()
            }
            for profile_claim_type, role_patterns in TEMPORAL_LEGAL_PATTERNS.items()
        }

    normalized_claim_type = TEMPORAL_LEGAL_PATTERN_ALIASES.get(
        _normalize_pattern_key(claim_type),
        _normalize_pattern_key(claim_type),
    )
    role_patterns = TEMPORAL_LEGAL_PATTERNS.get(normalized_claim_type, {})
    if event_role is None:
        return {
            normalized_claim_type: {
                role: list(patterns)
                for role, patterns in role_patterns.items()
            }
        } if role_patterns else {}

    normalized_role = _normalize_pattern_key(event_role)
    return list(role_patterns.get(normalized_role, []))


def _normalize_pattern_key(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", " ").split())


def register_legal_terms(category: str, patterns: List[str]) -> None:
    """
    Register legal term patterns for a category.
    
    Args:
        category: Category name (e.g., 'housing', 'employment', 'civil_rights')
        patterns: List of regex patterns
    """
    if category not in LEGAL_TERMS_REGISTRY:
        LEGAL_TERMS_REGISTRY[category] = []
    LEGAL_TERMS_REGISTRY[category].extend(patterns)


def get_legal_terms(category: Optional[str] = None) -> List[str]:
    """
    Get legal term patterns for a category.
    
    Args:
        category: Category name, or None for all patterns
        
    Returns:
        List of regex patterns
    """
    if category:
        return LEGAL_TERMS_REGISTRY.get(category, [])
    else:
        # Return all patterns from all categories
        all_patterns = []
        for patterns in LEGAL_TERMS_REGISTRY.values():
            all_patterns.extend(patterns)
        return all_patterns


# Default legal term patterns (maintained for backward compatibility)
COMPLAINT_LEGAL_TERMS = [
    # Fair Housing & Discrimination
    r"\b(fair housing)\b",
    r"\b(Fair Housing Act)\b",
    r"\b(FHA)\b",
    r"\b(discrimination)\b",
    r"\b(discriminate|discriminatory)\b",
    r"\b(harassment)\b",
    r"\b(retaliation|retaliate)\b",
    r"\b(hostile environment)\b",
    
    # Reasonable Accommodation
    r"\b(reasonable accommodation)\b",
    r"\b(reasonable modification)\b",
    r"\b(disability accommodation)\b",
    r"\b(auxiliary aids?)\b",
    
    # Protected Classes
    r"\b(protected class(es)?)\b",
    r"\b(familial status)\b",
    r"\b(disability|disabled)\b",
    r"\b(race|racial)\b",
    r"\b(color)\b",
    r"\b(national origin)\b",
    r"\b(religion|religious)\b",
    r"\b(sex|gender)\b",
    r"\b(sexual orientation)\b",
    r"\b(gender identity)\b",
    r"\b(source of income)\b",
    r"\b(marital status)\b",
    
    # Legal Impact
    r"\b(disparate (impact|treatment))\b",
    r"\b(intentional discrimination)\b",
    r"\b(unintentional discrimination)\b",
    r"\b(discriminatory effect)\b",
    r"\b(adverse (impact|effect))\b",
    
    # Housing Specific
    r"\b(Section 8)\b",
    r"\b(Housing Choice Voucher)\b",
    r"\b(public housing)\b",
    r"\b(affordable housing)\b",
    r"\b(tenant|tenancy)\b",
    r"\b(landlord)\b",
    r"\b(lease|rental agreement)\b",
    r"\b(eviction)\b",
    r"\b(housing authority)\b",
    
    # Employment Specific
    r"\b(Title VII)\b",
    r"\b(ADA)\b",
    r"\b(Americans with Disabilities Act)\b",
    r"\b(ADEA)\b",
    r"\b(Age Discrimination in Employment Act)\b",
    r"\b(FMLA)\b",
    r"\b(Family and Medical Leave Act)\b",
    r"\b(EEOC)\b",
    r"\b(Equal Employment Opportunity)\b",
    
    # Federal Law Citations
    r"\b(42 U\.S\.C\.)\b",
    r"\b(29 U\.S\.C\.)\b",
    r"\b(C\.F\.R\.)\b",
    r"\b(Federal Register)\b",
    
    # Remedies & Relief
    r"\b(damages)\b",
    r"\b(compensatory damages)\b",
    r"\b(punitive damages)\b",
    r"\b(injunctive relief)\b",
    r"\b(declaratory relief)\b",
    r"\b(attorney('s)? fees)\b",
    r"\b(equitable relief)\b",
    r"\b(monetary relief)\b",
    
    # Civil Rights
    r"\b(civil rights)\b",
    r"\b(equal protection)\b",
    r"\b(due process)\b",
    r"\b(constitutional (right|violation))\b",
    
    # Complaint-Specific Terms
    r"\b(complainant)\b",
    r"\b(respondent)\b",
    r"\b(charging party)\b",
    r"\b(aggrieved person)\b",
    r"\b(prima facie case)\b",
    r"\b(burden of proof)\b",
    r"\b(preponderance of evidence)\b",
]

# Register default patterns in categories
register_legal_terms('housing', [
    r"\b(fair housing)\b",
    r"\b(Fair Housing Act)\b",
    r"\b(FHA)\b",
    r"\b(Section 8)\b",
    r"\b(Housing Choice Voucher)\b",
    r"\b(public housing)\b",
    r"\b(affordable housing)\b",
    r"\b(tenant|tenancy)\b",
    r"\b(landlord)\b",
    r"\b(lease|rental agreement)\b",
    r"\b(eviction)\b",
    r"\b(housing authority)\b",
])

register_legal_terms('employment', [
    r"\b(Title VII)\b",
    r"\b(ADA)\b",
    r"\b(Americans with Disabilities Act)\b",
    r"\b(ADEA)\b",
    r"\b(Age Discrimination in Employment Act)\b",
    r"\b(FMLA)\b",
    r"\b(Family and Medical Leave Act)\b",
    r"\b(EEOC)\b",
    r"\b(Equal Employment Opportunity)\b",
])

register_legal_terms('discrimination', [
    r"\b(discrimination)\b",
    r"\b(discriminate|discriminatory)\b",
    r"\b(harassment)\b",
    r"\b(retaliation|retaliate)\b",
    r"\b(hostile environment)\b",
    r"\b(disparate (impact|treatment))\b",
    r"\b(intentional discrimination)\b",
    r"\b(unintentional discrimination)\b",
    r"\b(discriminatory effect)\b",
    r"\b(adverse (impact|effect))\b",
])

register_legal_terms('protected_classes', [
    r"\b(protected class(es)?)\b",
    r"\b(familial status)\b",
    r"\b(disability|disabled)\b",
    r"\b(race|racial)\b",
    r"\b(color)\b",
    r"\b(national origin)\b",
    r"\b(religion|religious)\b",
    r"\b(sex|gender)\b",
    r"\b(sexual orientation)\b",
    r"\b(gender identity)\b",
    r"\b(source of income)\b",
    r"\b(marital status)\b",
])

register_legal_terms('accommodations', [
    r"\b(reasonable accommodation)\b",
    r"\b(reasonable modification)\b",
    r"\b(disability accommodation)\b",
    r"\b(auxiliary aids?)\b",
])

register_legal_terms('remedies', [
    r"\b(damages)\b",
    r"\b(compensatory damages)\b",
    r"\b(punitive damages)\b",
    r"\b(injunctive relief)\b",
    r"\b(declaratory relief)\b",
    r"\b(attorney('s)? fees)\b",
    r"\b(equitable relief)\b",
    r"\b(monetary relief)\b",
])

register_legal_terms('civil_rights', [
    r"\b(civil rights)\b",
    r"\b(equal protection)\b",
    r"\b(due process)\b",
    r"\b(constitutional (right|violation))\b",
])

register_legal_terms('federal_law', [
    r"\b(42 U\.S\.C\.)\b",
    r"\b(29 U\.S\.C\.)\b",
    r"\b(C\.F\.R\.)\b",
    r"\b(Federal Register)\b",
])


class LegalPatternExtractor(BaseLegalPatternExtractor):
    """
    Extensible legal pattern extractor for complaints.
    
    This class extracts legal provisions using regex patterns organized by category.
    New complaint types can be added by registering additional patterns using
    register_legal_terms().
    
    Example:
        >>> # Use default patterns
        >>> extractor = LegalPatternExtractor()
        >>> result = extractor.extract_provisions(document_text)
        
        >>> # Add custom patterns for consumer protection
        >>> register_legal_terms('consumer', [r'\b(consumer protection)\b'])
        >>> extractor = LegalPatternExtractor(categories=['consumer', 'civil_rights'])
    """
    
    def __init__(self, categories: Optional[List[str]] = None, 
                 custom_patterns: Optional[List[str]] = None):
        """
        Initialize the legal pattern extractor.
        
        Args:
            categories: List of pattern categories to use (None = all registered)
            custom_patterns: Optional additional regex patterns to include
        """
        # Get patterns from specified categories or all if None
        if categories:
            patterns = []
            for category in categories:
                patterns.extend(get_legal_terms(category))
        else:
            patterns = get_legal_terms()  # All patterns
        
        # Add backwards compatibility with COMPLAINT_LEGAL_TERMS
        if not patterns:
            patterns = COMPLAINT_LEGAL_TERMS
        
        self.patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        
        if custom_patterns:
            self.patterns.extend([re.compile(p, re.IGNORECASE) for p in custom_patterns])

        # Batch 215: Analysis tracking
        self._analysis_history: List[Dict[str, Any]] = []
        self._protected_class_frequency: Dict[str, int] = {}
        self._complaint_type_frequency: Dict[str, int] = {}
    
    def extract_provisions(self, text: str, context_chars: int = 200) -> Dict[str, Any]:
        """
        Extract legal provisions with context from text.
        
        Args:
            text: Text to analyze
            context_chars: Number of characters to include before/after match
            
        Returns:
            Dictionary containing:
            - provisions: List of found provisions with context
            - terms_found: Set of unique legal terms found
            - citation_count: Number of legal citations found
            - timestamp: When analysis was performed
        """
        provisions = []
        terms_found = set()
        
        for pattern in self.patterns:
            for match in pattern.finditer(text):
                # Extract context around the match
                start = max(0, match.start() - context_chars)
                end = min(len(text), match.end() + context_chars)
                context = text[start:end]
                
                # Clean up context (remove extra whitespace)
                context = ' '.join(context.split())
                
                term = match.group(0)
                terms_found.add(term.lower())
                
                provisions.append({
                    'term': term,
                    'context': context,
                    'position': match.start(),
                    'pattern': pattern.pattern
                })
        
        # Sort by position in document
        provisions.sort(key=lambda x: x['position'])
        
        return {
            'provisions': provisions,
            'terms_found': list(terms_found),
            'provision_count': len(provisions),
            'unique_terms': len(terms_found),
            'timestamp': datetime.now().isoformat()
        }
    
    def extract_citations(self, text: str) -> List[Dict[str, str]]:
        """
        Extract legal citations (e.g., 42 U.S.C. § 3604).
        
        Args:
            text: Text to analyze
            
        Returns:
            List of found citations with metadata
        """
        citation_patterns = [
            # Federal statutes (e.g., 42 U.S.C. § 3604)
            (r'\b\d+\s+U\.S\.C\.\s+§\s*\d+[a-z]?(?:\(\w+\))?', 'federal_statute'),
            # Code of Federal Regulations (e.g., 24 C.F.R. § 100.70)
            (r'\b\d+\s+C\.F\.R\.\s+§\s*\d+\.\d+', 'cfr'),
            # State statutes (e.g., Cal. Civ. Code § 51)
            (r'\b[A-Z][a-z]+\.\s+[A-Z][a-z]+\.\s+Code\s+§\s*\d+', 'state_statute'),
            # Case citations (simplified)
            (r'\b\d+\s+F\.\s*(?:2d|3d|Supp\.)?\s+\d+', 'federal_case'),
        ]
        
        citations = []
        for pattern, citation_type in citation_patterns:
            regex = re.compile(pattern, re.IGNORECASE)
            for match in regex.finditer(text):
                citations.append({
                    'citation': match.group(0),
                    'type': citation_type,
                    'position': match.start()
                })
        
        return citations
    
    def categorize_complaint_type(self, text: str) -> List[str]:
        """
        Categorize the complaint based on legal terms found.
        
        Uses keyword matching with configurable thresholds to identify applicable
        complaint categories. Requires multiple keyword matches to avoid false positives.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of applicable complaint categories
        """
        # Import here to avoid circular dependency issues during module initialization
        from .keywords import get_type_specific_keywords, _global_registry
        
        text_lower = text.lower()
        categories = []
        
        # Check each registered complaint type
        complaint_types = _global_registry.get_complaint_types()
        
        for complaint_type in complaint_types:
            # Get type-specific keywords (excluding global keywords)
            type_keywords = get_type_specific_keywords('complaint', complaint_type)
            
            # Check if any type-specific keywords appear in text
            # Use a threshold to avoid false positives
            matches = sum(1 for kw in type_keywords if kw.lower() in text_lower)
            
            # If at least threshold keywords match, include this type
            # Use lower threshold for types with fewer keywords to avoid being too strict
            threshold = (DEFAULT_KEYWORD_MATCH_THRESHOLD 
                        if len(type_keywords) > MIN_KEYWORDS_FOR_THRESHOLD 
                        else 1)
            if matches >= threshold:
                categories.append(complaint_type)
        
        # Legacy categorization for backward compatibility
        # Disability
        if ('disability' in text_lower or 'ada' in text_lower or
                'reasonable accommodation' in text_lower):
            if 'disability' not in categories:
                categories.append('disability')
        
        # Discrimination type
        if 'discrimination' in text_lower or 'discriminate' in text_lower:
            if 'discrimination' not in categories:
                categories.append('discrimination')
        
        # Harassment
        if 'harassment' in text_lower or 'hostile environment' in text_lower:
            if 'harassment' not in categories:
                categories.append('harassment')
        
        # Retaliation
        if 'retaliation' in text_lower or 'retaliate' in text_lower:
            if 'retaliation' not in categories:
                categories.append('retaliation')
        
        return categories or ['general']
    
    def find_protected_classes(self, text: str) -> List[str]:
        """
        Identify protected classes mentioned in the text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of protected classes found
        """
        protected_classes = {
            'race': ['race', 'racial'],
            'color': ['color'],
            'national_origin': ['national origin', 'nationality'],
            'religion': ['religion', 'religious', 'creed'],
            'sex': ['sex', 'gender'],
            'familial_status': ['familial status', 'family status', 'children'],
            'disability': ['disability', 'disabled', 'handicap'],
            'age': ['age', 'elderly', 'senior'],
            'sexual_orientation': ['sexual orientation', 'lgbt', 'gay', 'lesbian'],
            'gender_identity': ['gender identity', 'transgender'],
            'source_of_income': ['source of income', 'section 8', 'voucher'],
        }
        
        text_lower = text.lower()
        found_classes = []
        
        for class_name, keywords in protected_classes.items():
            if any(keyword in text_lower for keyword in keywords):
                found_classes.append(class_name)
        
        return found_classes

    def analyze_text(self, text: str, context_chars: int = 200) -> Dict[str, Any]:
        """
        Run full analysis and track the results.

        Args:
            text: Text to analyze
            context_chars: Number of characters to include before/after match

        Returns:
            Dictionary with provisions, citations, categories, and protected classes
        """
        provisions = self.extract_provisions(text, context_chars=context_chars)
        citations = self.extract_citations(text)
        categories = self.categorize_complaint_type(text)
        protected_classes = self.find_protected_classes(text)

        self._record_analysis(
            provisions=provisions,
            citations=citations,
            categories=categories,
            protected_classes=protected_classes,
        )

        return {
            'provisions': provisions,
            'citations': citations,
            'categories': categories,
            'protected_classes': protected_classes,
        }

    def _record_analysis(
        self,
        provisions: Dict[str, Any],
        citations: List[Dict[str, str]],
        categories: List[str],
        protected_classes: List[str],
    ) -> None:
        """Record analysis results for aggregate metrics."""
        entry = {
            'provision_count': provisions.get('provision_count', 0),
            'unique_terms': provisions.get('unique_terms', 0),
            'citation_count': len(citations),
            'protected_classes': list(protected_classes),
            'complaint_types': list(categories),
        }
        self._analysis_history.append(entry)

        for protected_class in protected_classes:
            self._protected_class_frequency[protected_class] = (
                self._protected_class_frequency.get(protected_class, 0) + 1
            )

        for complaint_type in categories:
            self._complaint_type_frequency[complaint_type] = (
                self._complaint_type_frequency.get(complaint_type, 0) + 1
            )
    
    # ============================================================================
    # Batch 215: LegalPatternExtractor Analysis Methods
    # ============================================================================
    
    def total_analyses_performed(self) -> int:
        """Return total number of analyses performed.
        
        Returns:
            Count of analyses in history.
        """
        return len(self._analysis_history)
    
    def average_provisions_per_analysis(self) -> float:
        """Calculate average number of provisions found per analysis.
        
        Returns:
            Mean provision count, or 0.0 if no analyses.
        """
        if not self._analysis_history:
            return 0.0
        total = sum(a.get('provision_count', 0) for a in self._analysis_history)
        return total / len(self._analysis_history)
    
    def average_unique_terms_per_analysis(self) -> float:
        """Calculate average number of unique terms found per analysis.
        
        Returns:
            Mean unique term count, or 0.0 if no analyses.
        """
        if not self._analysis_history:
            return 0.0
        total = sum(a.get('unique_terms', 0) for a in self._analysis_history)
        return total / len(self._analysis_history)
    
    def protected_class_frequency_distribution(self) -> Dict[str, int]:
        """Get frequency distribution of protected classes found across analyses.
        
        Returns:
            Dict mapping protected class names to occurrence counts.
        """
        return dict(self._protected_class_frequency)
    
    def complaint_type_frequency_distribution(self) -> Dict[str, int]:
        """Get frequency distribution of complaint types identified.
        
        Returns:
            Dict mapping complaint types to occurrence counts.
        """
        return dict(self._complaint_type_frequency)
    
    def most_common_protected_class(self) -> str:
        """Find the most frequently identified protected class.
        
        Returns:
            Protected class name with highest frequency, or 'none' if none found.
        """
        if not self._protected_class_frequency:
            return 'none'
        return max(self._protected_class_frequency, key=self._protected_class_frequency.get)
    
    def most_common_complaint_type(self) -> str:
        """Find the most frequently identified complaint type.
        
        Returns:
            Complaint type with highest frequency, or 'none' if none identified.
        """
        if not self._complaint_type_frequency:
            return 'none'
        return max(self._complaint_type_frequency, key=self._complaint_type_frequency.get)
    
    def total_citations_found(self) -> int:
        """Return total number of citations found across all analyses.
        
        Returns:
            Count of all citations identified.
        """
        return sum(a.get('citation_count', 0) for a in self._analysis_history)
    
    def average_citations_per_analysis(self) -> float:
        """Calculate average number of citations per analysis.
        
        Returns:
            Mean citation count, or 0.0 if no analyses.
        """
        if not self._analysis_history:
            return 0.0
        return self.total_citations_found() / len(self._analysis_history)
    
    def maximum_provisions_found(self) -> int:
        """Find the highest number of provisions found in any single analysis.
        
        Returns:
            Maximum provision count, or 0 if no analyses.
        """
        if not self._analysis_history:
            return 0
        return max(a.get('provision_count', 0) for a in self._analysis_history)
    
    def minimum_provisions_found(self) -> int:
        """Find the lowest number of provisions found in any analysis.
        
        Returns:
            Minimum provision count, or 0 if no analyses.
        """
        if not self._analysis_history:
            return 0
        return min(a.get('provision_count', 0) for a in self._analysis_history)
    
    def analyses_with_protected_classes(self) -> int:
        """Count how many analyses identified at least one protected class.
        
        Returns:
            Number of analyses with protected class findings.
        """
        return sum(1 for a in self._analysis_history if a.get('protected_classes', []))
    
    def unique_protected_classes_found(self) -> int:
        """Count total number of unique protected classes identified.
        
        Returns:
            Number of distinct protected classes found.
        """
        return len(self._protected_class_frequency)
    
    def unique_complaint_types_identified(self) -> int:
        """Count total number of unique complaint types identified.
        
        Returns:
            Number of distinct complaint types found.
        """
        return len(self._complaint_type_frequency)
    
    def clear_analysis_history(self) -> None:
        """Clear all analysis history and frequency data."""
        self._analysis_history.clear()
        self._protected_class_frequency.clear()
        self._complaint_type_frequency.clear()

    # ============================================================================
    # Batch 225: LegalPatternExtractor Analysis Methods
    # ============================================================================

    def total_provisions_found(self) -> int:
        """Return total number of provisions found across analyses.

        Returns:
            Sum of provision counts.
        """
        return sum(a.get('provision_count', 0) for a in self._analysis_history)

    def total_unique_terms_counted(self) -> int:
        """Return total number of unique terms counted across analyses.

        Returns:
            Sum of per-analysis unique term counts.
        """
        return sum(a.get('unique_terms', 0) for a in self._analysis_history)

    def average_protected_classes_per_analysis(self) -> float:
        """Calculate average protected classes identified per analysis.

        Returns:
            Mean protected class count, or 0.0 if no analyses.
        """
        if not self._analysis_history:
            return 0.0
        total = sum(len(a.get('protected_classes', [])) for a in self._analysis_history)
        return total / len(self._analysis_history)

    def average_complaint_types_per_analysis(self) -> float:
        """Calculate average complaint types identified per analysis.

        Returns:
            Mean complaint type count, or 0.0 if no analyses.
        """
        if not self._analysis_history:
            return 0.0
        total = sum(len(a.get('complaint_types', [])) for a in self._analysis_history)
        return total / len(self._analysis_history)

    def analyses_with_citations(self) -> int:
        """Count analyses that include at least one citation.

        Returns:
            Number of analyses with citations.
        """
        return sum(1 for a in self._analysis_history if a.get('citation_count', 0) > 0)

    def citation_rate(self) -> float:
        """Calculate fraction of analyses that include citations.

        Returns:
            Ratio of analyses with citations, or 0.0 if no analyses.
        """
        if not self._analysis_history:
            return 0.0
        return self.analyses_with_citations() / len(self._analysis_history)

    def max_unique_terms_found(self) -> int:
        """Find maximum unique term count in any analysis.

        Returns:
            Maximum unique term count, or 0 if no analyses.
        """
        if not self._analysis_history:
            return 0
        return max(a.get('unique_terms', 0) for a in self._analysis_history)

    def min_unique_terms_found(self) -> int:
        """Find minimum unique term count in any analysis.

        Returns:
            Minimum unique term count, or 0 if no analyses.
        """
        if not self._analysis_history:
            return 0
        return min(a.get('unique_terms', 0) for a in self._analysis_history)

    def max_citations_found(self) -> int:
        """Find maximum citation count in any analysis.

        Returns:
            Maximum citation count, or 0 if no analyses.
        """
        if not self._analysis_history:
            return 0
        return max(a.get('citation_count', 0) for a in self._analysis_history)

    def min_citations_found(self) -> int:
        """Find minimum citation count in any analysis.

        Returns:
            Minimum citation count, or 0 if no analyses.
        """
        if not self._analysis_history:
            return 0
        return min(a.get('citation_count', 0) for a in self._analysis_history)
