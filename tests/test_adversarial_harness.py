"""Tests for adversarial harness system."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
from adversarial_harness import (
    Complainant,
    ComplaintContext,
    Critic,
    CriticScore,
    AdversarialSession,
    SessionResult,
    AdversarialHarness,
    Optimizer,
    OptimizationReport,
    SeedComplaintLibrary,
    ComplaintTemplate,
    HACC_QUERY_PRESETS,
    get_hacc_query_specs,
)
from adversarial_harness.demo_autopatch import (
    DemoBatchLLMBackend,
    DemoBatchMediator,
    run_adversarial_autopatch_batch,
)
import adversarial_harness.demo_autopatch as demo_autopatch_module
from adversarial_harness.hacc_evidence import (
    _best_rule_text,
    _extract_source_window,
    build_hacc_evidence_seed,
    build_hacc_mediator_evidence_packet,
)
import adversarial_harness.seed_complaints as seed_complaints_module


class MockLLMBackend:
    """Mock LLM backend for testing."""
    def __init__(self, response_template=None):
        self.response_template = response_template or "Mock response"
        self.call_count = 0
    
    def __call__(self, prompt):
        self.call_count += 1
        if callable(self.response_template):
            return self.response_template(prompt)
        return self.response_template


class MockMediator:
    """Mock mediator for testing."""
    def __init__(self):
        self.phase_manager = MockPhaseManager()
        self.questions_asked = 0
    
    def start_three_phase_process(self, complaint_text):
        return {
            'phase': 'intake',
            'initial_questions': [
                {
                    'question': 'Can you provide more details?',
                    'type': 'clarification',
                    'question_objective': 'clarify_low_confidence_fact',
                    'question_reason': 'The mediator needs more detail before relying on the current intake record.',
                    'expected_proof_gain': 'medium',
                }
            ]
        }
    
    def process_denoising_answer(self, question, answer):
        self.questions_asked += 1
        return {
            'converged': self.questions_asked >= 3,
            'next_questions': [
                {
                    'question': 'Tell me more',
                    'type': 'follow_up',
                    'question_objective': 'general_intake_clarification',
                    'question_reason': 'A follow-up is needed to complete the intake record.',
                    'expected_proof_gain': 'medium',
                }
            ]
        }
    
    def get_three_phase_status(self):
        return {
            'current_phase': 'intake',
            'iteration_count': self.questions_asked
        }


class MockPhaseManager:
    """Mock phase manager."""
    def get_phase_data(self, phase, key):
        if key == 'knowledge_graph':
            return MockKnowledgeGraph()
        elif key == 'dependency_graph':
            return MockDependencyGraph()
        return None


class MockKnowledgeGraph:
    """Mock knowledge graph."""
    def summary(self):
        return {'total_entities': 5, 'total_relationships': 3}


class MockDependencyGraph:
    """Mock dependency graph."""
    def summary(self):
        return {'total_nodes': 4, 'total_dependencies': 2}


class FakeAgenticOptimizationMethod:
    ACTOR_CRITIC = 'ACTOR_CRITIC'
    ADVERSARIAL = 'ADVERSARIAL'
    TEST_DRIVEN = 'TEST_DRIVEN'
    CHAOS = 'CHAOS'


class FakeOptimizationTask:
    def __init__(self, task_id, description, target_files, method, priority, constraints, metadata):
        self.task_id = task_id
        self.description = description
        self.target_files = target_files
        self.method = method
        self.priority = priority
        self.constraints = constraints
        self.metadata = metadata


class TestComplainant:
    """Tests for Complainant class."""
    
    def test_complainant_creation(self):
        """Test complainant can be created."""
        backend = MockLLMBackend()
        complainant = Complainant(backend, personality="cooperative")
        assert complainant.personality == "cooperative"
        assert complainant.context is None
    
    def test_set_context(self):
        """Test setting context."""
        backend = MockLLMBackend()
        complainant = Complainant(backend)
        
        context = ComplaintContext(
            complaint_type="employment_discrimination",
            key_facts={'employer': 'Acme Corp'}
        )
        complainant.set_context(context)
        
        assert complainant.context == context
    
    def test_generate_initial_complaint(self):
        """Test generating initial complaint."""
        backend = MockLLMBackend("I was discriminated against at work.")
        complainant = Complainant(backend)
        
        seed = {'type': 'employment_discrimination', 'summary': 'Fired unfairly'}
        complaint = complainant.generate_initial_complaint(seed)
        
        assert len(complaint) > 0
        assert backend.call_count == 1
    
    def test_respond_to_question(self):
        """Test responding to mediator questions."""
        backend = MockLLMBackend("Yes, it happened last month.")
        complainant = Complainant(backend)
        
        context = ComplaintContext(
            complaint_type="employment_discrimination",
            key_facts={'employer': 'Acme Corp'}
        )
        complainant.set_context(context)
        
        response = complainant.respond_to_question("When did this occur?")
        
        assert len(response) > 0
        assert backend.call_count == 1

    def test_default_context_carries_hacc_evidence(self):
        seed = {
            'type': 'housing_discrimination',
            'summary': 'A housing policy appears to support the complaint.',
            'key_facts': {
                'evidence_summary': 'The policy text suggests discriminatory treatment.',
            },
            'hacc_evidence': [
                {
                    'title': 'Admissions and Continued Occupancy Policy',
                    'snippet': 'Applicants requesting accommodations must be reviewed individually.',
                    'source_path': '/tmp/acop.txt',
                }
            ],
        }

        context = Complainant.build_default_context(seed, 'detailed')

        assert context.evidence_summary == 'The policy text suggests discriminatory treatment.'
        assert len(context.evidence_items) == 1

    def test_default_context_derives_blocker_objectives_and_workflow_priorities(self):
        seed = {
            'type': 'retaliation',
            'summary': 'After I complained, the agency denied my appeal and I still need the exact notice date.',
            'key_facts': {
                'synthetic_prompts': {
                    'intake_questionnaire_prompt': 'Ask who made the decision, when the hearing was requested, and when the response came back.',
                    'intake_questions': [
                        'Who at the agency made or communicated the decision?',
                        'When did you request a hearing or appeal?',
                        'What happened after you complained, and when?',
                    ],
                },
            },
            'hacc_evidence': [
                {'title': 'Denial Notice', 'snippet': 'Appeal denied by letter.'},
            ],
        }

        context = Complainant.build_default_context(seed, 'detailed')

        assert context.blocker_objectives == [
            'exact_dates',
            'staff_names_titles',
            'adverse_action_specificity',
            'hearing_request_timing',
            'response_dates',
            'causation_sequence',
            'evidence_identifiers',
        ]
        assert context.extraction_targets == [
            'timeline_anchors',
            'actor_role_mapping',
            'hearing_process',
            'response_timeline',
            'retaliation_sequence',
            'adverse_action_definition',
            'document_identifier_mapping',
        ]
        assert context.workflow_phase_priorities == [
            'graph_analysis',
            'document_generation',
            'intake_questioning',
        ]

    def test_prompt_includes_hacc_evidence(self):
        prompts = []

        def backend(prompt):
            prompts.append(prompt)
            return "Mock response"

        complainant = Complainant(backend, personality="detailed")
        seed = {
            'type': 'housing_discrimination',
            'summary': 'The evidence points to a policy problem.',
            'key_facts': {
                'evidence_summary': 'The policy text points to a policy problem.',
                'anchor_sections': ['grievance_hearing', 'appeal_rights'],
                'anchor_passages': [
                    {
                        'title': 'HACC Policy',
                        'snippet': 'A grievance hearing will be conducted by a single impartial person appointed by HACC.',
                        'section_labels': ['grievance_hearing'],
                    }
                ],
            },
            'hacc_evidence': [
                {
                    'title': 'HACC Policy',
                    'snippet': 'This is a supporting excerpt.',
                    'source_path': '/tmp/hacc-policy.txt',
                }
            ],
        }

        complainant.set_context(Complainant.build_default_context(seed, 'detailed'))
        complainant.generate_initial_complaint(seed)
        complainant.respond_to_question("What document supports this?")

        assert any('Evidence grounding:' in prompt for prompt in prompts)
        assert any('Evidence you can draw from:' in prompt for prompt in prompts)
        assert any('HACC Policy' in prompt for prompt in prompts)
        assert any('Decision-tree sections: grievance_hearing, appeal_rights' in prompt for prompt in prompts)
        assert any('Passage 1 [grievance_hearing] from HACC Policy' in prompt for prompt in prompts)

    def test_prompt_includes_intake_questionnaire_guidance(self):
        prompts = []

        def backend(prompt):
            prompts.append(prompt)
            return "Mock response"

        complainant = Complainant(backend, personality="detailed")
        seed = {
            'type': 'housing_discrimination',
            'summary': 'The evidence points to a policy problem.',
            'key_facts': {
                'evidence_summary': 'The policy text points to a policy problem.',
                'synthetic_prompts': {
                    'complaint_chatbot_prompt': 'Ask for timeline, actor, harm, and remedy facts.',
                    'intake_questionnaire_prompt': 'Before drafting, ask what adverse action happened and when.',
                    'intake_questions': [
                        'What happened, and what adverse action did HACC take or threaten to take?',
                        'When did the key events happen?',
                    ],
                },
            },
        }

        complainant.set_context(Complainant.build_default_context(seed, 'detailed'))
        complainant.generate_initial_complaint(seed)

        assert any('Intake questionnaire:' in prompt for prompt in prompts)
        assert any('Missing fact question 1:' in prompt for prompt in prompts)
        assert any('ask what adverse action happened and when' in prompt.lower() for prompt in prompts)

    def test_question_response_refreshes_dynamic_hacc_evidence(self, monkeypatch):
        prompts = []

        def backend(prompt):
            prompts.append(prompt)
            return "The grievance policy supports what happened."

        complainant = Complainant(backend, personality="detailed")
        seed = {
            'type': 'housing_discrimination',
            'summary': 'The evidence points to a grievance issue.',
            'key_facts': {
                'evidence_query': 'grievance hearing due process',
                'evidence_summary': 'Static summary.',
                'anchor_sections': ['grievance_hearing'],
            },
            'hacc_evidence': [
                {'title': 'Static Policy', 'snippet': 'Static seed evidence.'},
            ],
        }
        context = Complainant.build_default_context(seed, 'detailed')
        complainant.set_context(context)

        monkeypatch.setattr(
            'adversarial_harness.complainant._resolve_dynamic_hacc_evidence',
            lambda question, context: {
                'evidence_summary': 'Dynamic evidence for the specific question.',
                'evidence_items': [{'title': 'ADMINISTRATIVE PLAN', 'snippet': 'A grievance hearing will be conducted by an impartial person.'}],
                'anchor_passages': [{'title': 'ADMINISTRATIVE PLAN', 'snippet': 'A grievance hearing will be conducted by an impartial person.', 'section_labels': ['grievance_hearing']}],
                'anchor_sections': ['grievance_hearing'],
            },
        )

        response = complainant.respond_to_question("What policy supports your appeal rights?")

        assert response
        assert complainant.context.dynamic_evidence_summary == 'Dynamic evidence for the specific question.'
        assert complainant.context.dynamic_evidence_items[0]['title'] == 'ADMINISTRATIVE PLAN'
        assert any('Question-focused HACC evidence:' in prompt for prompt in prompts)
        assert any('Dynamic evidence for the specific question.' in prompt for prompt in prompts)

    def test_response_prompt_includes_intake_questionnaire_guidance(self):
        prompts = []

        def backend(prompt):
            prompts.append(prompt)
            return "I still need to confirm the date and who made the decision."

        complainant = Complainant(backend, personality="detailed")
        context = ComplaintContext(
            complaint_type="housing_discrimination",
            key_facts={'evidence_query': 'administrative plan grievance hearing'},
            evidence_items=[{'title': 'Static Policy', 'snippet': 'Static'}],
            evidence_summary='Static summary',
            synthetic_prompts={
                'intake_questionnaire_prompt': 'Ask for date, actor, process, harm, and remedy facts.',
                'intake_questions': [
                    'When did the key events happen?',
                    'Who at HACC made, communicated, or carried out each decision?',
                ],
            },
        )
        complainant.set_context(context)

        complainant.respond_to_question("What happened after you complained?")

        assert any('Intake questionnaire:' in prompt for prompt in prompts)
        assert any('Missing fact question 1:' in prompt for prompt in prompts)

    def test_response_history_persists_dynamic_evidence_context(self, monkeypatch):
        backend = MockLLMBackend("I relied on the administrative plan language.")
        complainant = Complainant(backend, personality="detailed")
        context = ComplaintContext(
            complaint_type="housing_discrimination",
            key_facts={'evidence_query': 'administrative plan grievance hearing'},
            evidence_items=[{'title': 'Static Policy', 'snippet': 'Static'}],
            evidence_summary='Static summary',
        )
        complainant.set_context(context)

        monkeypatch.setattr(
            'adversarial_harness.complainant._resolve_dynamic_hacc_evidence',
            lambda question, context: {
                'evidence_summary': 'Dynamic summary',
                'evidence_items': [{'title': 'ADMINISTRATIVE PLAN', 'snippet': 'Impartial person'}],
                'anchor_passages': [],
                'anchor_sections': ['grievance_hearing'],
            },
        )

        complainant.respond_to_question("Which document mentions an impartial person?")

        last_message = complainant.get_conversation_history()[-1]
        assert last_message['role'] == 'complainant'
        assert last_message['evidence_context']['dynamic_evidence_summary'] == 'Dynamic summary'
        assert last_message['evidence_context']['dynamic_anchor_sections'] == ['grievance_hearing']


class TestCritic:
    """Tests for Critic class."""
    
    def test_critic_creation(self):
        """Test critic can be created."""
        backend = MockLLMBackend()
        critic = Critic(backend)
        assert critic.llm_backend == backend
    
    def test_evaluate_session(self):
        """Test evaluating a session."""
        response_text = """SCORES:
