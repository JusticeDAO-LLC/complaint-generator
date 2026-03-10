"""
Unit tests for Legal Hooks

Tests for legal classification, statute retrieval, summary judgment requirements,
and question generation hooks.
"""
import pytest
import tempfile
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

            with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as f:
                db_path = f.name

            try:
                mediator = Mediator(backends=[mock_backend], claim_support_db_path=db_path)
                mediator.state.complaint = "Test complaint about breach of contract"

                # Mock the hook methods to avoid actual LLM calls
                mediator.legal_classifier.classify_complaint = Mock(return_value={
                    'claim_types': ['breach of contract'],
                    'jurisdiction': 'federal',
                    'legal_areas': ['contract law'],
                    'key_facts': ['written agreement']
                })
                mediator.statute_retriever.retrieve_statutes = Mock(return_value=[])
                mediator.summary_judgment.generate_requirements = Mock(return_value={
                    'breach of contract': ['Existence of a valid contract']
                })
                mediator.question_generator.generate_questions = Mock(return_value=[])

                result = mediator.analyze_complaint_legal_issues()

                assert 'classification' in result
                assert 'statutes' in result
                assert 'requirements' in result
                assert 'support_summary' in result
                assert 'questions' in result
                assert result['support_summary']['claims']['breach of contract']['total_elements'] == 1
                assert result['support_summary']['claims']['breach of contract']['uncovered_elements'] == 1
            finally:
                if os.path.exists(db_path):
                    os.unlink(db_path)
        except ImportError as e:
            pytest.skip(f"Test requires dependencies: {e}")
