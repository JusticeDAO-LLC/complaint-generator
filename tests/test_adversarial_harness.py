"""
Tests for adversarial harness system
"""

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
from adversarial_harness.hacc_evidence import build_hacc_evidence_seed
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
                {'question': 'Can you provide more details?', 'type': 'clarification'}
            ]
        }
    
    def process_denoising_answer(self, question, answer):
        self.questions_asked += 1
        return {
            'converged': self.questions_asked >= 3,
            'next_questions': [{'question': 'Tell me more', 'type': 'follow_up'}]
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
        monkeypatch.setattr(
            seed_complaints_module,
            'build_hacc_evidence_seeds',
            lambda **kwargs: [
                {
                    'type': 'housing_discrimination',
                    'key_facts': {'evidence_summary': 'Mocked evidence'},
                    'hacc_evidence': [{'title': 'Mock Policy'}],
                }
            ],
        )

        library = SeedComplaintLibrary()
        seeds = library.get_hacc_seed_complaints(count=1)

        assert len(seeds) == 1
        assert seeds[0]['key_facts']['evidence_summary'] == 'Mocked evidence'

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
        )

        assert seed is not None
        assert len(seed['key_facts']['anchor_passages']) == 2
        assert 'impartial person' in seed['key_facts']['anchor_passages'][0]['snippet'].lower()
        assert 'grievance_hearing' in seed['key_facts']['anchor_passages'][0]['section_labels']
        assert 'reasonable_accommodation' in seed['key_facts']['anchor_sections']


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
        )

        assert len(results) == 1
        assert captured['include_hacc_evidence'] is True
        assert captured['hacc_count'] == 1
        assert captured['hacc_preset'] == 'retaliation_focus'
        assert captured['hacc_query_specs'][0]['query'] == 'retaliation policy'
        assert captured['use_hacc_vector_search'] is True


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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
