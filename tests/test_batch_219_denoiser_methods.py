"""
Unit tests for Batch 219: ComplaintDenoiser question-answer interaction analysis methods.

Tests the 10 interaction tracking and statistics methods added to ComplaintDenoiser.
"""

import pytest
from complaint_phases.denoiser import ComplaintDenoiser


@pytest.fixture
def denoiser():
    """Create a ComplaintDenoiser instance for testing."""
    return ComplaintDenoiser()


def create_qa_item(question_type='clarification', priority='medium',
                   answer='Test answer', context=None):
    """Helper to create a question-answer item for testing."""
    if context is None:
        context = {}
    
    return {
        'question': {
            'type': question_type,
            'question': f'Test {question_type} question?',
            'priority': priority,
            'context': context
        },
        'answer': answer
    }


# ============================================================================ #
# Test total_answers_received()
# ============================================================================ #

class TestTotalAnswersReceived:
    def test_no_answers(self, denoiser):
        assert denoiser.total_answers_received() == 0
    
    def test_single_answer(self, denoiser):
        denoiser.questions_asked.append(create_qa_item())
        assert denoiser.total_answers_received() == 1
    
    def test_multiple_answers(self, denoiser):
        for i in range(5):
            denoiser.questions_asked.append(create_qa_item())
        assert denoiser.total_answers_received() == 5


# ============================================================================ #
# Test questions_by_priority()
# ============================================================================ #

class TestQuestionsByPriority:
    def test_no_questions(self, denoiser):
        assert denoiser.questions_by_priority('high') == 0
    
    def test_no_matching_priority(self, denoiser):
        denoiser.questions_asked.append(create_qa_item(priority='low'))
        assert denoiser.questions_by_priority('high') == 0
    
    def test_single_priority(self, denoiser):
        denoiser.questions_asked.append(create_qa_item(priority='high'))
        assert denoiser.questions_by_priority('high') == 1
    
    def test_multiple_priorities(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(priority='high'),
            create_qa_item(priority='medium'),
            create_qa_item(priority='high'),
            create_qa_item(priority='low'),
        ])
        assert denoiser.questions_by_priority('high') == 2
        assert denoiser.questions_by_priority('medium') == 1
        assert denoiser.questions_by_priority('low') == 1


# ============================================================================ #
# Test priority_distribution()
# ============================================================================ #

class TestPriorityDistribution:
    def test_no_questions(self, denoiser):
        assert denoiser.priority_distribution() == {}
    
    def test_single_priority(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(priority='medium'),
            create_qa_item(priority='medium'),
        ])
        assert denoiser.priority_distribution() == {'medium': 2}
    
    def test_multiple_priorities(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(priority='high'),
            create_qa_item(priority='low'),
            create_qa_item(priority='high'),
            create_qa_item(priority='medium'),
        ])
        dist = denoiser.priority_distribution()
        assert dist == {'high': 2, 'low': 1, 'medium': 1}


# ============================================================================ #
# Test unanswered_pool_questions()
# ============================================================================ #

class TestUnansweredPoolQuestions:
    def test_empty_pool(self, denoiser):
        assert denoiser.unanswered_pool_questions() == 0
    
    def test_questions_in_pool(self, denoiser):
        denoiser.questions_pool = [
            {'type': 'clarification', 'question': 'Q1?'},
            {'type': 'evidence', 'question': 'Q2?'},
            {'type': 'relationship', 'question': 'Q3?'},
        ]
        assert denoiser.unanswered_pool_questions() == 3


# ============================================================================ #
# Test questions_with_context()
# ============================================================================ #

class TestQuestionsWithContext:
    def test_no_questions(self, denoiser):
        assert denoiser.questions_with_context() == 0
    
    def test_no_context(self, denoiser):
        denoiser.questions_asked.append(create_qa_item(context={}))
        denoiser.questions_asked.append(create_qa_item(context={}))
        assert denoiser.questions_with_context() == 0
    
    def test_all_with_context(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(context={'entity_id': 'e1'}),
            create_qa_item(context={'claim_id': 'c1'}),
        ])
        assert denoiser.questions_with_context() == 2
    
    def test_mixed_context(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(context={'entity_id': 'e1'}),
            create_qa_item(context={}),
            create_qa_item(context={'claim_id': 'c1'}),
        ])
        assert denoiser.questions_with_context() == 2


# ============================================================================ #
# Test average_answer_length()
# ============================================================================ #

class TestAverageAnswerLength:
    def test_no_questions(self, denoiser):
        assert denoiser.average_answer_length() == 0.0
    
    def test_single_answer(self, denoiser):
        denoiser.questions_asked.append(create_qa_item(answer='test'))  # 4 chars
        assert abs(denoiser.average_answer_length() - 4.0) < 0.01
    
    def test_multiple_answers(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(answer='ab'),      # 2 chars
            create_qa_item(answer='abcd'),    # 4 chars
            create_qa_item(answer='abcdef'),  # 6 chars
        ])
        # Average: (2 + 4 + 6) / 3 = 4.0
        assert abs(denoiser.average_answer_length() - 4.0) < 0.01


# ============================================================================ #
# Test shortest_answer()
# ============================================================================ #

