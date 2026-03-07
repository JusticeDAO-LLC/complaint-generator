"""
Legal Classification and Analysis Hooks for Mediator

This module provides hooks for:
1. Classifying types of legal issues in complaints
2. Retrieving applicable statutes
3. Creating requirements for summary judgment
4. Generating questions based on legal requirements
"""

import sys
import os
from typing import Dict, List, Optional, Any

from .integrations import (
    IPFSDatasetsAdapter,
    IntegrationFeatureFlags,
    RetrievalOrchestrator,
    VectorRetrievalAugmentor,
    build_provenance_record,
)

# Add ipfs_datasets_py to path if available
ipfs_datasets_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ipfs_datasets_py')
if os.path.exists(ipfs_datasets_path) and ipfs_datasets_path not in sys.path:
    sys.path.insert(0, ipfs_datasets_path)


class LegalClassificationHook:
    """
    Hook for classifying legal issues in complaints.
    
    Uses LLM to identify:
    - Type of legal claim (e.g., contract, tort, civil rights)
    - Jurisdiction (federal, state, municipal)
    - Relevant areas of law
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
        
    def classify_complaint(self, complaint_text: str) -> Dict[str, Any]:
        """
        Classify the legal issues in a complaint.
        
        Args:
            complaint_text: The complaint summary text
            
        Returns:
            Dictionary with classification results:
            - claim_types: List of legal claim types
            - jurisdiction: Federal, state, or municipal
            - legal_areas: Areas of law involved
            - key_facts: Important facts extracted
        """
        prompt = f"""Analyze the following legal complaint and classify it:

Complaint:
{complaint_text}

Please provide:
1. Type of legal claims (e.g., breach of contract, negligence, civil rights violation, employment discrimination)
2. Jurisdiction level (federal, state, or municipal)
3. Relevant areas of law (e.g., contract law, tort law, civil rights law, employment law)
4. Key facts that are legally significant

