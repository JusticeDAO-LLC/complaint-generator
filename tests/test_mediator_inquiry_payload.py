from unittest.mock import Mock

from fastapi.testclient import TestClient


def test_get_current_inquiry_payload_returns_cached_question_and_explanation():
    from mediator import Mediator

    mock_backend = Mock()
    mock_backend.id = 'test-backend'

    mediator = Mediator(backends=[mock_backend])
    mediator.state.current_inquiry = {
        'question': 'Do you have the termination email?',
        'priority': 'Critical',
    }
    mediator.state.current_inquiry_explanation = {
        'summary': 'Selected because it is a critical-priority question and targets a missing claim element or dependency gap',
        'priority': 'Critical',
        'reasons': ['targets a missing claim element or dependency gap'],
    }

    payload = mediator.get_current_inquiry_payload()

    assert payload['question'] == 'Do you have the termination email?'
    assert payload['inquiry']['priority'] == 'Critical'
    assert payload['explanation']['priority'] == 'Critical'


def test_io_payload_includes_message_and_inquiry_metadata():
    from mediator import Mediator

    mock_backend = Mock()
    mock_backend.id = 'test-backend'

    mediator = Mediator(backends=[mock_backend])
    mediator.state.current_inquiry = {
        'question': 'Do you have the termination email?',
        'priority': 'Critical',
    }
    mediator.state.current_inquiry_explanation = {
        'summary': 'Selected because it targets a missing dependency gap',
        'priority': 'Critical',
        'reasons': ['targets a missing claim element or dependency gap'],
    }
    mediator.process = Mock(return_value='Do you have the termination email?')

    payload = mediator.io_payload('yes')

    assert payload['message'] == 'Do you have the termination email?'
    assert payload['question'] == 'Do you have the termination email?'
    assert payload['inquiry']['priority'] == 'Critical'
    assert payload['explanation']['summary'] == 'Selected because it targets a missing dependency gap'


def test_io_payload_normalizes_structured_message_response():
    from mediator import Mediator

    mock_backend = Mock()
    mock_backend.id = 'test-backend'

    mediator = Mediator(backends=[mock_backend])
    mediator.state.current_inquiry = {
        'question': 'Do you have the termination email?',
        'priority': 'Critical',
    }
    mediator.state.current_inquiry_explanation = {
        'summary': 'Selected because it targets a missing dependency gap',
        'priority': 'Critical',
        'reasons': ['targets a missing claim element or dependency gap'],
    }
    mediator.process = Mock(return_value={
        'message': 'Do you have the termination email?',
        'question': 'Do you have the termination email?',
    })

    payload = mediator.io_payload('yes')

    assert payload['message'] == 'Do you have the termination email?'
    assert payload['question'] == 'Do you have the termination email?'
    assert payload['inquiry']['priority'] == 'Critical'
    assert payload['explanation']['summary'] == 'Selected because it targets a missing dependency gap'


def test_server_build_chat_payload_preserves_message_and_explanation():
    from applications.server import SERVER

    payload = SERVER.build_chat_payload(
        'Do you have the termination email?',
        {
            'question': 'Do you have the termination email?',
            'inquiry': {'priority': 'Critical'},
            'explanation': {'summary': 'Critical missing support gap'},
        },
    )

    assert payload['sender'] == 'Bot:'
    assert payload['message'] == 'Do you have the termination email?'
    assert payload['question'] == 'Do you have the termination email?'
    assert payload['inquiry']['priority'] == 'Critical'
    assert payload['explanation']['summary'] == 'Critical missing support gap'


def test_server_build_chat_payload_preserves_hashed_username():
    from applications.server import SERVER

    payload = SERVER.build_chat_payload(
        'Do you have the termination email?',
        sender='Bot:',
        hashed_username='user-123',
    )

    assert payload['hashed_username'] == 'user-123'


def test_server_process_chat_message_uses_mediator_io_payload():
    from applications.server import SERVER

    mediator = Mock()
    mediator.io_payload.return_value = {
        'message': 'Do you have the termination email?',
        'question': 'Do you have the termination email?',
        'inquiry': {'priority': 'Critical'},
        'explanation': {'summary': 'Critical missing support gap'},
    }

    payload = SERVER.process_chat_message(mediator, 'yes')

    mediator.io_payload.assert_called_once_with('yes')
    assert payload['sender'] == 'Bot:'
    assert payload['message'] == 'Do you have the termination email?'
    assert payload['question'] == 'Do you have the termination email?'
    assert payload['inquiry']['priority'] == 'Critical'


def test_server_process_chat_message_preserves_hashed_username():
    from applications.server import SERVER

    mediator = Mock()
    mediator.io_payload.return_value = {
        'message': 'Do you have the termination email?',
        'question': 'Do you have the termination email?',
        'inquiry': {'priority': 'Critical'},
        'explanation': {'summary': 'Critical missing support gap'},
    }

    payload = SERVER.process_chat_message(mediator, 'yes', hashed_username='user-123')

    assert payload['hashed_username'] == 'user-123'