class TestShortestAnswer:
    def test_no_questions(self, denoiser):
        assert denoiser.shortest_answer() == 0
    
    def test_single_answer(self, denoiser):
        denoiser.questions_asked.append(create_qa_item(answer='test'))
        assert denoiser.shortest_answer() == 4
    
    def test_multiple_answers(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(answer='x'),
            create_qa_item(answer='abcdefgh'),
            create_qa_item(answer='abc'),
        ])
        assert denoiser.shortest_answer() == 1


# ============================================================================ #
# Test longest_answer()
# ============================================================================ #

class TestLongestAnswer:
    def test_no_questions(self, denoiser):
        assert denoiser.longest_answer() == 0
    
    def test_single_answer(self, denoiser):
        denoiser.questions_asked.append(create_qa_item(answer='test'))
        assert denoiser.longest_answer() == 4
    
    def test_multiple_answers(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(answer='x'),
            create_qa_item(answer='abcdefgh'),
            create_qa_item(answer='abc'),
        ])
        assert denoiser.longest_answer() == 8


# ============================================================================ #
# Test question_type_priority_matrix()
# ============================================================================ #

class TestQuestionTypePriorityMatrix:
    def test_no_questions(self, denoiser):
        assert denoiser.question_type_priority_matrix() == {}
    
    def test_single_type_single_priority(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(question_type='clarification', priority='high'),
            create_qa_item(question_type='clarification', priority='high'),
        ])
        matrix = denoiser.question_type_priority_matrix()
        assert matrix == {'clarification': {'high': 2}}
    
    def test_multiple_types_priorities(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(question_type='clarification', priority='high'),
            create_qa_item(question_type='evidence', priority='medium'),
            create_qa_item(question_type='clarification', priority='low'),
            create_qa_item(question_type='evidence', priority='high'),
        ])
        matrix = denoiser.question_type_priority_matrix()
        assert matrix == {
            'clarification': {'high': 1, 'low': 1},
            'evidence': {'medium': 1, 'high': 1}
        }


# ============================================================================ #
# Test recent_question_types()
# ============================================================================ #

class TestRecentQuestionTypes:
    def test_no_questions(self, denoiser):
        assert denoiser.recent_question_types(5) == []
    
    def test_fewer_than_requested(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(question_type='clarification'),
            create_qa_item(question_type='evidence'),
        ])
        types = denoiser.recent_question_types(5)
        # Should return in reverse order
        assert types == ['evidence', 'clarification']
    
    def test_exact_number(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(question_type='a'),
            create_qa_item(question_type='b'),
            create_qa_item(question_type='c'),
        ])
        types = denoiser.recent_question_types(3)
        assert types == ['c', 'b', 'a']
    
    def test_more_than_requested(self, denoiser):
        denoiser.questions_asked.extend([
            create_qa_item(question_type='a'),
            create_qa_item(question_type='b'),
            create_qa_item(question_type='c'),
            create_qa_item(question_type='d'),
            create_qa_item(question_type='e'),
        ])
        types = denoiser.recent_question_types(3)
        # Should return most recent 3 in reverse order
        assert types == ['e', 'd', 'c']


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch219Integration:
    def test_comprehensive_denoiser_interaction_analysis(self, denoiser):
        """Test that all Batch 219 methods work together correctly."""
        # Populate with question-answer interactions
        denoiser.questions_asked.extend([
            create_qa_item(
                question_type='clarification',
                priority='high',
                answer='Yes, John Smith',
                context={'entity_id': 'e1'}
            ),
            create_qa_item(
                question_type='evidence',
                priority='high',
                answer='Email dated January 5th',
                context={'claim_id': 'c1'}
            ),
            create_qa_item(
                question_type='relationship',
                priority='medium',
                answer='He was my supervisor',
                context={}
            ),
            create_qa_item(
                question_type='clarification',
                priority='low',
                answer='X',
                context={'entity_id': 'e2'}
            ),
        ])
        
        # Add some unanswered questions to pool
        denoiser.questions_pool = [
            {'type': 'evidence', 'question': 'Pending Q1?'},
            {'type': 'clarification', 'question': 'Pending Q2?'},
        ]
        
        # Test all Batch 219 methods
        assert denoiser.total_answers_received() == 4
        
        assert denoiser.questions_by_priority('high') == 2
        assert denoiser.questions_by_priority('medium') == 1
        assert denoiser.questions_by_priority('low') == 1
        
        dist = denoiser.priority_distribution()
        assert dist == {'high': 2, 'medium': 1, 'low': 1}
        
        assert denoiser.unanswered_pool_questions() == 2
        
        # 3 out of 4 have context
        assert denoiser.questions_with_context() == 3
        
        # Answer lengths: 15, 23, 20, 1
        # Average: (15 + 23 + 20 + 1) / 4 = 14.75
        assert abs(denoiser.average_answer_length() - 14.75) < 0.01
        
        assert denoiser.shortest_answer() == 1
        assert denoiser.longest_answer() == 23
        
        matrix = denoiser.question_type_priority_matrix()
        assert matrix == {
            'clarification': {'high': 1, 'low': 1},
            'evidence': {'high': 1},
            'relationship': {'medium': 1}
        }
        
        recent = denoiser.recent_question_types(3)
        assert recent == ['clarification', 'relationship', 'evidence']
