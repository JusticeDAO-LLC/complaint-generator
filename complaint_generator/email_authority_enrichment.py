from __future__ import annotations

from integrations.ipfs_datasets.legal_data import legal_module

_email_authority_enrichment = legal_module("email_authority_enrichment")

Mediator = _email_authority_enrichment.Mediator

build_email_authority_query_plan = _email_authority_enrichment.build_email_authority_query_plan
build_seed_authority_catalog = _email_authority_enrichment.build_seed_authority_catalog


def enrich_email_timeline_authorities(*args, **kwargs):
    original_mediator = _email_authority_enrichment.Mediator
    _email_authority_enrichment.Mediator = Mediator
    try:
        return _email_authority_enrichment.enrich_email_timeline_authorities(*args, **kwargs)
    finally:
        _email_authority_enrichment.Mediator = original_mediator


__all__ = [
    "Mediator",
    "build_email_authority_query_plan",
    "build_seed_authority_catalog",
    "enrich_email_timeline_authorities",
]
