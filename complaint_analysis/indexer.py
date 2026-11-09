"""
Hybrid Document Indexer

Combines ipfs_datasets_py's vector embeddings with HACC's keyword-based tagging
for optimal document indexing and search.

This provides the best of both approaches:
- Semantic search via vector embeddings (ipfs_datasets_py)
- Domain-specific keyword matching (HACC)
- Combined relevance scoring
"""

import inspect
import logging
import math
import re
from collections import Counter
from typing import Dict, List, Optional, Any
from datetime import datetime

from integrations.ipfs_datasets.vector_store import (
    EMBEDDINGS_AVAILABLE,
    EmbeddingsRouter,
)

logger = logging.getLogger(__name__)

from .keywords import get_keywords, get_type_specific_keywords
from .legal_patterns import LegalPatternExtractor
from .risk_scoring import ComplaintRiskScorer


class HybridDocumentIndexer:
    """
    Hybrid indexer combining vector embeddings with keyword tagging.
    
    This class provides:
    1. Vector embeddings for semantic search (ipfs_datasets_py)
    2. Keyword extraction and tagging (HACC)
    3. Legal provision extraction (HACC)
    4. Risk scoring (HACC)
    5. Combined relevance scoring
    
    Example:
        >>> indexer = HybridDocumentIndexer()
        >>> result = await indexer.index_document(text, metadata)
        >>> print(f"Risk: {result['risk_score']}, Keywords: {result['keywords']}")
    """
    
    def __init__(self, enable_embeddings: bool = True):
        """
        Initialize the hybrid indexer.
        
        Args:
            enable_embeddings: Whether to enable vector embeddings (requires ipfs_datasets_py)
        """
        self.enable_embeddings = enable_embeddings and EMBEDDINGS_AVAILABLE
        
        # Initialize ipfs_datasets_py components
        if self.enable_embeddings:
            try:
                self.embeddings_router = EmbeddingsRouter()
            except Exception as e:
                logger.warning(f"Failed to initialize embeddings: {e}")
                self.embeddings_router = None
                self.enable_embeddings = False
        else:
            self.embeddings_router = None
        
        # Initialize HACC components
        self.legal_extractor = LegalPatternExtractor()
        self.risk_scorer = ComplaintRiskScorer()
        
        # Batch 218: Track indexed documents
        self._indexed_documents: List[Dict[str, Any]] = []

        # Keep source text out of the public indexing result while retaining the
        # minimum state required for local keyword search.  Keys are object IDs
        # because callers may attach their own (non-unique) metadata identifiers.
        self._search_text_by_document_id: Dict[int, str] = {}
    
    async def index_document(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Index a document with both vector embeddings and keyword tagging.
        
        Args:
            text: Document text to index
            metadata: Optional metadata about the document
            
        Returns:
            Dictionary containing:
            - embedding: Vector embedding (if enabled)
            - keywords: Extracted keywords
            - legal_provisions: Found legal provisions
            - risk_score: Risk assessment
            - applicability: Domain tags
            - indexed_date: Timestamp
        """
        result = {
            'text_length': len(text),
            'metadata': metadata or {},
            'indexed_date': datetime.now().isoformat()
        }
        
        # Generate vector embedding (ipfs_datasets_py)
        if self.enable_embeddings and self.embeddings_router:
            try:
                embedding = self.embeddings_router.embed_text(text)
                if inspect.isawaitable(embedding):
                    embedding = await embedding
                result['embedding'] = embedding
                result['embedding_available'] = True
            except Exception as e:
                logger.warning(
                    "Document embedding failed; indexing without a vector: %s",
                    e,
                    exc_info=True,
                )
                result['embedding_available'] = False
        else:
            result['embedding_available'] = False
        
        # Extract keywords (using new function)
        complaint_keywords = self._extract_keywords(text, get_keywords('complaint'))
        evidence_keywords = self._extract_keywords(text, get_keywords('evidence'))
        legal_keywords = self._extract_keywords(text, get_keywords('legal'))
        binding_keywords = self._extract_keywords(text, get_keywords('binding'))
        
        result['keywords'] = {
            'complaint': complaint_keywords,
            'evidence': evidence_keywords,
            'legal': legal_keywords,
            'binding': binding_keywords
        }
        
        # Tag applicability (HACC)
        applicability = self._tag_applicability(text)
        result['applicability'] = applicability
        
        # Extract legal provisions (HACC)
        legal_result = self.legal_extractor.extract_provisions(text)
        result['legal_provisions'] = legal_result
        
        # Calculate risk score (HACC)
        risk_result = self.risk_scorer.calculate_risk(text, legal_result['provisions'])
        result['risk_score'] = risk_result['score']
        result['risk_level'] = risk_result['level']
        result['risk_factors'] = risk_result['factors']
        
        # Calculate combined relevance score
        result['relevance_score'] = self._calculate_relevance(result)
        
        # Batch 218: Track indexed document
        self._indexed_documents.append(result)
        self._search_text_by_document_id[id(result)] = text
        
        return result
    
    def _extract_keywords(self, text: str, keyword_list: List[str]) -> List[str]:
        """Extract keywords from text (case-insensitive)."""
        found = []
        text_lower = text.lower()
        for kw in keyword_list:
            if kw.lower() in text_lower:
                found.append(kw)
        return list(set(found))  # dedupe
    
    def _tag_applicability(self, text: str) -> List[str]:
        """
        Tag document with applicability areas.
        
        Uses type-specific keywords only to avoid false positives from
        global keywords that appear in all complaint types.
        """
        tags = []
        text_lower = text.lower()
        
        # Check for different complaint types using type-specific keywords only
        complaint_types = ['housing', 'employment', 'civil_rights', 'consumer', 'healthcare']
        for ctype in complaint_types:
            # Use type-specific keywords to avoid false positives
            keywords = get_type_specific_keywords('complaint', ctype)
            if not keywords:
                continue
            
            # Require multiple matches for confidence
            matches = sum(1 for kw in keywords if kw.lower() in text_lower)
            if matches >= 2:  # Require at least 2 type-specific keywords
                tags.append(ctype)
        
        return tags
    
    def _calculate_relevance(self, index_result: Dict[str, Any]) -> float:
        """
        Calculate combined relevance score.
        
        Combines:
        - Keyword count (weighted by type)
        - Legal provision count
        - Risk score
        - Applicability breadth
        
        Returns a score from 0.0 to 1.0
        """
        # Keyword scoring
        keyword_score = 0.0
        keyword_score += len(index_result['keywords']['complaint']) * 0.3
        keyword_score += len(index_result['keywords']['legal']) * 0.2
        keyword_score += len(index_result['keywords']['binding']) * 0.15
        keyword_score += len(index_result['keywords']['evidence']) * 0.1
        
        # Legal provisions scoring
        provision_score = min(index_result['legal_provisions']['provision_count'] * 0.1, 1.0)
        
        # Risk scoring
        risk_score = index_result['risk_score'] / 3.0  # Normalize to 0-1
        
        # Applicability scoring
        applicability_score = min(len(index_result['applicability']) * 0.2, 1.0)
        
        # Combined score (weighted average)
        combined = (
            keyword_score * 0.4 +
            provision_score * 0.2 +
            risk_score * 0.3 +
            applicability_score * 0.1
        )
        
        # Normalize to 0-1 range
        return min(combined, 1.0)
    
    async def search(self, query: str, top_k: int = 10, 
                    filter_by: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Hybrid search combining vector similarity and keyword matching.
        
        Args:
            query: Search query
            top_k: Number of results to return
            filter_by: Optional filters (e.g., {'applicability': 'housing'})
            
        Returns:
            Scored copies of matching documents sorted by combined relevance.
            Each result includes ``search_score``, ``keyword_score``, and
            ``vector_score`` (``None`` when embeddings are unavailable).

        Raises:
            TypeError: If arguments have the wrong type.
            ValueError: If query is blank or top_k is negative.
        """
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        query = query.strip()
        if not query:
            raise ValueError("query must not be blank")
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k must be an integer")
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        if filter_by is not None and not isinstance(filter_by, dict):
            raise TypeError("filter_by must be a dictionary")
        if top_k == 0 or not self._indexed_documents:
            return []

        query_terms = self._tokenize(query)
        query_embedding = await self._query_embedding(query)
        ranked = []

        for position, document in enumerate(self._indexed_documents):
            if filter_by and not self._matches_filters(document, filter_by):
                continue

            searchable_text = self._document_search_text(document)
            keyword_score = self._keyword_search_score(
                query,
                query_terms,
                searchable_text,
            )
            vector_score = self._vector_search_score(
                query_embedding,
                document.get('embedding'),
            )

            # Without a usable embedding, a document must match at least one
            # query term.  With embeddings, semantic similarity is sufficient.
            if keyword_score == 0.0 and (
                vector_score is None or vector_score == 0.0
            ):
                continue
            if vector_score is None:
                search_score = keyword_score
            else:
                search_score = (vector_score * 0.65) + (keyword_score * 0.35)

            result = dict(document)
            result['search_score'] = search_score
            result['keyword_score'] = keyword_score
            result['vector_score'] = vector_score
            ranked.append((
                search_score,
                keyword_score,
                float(document.get('relevance_score', 0.0) or 0.0),
                -position,
                result,
            ))

        ranked.sort(key=lambda item: item[:4], reverse=True)
        return [item[4] for item in ranked[:top_k]]

    async def _query_embedding(self, query: str) -> Optional[List[float]]:
        """Generate and normalize a query embedding, degrading to keywords."""
        if not self.enable_embeddings or self.embeddings_router is None:
            return None

        try:
            embedding = self.embeddings_router.embed_text(query)
            if inspect.isawaitable(embedding):
                embedding = await embedding
            return self._coerce_vector(embedding)
        except Exception as exc:
            logger.warning(
                "Query embedding failed; using keyword-only search: %s",
                exc,
                exc_info=True,
            )
            return None

    @staticmethod
    def _coerce_vector(value: Any) -> Optional[List[float]]:
        """Return a finite float vector for common embedding payload shapes."""
        if isinstance(value, dict):
            value = value.get('embedding', value.get('vector'))
        if hasattr(value, 'tolist'):
            value = value.tolist()
        if isinstance(value, tuple):
            value = list(value)
        if not isinstance(value, list) or not value:
            return None

        try:
            vector = [float(component) for component in value]
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(component) for component in vector):
            return None
        return vector

    @classmethod
    def _vector_search_score(
        cls,
        query_embedding: Optional[List[float]],
        document_embedding: Any,
    ) -> Optional[float]:
        """Calculate cosine similarity normalized to the 0..1 score range."""
        document_vector = cls._coerce_vector(document_embedding)
        if query_embedding is None or document_vector is None:
            return None
        if len(query_embedding) != len(document_vector):
            return None

        query_norm = math.sqrt(sum(value * value for value in query_embedding))
        document_norm = math.sqrt(sum(value * value for value in document_vector))
        if query_norm == 0.0 or document_norm == 0.0:
            return None

        cosine = sum(
            query_value * document_value
            for query_value, document_value in zip(query_embedding, document_vector)
        ) / (query_norm * document_norm)
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))

    @staticmethod
    def _tokenize(value: str) -> List[str]:
        """Tokenize search input consistently while preserving legal numbers."""
        return re.findall(r"[a-z0-9]+", value.lower())

    @classmethod
    def _keyword_search_score(
        cls,
        query: str,
        query_terms: List[str],
        searchable_text: str,
    ) -> float:
        """Score exact terms, bounded frequency, and an exact phrase bonus."""
        if not query_terms:
            return 0.0

        document_terms = cls._tokenize(searchable_text)
        if not document_terms:
            return 0.0
        document_term_counts = Counter(document_terms)
        term_counts = {
            term: document_term_counts[term]
            for term in set(query_terms)
        }
        matched_terms = sum(1 for count in term_counts.values() if count)
        if matched_terms == 0:
            return 0.0

        coverage = matched_terms / len(term_counts)
        bounded_frequency = sum(
            min(count, 3) for count in term_counts.values()
        ) / (len(term_counts) * 3)
        normalized_query = ' '.join(cls._tokenize(query))
        normalized_document = ' '.join(document_terms)
        phrase_bonus = float(normalized_query in normalized_document)
        return (coverage * 0.7) + (bounded_frequency * 0.2) + (phrase_bonus * 0.1)

    def _document_search_text(self, document: Dict[str, Any]) -> str:
        """Build searchable text from private content and public index fields."""
        values = [self._search_text_by_document_id.get(id(document), '')]
        values.extend(self._flatten_search_values(document.get('metadata', {})))
        values.extend(self._flatten_search_values(document.get('keywords', {})))
        values.extend(self._flatten_search_values(document.get('applicability', [])))
        values.extend(self._flatten_search_values(document.get('legal_provisions', {})))
        return ' '.join(value for value in values if value)

    @classmethod
    def _flatten_search_values(cls, value: Any) -> List[str]:
        """Flatten scalar values without stringifying opaque containers."""
        if isinstance(value, dict):
            flattened = []
            for key, nested_value in value.items():
                flattened.append(str(key))
                flattened.extend(cls._flatten_search_values(nested_value))
            return flattened
        if isinstance(value, (list, tuple, set)):
            flattened = []
            for nested_value in value:
                flattened.extend(cls._flatten_search_values(nested_value))
            return flattened
        if value is None or isinstance(value, bool):
            return []
        if isinstance(value, (str, int, float)):
            return [str(value)]
        return []

    @classmethod
    def _matches_filters(
        cls,
        document: Dict[str, Any],
        filters: Dict[str, Any],
    ) -> bool:
        """Match all filters against document fields or metadata fallback fields."""
        for field, expected in filters.items():
            if not isinstance(field, str) or not field:
                return False
            found, actual = cls._resolve_filter_value(document, field)
            if not found or not cls._filter_value_matches(actual, expected):
                return False
        return True

    @staticmethod
    def _resolve_filter_value(
        document: Dict[str, Any],
        field: str,
    ) -> tuple[bool, Any]:
        parts = field.split('.')
        current: Any = document
        found = True
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                found = False
                break
            current = current[part]
        if found:
            return True, current

        # A plain key conveniently falls back to metadata, while dotted paths
        # remain explicit (for example ``metadata.source``).
        metadata = document.get('metadata', {})
        if len(parts) == 1 and isinstance(metadata, dict) and field in metadata:
            return True, metadata[field]
        return False, None

    @staticmethod
    def _filter_value_matches(actual: Any, expected: Any) -> bool:
        collections = (list, tuple, set)
        if isinstance(expected, collections):
            if isinstance(actual, collections):
                return any(
                    actual_value == expected_value
                    for actual_value in actual
                    for expected_value in expected
                )
            return any(actual == expected_value for expected_value in expected)
        if isinstance(actual, collections):
            return any(actual_value == expected for actual_value in actual)
        return actual == expected
    
    def get_statistics(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get statistics about indexed documents.
        
        Args:
            documents: List of indexed document results
            
        Returns:
            Statistics including risk distribution, keyword frequencies, etc.
        """
        if not documents:
            return {'total': 0}
        
        stats = {
            'total': len(documents),
            'risk_distribution': {'high': 0, 'medium': 0, 'low': 0, 'minimal': 0},
            'applicability': {},
            'avg_provisions': 0,
            'avg_relevance': 0,
        }
        
        total_provisions = 0
        total_relevance = 0
        
        for doc in documents:
            # Risk distribution
            risk_level = doc.get('risk_level', 'minimal')
            stats['risk_distribution'][risk_level] += 1
            
            # Applicability
            for app in doc.get('applicability', []):
                stats['applicability'][app] = stats['applicability'].get(app, 0) + 1
            
            # Averages
            total_provisions += doc.get('legal_provisions', {}).get('provision_count', 0)
            total_relevance += doc.get('relevance_score', 0)
        
        stats['avg_provisions'] = total_provisions / len(documents)
        stats['avg_relevance'] = total_relevance / len(documents)
        
        return stats


    # =====================================================================
    # Batch 218: Document indexing analysis methods
    # =====================================================================
    
    def total_indexed_documents(self) -> int:
        """Return the total number of indexed documents."""
        return len(self._indexed_documents)
    
    def documents_by_risk_level(self, level: str) -> int:
        """
        Return count of documents with a specific risk level.
        
        Args:
            level: Risk level to filter by (minimal, low, medium, high)
            
        Returns:
            Count of documents with that risk level
        """
        return sum(1 for doc in self._indexed_documents 
                  if doc.get('risk_level') == level)
    
    def risk_level_distribution(self) -> Dict[str, int]:
        """
        Return frequency distribution of risk levels.
        
        Returns:
            Dict mapping risk level to count
        """
        dist = {}
        for doc in self._indexed_documents:
            level = doc.get('risk_level', 'minimal')
            dist[level] = dist.get(level, 0) + 1
        return dist
    
    def average_relevance_score(self) -> float:
        """Return average relevance score across all indexed documents."""
        if not self._indexed_documents:
            return 0.0
        total = sum(doc.get('relevance_score', 0) for doc in self._indexed_documents)
        return total / len(self._indexed_documents)
    
    def maximum_relevance_score(self) -> float:
        """Return the maximum relevance score among all indexed documents."""
        if not self._indexed_documents:
            return 0.0
        return max(doc.get('relevance_score', 0) for doc in self._indexed_documents)
    
    def documents_by_applicability(self, tag: str) -> int:
        """
        Return count of documents tagged with a specific applicability.
        
        Args:
            tag: Applicability tag to filter by
            
        Returns:
            Count of documents with that tag
        """
        return sum(1 for doc in self._indexed_documents 
                  if tag in doc.get('applicability', []))
    
    def applicability_distribution(self) -> Dict[str, int]:
        """
        Return frequency distribution of applicability tags.
        
        Returns:
            Dict mapping applicability tag to count
        """
        dist = {}
        for doc in self._indexed_documents:
            for tag in doc.get('applicability', []):
                dist[tag] = dist.get(tag, 0) + 1
        return dist
    
    def average_legal_provisions(self) -> float:
        """Return average number of legal provisions per document."""
        if not self._indexed_documents:
            return 0.0
        total = sum(doc.get('legal_provisions', {}).get('provision_count', 0) 
                   for doc in self._indexed_documents)
        return total / len(self._indexed_documents)
    
    def high_risk_documents_percentage(self) -> float:
        """Return percentage of documents classified as high risk."""
        if not self._indexed_documents:
            return 0.0
        high_risk_count = self.documents_by_risk_level('high')
        return (high_risk_count / len(self._indexed_documents)) * 100
    
    def documents_with_embeddings(self) -> int:
        """Return count of documents that have embeddings available."""
        return sum(1 for doc in self._indexed_documents 
                  if doc.get('embedding_available', False))