question_quality: 0.8
information_extraction: 0.7
empathy: 0.6
efficiency: 0.75
coverage: 0.7

FEEDBACK:
Good questioning overall.

STRENGTHS:
- Clear questions
- Good follow-ups

WEAKNESSES:
- Could be more empathetic

SUGGESTIONS:
- Add more rapport building
"""
        backend = MockLLMBackend(response_text)
        critic = Critic(backend)
        
        score = critic.evaluate_session(
            "Initial complaint",
            [{'role': 'mediator', 'content': 'Question'}],
            {'status': 'complete'}
        )
        
        assert isinstance(score, CriticScore)
        assert 0.0 <= score.overall_score <= 1.0
        assert score.question_quality == 0.8

    def test_evaluate_session_tracks_anchor_sections(self):
        backend = MockLLMBackend("""SCORES:
question_quality: 0.8
information_extraction: 0.8
empathy: 0.7
efficiency: 0.7
coverage: 0.8

FEEDBACK:
Good session.

STRENGTHS:
- Covered major issues

WEAKNESSES:
- Could ask more

SUGGESTIONS:
- Add follow-up
""")
        critic = Critic(backend)

        score = critic.evaluate_session(
            "Initial complaint",
            [
                {'role': 'mediator', 'type': 'question', 'content': 'Did you request a reasonable accommodation?'},
                {'role': 'complainant', 'type': 'response', 'content': 'Yes, I asked for an accommodation because of my disability.'},
            ],
            {'status': 'complete'},
            context={'key_facts': {'anchor_sections': ['reasonable_accommodation', 'grievance_hearing']}},
        )

        assert 'reasonable_accommodation' in score.anchor_sections_covered
        assert 'grievance_hearing' in score.anchor_sections_missing
        assert score.coverage < 0.8
        assert any('Missed anchor sections: grievance_hearing' == item for item in score.weaknesses)
        assert any('Add questions covering: grievance_hearing' == item for item in score.suggestions)
        assert 'Anchor-section coverage was incomplete' in score.feedback

    def test_evaluate_session_rewards_full_anchor_coverage(self):
        backend = MockLLMBackend("""SCORES:
question_quality: 0.7
information_extraction: 0.7
empathy: 0.7
efficiency: 0.7
coverage: 0.6

FEEDBACK:
Solid session.

STRENGTHS:
- Stayed on topic

WEAKNESSES:
- None

SUGGESTIONS:
- Keep going
""")
        critic = Critic(backend)

        score = critic.evaluate_session(
            "Initial complaint",
            [
                {'role': 'mediator', 'type': 'question', 'content': 'Did you request a reasonable accommodation or grievance hearing?'},
                {'role': 'complainant', 'type': 'response', 'content': 'Yes, I requested a reasonable accommodation and later asked for a grievance hearing.'},
            ],
            {'status': 'complete'},
            context={'key_facts': {'anchor_sections': ['reasonable_accommodation', 'grievance_hearing']}},
        )

        assert score.anchor_sections_missing == []
        assert score.coverage > 0.6
        assert any('Covered all seeded anchor sections' in item for item in score.strengths)

    def test_evaluate_session_tracks_intake_priority_coverage(self):
        prompts = []

        def backend(prompt):
            prompts.append(prompt)
            return """SCORES:
question_quality: 0.8
information_extraction: 0.6
empathy: 0.7
efficiency: 0.7
coverage: 0.6

FEEDBACK:
Good session.

STRENGTHS:
- Covered major issues

WEAKNESSES:
- Could ask more

SUGGESTIONS:
- Add follow-up
"""

        critic = Critic(backend)

        score = critic.evaluate_session(
            "Initial complaint",
            [
                {'role': 'mediator', 'type': 'question', 'content': 'When did the key events happen?'},
                {'role': 'complainant', 'type': 'response', 'content': 'The notice arrived last week.'},
            ],
            {
                'status': 'complete',
                'adversarial_intake_priority_summary': {
                    'expected_objectives': ['timeline', 'documents', 'harm_remedy'],
                    'covered_objectives': ['timeline'],
                    'uncovered_objectives': ['documents', 'harm_remedy'],
                },
            },
        )

        assert score.intake_priority_expected == ['timeline', 'documents', 'harm_remedy']
        assert score.intake_priority_covered == ['timeline']
        assert score.intake_priority_missing == ['documents', 'harm_remedy']
        assert score.information_extraction < 0.6
        assert score.coverage < 0.6
        assert any('Missed intake objectives: documents, harm_remedy' == item for item in score.weaknesses)
        assert any('Add questions covering intake objectives: documents, harm_remedy' == item for item in score.suggestions)
        assert 'Intake-priority coverage was incomplete' in score.feedback
        assert any('INTAKE PRIORITY COVERAGE:' in prompt for prompt in prompts)
        assert any('Objectives still uncovered: documents, harm_remedy' in prompt for prompt in prompts)

    def test_evaluate_session_rewards_full_intake_priority_coverage(self):
        critic = Critic(MockLLMBackend("""SCORES:
question_quality: 0.7
information_extraction: 0.6
empathy: 0.7
efficiency: 0.7
coverage: 0.5

FEEDBACK:
Solid session.

STRENGTHS:
- Stayed on topic

WEAKNESSES:
- None