def test_server_post_api_chat_returns_structured_payload():
    from applications.server import SERVER

    mediator = Mock()
    mediator.io_payload.return_value = {
        'message': 'Do you have the termination email?',
        'question': 'Do you have the termination email?',
        'inquiry': {'priority': 'Critical'},
        'explanation': {'summary': 'Critical missing support gap'},
    }

    client = TestClient(SERVER(mediator).app)
    response = client.post('/api/chat', json={'message': 'yes'})

    assert response.status_code == 200
    assert response.json()['message'] == 'Do you have the termination email?'
    assert response.json()['question'] == 'Do you have the termination email?'
    assert response.json()['inquiry']['priority'] == 'Critical'
    mediator.io_payload.assert_called_once_with('yes')


def test_server_post_api_chat_preserves_hashed_username_from_cookie():
    from applications.server import SERVER

    mediator = Mock()
    mediator.io_payload.return_value = {
        'message': 'Do you have the termination email?',
        'question': 'Do you have the termination email?',
        'inquiry': {'priority': 'Critical'},
        'explanation': {'summary': 'Critical missing support gap'},
    }

    client = TestClient(SERVER(mediator).app)
    client.cookies.update({'hashed_username': 'user-123'})
    response = client.post('/api/chat', json={'message': 'yes'})

    assert response.status_code == 200
    assert response.json()['hashed_username'] == 'user-123'


def test_server_post_api_chat_preserves_hashed_username_from_payload():
    from applications.server import SERVER

    mediator = Mock()
    mediator.io_payload.return_value = {
        'message': 'Do you have the termination email?',
        'question': 'Do you have the termination email?',
        'inquiry': {'priority': 'Critical'},
        'explanation': {'summary': 'Critical missing support gap'},
    }

    client = TestClient(SERVER(mediator).app)
    response = client.post('/api/chat', json={'message': 'yes', 'hashed_username': 'user-123'})

    assert response.status_code == 200
    assert response.json()['hashed_username'] == 'user-123'


def test_server_post_api_chat_requires_message():
    from applications.server import SERVER

    client = TestClient(SERVER(Mock()).app)
    response = client.post('/api/chat', json={})

    assert response.status_code == 400
    assert response.json()['detail'] == 'message is required'


def test_server_static_chat_script_is_served():
    from applications.server import SERVER

    client = TestClient(SERVER(Mock()).app)
    response = client.get('/static/chat.js')

    assert response.status_code == 200
    assert 'window.ChatPage' in response.text
    assert 'renderMessage' in response.text


def test_server_static_chat_entry_utils_script_is_served():
    from applications.server import SERVER

    client = TestClient(SERVER(Mock()).app)
    response = client.get('/static/chat_entry_utils.js')

    assert response.status_code == 200
    assert 'window.ChatEntryUtils' in response.text
    assert 'normalizeChatEntry' in response.text


def test_server_static_profile_data_script_is_served():
    from applications.server import SERVER

    client = TestClient(SERVER(Mock()).app)
    response = client.get('/static/profile_data.js')

    assert response.status_code == 200
    assert 'window.ProfileDataPage' in response.text
    assert 'renderProfileData' in response.text


def test_chat_template_loads_chat_entry_utils_before_chat_script():
    from applications.server import SERVER

    client = TestClient(SERVER(Mock()).app)
    response = client.get('/chat')

    assert response.status_code == 200
    assert response.text.index('/static/chat_entry_utils.js') < response.text.index('/static/chat.js')


def test_profile_template_loads_chat_entry_utils_before_profile_script():
    from applications.server import SERVER

    client = TestClient(SERVER(Mock()).app)
    response = client.get('/profile')

    assert response.status_code == 200
    assert response.text.index('/static/chat_entry_utils.js') < response.text.index('/static/profile_data.js')


def test_state_message_persists_structured_chat_payload():
    from mediator.state import State

    state = State()
    state.message({
        'sender': 'Bot:',
        'message': 'Do you have the termination email?',
        'question': 'Do you have the termination email?',
        'inquiry': {'priority': 'Critical'},
        'explanation': {'summary': 'Critical missing support gap'},
    })

    saved = next(iter(state.data['chat_history'].values()))

    assert saved['message'] == 'Do you have the termination email?'
    assert saved['question'] == 'Do you have the termination email?'
    assert saved['inquiry']['priority'] == 'Critical'
    assert saved['explanation']['summary'] == 'Critical missing support gap'


def test_state_normalize_chat_history_upgrades_legacy_string_entries():
    from mediator.state import State

    state = State()

    normalized = state.normalize_chat_history({
        '2026-03-07 12:00:00': 'Legacy bot message',
    })

    saved = normalized['2026-03-07 12:00:00']
    assert saved['message'] == 'Legacy bot message'
    assert saved['question'] == 'Legacy bot message'


