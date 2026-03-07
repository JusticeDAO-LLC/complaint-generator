"""
Unit tests for Legal Hooks

Tests for legal classification, statute retrieval, summary judgment requirements,
and question generation hooks.
"""
import pytest
import os
from unittest.mock import Mock, MagicMock, patch


class TestLegalClassificationHook:
    """Test cases for LegalClassificationHook"""
    
    def test_legal_classification_hook_can_be_imported(self):
        """Test that LegalClassificationHook can be imported"""
        try:
            from mediator.legal_hooks import LegalClassificationHook
            assert LegalClassificationHook is not None
        except ImportError as e:
            pytest.skip(f"LegalClassificationHook has import issues: {e}")
    
    def test_classify_complaint(self):
        """Test complaint classification"""
        try:
            from mediator.legal_hooks import LegalClassificationHook
            
            # Mock mediator
            mock_mediator = Mock()
            mock_mediator.query_backend = Mock(return_value="""
CLAIM TYPES: breach of contract, fraud
JURISDICTION: federal
LEGAL AREAS: contract law, business law
KEY FACTS: written agreement, failure to perform, damages incurred
            """)
            
            hook = LegalClassificationHook(mock_mediator)
            result = hook.classify_complaint("Test complaint about breach of contract")
            
            assert isinstance(result, dict)
            assert 'claim_types' in result
            assert 'jurisdiction' in result
            assert 'legal_areas' in result
            assert len(result['claim_types']) > 0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_classification_error_handling(self):
        """Test that classification handles errors gracefully"""
        try:
            from mediator.legal_hooks import LegalClassificationHook
            
            mock_mediator = Mock()
            mock_mediator.query_backend = Mock(side_effect=Exception("Backend error"))
            mock_mediator.log = Mock()
            
            hook = LegalClassificationHook(mock_mediator)
            result = hook.classify_complaint("Test complaint")
            
            # Should return empty classification on error
            assert result['claim_types'] == []
            assert result['jurisdiction'] == 'unknown'
            mock_mediator.log.assert_called_once()
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestStatuteRetrievalHook:
    """Test cases for StatuteRetrievalHook"""
    
    def test_statute_retrieval_hook_can_be_imported(self):
        """Test that StatuteRetrievalHook can be imported"""
        try:
            from mediator.legal_hooks import StatuteRetrievalHook
            assert StatuteRetrievalHook is not None
        except ImportError as e:
            pytest.skip(f"StatuteRetrievalHook has import issues: {e}")
    
    def test_retrieve_statutes(self):
        """Test statute retrieval"""
        try:
            from mediator.legal_hooks import StatuteRetrievalHook
            
            mock_mediator = Mock()
            mock_mediator.query_backend = Mock(return_value="""
STATUTE: 42 U.S.C. § 1983
TITLE: Civil Rights Act
RELEVANCE: Applies to civil rights violations
---
STATUTE: 29 U.S.C. § 2601
TITLE: Family and Medical Leave Act
RELEVANCE: Relevant to employment claims
            """)
            
            hook = StatuteRetrievalHook(mock_mediator)
            classification = {
                'claim_types': ['civil rights violation'],
                'legal_areas': ['civil rights law'],
                'jurisdiction': 'federal'
            }
            
            result = hook.retrieve_statutes(classification)
            
            assert isinstance(result, list)
            assert len(result) > 0
            assert 'citation' in result[0]
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    def test_retrieve_statutes_empty_classification(self):
        """Test statute retrieval with empty classification"""
        try:
            from mediator.legal_hooks import StatuteRetrievalHook
            
            mock_mediator = Mock()
            hook = StatuteRetrievalHook(mock_mediator)
            
            result = hook.retrieve_statutes({})
            assert result == []
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_get_capability_registry_returns_expected_shape(self):
        """Test capability registry shape for Phase 1 integration."""
        try:
            from mediator.legal_hooks import StatuteRetrievalHook

            mock_mediator = Mock()
            hook = StatuteRetrievalHook(mock_mediator)

            registry = hook.get_capability_registry()
            assert isinstance(registry, dict)
            assert 'legal_datasets' in registry
            assert 'search_tools' in registry
            assert 'available' in registry['legal_datasets']
            assert 'enabled' in registry['legal_datasets']
            assert 'active' in registry['legal_datasets']
            assert 'details' in registry['legal_datasets']
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_retrieve_statutes_bundle_enhanced_adds_normalized(self):
        """Enhanced mode should expose normalized deduped/ranked statutes."""
        try:
            from mediator.legal_hooks import StatuteRetrievalHook

            mock_mediator = Mock()
            mock_mediator.query_backend = Mock(return_value="""
STATUTE: 42 U.S.C. § 1983
TITLE: Civil Rights Act
RELEVANCE: Applies to civil rights violations
---
STATUTE: 42 U.S.C. § 1983
TITLE: Civil Rights Act (duplicate)
RELEVANCE: Strong match
            """)
            mock_mediator.log = Mock()

            classification = {
                'claim_types': ['civil rights violation'],
                'legal_areas': ['civil rights law'],
                'jurisdiction': 'federal'
            }

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_LEGAL': '1',
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
            }, clear=False):
                hook = StatuteRetrievalHook(mock_mediator)
                bundle = hook.retrieve_statutes_bundle(classification)

            assert isinstance(bundle, dict)
            assert 'raw' in bundle
            assert 'normalized' in bundle
            assert isinstance(bundle['normalized'], list)
            assert len(bundle['normalized']) >= 1
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_retrieve_statutes_bundle_enhanced_vector_marks_metadata(self):
        """Enhanced vector mode should annotate normalized statutes with vector metadata."""
        try:
            from mediator.legal_hooks import StatuteRetrievalHook

            mock_mediator = Mock()
            mock_mediator.query_backend = Mock(return_value="""
STATUTE: 42 U.S.C. § 1983
TITLE: Employment retaliation protection
RELEVANCE: Covers retaliation after reporting discrimination
            """)
            mock_mediator.log = Mock()

            classification = {
                'claim_types': ['employment retaliation'],
                'legal_areas': ['employment law'],
                'jurisdiction': 'federal',
                'key_facts': ['termination email', 'reported discrimination to HR'],
            }

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_LEGAL': '1',
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
                'IPFS_DATASETS_ENHANCED_VECTOR': '1',
            }, clear=False):
                hook = StatuteRetrievalHook(mock_mediator)
                bundle = hook.retrieve_statutes_bundle(classification)

            assert 'normalized' in bundle
            assert len(bundle['normalized']) >= 1
            assert bundle['normalized'][0]['metadata'].get('vector_augmented') is True
            assert bundle['normalized'][0]['metadata'].get('evidence_similarity_applied') is True
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_retrieve_statutes_bundle_vector_uses_context_to_boost_matching_statute(self):
        """Enhanced vector mode should prefer statutes aligned with case facts."""
        try:
            from mediator.legal_hooks import StatuteRetrievalHook

            mock_mediator = Mock()
            mock_mediator.log = Mock()
            mock_mediator.state = Mock()
            mock_mediator.state.complaint_summary = 'Retaliation after reporting discrimination to HR'
            mock_mediator.state.original_complaint = 'A termination email shows the retaliation.'
            mock_mediator.state.complaint = None
            mock_mediator.state.last_message = 'Need statutes matching the termination email evidence.'
            mock_mediator.state.data = {
                'chat_history': {
                    '1': 'termination email from manager',
                    '2': 'retaliation complaint details',
                }
            }

            classification = {
                'claim_types': ['employment retaliation'],
                'legal_areas': ['employment law'],
                'jurisdiction': 'federal',
                'key_facts': ['termination email', 'reported discrimination to HR'],
            }

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_LEGAL': '1',
                'IPFS_DATASETS_ENHANCED_SEARCH': '1',
                'IPFS_DATASETS_ENHANCED_VECTOR': '1',
            }, clear=False):
                hook = StatuteRetrievalHook(mock_mediator)
                hook.retrieve_statutes = Mock(return_value=[
                    {
                        'citation': '42 U.S.C. § 2000e-3',
                        'title': 'Termination email retaliation protection',
                        'relevance': 'Covers retaliation after reporting discrimination and adverse action evidence.',
                        'score': 0.35,
                        'confidence': 0.6,
                    },
                    {
                        'citation': '29 U.S.C. § 201',
                        'title': 'General wage notice rule',
                        'relevance': 'General workplace compliance rule.',
                        'score': 0.45,
                        'confidence': 0.6,
                    },
                ])
                bundle = hook.retrieve_statutes_bundle(classification)

            assert 'normalized' in bundle
            assert bundle['normalized'][0]['title'] == 'Termination email retaliation protection'
            assert bundle['normalized'][0]['metadata'].get('evidence_similarity_score', 0.0) > 0.0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestSummaryJudgmentHook:
    """Test cases for SummaryJudgmentHook"""
    
    def test_summary_judgment_hook_can_be_imported(self):
        """Test that SummaryJudgmentHook can be imported"""
        try:
            from mediator.legal_hooks import SummaryJudgmentHook
            assert SummaryJudgmentHook is not None
        except ImportError as e:
            pytest.skip(f"SummaryJudgmentHook has import issues: {e}")
    
    def test_generate_requirements(self):
        """Test requirements generation"""
        try:
            from mediator.legal_hooks import SummaryJudgmentHook
            
            mock_mediator = Mock()
            mock_mediator.query_backend = Mock(return_value="""
1. Existence of a valid contract
2. Plaintiff's performance under the contract
3. Defendant's breach of the contract
4. Damages resulting from the breach
            """)
            
            hook = SummaryJudgmentHook(mock_mediator)
            classification = {
                'claim_types': ['breach of contract'],
                'jurisdiction': 'federal',
                'legal_areas': ['contract law']
            }
            statutes = [{'citation': 'Test', 'title': 'Test Statute', 'relevance': 'Test'}]
            
            result = hook.generate_requirements(classification, statutes)
            
            assert isinstance(result, dict)
            assert 'breach of contract' in result
            assert len(result['breach of contract']) > 0
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestQuestionGenerationHook:
    """Test cases for QuestionGenerationHook"""
    
    def test_question_generation_hook_can_be_imported(self):
        """Test that QuestionGenerationHook can be imported"""
        try:
            from mediator.legal_hooks import QuestionGenerationHook
            assert QuestionGenerationHook is not None
        except ImportError as e:
            pytest.skip(f"QuestionGenerationHook has import issues: {e}")
    
    def test_generate_questions(self):
        """Test question generation"""
        try:
            from mediator.legal_hooks import QuestionGenerationHook
            
            mock_mediator = Mock()
            mock_mediator.query_backend = Mock(return_value="""
ELEMENT: 1. Existence of a valid contract
Q1: Do you have a written contract with the defendant?
Q2: When was the contract signed?
---
ELEMENT: 2. Plaintiff's performance
Q1: Did you fulfill all your obligations under the contract?
Q2: What evidence do you have of your performance?
            """)
            
            hook = QuestionGenerationHook(mock_mediator)
            requirements = {
                'breach of contract': [
                    'Existence of a valid contract',
                    'Plaintiff\'s performance'
                ]
            }
            classification = {
                'key_facts': ['Written agreement', 'Payment made'],
                'claim_types': ['breach of contract']
            }
            
            result = hook.generate_questions(requirements, classification)
            
            assert isinstance(result, list)
            assert len(result) > 0
            assert 'question' in result[0]
            assert 'claim_type' in result[0]
            assert 'provenance' in result[0]
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_generate_questions_includes_support_context_and_summary(self):
        """Question generation should include support-aware context in prompt and provenance."""
        try:
            from mediator.legal_hooks import QuestionGenerationHook

            mock_mediator = Mock()
            mock_mediator.query_backend = Mock(return_value="""
ELEMENT: 1. Protected activity
Q1: When did you report the discrimination to HR?
Q2: Do you have the email or message confirming that report?
            """)

            hook = QuestionGenerationHook(mock_mediator)
            requirements = {
                'employment retaliation': [
                    'Protected activity',
                ]
            }
            classification = {
                'key_facts': ['Reported discrimination to HR'],
                'claim_types': ['employment retaliation']
            }

            result = hook.generate_questions(
                requirements,
                classification,
                provenance_context={
                    'support_context': 'Cross-supported retrieved items:\n- Title VII retaliation guidance: HR complaint is protected activity',
                    'support_summary': {
                        'authority_count': 1,
                        'evidence_count': 1,
                        'cross_supported_count': 1,
                        'hybrid_cross_supported_count': 1,
                    },
                },
            )

            prompt = mock_mediator.query_backend.call_args.args[0]
            assert 'Retrieved Support Already Available' in prompt
            assert 'Title VII retaliation guidance' in prompt
            assert result[0]['provenance']['support_summary']['cross_supported_count'] == 1
            assert 'support_context' in result[0]['provenance']
            assert result[0]['priority'] == 'Medium'
            assert result[0]['support_gap_targeted'] is False
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    def test_generate_questions_marks_critical_when_no_support_is_cached(self):
        """Question generation should escalate priority when no corroborating support is available."""
        try:
            from mediator.legal_hooks import QuestionGenerationHook

            mock_mediator = Mock()
            mock_mediator.query_backend = Mock(return_value="""
ELEMENT: 1. Adverse action
Q1: On what exact date were you terminated?
Q2: Who communicated the termination to you?
            """)

            hook = QuestionGenerationHook(mock_mediator)
            result = hook.generate_questions(
                {'employment retaliation': ['Adverse action']},
                {
                    'key_facts': ['Reported discrimination to HR'],
                    'claim_types': ['employment retaliation'],
                },
                provenance_context={
                    'support_context': 'No cross-supported authorities or evidence are cached yet.',
                    'support_summary': {
                        'authority_count': 0,
                        'evidence_count': 0,
                        'cross_supported_count': 0,
                        'hybrid_cross_supported_count': 0,
                    },
                },
            )

            assert result[0]['priority'] == 'Critical'
            assert result[0]['support_gap_targeted'] is True
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")


