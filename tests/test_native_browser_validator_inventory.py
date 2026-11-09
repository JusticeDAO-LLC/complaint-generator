"""Kernel-backed cleanup inventory isolation between actual Node validators."""
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _actual_validator(connection):
    from tests import gui_native_browser as browser

    assert browser.probe_inherited_network_denial()["af_unix_only"]
    owner_pid = os.getpid()
    owner_birth = browser._process_birth(owner_pid)
    node, _chromium = browser.pin_executables()
    os.environ["PLAYWRIGHT_NODEJS_PATH"] = node.path
    playwright = None
    observed = set()
    try:
        playwright = browser._load_sync_playwright()().start()
        nodes = [pid for pid, (parent, argv, _exe) in browser._process_table().items()
                 if parent == owner_pid and tuple(argv) == node.argv]
        assert len(nodes) == 1
        node_pid = nodes[0]
        node_birth = browser._pinned_process(node_pid, node)
        assert node_birth[0] == owner_pid
        observed.add(node_pid)
        connection.send({"phase": "ready", "owner": owner_pid, "node": node_pid})
        assert connection.poll(20) and connection.recv() == "observe"
        matches = browser._matching_pids((node.argv[1],))
        assert browser._pinned_process(node_pid, node) == node_birth
        assert browser._process_birth(owner_pid) == owner_birth
        connection.send({"phase": "observed", "owner": owner_pid, "node": node_pid,
                         "matches": sorted(matches)})
        assert connection.poll(20) and connection.recv() == "close"
    finally:
        if playwright is not None:
            playwright.stop()
        assert browser._wait_for_cleanup(observed)["cleaned"]
        connection.close()


def test_real_node_inventory_is_confined_to_its_current_validator():
    """Shared driver argv cannot put a sibling validator in our cleanup set."""
    from tests import gui_native_browser as browser

    assert browser.probe_inherited_network_denial()["af_unix_only"]
    context = multiprocessing.get_context("fork")
    children, channels, observations = [], [], []
    try:
        for _ in range(2):
            parent, child = context.Pipe()
            process = context.Process(target=_actual_validator, args=(child,))
            process.start()
            child.close()
            children.append(process)
            channels.append(parent)
        ready = []
        for channel in channels:
            assert channel.poll(20), "actual Node validator did not start"
            item = channel.recv()
            assert item["phase"] == "ready"
            ready.append(item)
        assert ready[0]["node"] != ready[1]["node"]
        assert ready[0]["owner"] != ready[1]["owner"]
        for channel in channels:
            channel.send("observe")
        for channel in channels:
            assert channel.poll(20), "actual Node inventory did not return"
            item = channel.recv()
            assert item["phase"] == "observed"
            observations.append(item)
    finally:
        for channel in channels:
            try:
                channel.send("close")
            except (BrokenPipeError, EOFError):
                pass
        for process in children:
            process.join(timeout=20)
        for channel in channels:
            channel.close()
        assert all(not process.is_alive() and process.exitcode == 0 for process in children)
    assert len(observations) == 2
    assert all(item["matches"] == [item["node"]] for item in observations)
