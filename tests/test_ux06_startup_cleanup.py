"""A failed custody assertion must close the actual private browser resources."""
import pytest

from tests import gui_native_browser as browser
from tests import test_cimp_ux_06 as entry
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


class InjectedStartupFailure(Exception):
    pass


def test_failed_real_browser_startup_closes_owned_processes_and_allows_later_start(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / 'world')
    failed_root, recovered_root = tmp_path / 'failed', tmp_path / 'recovered'
    failed_root.mkdir(mode=0o700)
    recovered_root.mkdir(mode=0o700)
    node, chromium = browser.pin_executables()
    actual_launch = browser._launch_context
    created = []
    observed = set()
    recovered = None

    def launch_and_observe(playwright, executable, profile, bridge):
        context = actual_launch(playwright, executable, profile, bridge)
        created.append((playwright, context))
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        table = browser._process_table()
        assert any(table.get(pid, (None, (), ''))[2] == node.path for pid in observed)
        assert any(table.get(pid, (None, (), ''))[2] == chromium.path for pid in observed)
        return context

    def fail_after_real_context(*_args):
        raise InjectedStartupFailure('explicit custody-stage failure after actual browser launch')

    try:
        with monkeypatch.context() as failure:
            failure.setattr(browser, '_launch_context', launch_and_observe)
            failure.setattr(browser, '_assert_process_custody', fail_after_real_context)
            with pytest.raises(InjectedStartupFailure, match='actual browser launch'):
                entry._open(failed_root, monkeypatch, world=world)
        assert created and observed
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup['cleaned'] and cleanup['remaining_pids'] == [], (
            'startup failure left the actual owned Node/Chromium processes alive', cleanup)

        # Real same-process recovery also detects a leaked Sync Playwright loop.
        recovered = entry._open(recovered_root, monkeypatch, world=world)
        page = recovered[1]
        response = page.goto(browser.SAME_ORIGIN + '/cases', wait_until='domcontentloaded')
        assert response.status == 200
        entry._shell_ready(page)
        assert page.locator('#complaint-case-shell').get_attribute('aria-busy') == 'false'
    finally:
        if recovered is not None:
            entry._close(*recovered[2:])
        # The red baseline must still reap only the handles it actually created.
        for playwright, context in reversed(created):
            try:
                context.close()
            except Exception:
                pass
            try:
                playwright.stop()
            except Exception:
                pass
        assert browser._wait_for_cleanup(observed)['remaining_pids'] == []
