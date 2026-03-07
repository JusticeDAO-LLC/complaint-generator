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