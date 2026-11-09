from unittest.mock import Mock, call

import pytest

from mediator.legal_authority_hooks import LegalAuthoritySearchHook


pytestmark = pytest.mark.no_auto_network


def test_archive_domain_failure_is_logged_without_stopping_other_domains():
    mediator = Mock()
    mediator.log = Mock()
    hook = LegalAuthoritySearchHook.__new__(LegalAuthoritySearchHook)
    hook.mediator = mediator
    hook._collect_search_diagnostics = Mock(return_value={})

    error = RuntimeError("archive backend unavailable")
    recovered_result = {
        "title": "Recovered legal authority",
        "url": "https://law.justia.com/example",
    }
    hook.search_web_archives = Mock(
        side_effect=[error, [recovered_result], []],
    )

    results = hook.search_all_sources(
        "housing voucher hearing",
        authority_families=["agency_guidance"],
    )

    assert results["web_archives"] == [recovered_result]
    assert hook.search_web_archives.call_args_list == [
        call("law.cornell.edu", query="housing voucher hearing", max_results=3),
        call("law.justia.com", query="housing voucher hearing", max_results=3),
        call("findlaw.com", query="housing voucher hearing", max_results=3),
    ]
    mediator.log.assert_any_call(
        "legal_authority_search_error",
        search_type="web_archive",
        domain="law.cornell.edu",
        query="housing voucher hearing",
        error_type="RuntimeError",
        error="archive backend unavailable",
    )
