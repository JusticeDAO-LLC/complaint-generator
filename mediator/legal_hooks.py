"""
Legal Classification and Analysis Hooks for Mediator

This module provides hooks for:
1. Classifying types of legal issues in complaints
2. Retrieving applicable statutes
3. Creating requirements for summary judgment
4. Generating questions based on legal requirements
"""

from typing import Dict, List, Optional, Any


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
            return self._parse_statutes(response)
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
                          classification: Dict[str, Any]) -> List[Dict[str, Any]]:
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
                classification
            )
            all_questions.extend(questions)
        
        return all_questions
    
    def _generate_questions_for_claim(self, claim_type: str, 
                                     elements: List[str],
                                     classification: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate questions for a specific claim type."""
        elements_text = '\n'.join([f"{i+1}. {elem}" for i, elem in enumerate(elements)])
        
        prompt = f"""For a legal claim of "{claim_type}", generate specific factual questions to ask the plaintiff that will help prove each of these required elements:

Required Elements:
{elements_text}

Key Facts Already Known:
{', '.join(classification.get('key_facts', [])[:3])}

Generate 2-3 specific, concrete questions for each element. Questions should:
- Be direct and clear
- Ask for specific facts, dates, names, or evidence
- Help establish the required element

Format as:
ELEMENT: [element number and text]
Q1: [question]
Q2: [question]
---
"""
        
        try:
            response = self.mediator.query_backend(prompt)
            return self._parse_questions(response, claim_type, elements)
        except Exception as e:
            self.mediator.log('question_generation_error', error=str(e), claim_type=claim_type)
            return []
    
    def _parse_questions(self, response: str, claim_type: str, 
                        elements: List[str]) -> List[Dict[str, Any]]:
        """Parse generated questions from LLM response."""
        questions = []
        current_element = None
        
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
                        questions.append({
                            'question': question_text,
                            'claim_type': claim_type,
                            'element': current_element or 'Unknown',
                            'priority': 'High',
                            'answer': None
                        })
        
        return questions
