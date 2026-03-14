"""
Unified Complaint Analyzer

Provides a high-level interface for analyzing complaints with all components.
"""

from collections import Counter
from typing import Dict, Optional, Any, List
from .legal_patterns import LegalPatternExtractor
from .risk_scoring import ComplaintRiskScorer
from .keywords import get_keywords


class ComplaintAnalyzer:
    """
    Unified analyzer combining all complaint analysis components.
    
    Example:
        >>> analyzer = ComplaintAnalyzer(complaint_type='housing')
        >>> result = analyzer.analyze(document_text)
        >>> print(f"Risk: {result['risk_level']}")
    """
    
    def __init__(self, complaint_type: Optional[str] = None):
        """
        Initialize the analyzer.
        
        Args:
            complaint_type: Optional complaint type for specialized analysis
        """
        self.complaint_type = complaint_type
        self.legal_extractor = LegalPatternExtractor()
        self.risk_scorer = ComplaintRiskScorer()
        
        # Batch 212: Analysis tracking
        self._analysis_history = []  # Store results of all analyses
        self._keyword_frequency = {}  # Track keyword occurrences
    
    def analyze(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Perform complete analysis on complaint text.
        
        Args:
            text: Complaint text to analyze
            metadata: Optional metadata
            
        Returns:
            Complete analysis results
        """
        # Extract legal provisions
        provisions = self.legal_extractor.extract_provisions(text)
        citations = self.legal_extractor.extract_citations(text)
        categories = self.legal_extractor.categorize_complaint_type(text)
        
        # Calculate risk
        risk = self.risk_scorer.calculate_risk(text, provisions['provisions'])
        
        # Extract keywords using global registry
        complaint_keywords = get_keywords('complaint', self.complaint_type)
        found_keywords = [kw for kw in complaint_keywords if kw.lower() in text.lower()]
        
        result = {
            'legal_provisions': provisions,
            'citations': citations,
            'categories': categories,
            'risk_score': risk['score'],
            'risk_level': risk['level'],
            'risk_factors': risk['factors'],
            'recommendations': risk['recommendations'],
            'keywords_found': found_keywords[:20],  # Top 20
            'metadata': metadata or {}
        }
        
        # Batch 212: Track this analysis
        self._analysis_history.append(result)
        for kw in found_keywords:
            self._keyword_frequency[kw] = self._keyword_frequency.get(kw, 0) + 1
        
        return result

    # ============================================================================
    # Batch 212: ComplaintAnalyzer Analysis Methods
    # ============================================================================
    
    def total_analyses(self) -> int:
        """Return the total number of analyses performed.
        
        Returns:
            Count of analyses in history.
        """
        return len(self._analysis_history)

    def get_analysis_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return recorded analyses, optionally trimmed to the most recent entries."""
        history = list(self._analysis_history)
        if limit is None:
            return history
        try:
            count = max(0, int(limit))
        except Exception:
            count = 0
        if count <= 0:
            return []
        return history[-count:]

    def get_keyword_frequency(self) -> Dict[str, int]:
        """Return a copy of aggregate keyword counts across analyses."""
        return dict(self._keyword_frequency)

    def get_top_keywords(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Return the most common tracked keywords ordered by frequency."""
        try:
            count = max(0, int(top_n))
        except Exception:
            count = 0
        if count <= 0:
            return []
        counter = Counter(self._keyword_frequency)
        return [
            {"keyword": keyword, "count": frequency}
            for keyword, frequency in counter.most_common(count)
        ]

    def reset_history(self) -> None:
        """Clear stored analysis history and aggregate keyword counts."""
        self._analysis_history.clear()
        self._keyword_frequency.clear()
    
    def analyses_by_risk_level(self, level: str) -> int:
        """Count analyses with a specific risk level.
        
        Args:
            level: Risk level to count ('low', 'medium', 'high').
            
        Returns:
            Number of analyses with this risk level.
        """
        return sum(1 for a in self._analysis_history if a.get('risk_level') == level)
    
    def risk_level_distribution(self) -> Dict[str, int]:
        """Calculate frequency distribution of risk levels.
        
        Returns:
            Dict mapping risk levels to counts.
        """
        dist = {}
        for analysis in self._analysis_history:
            level = analysis.get('risk_level')
            if level:
                dist[level] = dist.get(level, 0) + 1
        return dist
    
    def average_risk_score(self) -> float:
        """Calculate the average risk score across all analyses.
        
        Returns:
            Mean risk score, or 0.0 if no analyses.
        """
        if not self._analysis_history:
            return 0.0
        total_score = sum(a.get('risk_score', 0) for a in self._analysis_history)
        return total_score / len(self._analysis_history)
    
    def highest_risk_score(self) -> int:
        """Find the highest risk score across all analyses.
        
        Returns:
            Maximum risk score, or 0 if no analyses.
        """
        if not self._analysis_history:
            return 0
        return max(a.get('risk_score', 0) for a in self._analysis_history)
    
    def most_common_keyword(self) -> str:
        """Find the keyword that appeared most frequently across analyses.
        
        Returns:
            Most common keyword, or 'none' if no keywords found.
        """
        if not self._keyword_frequency:
            return 'none'
        return max(self._keyword_frequency, key=self._keyword_frequency.get)
    
    def keyword_frequency(self, keyword: str) -> int:
        """Get the frequency count for a specific keyword.
        
        Args:
            keyword: The keyword to look up.
            
        Returns:
            Number of times this keyword appeared, or 0 if not found.
        """
        return self._keyword_frequency.get(keyword, 0)
    
    def total_unique_keywords(self) -> int:
        """Return the count of unique keywords found across all analyses.
        
        Returns:
            Number of distinct keywords.
        """
        return len(self._keyword_frequency)
    
    def high_risk_percentage(self) -> float:
        """Calculate the percentage of analyses classified as high risk.
        
        Returns:
            Percentage (0.0 to 100.0), or 0.0 if no analyses.
        """
        if not self._analysis_history:
            return 0.0
        high_risk_count = self.analyses_by_risk_level('high')
        return (high_risk_count / len(self._analysis_history)) * 100.0
    
    def categories_coverage(self) -> int:
        """Count how many distinct complaint categories have been analyzed.
        
        Returns:
            Number of unique categories found across analyses.
        """
        categories_set = set()
        for analysis in self._analysis_history:
            cats = analysis.get('categories', [])
            if isinstance(cats, list):
                categories_set.update(cats)
        return len(categories_set)
