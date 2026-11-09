"""Real Chromium privacy boundaries in the actual conversation inbox."""
import pytest

from tests.test_cimp_gui_44 import (
    _world, _seed, _browser, _sign_in, _open, _message_texts,
    OWNER_CREDENTIAL, STRANGER_CREDENTIAL, PAGE_ONE,
)

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _opened(tmp_path, monkeypatch):
    world = _world(tmp_path)
    seed = _seed(world)
    return world, seed


def test_typing_a_different_case_clears_old_inbox_before_blur(tmp_path, monkeypatch):
    world, seed = _opened(tmp_path, monkeypatch)
    with _browser(tmp_path, monkeypatch, world.app) as session:
        page = session.pages["owner"]
        _sign_in(page, OWNER_CREDENTIAL)
        _open(page, seed, poll="120000")
        page.wait_for_function("document.querySelectorAll('#message-list .message-text').length === 2")
        assert _message_texts(page) == list(PAGE_ONE)
        page.fill("#case-id", "different-case-with-no-authority")
        assert _message_texts(page) == [], "Private rows remained visible under a different case selector."
        assert page.locator("#unread-count").inner_text() == "Unread 0"


def test_signing_in_as_stranger_never_retains_previous_actor_inbox(tmp_path, monkeypatch):
    world, seed = _opened(tmp_path, monkeypatch)
    with _browser(tmp_path, monkeypatch, world.app) as session:
        page = session.pages["owner"]
        _sign_in(page, OWNER_CREDENTIAL)
        _open(page, seed, poll="120000")
        page.wait_for_function("document.querySelectorAll('#message-list .message-text').length === 2")
        page.fill("#inbox-credential", STRANGER_CREDENTIAL)
        # Start and wait for the actual login+case-list response, without a
        # navigation/reload that would trivially discard the private DOM.
        with page.expect_response(lambda response: response.url.endswith('/api/cases') and response.request.method == 'GET'):
            page.click("#inbox-login button[type=submit]")
        assert _message_texts(page) == [], "The previous actor's private conversation survived identity replacement."
        assert not any(text in page.locator('body').inner_text() for text in PAGE_ONE)


def test_actual_cookie_logout_then_refresh_clears_private_rows_and_counters(tmp_path, monkeypatch):
    world, seed = _opened(tmp_path, monkeypatch)
    with _browser(tmp_path, monkeypatch, world.app) as session:
        page = session.pages["owner"]
        with page.expect_response(lambda response: response.url.endswith('/api/complaint-workspace/auth/login')) as login:
            _sign_in(page, OWNER_CREDENTIAL)
        csrf = login.value.json()["csrf_token"]
        _open(page, seed, poll="120000")
        page.wait_for_function("document.querySelectorAll('#message-list .message-text').length === 2")
        logged_out = page.evaluate("""async (csrf) => {
            const response = await fetch('/api/complaint-workspace/auth/logout', {
                method:'POST', credentials:'same-origin', headers:{'x-csrf-token':csrf}});
            return response.status;
        }""", csrf)
        assert logged_out == 200
        page.click("#refresh-messages")
        page.wait_for_function("document.querySelector('#inbox-auth-status').textContent === 'Sign in required'")
        assert _message_texts(page) == []
        assert page.locator("#thread-list").inner_text() == ""
        assert page.locator("#unread-count").inner_text() == "Unread 0"
        assert page.locator("#page-meta").inner_text() == ""


def test_real_successful_old_page_cannot_repaint_after_case_input_changes(tmp_path, monkeypatch):
    world, seed = _opened(tmp_path, monkeypatch)
    with _browser(tmp_path, monkeypatch, world.app) as session:
        page = session.pages["owner"]
        _sign_in(page, OWNER_CREDENTIAL)
        # Hold only delivery of a genuine authorized HTTP200 Response. Neither
        # its API body nor its server authorization is fabricated or replaced.
        page.evaluate("""() => {
            const actualFetch = window.fetch;
            window.oldPageHeld = false; window.oldPageReadComplete = false;
            let release;
            const gate = new Promise(resolve => { release = resolve; });
            window.releaseOldPage = release;
            window.fetch = async (...args) => {
                const response = await actualFetch(...args);
                if (String(args[0]).includes('/messages?')) {
                    window.oldPageStatus = response.status;
                    window.oldPageHeld = true;
                    await gate;
                    const actualJson = response.json.bind(response);
                    response.json = async () => {
                        const payload = await actualJson();
                        // A timer after fulfillment lets the real queued
                        // request handler finish all its promise continuations.
                        setTimeout(() => { window.oldPageReadComplete = true; }, 0);
                        return payload;
                    };
                }
                return response;
            };
        }""")
        _open(page, seed, poll="120000")
        page.wait_for_function("window.oldPageHeld === true")
        assert page.evaluate("window.oldPageStatus") == 200
        page.fill("#case-id", "different-case-no-authority")
        page.evaluate("window.releaseOldPage()")
        page.wait_for_function("window.oldPageReadComplete === true")
        assert _message_texts(page) == []
        assert not any(text in page.locator('body').inner_text() for text in PAGE_ONE)
        assert page.locator("#unread-count").inner_text() == "Unread 0"