SUGGESTIONS:
- Keep going
"""))

        score = critic.evaluate_session(
            "Initial complaint",
            [
                {'role': 'mediator', 'type': 'question', 'content': 'When did the events happen and what documents do you have?'},
                {'role': 'complainant', 'type': 'response', 'content': 'It started in January and I have the notice letter.'},
            ],
            {
                'status': 'complete',
                'adversarial_intake_priority_summary': {
                    'expected_objectives': ['timeline', 'documents'],
                    'covered_objectives': ['timeline', 'documents'],
                    'uncovered_objectives': [],
                },
            },
        )

        assert score.intake_priority_missing == []
        assert score.coverage > 0.5
        assert any('Covered all intake-priority objectives: timeline, documents' in item for item in score.strengths)
    
    def test_fallback_score(self):
        """Test fallback when evaluation fails."""
        backend = MockLLMBackend()
        backend.__call__ = lambda x: None  # Force failure
        critic = Critic(backend)
        
        score = critic._fallback_score([])
        
        assert isinstance(score, CriticScore)
        assert score.overall_score >= 0.0


class TestSeedComplaintLibrary:
    """Tests for SeedComplaintLibrary."""
    
    def test_library_creation(self):
        """Test library can be created with default templates."""
        library = SeedComplaintLibrary()
        assert len(library.templates) > 0
    
    def test_get_template(self):
        """Test getting a template by ID."""
        library = SeedComplaintLibrary()
        template = library.get_template('employment_discrimination_1')
        
        assert isinstance(template, ComplaintTemplate)
        assert template.type == 'employment_discrimination'
    
    def test_list_templates(self):
        """Test listing templates."""
        library = SeedComplaintLibrary()
        all_templates = library.list_templates()
        
        assert len(all_templates) > 0
        
        employment_templates = library.list_templates(category='employment')
        assert all(t.category == 'employment' for t in employment_templates)
    
    def test_get_seed_complaints(self):
        """Test getting seed complaints."""
        library = SeedComplaintLibrary()
        seeds = library.get_seed_complaints(count=5)
        
        assert len(seeds) == 5
        assert all('type' in s for s in seeds)
        assert all('key_facts' in s for s in seeds)

    def test_get_hacc_seed_complaints(self, monkeypatch):
        captured = {}

        def fake_build_hacc_evidence_seeds(**kwargs):
            captured['kwargs'] = kwargs
            return [
                {
                    'type': 'housing_discrimination',
                    'key_facts': {'evidence_summary': 'Mocked evidence'},
                    'hacc_evidence': [{'title': 'Mock Policy'}],
                }
            ]

        monkeypatch.setattr(
            seed_complaints_module,
            'build_hacc_evidence_seeds',
            fake_build_hacc_evidence_seeds,
        )

        library = SeedComplaintLibrary()
        seeds = library.get_hacc_seed_complaints(count=1, search_mode='hybrid')

        assert len(seeds) == 1
        assert seeds[0]['key_facts']['evidence_summary'] == 'Mocked evidence'
        assert captured['kwargs']['search_mode'] == 'hybrid'

    def test_get_seed_complaints_can_include_hacc_evidence(self, monkeypatch):
        monkeypatch.setattr(
            SeedComplaintLibrary,
            'get_hacc_seed_complaints',
            lambda self, **kwargs: [
                {
                    'type': 'housing_discrimination',
                    'key_facts': {'evidence_summary': 'Mocked evidence'},
                    'hacc_evidence': [{'title': 'Mock Policy'}],
                }
            ],
        )

        library = SeedComplaintLibrary()
        seeds = library.get_seed_complaints(count=3, include_hacc_evidence=True, hacc_count=1)

        assert len(seeds) == 3
        assert seeds[0]['key_facts']['evidence_summary'] == 'Mocked evidence'

    def test_get_hacc_query_specs_uses_preset(self):
        specs = get_hacc_query_specs(preset='retaliation_focus')

        assert len(specs) > 0
        assert specs == HACC_QUERY_PRESETS['retaliation_focus']

    def test_build_hacc_evidence_seed_prefers_anchor_titles(self):
        payload = {
            'results': [
                {'document_id': 'doc-1', 'title': 'Unrelated Policy', 'source_path': '/tmp/unrelated', 'score': 10, 'snippet': 'low value'},
                {'document_id': 'doc-2', 'title': 'ADMINISTRATIVE PLAN', 'source_path': '/tmp/admin-plan', 'score': 5, 'snippet': 'important grievance text'},
            ]
        }

        seed = build_hacc_evidence_seed(
            payload,
            query='retaliation grievance hearing',
            complaint_type='housing_discrimination',
            category='housing',
            description='Anchored complaint',
            anchor_titles=['ADMINISTRATIVE PLAN'],
        )

        assert seed is not None
        assert seed['hacc_evidence'][0]['title'] == 'ADMINISTRATIVE PLAN'
        assert seed['key_facts']['anchor_titles'] == ['ADMINISTRATIVE PLAN']

    def test_build_hacc_evidence_seed_collects_anchor_passages(self):
        payload = {
            'results': [
                {
                    'document_id': 'doc-1',
                    'title': 'ADMISSIONS AND CONTINUED OCCUPANCY POLICY',
                    'source_path': '/tmp/acop',
                    'score': 10,
                    'snippet': 'A grievance hearing will be conducted by a single impartial person appointed by HACC.',
                },
                {
                    'document_id': 'doc-2',
                    'title': 'ADMINISTRATIVE PLAN',
                    'source_path': '/tmp/admin-plan',
                    'score': 5,
                    'snippet': 'An applicant as a reasonable accommodation for a person with a disability may request review.',
                },
            ]
        }

        seed = build_hacc_evidence_seed(
            payload,
            query='hearing reasonable accommodation',
            complaint_type='housing_discrimination',
            category='housing',
            description='Anchored complaint',
            anchor_terms=['impartial person', 'reasonable accommodation'],
            theory_labels=['reasonable_accommodation', 'disability_discrimination'],
            protected_bases=['disability'],
            authority_hints=['Section 504 of the Rehabilitation Act', 'Americans with Disabilities Act'],
        )

        assert seed is not None
        assert len(seed['key_facts']['anchor_passages']) == 2
        assert 'impartial person' in seed['key_facts']['anchor_passages'][0]['snippet'].lower()
        assert 'grievance_hearing' in seed['key_facts']['anchor_passages'][0]['section_labels']
        assert 'reasonable_accommodation' in seed['key_facts']['anchor_sections']
        assert seed['key_facts']['theory_labels'] == ['reasonable_accommodation', 'disability_discrimination']
        assert seed['key_facts']['protected_bases'] == ['disability']
        assert seed['key_facts']['authority_hints'] == ['Section 504 of the Rehabilitation Act', 'Americans with Disabilities Act']

    def test_build_hacc_evidence_seed_prefers_more_specific_anchor_passages(self):
        payload = {
            'results': [
                {
                    'document_id': 'doc-1',
                    'title': 'ADMINISTRATIVE PLAN',
                    'source_path': '/tmp/admin-plan',
                    'score': 10,
                    'snippet': 'Applicants or tenant families who wish to file a VAWA complaint against HACC may proceed.',
                },
                {
                    'document_id': 'doc-2',
                    'title': 'ADMINISTRATIVE PLAN',
                    'source_path': '/tmp/admin-plan',
                    'score': 8,
                    'snippet': 'HACC will advise the family of the right to appeal HACC’s decision through an informal hearing and provide written notice of the final decision.',
                },
            ]
        }

        seed = build_hacc_evidence_seed(
            payload,
            query='retaliation grievance hearing due process',
            complaint_type='housing_discrimination',
            category='housing',
            description='Administrative-plan retaliation complaint',
            anchor_titles=['ADMINISTRATIVE PLAN'],
            anchor_terms=['right to appeal', 'informal hearing', 'written notice'],
        )

        assert seed is not None
        assert seed['key_facts']['anchor_passages'][0]['snippet'].startswith('HACC will advise the family')
        assert 'appeal_rights' in seed['key_facts']['anchor_passages'][0]['section_labels']
        assert 'grievance_hearing' in seed['key_facts']['anchor_passages'][0]['section_labels']

    def test_build_hacc_evidence_seed_expands_anchor_passage_from_source_file(self, tmp_path):
        source_path = tmp_path / 'admin-plan.txt'
        source_path.write_text(
            'Intro text. HACC will advise the family of the right to appeal HACC decision through an '
            'informal hearing, provide written notice of the final decision, and preserve due process rights. '
            'Additional surrounding context appears here.',
            encoding='utf-8',
        )

        payload = {
            'results': [
                {
                    'document_id': 'doc-1',
                    'title': 'ADMINISTRATIVE PLAN',
                    'source_path': str(source_path),
                    'score': 9,
                    'snippet': 'right to appeal HACC decision',
                },
            ]
        }

        seed = build_hacc_evidence_seed(
            payload,
            query='appeal due process hearing',
            complaint_type='housing_discrimination',
            category='housing',
            description='Expanded passage complaint',
            anchor_titles=['ADMINISTRATIVE PLAN'],
            anchor_terms=['right to appeal', 'informal hearing', 'written notice'],
        )

        assert seed is not None
        passage = seed['key_facts']['anchor_passages'][0]['snippet']
        assert 'informal hearing' in passage
        assert 'written notice of the final decision' in passage
        assert len(passage) > len('right to appeal HACC decision')

    def test_build_hacc_evidence_seed_uses_sidecar_text_file_for_anchor_passage(self, tmp_path):
        source_path = tmp_path / 'admin-plan'
        sidecar_path = tmp_path / 'admin-plan.txt'
        source_path.write_text('binary-ish placeholder', encoding='utf-8')
        sidecar_path.write_text(
            'Expanded text. HACC will advise the family of the right to appeal through an informal hearing and '
            'provide written notice of the final decision. More context follows.',
            encoding='utf-8',
        )

        payload = {
            'results': [
                {
                    'document_id': 'doc-1',
                    'title': 'ADMINISTRATIVE PLAN',
                    'source_path': str(source_path),
                    'score': 9,
                    'snippet': 'right to appeal',
                },
            ]
        }

        seed = build_hacc_evidence_seed(
            payload,
            query='appeal due process hearing',
            complaint_type='housing_discrimination',
            category='housing',
            description='Sidecar passage complaint',
            anchor_titles=['ADMINISTRATIVE PLAN'],
            anchor_terms=['right to appeal', 'informal hearing'],
        )

        assert seed is not None
        passage = seed['key_facts']['anchor_passages'][0]['snippet']
        assert 'informal hearing' in passage
        assert 'written notice of the final decision' in passage

    def test_build_hacc_evidence_seed_expands_supporting_evidence_and_summary(self, tmp_path):
        source_path = tmp_path / 'admin-plan.txt'
        source_path.write_text(
            'Expanded text. HACC will advise the family of the right to appeal through an informal hearing and '
            'provide written notice of the final decision. More context follows here.',
            encoding='utf-8',
        )

        payload = {
            'results': [
                {
                    'document_id': 'doc-1',
                    'title': 'ADMINISTRATIVE PLAN',
                    'source_path': str(source_path),
                    'score': 9,
                    'snippet': 'right to appeal',
                },
            ]
        }

        seed = build_hacc_evidence_seed(
            payload,
            query='appeal due process hearing',
            complaint_type='housing_discrimination',
            category='housing',
            description='Expanded supporting evidence complaint',
            anchor_titles=['ADMINISTRATIVE PLAN'],
            anchor_terms=['right to appeal', 'informal hearing'],
        )

        assert seed is not None
        assert 'informal hearing' in seed['hacc_evidence'][0]['snippet']
        assert 'written notice of the final decision' in seed['hacc_evidence'][0]['snippet']
        assert 'informal hearing' in seed['key_facts']['evidence_summary']
        assert 'written notice of the final decision' in seed['summary']

    def test_build_hacc_evidence_seed_trims_expanded_windows_to_clean_boundaries(self, tmp_path):
        source_path = tmp_path / 'admin-plan.txt'
        source_path.write_text(
            'Intro text before the match. HACC will advise the family of the right to appeal through an informal '
            'hearing and provide written notice of the final decision. Additional context after the match.',
            encoding='utf-8',
        )

        payload = {
            'results': [
                {
                    'document_id': 'doc-1',
                    'title': 'ADMINISTRATIVE PLAN',
                    'source_path': str(source_path),
                    'score': 9,
                    'snippet': 'the right to appeal',
                },
            ]
        }

        seed = build_hacc_evidence_seed(
            payload,
            query='appeal due process hearing',
            complaint_type='housing_discrimination',
            category='housing',
            description='Boundary-trimmed supporting evidence complaint',
            anchor_titles=['ADMINISTRATIVE PLAN'],
            anchor_terms=['right to appeal', 'informal hearing'],
        )

        assert seed is not None
        expanded = seed['hacc_evidence'][0]['snippet']
        assert expanded.startswith('Intro text before the match.')
        assert 'HACC will advise the family' in expanded
        assert 'written notice of the final decision.' in expanded
        assert expanded.endswith('.')

    def test_build_hacc_evidence_seed_removes_policy_footer_boilerplate(self, tmp_path):
        source_path = tmp_path / 'admin-plan.txt'
        source_path.write_text(
            'HACC Policy If HACC elects to deny or terminate assistance for a portable family, HACC will notify '
            'the initial PHA within 10 business days after the informal review or hearing if the denial or '
            'termination is upheld. HACC will furnish the initial PHA with a copy of the review or hearing '
            'decision. © Copyright 2024 Nan McKay & Associates, Inc. Unlimited copies may be made for internal '
            'use. Page 10-23 Adminplan 7/1/2025 Absorbing a Portable Family The receiving PHA may absorb an '
            'incoming portable family.',
            encoding='utf-8',
        )

        payload = {
            'results': [
                {
                    'document_id': 'doc-1',
                    'title': 'ADMINISTRATIVE PLAN',
                    'source_path': str(source_path),
                    'score': 9,
                    'snippet': 'informal review or hearing',
                },
            ]
        }

        seed = build_hacc_evidence_seed(
            payload,
            query='appeal due process hearing',
            complaint_type='housing_discrimination',
            category='housing',
            description='Footer-trimmed supporting evidence complaint',
            anchor_titles=['ADMINISTRATIVE PLAN'],
            anchor_terms=['informal review or hearing', 'copy of the review or hearing decision'],
        )

        assert seed is not None
        expanded = seed['hacc_evidence'][0]['snippet']
        assert 'informal review or hearing' in expanded
        assert 'copy of the review or hearing decision' in expanded
        assert 'Nan McKay' not in expanded
        assert 'Unlimited copies may be made for internal use' not in expanded
        assert 'Page 10-23' not in expanded
        assert 'Absorbing a Portable Family' not in expanded

    def test_best_rule_text_prefers_required_procedural_language(self):
        hit = {
            'matched_rules': [
                {
                    'text': 'General policy statement without the strongest procedural language but still fairly long for comparison.',
                    'rule_type': 'statement',
                    'modality': 'optional',
                },
                {
                    'text': 'The family must receive written notice and may request an informal hearing before termination.',
                    'rule_type': 'obligation',
                    'modality': 'required',
                },
            ],
            'matched_entities': [],
        }

        assert _best_rule_text(hit) == (
            'The family must receive written notice and may request an informal hearing before termination.'
        )

    def test_extract_source_window_skips_toc_excerpt_when_source_contains_policy_text(self, tmp_path):
        source_path = tmp_path / 'policy.txt'
        source_path.write_text(
            'SECTION 16-1 OVERVIEW ........ 16-1 APPEALS ........ 16-4 INFORMAL HEARING ........ 16-8 '
            'Actual policy text. The family may request an informal hearing and receive written notice of the decision. '
            'More details follow.',
            encoding='utf-8',
        )

        excerpt = _extract_source_window(
            source_path=str(source_path),
            anchor_terms=['informal hearing', 'written notice'],
            fallback_snippet='informal hearing',
        )

        assert 'written notice of the decision' in excerpt
        assert '........' not in excerpt

    def test_build_hacc_mediator_evidence_packet_prefers_grounded_seed_packets(self, tmp_path):
        source_path = tmp_path / 'policy.pdf'
        packet = build_hacc_mediator_evidence_packet(
            {
                'type': 'housing_discrimination',
                'key_facts': {
                    'evidence_query': 'grievance hearing',
                    'anchor_sections': ['grievance_hearing'],
                    'mediator_evidence_packets': [
                        {
                            'document_text': 'Grounded extracted policy text about grievance hearings and impartial review.',
                            'document_label': 'ADMINISTRATIVE PLAN',
                            'source_path': str(source_path),
                            'filename': 'policy.txt',
                            'mime_type': 'text/plain',
                            'metadata': {
                                'anchor_sections': ['grievance_hearing'],
                                'upload_strategy': 'extracted_text_fallback',
                                'original_mime_type': 'application/pdf',
                            },
                        }
                    ],
                },
                'hacc_evidence': [
                    {'title': 'ADMINISTRATIVE PLAN', 'source_path': str(source_path), 'snippet': 'Short snippet'},
                ],
            }
        )

        assert len(packet) == 1
        assert packet[0]['document_text'].startswith('Grounded extracted policy text')
        assert packet[0]['metadata']['anchor_sections'] == ['grievance_hearing']
        assert packet[0]['metadata']['upload_strategy'] == 'extracted_text_fallback'


class TestAdversarialSession:
    """Tests for AdversarialSession."""
    
    def test_session_creation(self):
        """Test session can be created."""
        complainant = Complainant(MockLLMBackend())
        mediator = MockMediator()
        critic = Critic(MockLLMBackend())
        
        session = AdversarialSession(
            "test_session",
            complainant,
            mediator,
            critic,
            max_turns=3
        )
        
        assert session.session_id == "test_session"
        assert session.max_turns == 3
    
    def test_session_run(self):
        """Test running a session."""
        complainant_backend = MockLLMBackend("I was discriminated against.")
        complainant = Complainant(complainant_backend)
        
        context = ComplaintContext(
            complaint_type="employment_discrimination",
            key_facts={'employer': 'Test Corp'}
        )
        complainant.set_context(context)
        
        mediator = MockMediator()
        
        critic_backend = MockLLMBackend("""SCORES:
question_quality: 0.8
information_extraction: 0.7
empathy: 0.6
efficiency: 0.75
coverage: 0.7

FEEDBACK: Good session
STRENGTHS:
- Good questions
WEAKNESSES:
- None
SUGGESTIONS:
- None
""")
        critic = Critic(critic_backend)
        
        session = AdversarialSession(
            "test_run",
            complainant,
            mediator,
            critic,
            max_turns=2
        )
        
        seed = {
            'type': 'employment_discrimination',
            'key_facts': {'employer': 'Test Corp'}
        }
        
        result = session.run(seed)
        
        assert isinstance(result, SessionResult)
        assert result.session_id == "test_run"
        assert result.num_questions >= 0
        mediator_questions = [
            item for item in result.conversation_history
            if item.get('role') == 'mediator' and item.get('type') == 'question'
        ]
        assert mediator_questions
        assert all(item.get('content') for item in mediator_questions)
        question_with_metadata = next(
            (item for item in mediator_questions if item.get('question_objective')),
            None,
        )
        if question_with_metadata is not None:
            assert question_with_metadata['question_objective'] == 'clarify_low_confidence_fact'
            assert 'question_reason' in question_with_metadata

    def test_session_result_to_dict_includes_anchor_section_summary(self):
        result = SessionResult(
            session_id="test_session",
            timestamp="2024-01-01",
            seed_complaint={},
            initial_complaint_text="Test",
            conversation_history=[],
            num_questions=1,
            num_turns=1,
            final_state={},
            critic_score=CriticScore(
                overall_score=0.7,
                question_quality=0.7,
                information_extraction=0.7,
                empathy=0.7,
                efficiency=0.7,
                coverage=0.7,
                feedback="ok",
                strengths=[],
                weaknesses=[],
                suggestions=[],
                anchor_sections_expected=['grievance_hearing'],
                anchor_sections_covered=['grievance_hearing'],
                anchor_sections_missing=[],
            ),
            success=True,
        )

        payload = result.to_dict()

        assert payload['anchor_section_summary']['expected'] == ['grievance_hearing']
        assert payload['anchor_section_summary']['covered'] == ['grievance_hearing']

    def test_session_result_to_dict_preserves_workflow_optimization_guidance(self):
        result = SessionResult(
            session_id="test_session",
            timestamp="2024-01-01",
            seed_complaint={},
            initial_complaint_text="Test",
            conversation_history=[],
            num_questions=1,
            num_turns=1,
            final_state={
                "workflow_optimization_guidance": {
                    "phase_scorecards": {
                        "intake_questioning": {"status": "warning", "focus_areas": ["timeline"]},
                    },
                    "cross_phase_findings": ["Intake gaps still affect graph support."],
                }
            },
            critic_score=CriticScore(
                overall_score=0.7,
                question_quality=0.7,
                information_extraction=0.7,
                empathy=0.7,
                efficiency=0.7,
                coverage=0.7,
                feedback="ok",
                strengths=[],
                weaknesses=[],
                suggestions=[],
            ),
            success=True,
        )

        payload = result.to_dict()

        assert payload["final_state"]["workflow_optimization_guidance"]["phase_scorecards"]["intake_questioning"]["status"] == "warning"
        assert payload["final_state"]["workflow_optimization_guidance"]["cross_phase_findings"] == [
            "Intake gaps still affect graph support."
        ]

    def test_fallback_probe_prioritizes_missing_anchor_section(self):
        session = AdversarialSession(
            "test_session",
            Complainant(MockLLMBackend()),
            MockMediator(),
            Critic(MockLLMBackend()),
            max_turns=3,
        )

        probe = session._build_fallback_probe(
            asked_question_counts={},
            asked_intent_counts={},
            need_timeline=False,
            need_harm_remedy=False,
            need_actor_decisionmaker=False,
            need_documentary_evidence=False,
            need_witness=False,
            last_question_key=None,
            last_question_intent_key=None,
            recent_intent_keys=set(),
            missing_anchor_sections={'reasonable_accommodation'},
        )

        assert probe is not None
        assert 'reasonable accommodation' in probe['question'].lower()
        assert probe['question_reason'] == 'Harness fallback probe to cover a missing intake objective.'

    def test_fallback_probe_for_appeal_rights_also_mentions_grievance_hearing(self):
        session = AdversarialSession(
            "test_session",
            Complainant(MockLLMBackend()),
            MockMediator(),
            Critic(MockLLMBackend()),
            max_turns=3,
        )

        probe = session._build_fallback_probe(
            asked_question_counts={},
            asked_intent_counts={},
            need_timeline=False,
            need_harm_remedy=False,
            need_actor_decisionmaker=False,
            need_documentary_evidence=False,
            need_witness=False,
            last_question_key=None,
            last_question_intent_key=None,
            recent_intent_keys=set(),
            missing_anchor_sections={'appeal_rights'},
        )

        assert probe is not None
        assert 'grievance hearing' in probe['question'].lower()
        assert 'due-process rights' in probe['question'].lower()

    def test_fallback_probe_prefers_harm_remedy_before_timeline_after_anchor_coverage(self):
        session = AdversarialSession(
            "test_session",
            Complainant(MockLLMBackend()),
            MockMediator(),
            Critic(MockLLMBackend()),
            max_turns=3,
        )

        probe = session._build_fallback_probe(
            asked_question_counts={},
            asked_intent_counts={},
            need_timeline=True,
            need_harm_remedy=True,
            need_actor_decisionmaker=False,
            need_documentary_evidence=False,
            need_witness=False,
            last_question_key=None,
            last_question_intent_key=None,
            recent_intent_keys=set(),
            missing_anchor_sections=set(),
        )

        assert probe is not None
        assert probe['type'] == 'harm_remedy'
        assert 'what concrete harms did this cause you' in probe['question'].lower()

    def test_select_next_question_uses_question_objective_metadata(self):
        session = AdversarialSession(
            "test_session",
            Complainant(MockLLMBackend()),
            MockMediator(),
            Critic(MockLLMBackend()),
            max_turns=3,
        )

        questions = [
            {
                'question': 'Please walk through the events in order from the beginning.',
                'type': 'clarification',
                'question_objective': 'establish_chronology',
                'context': {},
            },
            {
                'question': 'Can you clarify one point about your employer?',
                'type': 'clarification',
                'context': {},
            },
        ]

        selected = session._select_next_question(
            questions=questions,
            asked_question_counts={},
            asked_intent_counts={},
            need_timeline=True,
            need_harm_remedy=False,
            need_actor_decisionmaker=False,
            need_documentary_evidence=False,
            need_witness=False,
            last_question_key=None,
            last_question_intent_key=None,
            recent_intent_keys=set(),
            missing_anchor_sections=set(),
        )

        assert selected is not None
        assert selected['question_objective'] == 'establish_chronology'

    def test_select_next_question_prioritizes_contradiction_resolution_metadata(self):
        session = AdversarialSession(
            "test_session",
            Complainant(MockLLMBackend()),
            MockMediator(),
            Critic(MockLLMBackend()),
            max_turns=3,
        )

        questions = [
            {
                'question': 'When did this happen?',
                'type': 'timeline',
                'question_objective': 'establish_chronology',
                'context': {},
            },
            {
                'question': 'I have conflicting information about the sequence of events. Which version is correct?',
                'type': 'contradiction',
                'question_objective': 'resolve_factual_contradiction',
                'context': {},
            },
        ]

        selected = session._select_next_question(
            questions=questions,
            asked_question_counts={},
            asked_intent_counts={},
            need_timeline=True,
            need_harm_remedy=False,
            need_actor_decisionmaker=False,
            need_documentary_evidence=False,
            need_witness=False,
            last_question_key=None,
            last_question_intent_key=None,
            recent_intent_keys=set(),
            missing_anchor_sections=set(),
        )

        assert selected is not None
        assert selected['question_objective'] == 'resolve_factual_contradiction'

    def test_select_next_question_prioritizes_adverse_action_details_when_actor_gap_open(self):
        session = AdversarialSession(
            "test_session",
            Complainant(MockLLMBackend()),
            MockMediator(),
            Critic(MockLLMBackend()),
            max_turns=3,
        )

        questions = [
            {
                'question': 'Who made the decision?',
                'type': 'responsible_party',
                'question_objective': 'actors',
                'context': {},
            },
            {
                'question': 'What exact reason was given for the housing decision, who gave it, and what date was it communicated?',
                'type': 'adverse_action_details',
                'question_objective': 'adverse_action_details',
                'context': {},
            },
        ]

        selected = session._select_next_question(
            questions=questions,
            asked_question_counts={},
            asked_intent_counts={},
            need_timeline=False,
            need_harm_remedy=False,
            need_actor_decisionmaker=True,
            need_documentary_evidence=False,
            need_witness=False,
            last_question_key=None,
            last_question_intent_key=None,
            recent_intent_keys=set(),
            missing_anchor_sections=set(),
        )

        assert selected is not None
        assert selected['question_objective'] == 'adverse_action_details'

    def test_question_intent_key_prefers_question_objective(self):
        question = {
            'question': 'Who handled the issue?',
            'type': 'responsible_party',
            'question_objective': 'identify_responsible_party',
            'context': {'claim_id': 'claim-1'},
        }

        intent_key = AdversarialSession._question_intent_key(question['question'], question)

        assert intent_key == 'identify_responsible_party:responsible_party:claim-1'

    def test_covered_anchor_sections_from_questions(self):
        covered = AdversarialSession._covered_anchor_sections_from_questions(
            ['did you request a reasonable accommodation', 'were you given any appeal rights'],
            {'reasonable_accommodation', 'appeal_rights', 'grievance_hearing'},
        )

        assert 'reasonable_accommodation' in covered
        assert 'appeal_rights' in covered
        assert 'grievance_hearing' not in covered

    def test_covered_anchor_sections_from_combined_due_process_question(self):
        covered = AdversarialSession._covered_anchor_sections_from_questions(
            ['were you told you could request a grievance hearing, appeal, review, or other due-process rights'],
            {'appeal_rights', 'grievance_hearing'},
        )

        assert 'appeal_rights' in covered
        assert 'grievance_hearing' in covered


class TestAdversarialHarness:
    """Tests for AdversarialHarness."""
    
    def test_harness_creation(self):
        """Test harness can be created."""
        complainant_backend = MockLLMBackend()
        critic_backend = MockLLMBackend()
        
        def mediator_factory():
            return MockMediator()
        
        harness = AdversarialHarness(
            complainant_backend,
            critic_backend,
            mediator_factory,
            max_parallel=2
        )
        
        assert harness.max_parallel == 2
        assert hasattr(harness, 'seed_library')
    
    def test_get_statistics_empty(self):
        """Test statistics with no results."""
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator
        )
        
        stats = harness.get_statistics()
        assert stats['total_sessions'] == 0

    def test_run_batch_forwards_hacc_seed_options(self, monkeypatch):
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator,
            max_parallel=1
        )

        captured = {}

        def fake_get_seed_complaints(**kwargs):
            captured.update(kwargs)
            return [{
                'type': 'housing_discrimination',
                'key_facts': {'evidence_summary': 'Mocked HACC evidence'},
                'hacc_evidence': [{'title': 'Mock Policy'}],
            }]

        monkeypatch.setattr(harness.seed_library, 'get_seed_complaints', fake_get_seed_complaints)
        monkeypatch.setattr(
            harness,
            '_run_single_session',
            lambda spec: SessionResult(
                session_id=spec['session_id'],
                timestamp="2024-01-01T00:00:00+00:00",
                seed_complaint=spec['seed'],
                initial_complaint_text="Complaint",
                conversation_history=[],
                num_questions=0,
                num_turns=0,
                final_state={},
                critic_score=CriticScore(
                    overall_score=0.7,
                    question_quality=0.7,
                    information_extraction=0.7,
                    empathy=0.7,
                    efficiency=0.7,
                    coverage=0.7,
                    feedback="ok",
                    strengths=[],
                    weaknesses=[],
                    suggestions=[],
                ),
                success=True,
            ),
        )

        results = harness.run_batch(
            num_sessions=1,
            include_hacc_evidence=True,
            hacc_count=1,
            hacc_preset='retaliation_focus',
            hacc_query_specs=[{'query': 'retaliation policy', 'type': 'housing_discrimination'}],
            use_hacc_vector_search=True,
            hacc_search_mode='hybrid',
        )

        assert len(results) == 1
        assert captured['include_hacc_evidence'] is True
        assert captured['hacc_count'] == 1
        assert captured['hacc_preset'] == 'retaliation_focus'
        assert captured['hacc_query_specs'][0]['query'] == 'retaliation policy'
        assert captured['use_hacc_vector_search'] is True
        assert captured['hacc_search_mode'] == 'hybrid'

    def test_get_statistics_includes_anchor_section_coverage(self):
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator,
            max_parallel=1
        )
        harness.results = [
            SessionResult(
                session_id='session_1',
                timestamp='2024-01-01',
                seed_complaint={
                    '_meta': {
                        'include_hacc_evidence': True,
                        'hacc_preset': 'retaliation_focus',
                        'use_hacc_vector_search': True,
                    }
                },
                initial_complaint_text='Test',
                conversation_history=[],
                num_questions=2,
                num_turns=1,
                final_state={},
                critic_score=CriticScore(
                    overall_score=0.7,
                    question_quality=0.7,
                    information_extraction=0.7,
                    empathy=0.7,
                    efficiency=0.7,
                    coverage=0.7,
                    feedback='ok',
                    strengths=[],
                    weaknesses=[],
                    suggestions=[],
                    anchor_sections_expected=['grievance_hearing', 'reasonable_accommodation'],
                    anchor_sections_covered=['reasonable_accommodation'],
                    anchor_sections_missing=['grievance_hearing'],
                ),
                success=True,
                duration_seconds=1.0,
            )
        ]

        stats = harness.get_statistics()

        assert stats['anchor_sections']['expected_counts']['grievance_hearing'] == 1
        assert stats['anchor_sections']['covered_counts']['reasonable_accommodation'] == 1
        assert stats['anchor_sections']['missing_counts']['grievance_hearing'] == 1

    def test_get_statistics_includes_intake_priority_coverage(self):
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator,
            max_parallel=1
        )
        harness.results = [
            SessionResult(
                session_id='session_1',
                timestamp='2024-01-01',
                seed_complaint={'_meta': {'include_hacc_evidence': True}},
                initial_complaint_text='Test',
                conversation_history=[],
                num_questions=2,
                num_turns=1,
                final_state={
                    'adversarial_intake_priority_summary': {
                        'expected_objectives': ['anchor_adverse_action', 'timeline', 'documents'],
                        'covered_objectives': ['anchor_adverse_action', 'timeline'],
                        'uncovered_objectives': ['documents'],
                    }
                },
                critic_score=CriticScore(
                    overall_score=0.7,
                    question_quality=0.7,
                    information_extraction=0.7,
                    empathy=0.7,
                    efficiency=0.7,
                    coverage=0.7,
                    feedback='ok',
                    strengths=[],
                    weaknesses=[],
                    suggestions=[],
                    anchor_sections_expected=['grievance_hearing'],
                    anchor_sections_covered=['grievance_hearing'],
                    anchor_sections_missing=[],
                ),
                success=True,
                duration_seconds=1.0,
            )
        ]

        stats = harness.get_statistics()

        assert stats['intake_priority']['expected_counts']['anchor_adverse_action'] == 1
        assert stats['intake_priority']['covered_counts']['timeline'] == 1
        assert stats['intake_priority']['uncovered_counts']['documents'] == 1
        assert stats['intake_priority']['coverage_by_objective']['documents']['coverage_rate'] == 0.0
        assert stats['intake_priority']['sessions_with_full_coverage'] == 0
        assert stats['intake_priority']['sessions_with_partial_coverage'] == 1

    def test_save_anchor_section_report_csv(self, tmp_path):
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator,
            max_parallel=1
        )
        harness.results = [
            SessionResult(
                session_id='session_1',
                timestamp='2024-01-01',
                seed_complaint={
                    '_meta': {
                        'include_hacc_evidence': True,
                        'hacc_preset': 'retaliation_focus',
                        'use_hacc_vector_search': True,
                    }
                },
                initial_complaint_text='Test',
                conversation_history=[],
                num_questions=2,
                num_turns=1,
                final_state={},
                critic_score=CriticScore(
                    overall_score=0.7,
                    question_quality=0.7,
                    information_extraction=0.7,
                    empathy=0.7,
                    efficiency=0.7,
                    coverage=0.7,
                    feedback='ok',
                    strengths=[],
                    weaknesses=[],
                    suggestions=[],
                    anchor_sections_expected=['grievance_hearing'],
                    anchor_sections_covered=[],
                    anchor_sections_missing=['grievance_hearing'],
                ),
                success=True,
                duration_seconds=1.0,
            )
        ]

        output = tmp_path / 'anchor_sections.csv'
        harness.save_anchor_section_report(str(output), format='csv')
        text = output.read_text(encoding='utf-8')

        assert 'section,expected,covered,missing,coverage_rate' in text
        assert 'grievance_hearing,1,0,1,0.0' in text

    def test_save_anchor_section_report_markdown(self, tmp_path):
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator,
            max_parallel=1
        )
        harness.results = [
            SessionResult(
                session_id='session_1',
                timestamp='2024-01-01',
                seed_complaint={
                    '_meta': {
                        'include_hacc_evidence': True,
                        'hacc_preset': 'retaliation_focus',
                        'use_hacc_vector_search': True,
                    }
                },
                initial_complaint_text='Test',
                conversation_history=[],
                num_questions=2,
                num_turns=1,
                final_state={},
                critic_score=CriticScore(
                    overall_score=0.7,
                    question_quality=0.7,
                    information_extraction=0.7,
                    empathy=0.7,
                    efficiency=0.7,
                    coverage=0.7,
                    feedback='ok',
                    strengths=[],
                    weaknesses=[],
                    suggestions=[],
                    anchor_sections_expected=['reasonable_accommodation'],
                    anchor_sections_covered=['reasonable_accommodation'],
                    anchor_sections_missing=[],
                ),
                success=True,
                duration_seconds=1.0,
            )
        ]

        output = tmp_path / 'anchor_sections.md'
        harness.save_anchor_section_report(str(output), format='markdown')
        text = output.read_text(encoding='utf-8')

        assert '# Anchor Section Coverage' in text
        assert '| reasonable_accommodation | 1 | 1 | 0 | 1.00 |' in text
        assert harness.results[0].seed_complaint['_meta']['include_hacc_evidence'] is True
        assert harness.results[0].seed_complaint['_meta']['hacc_preset'] == 'retaliation_focus'
        assert harness.results[0].seed_complaint['_meta']['use_hacc_vector_search'] is True

    def test_run_batch_records_anchor_metadata_for_optimizer(self, monkeypatch):
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator,
            max_parallel=1
        )

        monkeypatch.setattr(
            harness.seed_library,
            'get_seed_complaints',
            lambda **kwargs: [{
                'type': 'housing_discrimination',
                'source': 'hacc_research_engine',
                'key_facts': {
                    'evidence_summary': 'Anchored evidence',
                    'anchor_sections': ['grievance_hearing', 'appeal_rights'],
                    'search_summary': {
                        'requested_search_mode': 'hybrid',
                        'effective_search_mode': 'lexical_only',
                        'fallback_note': 'Requested hybrid search, but vector support is unavailable; using lexical results instead.',
                    },
                },
                'hacc_evidence': [{'title': 'Mock Policy'}],
            }],
        )
        monkeypatch.setattr(
            harness,
            '_run_single_session',
            lambda spec: SessionResult(
                session_id=spec['session_id'],
                timestamp="2024-01-01T00:00:00+00:00",
                seed_complaint=spec['seed'],
                initial_complaint_text="Complaint",
                conversation_history=[],
                num_questions=0,
                num_turns=0,
                final_state={},
                critic_score=CriticScore(
                    overall_score=0.7,
                    question_quality=0.7,
                    information_extraction=0.7,
                    empathy=0.7,
                    efficiency=0.7,
                    coverage=0.7,
                    feedback="ok",
                    strengths=[],
                    weaknesses=[],
                    suggestions=[],
                ),
                success=True,
            ),
        )

        results = harness.run_batch(
            num_sessions=1,
            include_hacc_evidence=True,
            hacc_preset='core_hacc_policies',
        )

        assert results[0].seed_complaint['_meta']['seed_source'] == 'hacc_research_engine'
        assert results[0].seed_complaint['_meta']['anchor_sections'] == ['grievance_hearing', 'appeal_rights']
        assert results[0].seed_complaint['_meta']['hacc_search_mode'] == 'hybrid'
        assert results[0].seed_complaint['_meta']['hacc_effective_search_mode'] == 'lexical_only'
        assert results[0].seed_complaint['_meta']['hacc_search_fallback_note'] == (
            'Requested hybrid search, but vector support is unavailable; using lexical results instead.'
        )

    def test_run_batch_enriches_later_seeds_with_optimizer_feedback(self, monkeypatch):
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator,
            max_parallel=1,
        )

        seen_specs = []
        seeds = [
            {
                'type': 'housing_discrimination',
                'summary': 'HACC retaliation chronology remains incomplete.',
                'key_facts': {},
            },
            {
                'type': 'employment_discrimination',
                'summary': 'Second seed should inherit optimizer feedback.',
                'key_facts': {},
            },
        ]

        def fake_run_single_session(spec):
            seen_specs.append(json.loads(json.dumps(spec)))
            final_state = {}
            overall_score = 0.8
            if len(seen_specs) == 1:
                overall_score = 0.4
                final_state = {
                    'adversarial_intake_priority_summary': {
                        'expected_objectives': ['timeline', 'documents'],
                        'covered_objectives': ['timeline'],
                        'uncovered_objectives': ['documents'],
                    },
                    'alignment_evidence_tasks': [
                        {
                            'action': 'fill_temporal_chronology_gap',
                            'claim_type': 'retaliation',
                            'claim_element_id': 'causation',
                            'fallback_lanes': ['authority', 'testimony'],
                        }
                    ],
                    'evidence_workflow_action_queue': [
                        {
                            'phase_name': 'graph_analysis',
                            'claim_type': 'retaliation',
                            'claim_element_id': 'causation',
                            'focus_areas': ['timeline', 'chronology'],
                            'action': 'Resolve chronology support for causation.',
                        }
                    ],
                    'intake_legal_targeting_summary': {
                        'claims': {
                            'retaliation': {
                                'missing_requirement_element_ids': ['protected_activity'],
                            }
                        }
                    },
                }
            return SessionResult(
                session_id=spec['session_id'],
                timestamp='2024-01-01T00:00:00+00:00',
                seed_complaint=spec['seed'],
                initial_complaint_text='Complaint',
                conversation_history=[],
                num_questions=0,
                num_turns=0,
                final_state=final_state,
                critic_score=CriticScore(
                    overall_score=overall_score,
                    question_quality=overall_score,
                    information_extraction=overall_score,
                    empathy=overall_score,
                    efficiency=overall_score,
                    coverage=overall_score,
                    feedback='ok',
                    strengths=[],
                    weaknesses=[],
                    suggestions=[],
                ),
                success=True,
            )

        monkeypatch.setattr(harness, '_run_single_session', fake_run_single_session)

        results = harness.run_batch(
            num_sessions=2,
            seed_complaints=seeds,
            max_turns_per_session=1,
        )

        assert len(results) == 2
        assert 'actor_critic_optimizer' not in seeds[1]
        second_seed = seen_specs[1]['seed']
        assert second_seed['actor_critic_optimizer']['num_sessions_analyzed'] == 1
        assert second_seed['actor_critic_optimizer']['unresolved_intake_objectives'] == ['documents']
        assert second_seed['actor_critic_optimizer']['graph_element_targeting_summary']['claim_element_counts'] == {
            'causation': 2,
            'protected_activity': 1,
        }
        assert 'housing_discrimination' in second_seed['actor_critic_optimizer']['weak_complaint_types']
        assert second_seed['optimization_guidance']['latest_batch_priorities']
        assert second_seed['key_facts']['workflow_phase_priorities'] == second_seed['optimization_guidance']['latest_batch_priorities']

    def test_preload_hacc_seed_evidence_submits_documents_to_mediator(self, tmp_path):
        source_path = tmp_path / 'policy.pdf'

        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator,
            max_parallel=1,
        )

        captured = []

        class MediatorWithSave:
            def save_claim_support_document(self, **kwargs):
                captured.append(kwargs)
                return {'cid': 'cid-1', 'record_id': 7, 'metadata': {'source_path': kwargs.get('source_url', '')}}

        seed = {
            'type': 'housing_discrimination',
            'summary': 'Grounded HACC complaint seed',
            'key_facts': {
                'evidence_query': 'grievance hearing due process',
                'anchor_sections': ['grievance_hearing'],
                'mediator_evidence_packets': [
                    {
                        'document_text': 'Grounded extracted due process evidence text.',
                        'document_label': 'ADMINISTRATIVE PLAN',
                        'source_path': str(source_path),
                        'filename': 'policy.txt',
                        'mime_type': 'text/plain',
                        'metadata': {
                            'upload_strategy': 'extracted_text_fallback',
                            'original_mime_type': 'application/pdf',
                        },
                    }
                ],
            },
            'hacc_evidence': [{'title': 'ADMINISTRATIVE PLAN', 'source_path': str(source_path)}],
        }

        stored = harness._preload_hacc_seed_evidence(MediatorWithSave(), seed, session_id='session_123')

        assert len(stored) == 1
        assert len(captured) == 1
        assert captured[0]['user_id'] == 'session_123'
        assert captured[0]['claim_type'] == 'housing_discrimination'
        assert captured[0]['document_text'] == 'Grounded extracted due process evidence text.'
        assert captured[0]['mime_type'] == 'text/plain'
        assert captured[0]['metadata']['upload_strategy'] == 'extracted_text_fallback'

    def test_run_batch_writes_progress_callback_and_session_progress(self, tmp_path):
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator,
            max_parallel=1,
            session_state_dir=str(tmp_path / "sessions"),
        )

        progress_events = []
        seeds = [
            {
                'type': 'housing_discrimination',
                'summary': 'Grounded complaint seed',
                'key_facts': {},
            }
        ]

        results = harness.run_batch(
            num_sessions=1,
            seed_complaints=seeds,
            max_turns_per_session=1,
            progress_callback=lambda payload: progress_events.append(json.loads(json.dumps(payload))),
        )

        assert len(results) == 1
        assert progress_events
        assert progress_events[0]['status'] == 'running'
        assert progress_events[-1]['status'] == 'completed'
        session_id = results[0].session_id
        progress_path = tmp_path / "sessions" / session_id / "progress.json"
        assert progress_path.exists()
        session_progress = json.loads(progress_path.read_text(encoding='utf-8'))
        assert session_progress['session_id'] == session_id
        assert session_progress['stage'] == 'completed'
        assert session_progress['status'] == 'completed'

    def test_write_session_progress_sanitizes_set_metadata(self, tmp_path):
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator,
            max_parallel=1,
            session_state_dir=str(tmp_path / "sessions"),
        )

        harness._write_session_progress(
            "session_set_progress",
            stage="awaiting_complainant_answer",
            status="running",
            metadata={"weak_evidence_modalities": {"policy_document", "file_evidence"}},
        )

        progress_path = tmp_path / "sessions" / "session_set_progress" / "progress.json"
        payload = json.loads(progress_path.read_text(encoding="utf-8"))
        assert payload["metadata"]["weak_evidence_modalities"] == ["file_evidence", "policy_document"]

    def test_ensure_session_db_paths_rebinds_shared_storage_hooks(self):
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            MockMediator,
            max_parallel=1,
        )

        class Hook:
            def __init__(self, mediator, db_path=None):
                self.mediator = mediator
                self.db_path = db_path

        class MediatorWithSharedHooks:
            def __init__(self):
                self.evidence_state = Hook(self, db_path='statefiles/evidence.duckdb')
                self.legal_authority_storage = Hook(self, db_path='statefiles/legal_authorities.duckdb')
                self.claim_support = Hook(self, db_path='statefiles/claim_support.duckdb')

        mediator = MediatorWithSharedHooks()
        rebound = harness._ensure_session_db_paths(
            mediator,
            evidence_db_path='/tmp/session/evidence.duckdb',
            legal_authority_db_path='/tmp/session/legal_authorities.duckdb',
            claim_support_db_path='/tmp/session/claim_support.duckdb',
        )

        assert rebound.evidence_state.db_path == '/tmp/session/evidence.duckdb'
        assert rebound.legal_authority_storage.db_path == '/tmp/session/legal_authorities.duckdb'
        assert rebound.claim_support.db_path == '/tmp/session/claim_support.duckdb'


class TestOptimizer:
    """Tests for Optimizer."""
    
    def test_optimizer_creation(self):
        """Test optimizer can be created."""
        optimizer = Optimizer()
        assert len(optimizer.history) == 0
    
    def test_analyze_empty_results(self):
        """Test analyzing empty results."""
        optimizer = Optimizer()
        report = optimizer.analyze([])
        
        assert isinstance(report, OptimizationReport)
        assert report.num_sessions_analyzed == 0
    
    def test_analyze_with_results(self):
        """Test analyzing real results."""
        optimizer = Optimizer()
        
        # Create mock results
        mock_results = []
        for i in range(3):
            score = CriticScore(
                overall_score=0.7 + i * 0.05,
                question_quality=0.7,
                information_extraction=0.6,
                empathy=0.8,
                efficiency=0.7,
                coverage=0.65,
                feedback="Test feedback",
                strengths=["Good questions"],
                weaknesses=["Could improve efficiency"],
                suggestions=["Add more follow-ups"]
            )
            
            result = SessionResult(
                session_id=f"session_{i}",
                timestamp="2024-01-01",
                seed_complaint={},
                initial_complaint_text="Test",
                conversation_history=[],
                num_questions=5,
                num_turns=3,
                final_state={},
                critic_score=score,
                success=True
            )
            mock_results.append(result)
        
        report = optimizer.analyze(mock_results)
        
        assert isinstance(report, OptimizationReport)
        assert report.num_sessions_analyzed == 3
        assert 0.0 <= report.average_score <= 1.0
        assert len(report.recommendations) > 0
    
    def test_analyze_reports_hacc_preset_and_anchor_performance(self):
        optimizer = Optimizer()

        results = []
        scenarios = [
            ("core_hacc_policies", ["grievance_hearing"], 0.82),
            ("core_hacc_policies", ["grievance_hearing", "appeal_rights"], 0.78),
            ("retaliation_focus", ["appeal_rights"], 0.61),
        ]
        for idx, (preset, anchor_sections, overall_score) in enumerate(scenarios):
            results.append(
                SessionResult(
                    session_id=f"session_meta_{idx}",
                    timestamp="2024-01-01",
                    seed_complaint={
                        "_meta": {
                            "hacc_preset": preset,
                            "include_hacc_evidence": True,
                            "seed_source": "hacc_research_engine",
                            "anchor_sections": anchor_sections,
                        },
                        "key_facts": {
                            "anchor_sections": anchor_sections,
                        },
                    },
                    initial_complaint_text="Test",
                    conversation_history=[],
                    num_questions=4,
                    num_turns=3,
                    final_state={},
                    critic_score=CriticScore(
                        overall_score=overall_score,
                        question_quality=overall_score,
                        information_extraction=overall_score,
                        empathy=overall_score,
                        efficiency=overall_score,
                        coverage=overall_score,
                        feedback="Test feedback",
                        strengths=[],
                        weaknesses=[],
                        suggestions=[],
                    ),
                    success=True,
                )
            )

        report = optimizer.analyze(results)

        assert report.recommended_hacc_preset == "core_hacc_policies"
        assert report.hacc_preset_performance["core_hacc_policies"]["count"] == 2
        assert report.anchor_section_performance["grievance_hearing"]["count"] == 2
        assert any("Best HACC preset so far is 'core_hacc_policies'" in rec for rec in report.recommendations)

    def test_optimizer_recommends_missing_anchor_sections(self):
        optimizer = Optimizer()
        score = CriticScore(
            overall_score=0.6,
            question_quality=0.6,
            information_extraction=0.6,
            empathy=0.6,
            efficiency=0.6,
            coverage=0.5,
            feedback="Test",
            strengths=[],
            weaknesses=[],
            suggestions=[],
            anchor_sections_expected=['grievance_hearing', 'reasonable_accommodation'],
            anchor_sections_covered=['reasonable_accommodation'],
            anchor_sections_missing=['grievance_hearing'],
        )
        result = SessionResult(
            session_id="session_anchor",
            timestamp="2024-01-01",
            seed_complaint={},
            initial_complaint_text="Test",
            conversation_history=[],
            num_questions=3,
            num_turns=2,
            final_state={},
            critic_score=score,
            success=True,
        )

        report = optimizer.analyze([result])

        assert any('grievance_hearing' in rec for rec in report.recommendations)

    def test_optimizer_reports_intake_priority_performance(self):
        optimizer = Optimizer()

        results = [
            SessionResult(
                session_id="session_intake_1",
                timestamp="2024-01-01",
                seed_complaint={},
                initial_complaint_text="Test",
                conversation_history=[],
                num_questions=3,
                num_turns=2,
                final_state={
                    'adversarial_intake_priority_summary': {
                        'expected_objectives': ['anchor_adverse_action', 'timeline', 'documents'],
                        'covered_objectives': ['anchor_adverse_action', 'timeline'],
                        'uncovered_objectives': ['documents'],
                    }
                },
                critic_score=CriticScore(
                    overall_score=0.72,
                    question_quality=0.72,
                    information_extraction=0.72,
                    empathy=0.72,
                    efficiency=0.72,
                    coverage=0.72,
                    feedback="Test",
                    strengths=[],
                    weaknesses=[],
                    suggestions=[],
                ),
                success=True,
            ),
            SessionResult(
                session_id="session_intake_2",
                timestamp="2024-01-01",
                seed_complaint={},
                initial_complaint_text="Test",
                conversation_history=[],
                num_questions=3,
                num_turns=2,
                final_state={
                    'adversarial_intake_priority_summary': {
                        'expected_objectives': ['anchor_adverse_action', 'timeline'],
                        'covered_objectives': ['anchor_adverse_action'],
                        'uncovered_objectives': ['timeline'],
                    }
                },
                critic_score=CriticScore(
                    overall_score=0.68,
                    question_quality=0.68,
                    information_extraction=0.68,
                    empathy=0.68,
                    efficiency=0.68,
                    coverage=0.68,
                    feedback="Test",
                    strengths=[],
                    weaknesses=[],
                    suggestions=[],
                ),
                success=True,
            ),
        ]

        report = optimizer.analyze(results)

        assert report.intake_priority_performance["expected_counts"]["timeline"] == 2
        assert report.intake_priority_performance["covered_counts"]["anchor_adverse_action"] == 2
        assert report.intake_priority_performance["uncovered_counts"]["documents"] == 1
        assert report.intake_priority_performance["coverage_by_objective"]["timeline"]["coverage_rate"] == 0.5
        assert report.intake_priority_performance["sessions_with_full_coverage"] == 0
        assert report.intake_priority_performance["sessions_with_partial_coverage"] == 2
        assert report.coverage_remediation["intake_priorities"]["uncovered_objectives"] == ["documents", "timeline"]
        assert report.coverage_remediation["intake_priorities"]["recommended_actions"][0]["objective"] == "documents"
        assert "written records earlier" in report.coverage_remediation["intake_priorities"]["recommended_actions"][0]["recommended_action"]
        assert any("documents (0/1)" in rec for rec in report.recommendations)
        assert any(improvement.startswith("Improve intake priority coverage:") for improvement in report.priority_improvements)

    def test_optimizer_distinguishes_anchor_and_intake_remediation(self):
        optimizer = Optimizer()
        result = SessionResult(
            session_id="session_remediation",
            timestamp="2024-01-01",
            seed_complaint={},
            initial_complaint_text="Test",
            conversation_history=[],
            num_questions=3,
            num_turns=2,
            final_state={
                'adversarial_intake_priority_summary': {
                    'expected_objectives': ['timeline', 'anchor_appeal_rights'],
                    'covered_objectives': ['timeline'],
                    'uncovered_objectives': ['anchor_appeal_rights'],
                }
            },
            critic_score=CriticScore(
                overall_score=0.58,
                question_quality=0.58,
                information_extraction=0.58,
                empathy=0.58,
                efficiency=0.58,
                coverage=0.50,
                feedback="Test",
                strengths=[],
                weaknesses=[],
                suggestions=[],
                anchor_sections_expected=['appeal_rights'],
                anchor_sections_covered=[],
                anchor_sections_missing=['appeal_rights'],
            ),
            success=True,
        )

        report = optimizer.analyze([result])

        assert report.coverage_remediation["anchor_sections"]["missing_sections"] == ["appeal_rights"]
        assert report.coverage_remediation["anchor_sections"]["recommended_actions"][0]["section"] == "appeal_rights"
        assert report.coverage_remediation["intake_priorities"]["uncovered_objectives"] == ["anchor_appeal_rights"]
        assert report.coverage_remediation["intake_priorities"]["recommended_actions"][0]["objective"] == "anchor_appeal_rights"
        assert any(improvement.startswith("Close anchor-section coverage gaps:") for improvement in report.priority_improvements)

    def test_optimizer_phase_scorecards_include_document_exhibit_backed_ratio(self):
        optimizer = Optimizer()
        result = SessionResult(
            session_id="session_document_exhibits",
            timestamp="2024-01-01",
            seed_complaint={},
            initial_complaint_text="Test",
            conversation_history=[],
            num_questions=3,
            num_turns=2,
            final_state={
                "workflow_phase_plan": {
                    "phases": {
                        "intake_questioning": {"status": "ready"},
                        "graph_analysis": {"status": "ready"},
                        "document_generation": {"status": "ready"},
                    }
                },
                "document_provenance_summary": {
                    "summary_fact_count": 2,
                    "summary_fact_backed_count": 2,
                    "summary_fact_exhibit_backed_count": 2,
                    "factual_allegation_paragraph_count": 2,
                    "factual_allegation_fact_backed_count": 2,
                    "factual_allegation_exhibit_backed_count": 2,
                    "claim_supporting_fact_count": 2,
                    "claim_supporting_fact_backed_count": 2,
                    "claim_supporting_fact_exhibit_backed_count": 2,
                    "low_grounding_flag": False,
                },
            },
            critic_score=CriticScore(
                overall_score=0.8,
                question_quality=0.8,
                information_extraction=0.8,
                empathy=0.8,
                efficiency=0.8,
                coverage=0.8,
                feedback="Test",
                strengths=[],
                weaknesses=[],
                suggestions=[],
            ),
            success=True,
        )

        report = optimizer.analyze([result])

        assert report.document_provenance_summary["avg_exhibit_backed_ratio"] == pytest.approx(1.0)
        assert report.phase_scorecards["document_generation"]["document_exhibit_backed_ratio"] == pytest.approx(1.0)

    def test_optimizer_recommends_stronger_exhibit_grounding_when_ratio_is_low(self):
        optimizer = Optimizer()
        result = SessionResult(
            session_id="session_document_exhibit_gap",
            timestamp="2024-01-01",
            seed_complaint={},
            initial_complaint_text="Test",
            conversation_history=[],
            num_questions=3,
            num_turns=2,
            final_state={
                "workflow_phase_plan": {
                    "phases": {
                        "intake_questioning": {"status": "ready"},
                        "graph_analysis": {"status": "ready"},
                        "document_generation": {"status": "warning"},
                    }
                },
                "document_provenance_summary": {
                    "summary_fact_count": 2,
                    "summary_fact_backed_count": 2,
                    "summary_fact_exhibit_backed_count": 0,
                    "factual_allegation_paragraph_count": 2,
                    "factual_allegation_fact_backed_count": 2,
                    "factual_allegation_exhibit_backed_count": 0,
                    "claim_supporting_fact_count": 2,
                    "claim_supporting_fact_backed_count": 2,
                    "claim_supporting_fact_exhibit_backed_count": 0,
                    "low_grounding_flag": False,
                },
            },
            critic_score=CriticScore(
                overall_score=0.72,
                question_quality=0.72,
                information_extraction=0.72,
                empathy=0.72,
                efficiency=0.72,
                coverage=0.72,
                feedback="Test",
                strengths=[],
                weaknesses=[],
                suggestions=[],
            ),
            success=True,
        )

        report = optimizer.analyze([result])

        assert any("exhibit-backed" in rec for rec in report.recommendations)
        assert any(item.startswith("Increase exhibit-backed complaint grounding") for item in report.priority_improvements)
        assert "exhibit_grounding" in report.phase_scorecards["document_generation"]["focus_areas"]

    def test_optimizer_phase_scorecards_include_intake_exhibit_ready_ratio(self):
        optimizer = Optimizer()
        result = SessionResult(
            session_id="session_intake_exhibit_ready",
            timestamp="2024-01-01",
            seed_complaint={},
            initial_complaint_text="Test",
            conversation_history=[],
            num_questions=3,
            num_turns=2,
            final_state={
                "workflow_phase_plan": {
                    "phases": {
                        "intake_questioning": {"status": "warning"},
                        "graph_analysis": {"status": "ready"},
                        "document_generation": {"status": "ready"},
                    }
                },
                "intake_question_structure_summary": {
                    "question_count": 3,
                    "documentary_question_count": 2,
                    "exhibit_ready_question_count": 2,
                    "temporal_exhibit_ready_question_count": 1,
                    "documentary_exhibit_ready_question_count": 2,
                    "documentary_exhibit_ready_ratio": 1.0,
                    "needs_exhibit_grounding": True,
                },
            },
            critic_score=CriticScore(
                overall_score=0.8,
                question_quality=0.8,
                information_extraction=0.8,
                empathy=0.8,
                efficiency=0.8,
                coverage=0.8,
                feedback="Test",
                strengths=[],
                weaknesses=[],
                suggestions=[],
            ),
            success=True,
        )

        report = optimizer.analyze([result])

        assert report.intake_question_structure_summary["avg_documentary_exhibit_ready_ratio"] == pytest.approx(1.0)
        assert report.phase_scorecards["intake_questioning"]["documentary_exhibit_ready_ratio"] == pytest.approx(1.0)

    def test_optimizer_recommends_stronger_exhibit_ready_intake_prompts_when_ratio_is_low(self):
        optimizer = Optimizer()
        result = SessionResult(
            session_id="session_intake_exhibit_ready_gap",
            timestamp="2024-01-01",
            seed_complaint={},
            initial_complaint_text="Test",
            conversation_history=[],
            num_questions=3,
            num_turns=2,
            final_state={
                "workflow_phase_plan": {
                    "phases": {
                        "intake_questioning": {"status": "warning"},
                        "graph_analysis": {"status": "ready"},
                        "document_generation": {"status": "warning"},
                    }
                },
                "intake_question_structure_summary": {
                    "question_count": 3,
                    "documentary_question_count": 2,
                    "exhibit_ready_question_count": 0,
                    "temporal_exhibit_ready_question_count": 0,
                    "documentary_exhibit_ready_question_count": 0,
                    "documentary_exhibit_ready_ratio": 0.0,
                    "needs_exhibit_grounding": True,
                },
            },
            critic_score=CriticScore(
                overall_score=0.72,
                question_quality=0.72,
                information_extraction=0.72,
                empathy=0.72,
                efficiency=0.72,
                coverage=0.72,
                feedback="Test",
                strengths=[],
                weaknesses=[],
                suggestions=[],
            ),
            success=True,
        )

        report = optimizer.analyze([result])

        assert any("exhibit-ready" in rec for rec in report.recommendations)
        assert any(item.startswith("Increase exhibit-ready intake prompts") for item in report.priority_improvements)
        assert "exhibit_ready_questions" in report.phase_scorecards["intake_questioning"]["focus_areas"]

    def test_build_agentic_patch_task_uses_report_recommendations(self, monkeypatch):
        optimizer = Optimizer()

        monkeypatch.setattr(
            Optimizer,
            '_load_agentic_optimizer_components',
            staticmethod(
                lambda: {
                    'OptimizationTask': FakeOptimizationTask,
                    'OptimizationMethod': FakeAgenticOptimizationMethod,
                    'OptimizerLLMRouter': object,
                    'optimizer_classes': {},
                }
            ),
        )

        score = CriticScore(
            overall_score=0.61,
            question_quality=0.55,
            information_extraction=0.58,
            empathy=0.65,
            efficiency=0.54,
            coverage=0.52,
            feedback='Needs work',
            strengths=[],
            weaknesses=['Repetitive questioning'],
            suggestions=['Ask more targeted follow-ups'],
        )
        result = SessionResult(
            session_id='session_task',
            timestamp='2024-01-01',
            seed_complaint={},
            initial_complaint_text='Test',
            conversation_history=[],
            num_questions=3,
            num_turns=2,
            final_state={},
            critic_score=score,
            success=True,
        )

        task, report = optimizer.build_agentic_patch_task(
            [result],
            target_files=['adversarial_harness/session.py'],
            method='actor_critic',
        )

        assert report.average_score == pytest.approx(0.61)
        assert task.method == 'ACTOR_CRITIC'
        assert task.target_files == [Path('adversarial_harness/session.py')]
        assert 'adversarial complainant/mediator loop' in task.description
        assert task.metadata['report_summary']['average_score'] == pytest.approx(0.61)
        assert 'workflow_phase_plan' in task.metadata['report_summary']
        assert 'recommendations' in task.metadata['report_summary']

    def test_run_agentic_autopatch_invokes_upstream_optimizer_and_attaches_report(self, monkeypatch):
        optimizer = Optimizer()
        captured = {}

        class FakeAgenticOptimizer:
            def __init__(self, agent_id, llm_router):
                captured['agent_id'] = agent_id
                captured['llm_router'] = llm_router

            def optimize(self, task):
                captured['task'] = task
                return SimpleNamespace(success=True, patch_path=Path('patches/fake.patch'), patch_cid='bafytest', metadata={})

        monkeypatch.setattr(
            Optimizer,
            '_load_agentic_optimizer_components',
            staticmethod(
                lambda: {
                    'OptimizationTask': FakeOptimizationTask,
                    'OptimizationMethod': FakeAgenticOptimizationMethod,
                    'OptimizerLLMRouter': object,
                    'optimizer_classes': {
                        'actor_critic': FakeAgenticOptimizer,
                    },
                }
            ),
        )

        score = CriticScore(
            overall_score=0.72,
            question_quality=0.7,
            information_extraction=0.71,
            empathy=0.73,
            efficiency=0.68,
            coverage=0.74,
            feedback='Solid',
            strengths=['Good coverage'],
            weaknesses=['Mediator could be more specific'],
            suggestions=['Improve targeted follow-ups'],
        )
        result = SessionResult(
            session_id='session_patch',
            timestamp='2024-01-01',
            seed_complaint={},
            initial_complaint_text='Test',
            conversation_history=[],
            num_questions=4,
            num_turns=3,
            final_state={},
            critic_score=score,
            success=True,
        )
        sentinel_router = object()

        autopatch_result = optimizer.run_agentic_autopatch(
            [result],
            target_files=['adversarial_harness/session.py', 'adversarial_harness/harness.py'],
            llm_router=sentinel_router,
            method='actor_critic',
        )

        assert autopatch_result.success is True
        assert captured['agent_id'] == 'adversarial-harness-optimizer'
        assert captured['llm_router'] is sentinel_router
        assert captured['task'].target_files == [
            Path('adversarial_harness/session.py'),
            Path('adversarial_harness/harness.py'),
        ]
        assert autopatch_result.metadata['agentic_method'] == 'actor_critic'
        assert autopatch_result.metadata['adversarial_report']['average_score'] == pytest.approx(0.72)
        assert autopatch_result.metadata['target_files'] == [
            'adversarial_harness/session.py',
            'adversarial_harness/harness.py',
        ]

    def test_harness_batch_can_flow_into_agentic_autopatch(self, monkeypatch):
        harness = AdversarialHarness(
            MockLLMBackend("I reported discrimination to HR."),
            MockLLMBackend(
                """SCORES:
question_quality: 0.7
information_extraction: 0.72
empathy: 0.68
efficiency: 0.66
coverage: 0.71

FEEDBACK: Good session
STRENGTHS:
- Good coverage
WEAKNESSES:
- More specificity needed
SUGGESTIONS:
- Improve targeted follow-ups
"""
            ),
            MockMediator,
            max_parallel=1,
        )

        captured = {}

        class FakeAgenticOptimizer:
            def __init__(self, agent_id, llm_router):
                captured['agent_id'] = agent_id
                captured['llm_router'] = llm_router

            def optimize(self, task):
                captured['task'] = task
                return SimpleNamespace(success=True, patch_path=Path('patches/harness-flow.patch'), patch_cid='bafy-harness-flow', metadata={})

        monkeypatch.setattr(
            Optimizer,
            '_load_agentic_optimizer_components',
            staticmethod(
                lambda: {
                    'OptimizationTask': FakeOptimizationTask,
                    'OptimizationMethod': FakeAgenticOptimizationMethod,
                    'OptimizerLLMRouter': object,
                    'optimizer_classes': {
                        'actor_critic': FakeAgenticOptimizer,
                    },
                }
            ),
        )

        results = harness.run_batch(
            num_sessions=1,
            seed_complaints=[{
                'type': 'employment_discrimination',
                'summary': 'Retaliation after reporting discrimination',
                'key_facts': {'employer': 'Acme Corp'},
            }],
            max_turns_per_session=1,
            personalities=['cooperative'],
        )
        autopatch_result = Optimizer().run_agentic_autopatch(
            results,
            target_files=['adversarial_harness/session.py'],
            llm_router=object(),
            method='actor_critic',
        )

        assert len(results) == 1
        assert results[0].success is True
        assert autopatch_result.success is True
        assert captured['task'].target_files == [Path('adversarial_harness/session.py')]
        assert captured['task'].metadata['source'] == 'adversarial_harness'
        assert autopatch_result.metadata['adversarial_report']['num_sessions_analyzed'] == 1
        assert autopatch_result.patch_cid == 'bafy-harness-flow'

    def test_batch_demo_can_emit_autopatch_summary(self, monkeypatch, tmp_path):
        module_path = Path(__file__).resolve().parents[1] / 'examples' / 'adversarial_optimization_demo.py'
        spec = importlib.util.spec_from_file_location('adversarial_optimization_demo_test', module_path)
        assert spec is not None and spec.loader is not None
        demo_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(demo_module)

        captured = {}

        class FakeHarness:
            def __init__(self, *args, **kwargs):
                captured['harness_init'] = kwargs

            def run_batch(self, num_sessions, max_turns_per_session):
                captured['run_batch'] = {
                    'num_sessions': num_sessions,
                    'max_turns_per_session': max_turns_per_session,
                }
                return [SimpleNamespace(session_id='session_cli')]

        class FakeOptimizer:
            def analyze(self, results):
                captured['analyze_results'] = list(results)
                return SimpleNamespace(
                    to_dict=lambda: {
                        'average_score': 0.75,
                        'num_sessions_analyzed': len(results),
                    }
                )

            def run_agentic_autopatch(self, results, **kwargs):
                captured['autopatch_kwargs'] = kwargs
                patch_path = tmp_path / 'cli-autopatch.patch'
                patch_path.write_text('demo patch', encoding='utf-8')
                return SimpleNamespace(
                    success=True,
                    patch_path=patch_path,
                    patch_cid='demo-cli-cid',
                    metadata={'demo': True},
                )

        monkeypatch.setattr(
            demo_module,
            '_load_config',
            lambda path: {
                'MEDIATOR': {'backends': ['router']},
                'BACKENDS': [{'id': 'router', 'type': 'llm_router'}],
            },
        )
        monkeypatch.setattr(demo_module, 'LLMRouterBackend', lambda **kwargs: SimpleNamespace())
        monkeypatch.setattr(demo_module, 'AdversarialHarness', FakeHarness)
        monkeypatch.setattr(demo_module, 'Optimizer', FakeOptimizer)
        monkeypatch.setattr(
            sys,
            'argv',
            [
                'adversarial_optimization_demo.py',
                '--mode',
                'batch',
                '--emit-autopatch',
                '--num-sessions',
                '2',
                '--max-turns',
                '4',
                '--autopatch-target-file',
                'adversarial_harness/session.py',
                '--autopatch-output-dir',
                str(tmp_path),
            ],
        )

        exit_code = demo_module.main()

        assert exit_code == 0
        assert captured['run_batch'] == {'num_sessions': 2, 'max_turns_per_session': 4}
        assert captured['autopatch_kwargs']['target_files'] == ['adversarial_harness/session.py']
        summary = json.loads((tmp_path / 'summary.json').read_text(encoding='utf-8'))
        assert summary['num_results'] == 1
        assert summary['autopatch']['success'] is True
        assert summary['autopatch']['patch_cid'] == 'demo-cli-cid'

    def test_run_adversarial_autopatch_batch_live_mode_with_mock_backends(self, tmp_path):
        payload = run_adversarial_autopatch_batch(
            project_root=Path(__file__).resolve().parents[1],
            output_dir=tmp_path,
            target_file='adversarial_harness/session.py',
            num_sessions=1,
            max_turns=2,
            max_parallel=1,
            demo_backend=False,
            backends=[DemoBatchLLMBackend()],
            mediator_factory=DemoBatchMediator,
        )

        assert payload['num_results'] == 1
        assert payload['runtime']['mode'] == 'live'
        assert payload['runtime']['backend_count'] == 1
        assert payload['runtime']['backend_type'] == 'DemoBatchLLMBackend'
        assert payload['runtime']['selected_backend_id'] == 'DemoBatchLLMBackend'
        assert payload['runtime']['selected_backend_healthy'] is True
        assert payload['runtime']['preflight_warnings'] == []
        assert payload['runtime']['probe_attempts'][0]['ok'] is True
        assert payload['runtime']['degraded'] is False
        assert payload['runtime']['critic_fallback_sessions'] == 0
        assert payload['autopatch']['success'] is True
        assert Path(payload['autopatch']['patch_path']).is_file()
        summary_path = tmp_path / 'summary.json'
        assert summary_path.is_file()
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        assert summary['runtime']['mode'] == 'live'
        assert summary['runtime']['degraded'] is False
        assert summary['autopatch']['patch_cid'].startswith('demo-')

    def test_run_adversarial_autopatch_batch_workflow_mode_emits_phase_tasks(self, tmp_path):
        payload = run_adversarial_autopatch_batch(
            project_root=Path(__file__).resolve().parents[1],
            output_dir=tmp_path,
            target_file='adversarial_harness/session.py',
            num_sessions=1,
            max_turns=2,
            max_parallel=1,
            demo_backend=False,
            phase_mode='workflow',
            backends=[DemoBatchLLMBackend()],
            mediator_factory=DemoBatchMediator,
        )

        assert payload['phase_mode'] == 'workflow'
        assert payload['phase_tasks']
        assert payload['workflow_optimization_bundle']['workflow_phase_plan']['recommended_order']
        assert payload['optimization_guidance']['phase_scorecards']['intake_questioning']['status'] in {'critical', 'warning', 'ready'}
        assert 'cross_phase_findings' in payload['optimization_guidance']
        assert payload['phase_tasks'][0]['phase'] in {'intake_questioning', 'graph_analysis', 'document_generation'}
        assert Path(payload['phase_tasks'][0]['patch_path']).is_file()
        summary = json.loads((tmp_path / 'summary.json').read_text(encoding='utf-8'))
        assert summary['phase_mode'] == 'workflow'
        assert summary['phase_tasks']
        assert summary['workflow_optimization_bundle']['workflow_phase_plan']['recommended_order']
        assert summary['optimization_guidance']['phase_scorecards']['document_generation']['status'] in {'critical', 'warning', 'ready'}

    def test_run_adversarial_autopatch_batch_live_mode_probes_multiple_backends(self, tmp_path):
        class FailingBackend:
            id = 'failing-backend'

            def __call__(self, prompt: str) -> str:
                raise Exception('probe failed')

        payload = run_adversarial_autopatch_batch(
            project_root=Path(__file__).resolve().parents[1],
            output_dir=tmp_path,
            target_file='adversarial_harness/session.py',
            num_sessions=1,
            max_turns=2,
            max_parallel=1,
            demo_backend=False,
            backends=[FailingBackend(), DemoBatchLLMBackend()],
            mediator_factory=DemoBatchMediator,
        )

        assert payload['runtime']['mode'] == 'live'
        assert payload['runtime']['selected_backend_id'] == 'DemoBatchLLMBackend'
        assert payload['runtime']['selected_backend_healthy'] is True
        assert payload['runtime']['probe_attempts'][0]['backend_id'] == 'failing-backend'
        assert payload['runtime']['probe_attempts'][0]['ok'] is False
        assert payload['runtime']['probe_attempts'][1]['backend_id'] == 'DemoBatchLLMBackend'
        assert payload['runtime']['probe_attempts'][1]['ok'] is True
        assert payload['autopatch']['success'] is True

    def test_run_adversarial_autopatch_batch_marks_probe_failure_when_all_live_backends_fail(self, tmp_path):
        class FailingBackend:
            def __init__(self, backend_id):
                self.id = backend_id

            def __call__(self, prompt: str) -> str:
                raise Exception(f'{self.id} failed')

        payload = run_adversarial_autopatch_batch(
            project_root=Path(__file__).resolve().parents[1],
            output_dir=tmp_path,
            target_file='adversarial_harness/session.py',
            num_sessions=1,
            max_turns=2,
            max_parallel=1,
            demo_backend=False,
            backends=[FailingBackend('backend-a'), FailingBackend('backend-b')],
            mediator_factory=DemoBatchMediator,
        )

        assert payload['runtime']['selected_backend_id'] == 'backend-a'
        assert payload['runtime']['selected_backend_healthy'] is False
        assert payload['runtime']['degraded'] is True
        assert 'backend_probe_failed' in payload['runtime']['degraded_reasons']

    def test_run_adversarial_autopatch_batch_collects_live_preflight_warnings(self, tmp_path, monkeypatch):
        monkeypatch.delenv('HF_TOKEN', raising=False)
        monkeypatch.delenv('HUGGINGFACE_HUB_TOKEN', raising=False)
        monkeypatch.delenv('HUGGINGFACE_API_KEY', raising=False)
        monkeypatch.delenv('HF_API_TOKEN', raising=False)
        monkeypatch.setattr(demo_autopatch_module.shutil, 'which', lambda name: None)

        class FailingBackend:
            def __init__(self, backend_id, provider):
                self.id = backend_id
                self.provider = provider

            def __call__(self, prompt: str) -> str:
                raise Exception(f'{self.id} failed')

        payload = run_adversarial_autopatch_batch(
            project_root=Path(__file__).resolve().parents[1],
            output_dir=tmp_path,
            target_file='adversarial_harness/session.py',
            num_sessions=1,
            max_turns=2,
            max_parallel=1,
            demo_backend=False,
            backends=[
                FailingBackend('hf-router', 'huggingface_router'),
                FailingBackend('llm-router-codex', 'codex_cli'),
                FailingBackend('llm-router', 'accelerate'),
            ],
            mediator_factory=DemoBatchMediator,
        )

        warnings = payload['runtime']['preflight_warnings']
        assert any('hf-router: Hugging Face router requires HF_TOKEN or HUGGINGFACE_HUB_TOKEN' in warning for warning in warnings)
        assert any('llm-router-codex: Codex CLI backend requires a codex binary on PATH.' == warning for warning in warnings)
        assert any('llm-router: accelerate is best-effort and may degrade to local_fallback' in warning for warning in warnings)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
