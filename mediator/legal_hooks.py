"""
Legal Classification and Analysis Hooks for Mediator

This module provides hooks for:
1. Classifying types of legal issues in complaints
2. Retrieving applicable statutes
3. Creating requirements for summary judgment
4. Generating questions based on legal requirements
"""

from typing import Dict, List, Optional, Any
from mediator.state import extract_chat_history_context_strings_from_state

from .integrations import (
    IPFSDatasetsAdapter,
    IntegrationFeatureFlags,
    RetrievalOrchestrator,
    VectorRetrievalAugmentor,
    build_provenance_record,
)


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

            for value in extract_chat_history_context_strings_from_state(state, limit=3):
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

    def adapt_requirements_for_dependency_graph(self, requirements: Any, legal_context: Optional[Dict[str, Any]] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Adapt hook output into DependencyGraphBuilder entries.

        ``generate_requirements`` still returns ``dict[str, list[str]]`` for
        question prompts. Those strings are not legal elements. The adapter
        records them as unresolved requirements.
        """
        from integrations.ipfs_datasets.legal import adapt_sourced_legal_requirements

        return adapt_sourced_legal_requirements(requirements, legal_context=legal_context)
    
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

    def finite_factual_inquiries(self, gaps: List[Dict[str, Any]], *, cap: int = 4) -> List[Dict[str, Any]]:
        """Ask a bounded set of factual questions. The list does not grow itself.

        Each gap is one inquiry. A legal-research gap stays a research question
        and is not stored as an element of law. Past the cap, remaining gaps
        are counted and not emitted.
        """
        limit = cap if type(cap) is int and cap > 0 else 4
        if limit > 8:
            limit = 8
        inquiries: List[Dict[str, Any]] = []
        for index, gap in enumerate(gaps):
            if len(inquiries) >= limit:
                break
            if not isinstance(gap, dict):
                continue
            kind = str(gap.get("record_kind") or "factual_assertion")
            target = str(gap.get("target_id") or f"gap-{index}")
            inquiries.append({
                "inquiry_id": f"inq-{index + 1}",
                "sequence": index + 1,
                "question": str(gap.get("question") or "").strip(),
                "record_kind": kind,
                "creates_law": False,
                "target_id": target,
                "disposition": "open",
                "answer": None,
                "finite": True,
                "priority": "High" if kind == "factual_assertion" else "Medium",
            })
        return inquiries


_GROUNDING_INQUIRY_CAP = 4


def _freeze_payload(payload: Any) -> Dict[str, Any]:
    import copy

    if not isinstance(payload, dict):
        raise TypeError("grounding input must be a dict")
    return copy.deepcopy(payload)


def _requirement_from_authority(authority: Dict[str, Any], claim_type: str) -> Optional[Dict[str, Any]]:
    from integrations.ipfs_datasets.logic import extract_source_bound_rule_candidates

    if not isinstance(authority, dict):
        return None
    extracted = extract_source_bound_rule_candidates(authority)
    promoted = extracted.get("promoted_requirements") or []
    if not promoted:
        return None
    candidate = dict(promoted[0])
    dates = candidate.get("applicable_date") if isinstance(candidate.get("applicable_date"), dict) else {}
    record = dict(candidate)
    record.update({
        "claim_type": claim_type,
        "name": str(candidate.get("authority_id") or candidate.get("citation") or "Sourced requirement"),
        "description": str(candidate.get("rule_text") or ""),
        "authority_locator": str(candidate.get("citation") or candidate.get("authority_id") or ""),
        "source_locator": str(candidate.get("citation") or candidate.get("authority_id") or ""),
        "jurisdiction": str(candidate.get("jurisdiction") or authority.get("jurisdiction") or ""),
        "effective_date": str(dates.get("effective_date") or authority.get("effective_date") or ""),
        "authority_version": str(candidate.get("authority_version") or ""),
        "source_record": dict(authority),
        "origin": "admitted_authority",
    })
    return record


def qualify_grounded_legal_hooks(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Public workflow for the four legal hooks against canonical tools.

    Classification is a suggestion. Statute lookup uses
    ``lookup_bounded_legal_corpus`` and stays discovery. Requirements enter the
    dependency graph only when the current admitted authority promotes a
    source-bound rule. Model text and default claim taxonomies do not create
    law. The caller's mapping is not modified.
    """
    import copy

    from integrations.ipfs_datasets.legal import (
        CORPUS_FAMILY_STATE_STATUTE,
        CORPUS_FAMILY_US_CODE,
        UNKNOWN_LEGAL_CONTEXT,
        lookup_bounded_legal_corpus,
        resolve_explicit_jurisdiction,
    )
    from integrations.ipfs_datasets.logic import legacy_unverified_requirement_templates
    from complaint_phases.dependency_graph import DependencyGraphBuilder

    if not isinstance(payload, dict):
        return {
            "status": "refused",
            "code": "malformed_input",
            "workflow": "qualify_grounded_legal_hooks",
            "creates_law": False,
            "provider_invoked": False,
        }
    before = copy.deepcopy(payload)
    working = _freeze_payload(payload)
    jurisdiction = resolve_explicit_jurisdiction(working.get("jurisdiction"))
    applicable = str(working.get("applicable_law_date") or "").strip()
    context_known = jurisdiction != UNKNOWN_LEGAL_CONTEXT and bool(applicable)
    claim_candidates = [
        str(item).strip()
        for item in (working.get("claim_candidates") or [])
        if str(item).strip()
    ]
    model_text = str(working.get("model_text") or "").strip()
    taxonomy = legacy_unverified_requirement_templates([*claim_candidates, "employment_discrimination"])
    taxonomy_names = [str(item.get("name") or "") for item in taxonomy]

    classification = {
        "owner": "LegalClassificationHook",
        "record_kind": "classifier_suggestion",
        "creates_law": False,
        "claim_types": claim_candidates,
        "jurisdiction": jurisdiction if jurisdiction != UNKNOWN_LEGAL_CONTEXT else "unknown",
        "jurisdiction_explicit": jurisdiction != UNKNOWN_LEGAL_CONTEXT,
        "legal_areas": [],
        "key_facts": [],
        "model_text": model_text,
        "model_text_creates_law": False,
        "default_taxonomy_creates_law": False,
    }
    factual = {
        "record_kind": "factual_assertion",
        "text": str(working.get("narrative") or ""),
        "creates_law": False,
        "about_complainant": True,
    }

    tool_calls = 0
    corpus: Dict[str, Any]
    if not context_known:
        corpus = {
            "status": "not_called",
            "code": "unknown_legal_context",
            "results": [],
            "creates_law": False,
        }
    else:
        family = CORPUS_FAMILY_US_CODE if jurisdiction == "federal" else CORPUS_FAMILY_STATE_STATUTE
        state = None if jurisdiction == "federal" else jurisdiction
        tool_calls += 1
        try:
            corpus = lookup_bounded_legal_corpus(
                source_family=family,
                query=str(working.get("corpus_query") or claim_candidates[0] if claim_candidates else "statute"),
                retrieval_mode="cache",
                jurisdiction=jurisdiction,
                state=state,
                max_results=3,
                timeout_seconds=2.0,
                offline_cache=working.get("offline_cache") if isinstance(working.get("offline_cache"), dict) else {},
                contains_private_facts=False,
                privacy_policy_accepted=False,
            )
        except Exception as exc:
            corpus = {
                "status": "unavailable",
                "error_code": "missing_capability",
                "error_message": str(exc),
                "results": [],
            }
        if not isinstance(corpus, dict):
            corpus = {"status": "unavailable", "error_code": "missing_capability", "results": []}
        corpus = dict(corpus)
        corpus["creates_law"] = False
        corpus["discovery_only"] = True
        corpus["owner"] = "StatuteRetrievalHook"
        corpus["tool"] = "lookup_bounded_legal_corpus"

    if corpus.get("status") == "unavailable" or corpus.get("error_code") == "missing_capability":
        if payload != before:
            raise RuntimeError("grounding input was mutated")
        return {
            "status": "unavailable",
            "code": str(corpus.get("error_code") or "missing_capability"),
            "workflow": "qualify_grounded_legal_hooks",
            "classification": classification,
            "factual_assertion": factual,
            "statutes": [],
            "statute_discovery": corpus,
            "requirements": {},
            "inquiries": [],
            "legal_element_count": 0,
            "creates_law": False,
            "provider_invoked": False,
            "tool_calls": tool_calls,
            "input_mutated": False,
            "handler_enabled_by_caller": False,
        }

    claim_type = claim_candidates[0] if claim_candidates else "unknown"
    requirements: Dict[str, List[Any]] = {claim_type: []}
    for authority in working.get("admitted_authorities") or []:
        record = _requirement_from_authority(authority, claim_type)
        if record is not None:
            requirements[claim_type].append(record)
    for text in working.get("model_requirements") or []:
        requirements[claim_type].append(str(text))
    if model_text:
        requirements[claim_type].append(model_text)
    for name in taxonomy_names:
        requirements[claim_type].append({
            "name": name,
            "description": name,
            "legacy_template": True,
            "template_kind": "claim_keyword_template",
            "claim_type": claim_type,
            "origin": "default_taxonomy",
        })

    graph = DependencyGraphBuilder().build_grounded_hook_graph(
        [{
            "name": claim_type,
            "type": claim_type,
            "description": str(working.get("narrative") or ""),
        }],
        requirements,
        model_text=model_text,
        taxonomy_names=taxonomy_names,
        legal_context={
            "jurisdiction": jurisdiction,
            "applicable_law_date": applicable,
            "context_revision": working.get("context_revision", 0),
        } if context_known else None,
    )
    legal_elements = [
        node for node in graph.nodes.values()
        if node.node_type.value == "legal_element"
        and (node.attributes or {}).get("record_kind") == "legal_requirement"
    ]
    unresolved = list(graph.metadata.get("unresolved_legal_requirements") or [])

    gaps: List[Dict[str, Any]] = []
    if not context_known:
        gaps.append({
            "record_kind": "unknown_legal_context",
            "target_id": "unknown-legal-context",
            "question": "Which jurisdiction and applicable-law date should be used? They were not stated.",
        })
    else:
        for node in graph.metadata.get("factual_nodes") or []:
            if node.get("node_type") != "fact":
                continue
            gaps.append({
                "record_kind": "factual_assertion",
                "target_id": str(node.get("id") or ""),
                "question": f"What fact supplies {node.get('name')}?",
            })
        if unresolved and not legal_elements:
            gaps.append({
                "record_kind": "legal_research",
                "target_id": "unresolved-authority",
                "question": "Which admitted authority applies? Model text was not treated as law.",
            })
    cap = working.get("inquiry_cap", _GROUNDING_INQUIRY_CAP)
    inquiries = QuestionGenerationHook(mediator=None).finite_factual_inquiries(gaps, cap=cap if type(cap) is int else _GROUNDING_INQUIRY_CAP)
    truncated = len(inquiries) < len([gap for gap in gaps if isinstance(gap, dict)])
    if payload != before:
        raise RuntimeError("grounding input was mutated")
    return {
        "status": "qualified",
        "code": "unknown_legal_context" if not context_known else "grounded",
        "workflow": "qualify_grounded_legal_hooks",
        "classification": classification,
        "factual_assertion": factual,
        "statute_discovery": {
            "status": corpus.get("status"),
            "tool": "lookup_bounded_legal_corpus",
            "owner": "StatuteRetrievalHook",
            "result_count": len(corpus.get("results") or []),
            "creates_law": False,
            "discovery_only": True,
            "citations": [
                str(item.get("citation") or "")
                for item in (corpus.get("results") or [])
                if isinstance(item, dict)
            ],
        },
        "requirements_owner": "SummaryJudgmentHook",
        "legal_element_count": len(legal_elements),
        "legal_element_names": [node.name for node in legal_elements],
        "unresolved_count": len(unresolved),
        "unresolved_reasons": [item.get("reason") for item in unresolved],
        "taxonomy_names": taxonomy_names,
        "taxonomy_names_in_legal_elements": [
            node.name for node in legal_elements if node.name in taxonomy_names or node.name == model_text
        ],
        "model_text_created_law": False,
        "default_taxonomy_created_law": False,
        "factual_nodes": graph.metadata.get("factual_nodes") or [],
        "legal_nodes": graph.metadata.get("legal_nodes") or [],
        "factual_legal_separated": True,
        "inquiries": inquiries,
        "inquiry_cap": cap if type(cap) is int else _GROUNDING_INQUIRY_CAP,
        "inquiry_truncated": truncated,
        "inquiry_semantics": "capped" if truncated else ("open" if inquiries else "none"),
        "creates_law": False,
        "provider_invoked": False,
        "tool_calls": tool_calls,
        "input_mutated": False,
        "handler_enabled_by_caller": False,
        "graph_owner": "DependencyGraphBuilder.build_grounded_hook_graph",
    }