class TestLegalHooksIntegration:
    """Integration tests for legal hooks with mediator"""
    
    @pytest.mark.integration
    def test_mediator_has_legal_hooks(self):
        """Test that mediator initializes with legal hooks"""
        try:
            from mediator import Mediator
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            
            mediator = Mediator(backends=[mock_backend])
            
            assert hasattr(mediator, 'legal_classifier')
            assert hasattr(mediator, 'statute_retriever')
            assert hasattr(mediator, 'summary_judgment')
            assert hasattr(mediator, 'question_generator')
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
    
    @pytest.mark.integration
    def test_analyze_complaint_legal_issues(self):
        """Test the full legal analysis workflow"""
        try:
            from mediator import Mediator
            
            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mock_backend.return_value = "Mock LLM response"
            
            mediator = Mediator(backends=[mock_backend])
            mediator.state.complaint = "Test complaint about breach of contract"
            
            # Mock the hook methods to avoid actual LLM calls
            mediator.legal_classifier.classify_complaint = Mock(return_value={
                'claim_types': ['breach of contract'],
                'jurisdiction': 'federal',
                'legal_areas': ['contract law'],
                'key_facts': ['written agreement']
            })
            mediator.statute_retriever.retrieve_statutes = Mock(return_value=[])
            mediator.summary_judgment.generate_requirements = Mock(return_value={})
            mediator.question_generator.generate_questions = Mock(return_value=[])
            
            result = mediator.analyze_complaint_legal_issues()
            
            assert 'classification' in result
            assert 'statutes' in result
            assert 'requirements' in result
            assert 'questions' in result
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")

    @pytest.mark.integration
    def test_analyze_complaint_legal_issues_enhanced_includes_statute_bundle(self):
        """Enhanced mode should include statute bundle in analysis results."""
        try:
            from mediator import Mediator

            mock_backend = Mock()
            mock_backend.id = 'test-backend'
            mock_backend.return_value = "Mock LLM response"

            mediator = Mediator(backends=[mock_backend])
            mediator.state.complaint = "Test complaint about civil rights"

            mediator.legal_classifier.classify_complaint = Mock(return_value={
                'claim_types': ['civil rights violation'],
                'jurisdiction': 'federal',
                'legal_areas': ['civil rights law'],
                'key_facts': ['incident details']
            })
            mediator.statute_retriever.retrieve_statutes_bundle = Mock(return_value={
                'raw': [{'citation': '42 U.S.C. § 1983', 'title': 'Civil Rights Act'}],
                'normalized': [{'citation': '42 U.S.C. § 1983', 'score': 0.9}]
            })
            mediator.summary_judgment.generate_requirements = Mock(return_value={})
            mediator.question_generator.generate_questions = Mock(return_value=[])

            with patch.dict(os.environ, {
                'IPFS_DATASETS_ENHANCED_LEGAL': '1',
            }, clear=False):
                result = mediator.analyze_complaint_legal_issues()

            assert 'statute_bundle' in result
            assert 'raw' in result['statute_bundle']
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