def test_state_load_profile_normalizes_chat_history_entries():
    from mediator.state import State

    state = State()

    class DummyResponse:
        text = '{"data": {"chat_history": {"2026-03-07 12:00:00": "Legacy bot message"}}}'

    original_post = __import__('requests').post
    try:
        __import__('requests').post = lambda *args, **kwargs: DummyResponse()
        result = state.load_profile({
            'results': {
                'hashed_username': 'user-123',
                'hashed_password': 'pw-123',
            }
        })
    finally:
        __import__('requests').post = original_post

    assert result['chat_history']['2026-03-07 12:00:00']['message'] == 'Legacy bot message'
    assert result['chat_history']['2026-03-07 12:00:00']['question'] == 'Legacy bot message'


def test_state_extract_chat_history_context_strings_uses_structured_fields():
    from mediator.state import State

    state = State()
    state.data['chat_history'] = {
        '1': {
            'sender': 'user-123',
            'message': 'I was fired after reporting discrimination.',
        },
        '2': {
            'sender': 'Bot:',
            'message': 'Do you have the termination email?',
            'question': 'Do you have the termination email?',
            'explanation': {'summary': 'Critical missing support gap'},
        },
    }

    context = state.extract_chat_history_context_strings(limit=3)

    assert 'I was fired after reporting discrimination.' in context
    assert 'Do you have the termination email?' in context


def test_extract_chat_history_context_strings_from_state_handles_invalid_helper_and_structured_entries():
    from mediator.state import extract_chat_history_context_strings_from_state

    mock_state = type('MockState', (), {})()
    mock_state.extract_chat_history_context_strings = lambda limit=3: 'not-a-list'
    mock_state.data = {
        'chat_history': {
            '1': {
                'sender': 'user-123',
                'message': 'The employer admitted retaliation in writing.',
                'question': 'Do you have that email?',
            }
        }
    }

    context = extract_chat_history_context_strings_from_state(mock_state, limit=3)

    assert 'The employer admitted retaliation in writing.' in context
    assert 'Do you have that email?' in context
    assert not any('{\'sender\':' in item for item in context)


def test_state_append_chat_history_syncs_chat_history_and_last_message():
    from mediator.state import State

    state = State()
    state.append_chat_history({
        'sender': 'Bot:',
        'message': 'Do you have the termination email?',
        'question': 'Do you have the termination email?',
    })

    assert state.chat_history == state.data['chat_history']
    assert state.last_message == 'Do you have the termination email?'


def test_state_load_profile_syncs_chat_history_and_last_message():
    from mediator.state import State

    state = State()

    class DummyResponse:
        text = '{"data": {"chat_history": {"2026-03-07 12:00:00": {"message": "Structured bot message", "question": "Structured bot message"}}}}'

    original_post = __import__('requests').post
    try:
        __import__('requests').post = lambda *args, **kwargs: DummyResponse()
        state.load_profile({
            'results': {
                'hashed_username': 'user-123',
                'hashed_password': 'pw-123',
            }
        })
    finally:
        __import__('requests').post = original_post

    assert state.chat_history == state.data['chat_history']
    assert state.last_message == 'Structured bot message'


def test_server_websocket_chat_broadcasts_structured_payloads():
    from applications.server import SERVER

    mediator = Mock()
    mediator.get_current_inquiry_payload.return_value = {
        'question': 'Please describe what happened.',
        'inquiry': {'question': 'Please describe what happened.', 'priority': 'High'},
        'explanation': {'summary': 'Needed to establish the core complaint facts.'},
    }
    mediator.io_payload.return_value = {
        'message': 'Do you have the termination email?',
        'question': 'Do you have the termination email?',
        'inquiry': {'question': 'Do you have the termination email?', 'priority': 'Critical'},
        'explanation': {'summary': 'Critical missing support gap'},
    }
    mediator.state.load_profile = Mock()
    mediator.state.message = Mock()
    mediator.state.store_profile = Mock()

    client = TestClient(SERVER(mediator).app)

    client.cookies.update(
        {
            'token': 'test-token',
            'hashed_username': 'user-123',
            'hashed_password': 'pw-123',
        }
    )

    with client.websocket_connect('/api/chat') as websocket:
        initial = websocket.receive_json()
        assert initial['message'] == 'Please state your legal complaint'
        assert initial['question'] == 'Please describe what happened.'
        assert initial['explanation']['summary'] == 'Needed to establish the core complaint facts.'
        assert initial['hashed_username'] == 'user-123'

        websocket.send_json({'message': 'I was fired after reporting discrimination.'})

        echoed_user = websocket.receive_json()
        assert echoed_user['sender'] == 'user-123'
        assert echoed_user['message'] == 'I was fired after reporting discrimination.'
        assert echoed_user['question'] == 'I was fired after reporting discrimination.'
        assert echoed_user['hashed_username'] == 'user-123'

        bot_reply = websocket.receive_json()
        assert bot_reply['sender'] == 'Bot:'
        assert bot_reply['message'] == 'Do you have the termination email?'
        assert bot_reply['question'] == 'Do you have the termination email?'
        assert bot_reply['inquiry']['priority'] == 'Critical'
        assert bot_reply['explanation']['summary'] == 'Critical missing support gap'
        assert bot_reply['hashed_username'] == 'user-123'

    mediator.state.load_profile.assert_called_once()
    assert mediator.state.message.call_count == 2
    mediator.state.store_profile.assert_called_once()