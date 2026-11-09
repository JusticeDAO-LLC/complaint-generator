"""Current owner reports must bind their verified source, not incidental text."""
from types import SimpleNamespace
import pytest
from applications.legal_analysis_api import bind_case_definition_correspondence
from tests.test_cimp_gui_30 import _bundle, _populations, LEGAL_SOURCE

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_genuine_different_source_owner_reports_do_not_bind_selected_metadata_decoy():
    bundle = _bundle()
    genuine = bind_case_definition_correspondence(SimpleNamespace(intake_case_file={}), {
        'source_text':LEGAL_SOURCE, 'request_id':'synthetic-real-source-control',
        'declared_populations':_populations(), **bundle})
    assert genuine['status'] == 'bound'
    assert all(row['genuine_current_owner_receipt'] is True for row in genuine['owners'].values())
    # This is an occurrence population pointer in the authenticated replay
    # metadata. It is not the source text used by any of the actual Data owners.
    decoy = '/occurrences/0/anchor'
    assert decoy != LEGAL_SOURCE and decoy not in LEGAL_SOURCE
    unrelated = bind_case_definition_correspondence(SimpleNamespace(intake_case_file={}), {
        'source_text':decoy, 'request_id':'synthetic-metadata-decoy-source',
        'declared_populations':_populations(), **bundle})
    assert unrelated['status'] != 'bound', 'incidental_metadata_promoted_to_current_source_basis'
    assert all(row['source_bound'] is False for row in unrelated['owners'].values())
    assert unrelated['authorizes_law'] is False and unrelated['proof'] is False
