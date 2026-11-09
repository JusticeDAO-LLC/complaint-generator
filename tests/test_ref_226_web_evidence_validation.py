"""Focused regression coverage for REF-226."""

from unittest.mock import Mock

from mediator.web_evidence_hooks import WebEvidenceSearchHook


def test_relevance_assessment_failure_is_logged_and_uses_source_score():
    mediator = Mock()
    mediator.query_backend.side_effect = RuntimeError('relevance backend unavailable')
    hook = WebEvidenceSearchHook.__new__(WebEvidenceSearchHook)
    hook.mediator = mediator

    validation = hook.validate_evidence({
        'title': 'Archived policy',
        'url': 'https://example.com/policy',
        'content': 'Policy text',
        'source_type': 'common_crawl',
    })

    assert validation['valid'] is True
    assert validation['relevance_score'] == 0.6
    assert validation['recommendations'] == []
    mediator.log.assert_called_once_with(
        'web_evidence_relevance_assessment_error',
        error='relevance backend unavailable',
        error_type='RuntimeError',
        source_type='common_crawl',
        url='https://example.com/policy',
        fallback_relevance_score=0.6,
    )
