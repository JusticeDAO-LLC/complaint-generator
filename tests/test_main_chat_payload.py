from main import build_chat_payload


def test_build_chat_payload_preserves_legacy_message_field():
    payload = build_chat_payload(
        'Do you have the termination email?',
        sender='Bot:',
        hashed_username='abc123',
    )

    assert payload['message'] == 'Do you have the termination email?'
    assert payload['sender'] == 'Bot:'
    assert payload['hashed_username'] == 'abc123'


def test_build_chat_payload_includes_inquiry_metadata_when_present():
    payload = build_chat_payload(
        'Do you have the termination email?',
        inquiry_payload={
            'question': 'Do you have the termination email?',
            'inquiry': {'priority': 'Critical'},
            'explanation': {'summary': 'Critical missing support gap'},
        },
        sender='Bot:',
    )

    assert payload['question'] == 'Do you have the termination email?'
    assert payload['inquiry']['priority'] == 'Critical'
    assert payload['explanation']['summary'] == 'Critical missing support gap'


def test_build_chat_payload_normalizes_structured_message_dict():
    payload = build_chat_payload(
        {
            'message': 'Do you have the termination email?',
            'question': 'Do you have the termination email?',
            'inquiry': {'priority': 'High'},
        },
        sender='Bot:',
    )

    assert payload['message'] == 'Do you have the termination email?'
    assert payload['question'] == 'Do you have the termination email?'
    assert payload['inquiry']['priority'] == 'High'
    assert payload['sender'] == 'Bot:'


def test_build_chat_payload_defaults_question_to_message_for_plain_messages():
    payload = build_chat_payload(
        'I was fired after reporting discrimination.',
        sender='user-123',
    )

    assert payload['message'] == 'I was fired after reporting discrimination.'
    assert payload['question'] == 'I was fired after reporting discrimination.'


def test_build_chat_payload_uses_inquiry_question_when_message_missing():
    payload = build_chat_payload(
        {
            'inquiry': {'question': 'Do you have the termination email?', 'priority': 'Critical'},
            'explanation': {'summary': 'Critical gap'},
        },
        sender='Bot:',
    )

    assert payload['message'] == 'Do you have the termination email?'
    assert payload['question'] == 'Do you have the termination email?'
    assert payload['inquiry']['priority'] == 'Critical'