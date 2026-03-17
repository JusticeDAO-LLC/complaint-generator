from types import SimpleNamespace
from unittest.mock import Mock

from mediator.complaint import Complaint


def test_complaint_generate_includes_support_context_in_prompt():
    mediator = Mock()
    mediator.state = SimpleNamespace(
        inquiries=[
            {
                'question': 'What happened?',
                'answer': 'I was terminated after reporting discrimination.',
            }
        ],
        complaint=None,
    )
    mediator.build_drafting_support_context = Mock(return_value='Support Context:\nStatutes Support:\n- Title VII: Employment discrimination statute')
    mediator.query_backend = Mock(return_value='Generated complaint summary')

    complaint = Complaint(mediator)
    complaint.generate()

    prompt = mediator.query_backend.call_args.args[0]
    assert 'Support Context:' in prompt
    assert 'Title VII' in prompt
    assert mediator.state.complaint == 'Generated complaint summary'