Format your response as:
CLAIM TYPES: [list]
JURISDICTION: [level]
LEGAL AREAS: [list]
KEY FACTS: [list]
"""
        
        try:
            response = self.mediator.query_backend(prompt)
            return self._parse_classification(response)
        except Exception as e:
            self.mediator.log('classification_error', error=str(e))
            return {
                'claim_types': [],
                'jurisdiction': 'unknown',
                'legal_areas': [],
                'key_facts': []
            }
    
    def _parse_classification(self, response: str) -> Dict[str, Any]:
        """Parse the LLM classification response."""
        result = {
            'claim_types': [],
            'jurisdiction': 'unknown',
            'legal_areas': [],
            'key_facts': []
        }
        
        lines = response.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if line.startswith('CLAIM TYPES:'):
                current_section = 'claim_types'
                items = line.replace('CLAIM TYPES:', '').strip()
                if items:
                    result['claim_types'] = [item.strip() for item in items.split(',')]
            elif line.startswith('JURISDICTION:'):
                result['jurisdiction'] = line.replace('JURISDICTION:', '').strip().lower()
            elif line.startswith('LEGAL AREAS:'):
                current_section = 'legal_areas'
                items = line.replace('LEGAL AREAS:', '').strip()
                if items:
                    result['legal_areas'] = [item.strip() for item in items.split(',')]
            elif line.startswith('KEY FACTS:'):
                current_section = 'key_facts'
                items = line.replace('KEY FACTS:', '').strip()
                if items:
                    result['key_facts'] = [item.strip() for item in items.split(',')]
            elif line and current_section and line.startswith('-'):
                # Handle bullet point items
                item = line.lstrip('- ').strip()
                if item and current_section in result:
                    if isinstance(result[current_section], list):
                        result[current_section].append(item)
        
        return result


class StatuteRetrievalHook:
    """
    Hook for retrieving applicable statutes.
    
    Uses ipfs_datasets_py legal scrapers to find relevant statutes
    based on classified legal issues.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
        self.integration_flags = IntegrationFeatureFlags.from_env()
        self.integration_adapter = IPFSDatasetsAdapter(feature_flags=self.integration_flags)
        self.retrieval_orchestrator = RetrievalOrchestrator()
        self.vector_augmentor = VectorRetrievalAugmentor()

    def get_capability_registry(self) -> Dict[str, Dict[str, object]]:
        """Get capability and feature-flag status for enhanced integrations."""
        return self.integration_adapter.capability_registry()

    def _with_provenance(
        self,
        statutes: List[Dict[str, str]],
        classification: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        claim_types = classification.get('claim_types', []) if isinstance(classification, dict) else []
        legal_areas = classification.get('legal_areas', []) if isinstance(classification, dict) else []
        enriched: List[Dict[str, Any]] = []

        for statute in statutes:
            provenance = build_provenance_record(
                source_type='legal_dataset',
                source_name='llm_statute_retrieval',
                query=', '.join([*claim_types[:3], *legal_areas[:3]]),
                confidence=0.6,
                metadata={
                    'jurisdiction': classification.get('jurisdiction', 'unknown') if isinstance(classification, dict) else 'unknown',
                    'claim_types': claim_types,
                    'legal_areas': legal_areas,
                },
            )

            with_prov = dict(statute)
            with_prov['provenance'] = {
                'source_type': provenance.source_type,
                'source_name': provenance.source_name,
                'query': provenance.query,
                'confidence': provenance.confidence,
                'retrieved_at': provenance.retrieved_at,
                'metadata': provenance.metadata,
            }
            enriched.append(with_prov)

        return enriched

    def _normalize_records(
        self,
        statutes: List[Dict[str, Any]],
        classification: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        query = ', '.join(classification.get('claim_types', [])) if isinstance(classification, dict) else ''
        query_context = self.retrieval_orchestrator.build_query_context(
            query=query,
            complaint_type=classification.get('claim_types', [query])[0] if isinstance(classification, dict) and classification.get('claim_types') else query,
            jurisdiction=classification.get('jurisdiction') if isinstance(classification, dict) else None,
        )
        evidence_context = self._build_evidence_context(classification)
        normalized = []
        for statute in statutes:
            normalized_record = self.integration_adapter.normalize_record(
                query=query,
                source_type='statute',
                source_name='llm_statute_retrieval',
                record={
                    'citation': statute.get('citation', ''),
                    'title': statute.get('title', ''),
                    'content': statute.get('relevance', ''),
                    'snippet': statute.get('relevance', ''),
                    'score': statute.get('score', 0.0),
                    'confidence': statute.get('confidence', 0.6),
                    'metadata': {
                        'jurisdiction': classification.get('jurisdiction', 'unknown') if isinstance(classification, dict) else 'unknown',
                    },
                },
            )
            normalized.append({
                'source_type': normalized_record.source_type,
                'source_name': normalized_record.source_name,
                'query': normalized_record.query,
                'retrieved_at': normalized_record.retrieved_at,
                'title': normalized_record.title,
                'url': normalized_record.url,
                'citation': normalized_record.citation,
                'snippet': normalized_record.snippet,
                'content': normalized_record.content,
                'score': normalized_record.score,
                'confidence': normalized_record.confidence,
                'metadata': normalized_record.metadata,
            })

        if self.integration_flags.enhanced_vector:
            normalized = self.vector_augmentor.augment_normalized_records(
                records=normalized,
                query=query,
                context_texts=evidence_context,
            )
            self.mediator.log(
                'statute_retrieval_vector_augmentation',
                query=query,
                records=len(normalized),
                evidence_context_items=len(evidence_context),
                capabilities=self.vector_augmentor.capabilities(),
            )

        model_records = []
        for item in normalized:
            model_records.append(self.integration_adapter.normalize_record(
                query=str(item.get('query', '')),
                source_type=str(item.get('source_type', 'statute')),
                source_name=str(item.get('source_name', 'llm_statute_retrieval')),
                record=item,
            ))

        ranked = self.retrieval_orchestrator.merge_and_rank(
            model_records,
            max_results=10,
            query_context=query_context,
        )
        return [
            {
                'source_type': rec.source_type,
                'source_name': rec.source_name,
                'query': rec.query,
                'retrieved_at': rec.retrieved_at,
                'title': rec.title,
                'url': rec.url,
                'citation': rec.citation,
                'snippet': rec.snippet,
                'content': rec.content,
                'score': rec.score,
                'confidence': rec.confidence,
                'metadata': rec.metadata,
            }
            for rec in ranked
        ]

    def _build_support_bundle(self, normalized_records: List[Dict[str, Any]], max_items: int = 5) -> Dict[str, Any]:
        model_records = []
        for item in normalized_records:
            model_records.append(self.integration_adapter.normalize_record(
                query=str(item.get('query', '')),
                source_type=str(item.get('source_type', 'statute')),
                source_name=str(item.get('source_name', 'llm_statute_retrieval')),
                record=item,
            ))
        return self.retrieval_orchestrator.build_support_bundle(model_records, max_items_per_bucket=max_items)

    def _build_evidence_context(self, classification: Dict[str, Any]) -> List[str]:
        context: List[str] = []

        def _add(value: Any):
            text = str(value or '').strip()
            if text and text not in context:
                context.append(text)

        if isinstance(classification, dict):
            for key in ('claim_types', 'legal_areas', 'key_facts'):
                values = classification.get(key, []) or []
                if isinstance(values, list):
                    for value in values[:5]:
                        _add(value)
                else:
                    _add(values)
            _add(classification.get('jurisdiction'))

        state = getattr(self.mediator, 'state', None)
        if state is not None:
            for attr in ('complaint_summary', 'original_complaint', 'complaint', 'last_message'):
                _add(getattr(state, attr, None))

            state_data = getattr(state, 'data', {}) or {}
            if isinstance(state_data, dict):
                context_values = []
                extractor = getattr(state, 'extract_chat_history_context_strings', None)
                if callable(extractor):
                    extracted = extractor(limit=3)
                    if isinstance(extracted, (list, tuple)):
                        context_values = list(extracted)
                if not context_values:
                    chat_history = state_data.get('chat_history', {})
                    if isinstance(chat_history, dict):
                        for _, value in list(chat_history.items())[-3:]:
                            if isinstance(value, dict):
                                for candidate in (value.get('message'), value.get('question')):
                                    text = str(candidate or '').strip()
                                    if text and text not in context_values:
                                        context_values.append(text)
                            else:
                                context_values.append(value)
                for value in context_values:
                    _add(value)

        return context[:10]

    def retrieve_statutes_bundle(self, classification: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve statute results as raw + optional normalized bundle."""
        raw = self.retrieve_statutes(classification)
        bundle: Dict[str, Any] = {'raw': raw}

        if self.integration_flags.enhanced_legal or self.integration_flags.enhanced_search:
            bundle['normalized'] = self._normalize_records(raw, classification)
            bundle['support_bundle'] = self._build_support_bundle(bundle['normalized'])
            self.mediator.log(
                'statute_retrieval_normalized',
                raw_total=len(raw),
                normalized_total=len(bundle['normalized']),
                enhanced_legal=self.integration_flags.enhanced_legal,
                enhanced_search=self.integration_flags.enhanced_search,
            )

        return bundle
    
    def retrieve_statutes(self, classification: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Retrieve applicable statutes based on classification.
        
        Args:
            classification: Classification results from LegalClassificationHook
            
        Returns:
            List of dictionaries containing statute information:
            - citation: Legal citation
            - title: Statute title
            - text: Statute text (summary or full)
            - relevance: Why this statute is relevant
        """
        if not classification or not classification.get('legal_areas'):
            return []
        
        # Use LLM to identify relevant statutes
        prompt = f"""Based on the following legal classification, identify the most relevant federal and state statutes:

Claim Types: {', '.join(classification.get('claim_types', []))}
Jurisdiction: {classification.get('jurisdiction', 'unknown')}
Legal Areas: {', '.join(classification.get('legal_areas', []))}
Key Facts: {', '.join(classification.get('key_facts', []))}

Please list the top 5-10 most relevant statutes with:
1. Citation (e.g., 42 U.S.C. § 1983, 29 U.S.C. § 2601)
2. Title/Name
3. Brief description of relevance

Format as:
STATUTE: [citation]
TITLE: [title]
RELEVANCE: [description]
---
"""
        
        try:
            response = self.mediator.query_backend(prompt)
            parsed = self._parse_statutes(response)
            return self._with_provenance(parsed, classification)
        except Exception as e:
            self.mediator.log('statute_retrieval_error', error=str(e))
            return []
    
    def _parse_statutes(self, response: str) -> List[Dict[str, str]]:
        """Parse statute information from LLM response."""
        statutes = []
        current_statute = {}
        
        sections = response.split('---')
        for section in sections:
            lines = section.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('STATUTE:'):
                    if current_statute:
                        statutes.append(current_statute)
                    current_statute = {'citation': line.replace('STATUTE:', '').strip()}
                elif line.startswith('TITLE:'):
                    current_statute['title'] = line.replace('TITLE:', '').strip()
                elif line.startswith('RELEVANCE:'):
                    current_statute['relevance'] = line.replace('RELEVANCE:', '').strip()
        
        if current_statute:
            statutes.append(current_statute)
        
        return statutes


class SummaryJudgmentHook:
    """
    Hook for creating summary judgment requirements.
    
    Generates the legal elements that must be proven for each claim type
    to prevail on a motion for summary judgment.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
    
    def generate_requirements(self, classification: Dict[str, Any], 
                            statutes: List[Dict[str, str]]) -> Dict[str, List[str]]:
        """
        Generate summary judgment requirements for each claim.
        
        Args:
            classification: Classification results
            statutes: Relevant statutes
            
        Returns:
            Dictionary mapping claim types to lists of required elements
        """
        requirements = {}
        
        for claim_type in classification.get('claim_types', []):
            requirements[claim_type] = self._get_claim_requirements(
                claim_type, 
                classification,
                statutes
            )
        
        return requirements
    
    def _get_claim_requirements(self, claim_type: str, 
                               classification: Dict[str, Any],
                               statutes: List[Dict[str, str]]) -> List[str]:
        """Get the legal elements required to prove a specific claim."""
        statute_info = '\n'.join([
            f"- {s.get('citation', '')}: {s.get('title', '')} - {s.get('relevance', '')}"
            for s in statutes[:5]  # Top 5 most relevant
        ])
        
        prompt = f"""For a legal claim of "{claim_type}", what are the essential elements that must be proven to prevail on a motion for summary judgment?

Context:
- Jurisdiction: {classification.get('jurisdiction', 'unknown')}
- Legal Areas: {', '.join(classification.get('legal_areas', []))}
- Relevant Statutes:
{statute_info}

Please list each required element clearly. Format as a numbered list:
1. [First element]
2. [Second element]
etc.
"""
        
        try:
            response = self.mediator.query_backend(prompt)
            return self._parse_requirements(response)
        except Exception as e:
            self.mediator.log('requirements_error', error=str(e), claim_type=claim_type)
            return []
    
    def _parse_requirements(self, response: str) -> List[str]:
        """Parse requirements from LLM response."""
        requirements = []
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            # Match numbered items like "1.", "2)", etc.
            if line and (line[0].isdigit() or line.startswith('-')):
                # Remove numbering and clean up
                cleaned = line.lstrip('0123456789.-) ').strip()
                if cleaned:
                    requirements.append(cleaned)
        
        return requirements


class QuestionGenerationHook:
    """
    Hook for generating targeted questions based on legal requirements.
    
    Creates specific questions that help gather evidence for each
    required element of the legal claims.
    """
    
    def __init__(self, mediator):
        self.mediator = mediator
    
    def generate_questions(self, requirements: Dict[str, List[str]],
                          classification: Dict[str, Any],
                          provenance_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Generate questions to gather evidence for legal requirements.
        
        Args:
            requirements: Summary judgment requirements by claim type
            classification: Complaint classification
            
        Returns:
            List of question dictionaries:
            - question: The question text
            - claim_type: Related claim type
            - element: Legal element being addressed
            - priority: High/Medium/Low
        """
        all_questions = []
        
        for claim_type, elements in requirements.items():
            questions = self._generate_questions_for_claim(
                claim_type, 
                elements,
                classification,
                provenance_context=provenance_context,
            )
            all_questions.extend(questions)
        
        return all_questions
    
    def _generate_questions_for_claim(self, claim_type: str, 
                                     elements: List[str],
                                     classification: Dict[str, Any],
                                     provenance_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Generate questions for a specific claim type."""
        elements_text = '\n'.join([f"{i+1}. {elem}" for i, elem in enumerate(elements)])
        support_context = ''
        support_summary = {}
        if isinstance(provenance_context, dict):
            support_context = str(provenance_context.get('support_context') or '').strip()
            support_summary = provenance_context.get('support_summary', {}) or {}

        support_guidance = ''
        if support_context:
            support_guidance = f"""

Retrieved Support Already Available:
{support_context}

Support Coverage Summary:
- authority_count: {support_summary.get('authority_count', 0)}
- evidence_count: {support_summary.get('evidence_count', 0)}
- cross_supported_count: {support_summary.get('cross_supported_count', 0)}
- hybrid_cross_supported_count: {support_summary.get('hybrid_cross_supported_count', 0)}
"""
        
        prompt = f"""For a legal claim of "{claim_type}", generate specific factual questions to ask the plaintiff that will help prove each of these required elements:

Required Elements:
{elements_text}

Key Facts Already Known:
{', '.join(classification.get('key_facts', [])[:3])}
{support_guidance}

Generate 2-3 specific, concrete questions for each element. Questions should:
- Be direct and clear
- Ask for specific facts, dates, names, or evidence
- Help establish the required element
- Prioritize facts or evidence that are not already strongly corroborated by retrieved support

Format as:
ELEMENT: [element number and text]
Q1: [question]
Q2: [question]
---
"""
        
        try:
            response = self.mediator.query_backend(prompt)
            return self._parse_questions(response, claim_type, elements, provenance_context)
        except Exception as e:
            self.mediator.log('question_generation_error', error=str(e), claim_type=claim_type)
            return []
    
    def _parse_questions(self, response: str, claim_type: str, 
                        elements: List[str],
                        provenance_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Parse generated questions from LLM response."""
        questions = []
        current_element = None
        support_summary = provenance_context.get('support_summary', {}) if isinstance(provenance_context, dict) else {}
        support_summary = support_summary if isinstance(support_summary, dict) else {}

        authority_count = int(support_summary.get('authority_count', 0) or 0)
        evidence_count = int(support_summary.get('evidence_count', 0) or 0)
        cross_supported_count = int(support_summary.get('cross_supported_count', 0) or 0)
        hybrid_cross_supported_count = int(support_summary.get('hybrid_cross_supported_count', 0) or 0)

        if hybrid_cross_supported_count > 0:
            default_priority = 'Medium'
        elif cross_supported_count > 0 or authority_count > 0 or evidence_count > 0:
            default_priority = 'High'
        else:
            default_priority = 'Critical'

        support_gap_targeted = cross_supported_count == 0
        
        sections = response.split('---')
        for section in sections:
            lines = section.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('ELEMENT:'):
                    current_element = line.replace('ELEMENT:', '').strip()
                elif line.startswith('Q') and ':' in line:
                    # Extract question
                    question_text = line.split(':', 1)[1].strip()
                    if question_text:
                        provenance = {
                            'source_type': 'question_generation',
                            'source_name': 'llm_question_generator',
                            'claim_type': claim_type,
                            'element': current_element or 'Unknown',
                        }
                        if provenance_context:
                            provenance.update(provenance_context)

                        questions.append({
                            'question': question_text,
                            'claim_type': claim_type,
                            'element': current_element or 'Unknown',
                            'priority': default_priority,
                            'answer': None,
                            'support_gap_targeted': support_gap_targeted,
                            'provenance': provenance,
                        })
        
        return questions
