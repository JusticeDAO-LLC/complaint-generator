"""Attach current source-sampling context and contextual definition evidence.

Cases are synthetic private fixtures. No test is skipped. Context preparation
calls the current sampling and definition owners. A replay does not grant
applicability, truth, training, graph, or proof authority.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from integrations.ipfs_datasets import definition_evidence
from ipfs_datasets_py.logic.autoformal import corpus_definition_review_v2 as definition_review
from ipfs_datasets_py.logic.autoformal import legal_graph_dependencies as dependencies
from ipfs_datasets_py.logic.autoformal import legal_official_source_custody as custody
from ipfs_datasets_py.logic.autoformal import legal_source_definition_bridge_v2 as bridge
from ipfs_datasets_py.logic.autoformal import legal_source_sampling as sampler
from ipfs_datasets_py.logic.autoformal import legal_source_sampling_review as intake
from ipfs_datasets_py.logic.autoformal import legal_statutory_context_v2 as statutory_context
from tests.mgnd_fixtures import CASE_LABELS, meaningful_cases


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_DENIED = ("applicability", "truth", "training", "graph", "proof")


def _wire(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _transport(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False,
    ).encode("utf-8") + b"\n"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value) -> str:
    return _sha(_wire(value))


def _html(edition: int, body: str) -> bytes:
    return (
        '<html><head><meta charset="utf-8"><title>Fictional source</title></head><body>'
        f"<span>{edition} cafe metadata</span><!-- field-start:head -->"
        '<h3 class="section-head">§1. Authored definition</h3><!-- field-end:head -->'
        "<!-- field-start:statute -->"
        '<p class="statutory-body">(a) In this title:</p>'
        + body
        + '<p class="statutory-body-block-1em">Such term includes a condition.</p>'
        '<p class="statutory-body">(b) Later authored body.</p>'
        "<!-- field-end:statute --><!-- field-start:notes -->"
        '<!-- field-start:miscellaneous-note --><h4 class="note-head">Editorial Notes</h4>'
        '<!-- field-end:miscellaneous-note --><p class="note-body">Authored control.</p>'
        "<!-- field-end:notes --></body></html>"
    ).encode()


def _source(edition: int, body: str) -> dict:
    raw = _html(edition, body)
    url = (
        f"https://www.govinfo.gov/content/pkg/USCODE-{edition}-title10/html/"
        f"USCODE-{edition}-title10-chap1-sec1.htm"
    )
    descriptor = {
        "schema": custody.DESCRIPTOR_SCHEMA,
        "legal_id": "usc:us:10:1",
        "edition": edition,
        "package_id": f"USCODE-{edition}-title10",
        "granule_id": f"USCODE-{edition}-title10-chap1-sec1",
        "url": url,
        "retrieved_at": "2026-10-15T01:00:00Z",
        "raw_sha256": _sha(raw),
        "raw_bytes": len(raw),
        "http_provenance": {
            "requested_url": url,
            "final_url": url,
            "status_code": 200,
            "content_type": "text/html",
            "etag": None,
            "last_modified": None,
        },
    }
    replay = {
        "descriptor": descriptor,
        "expected_descriptor_sha256": custody.acquisition_descriptor_sha256(descriptor),
        "expected_raw_sha256": descriptor["raw_sha256"],
        "expected_raw_bytes": len(raw),
    }
    sampling = sampler.prepare_source_sampling(raw, **replay)
    replay["expected_sampling_report_sha256"] = sampler.source_sampling_report_sha256(sampling)
    bundle = intake.prepare_sampling_review_bundle(raw, **replay)
    return {
        "bundle": bundle,
        "raw": raw,
        "expected_bundle_sha256": _digest(bundle),
        "replay_inputs": replay,
    }


def _span_text(entry, guide) -> str:
    records = {row["record_cid"]: row for row in entry["bundle"]["sampling_report"]["records"]}
    return records[guide["source_occurrence_ref"]["record_cid"]]["span_text"]


def _guide(entry, prefix: str) -> dict:
    return next(guide for guide in entry["bundle"]["guides"] if _span_text(entry, guide).startswith(prefix))


def _attachment(target, target_guide, supporting, supporting_guide, role: str) -> dict:
    return {
        "target_bundle_sha256": target["expected_bundle_sha256"],
        "target_subject_ref": deepcopy(target_guide["subject_ref"]),
        "supporting_bundle_sha256": supporting["expected_bundle_sha256"],
        "supporting_subject_ref": deepcopy(supporting_guide["subject_ref"]),
        "role": role,
    }


def _full_ref(record) -> dict:
    return {"record_cid": record["record_cid"], "schema": record["schema"], "sha256": _digest(record)}


def _request(entry) -> dict:
    sampling = entry["bundle"]["sampling_report"]
    text = sampling["document_view_report"]["document"]["document_text"]
    records = {row["record_cid"]: row for row in sampling["records"]}
    units = [row for row in records.values() if row["schema"] == sampler.UNIT_SCHEMA]

    def unit_text(unit):
        return records[unit["source_occurrence_ref"]["record_cid"]]["span_text"]

    def span(literal: str) -> dict:
        at = text.index(literal)
        return {"char_start": at, "char_end": at + len(literal), "text": literal}

    scope = next(unit for unit in units if unit_text(unit) == "(a) In this title:")
    head = next(unit for unit in units if unit_text(unit).startswith('(1) The term "café filer"'))
    return {
        "schema": bridge.REQUEST_SCHEMA,
        "profile": bridge.PROFILE,
        "family": "fol",
        "declaration": {
            "declaration_id": "authored-widget-definition",
            "interpretation_status": "unreviewed_caller_declaration",
            "source_version_ref": head["source_version_ref"],
            "normalized_view_id": head["normalized_view_id"],
            "contributor_unit_refs": [_full_ref(head)],
            "scope_unit_ref": _full_ref(scope),
            "scope_span": span("In this title:"),
            "head": span("café filer"),
            "definition_cue": span("means"),
            "body": {
                "op": "all",
                "operands": [
                    {"op": "atom", "span": span("registered")},
                    {
                        "op": "any",
                        "operands": [
                            {"op": "atom", "span": span("active")},
                            {"op": "not", "operand": {"op": "atom", "span": span("exempt")}},
                        ],
                    },
                ],
            },
            "applicability": {
                "scope_kind": "title",
                "scope_id": "authored-title10-scope",
                "jurisdiction_id": "us",
                "instrument_id": "usc:us:10",
                "legal_as_of_civil_date": None,
                "source_edition": entry["replay_inputs"]["descriptor"]["edition"],
                "source_release_id": records[head["source_version_ref"]["record_cid"]]["release_id"],
            },
        },
    }


def _declaration(entry, guide, packet, *, cite: bool) -> dict:
    value = deepcopy(guide["response_template"])
    value["bundle_sha256"] = entry["expected_bundle_sha256"]
    value["reviewer_declaration"] = {
        "principal_id": "synthetic-reviewer-not-a-real-person",
        "role": "source_reviewer",
        "issued_at_utc": "2026-10-15T01:00:00Z",
        "identity_evidence_refs": [],
        "independence_evidence_refs": [],
    }
    value["exposure_declaration"] = {
        "candidate_interpretations_exposed": True,
        "organizer_source_metadata_exposed": True,
        "other_exposure": ["Synthetic private fixture. No admitted meaning."],
    }
    attached = next(
        row for row in packet["attachments"]
        if row["nomination"]["target_bundle_sha256"] == entry["expected_bundle_sha256"]
        and row["nomination"]["target_subject_ref"] == guide["subject_ref"]
    )
    refs = deepcopy(attached["evidence_refs"][:1]) if cite else []
    for field, disposition in (("source_answers", "evidence_declared"), ("meaning_proposals", "proposal")):
        for answer in value[field]:
            answer.update(
                disposition=disposition if cite else "unresolved",
                finding="Synthetic declaration, not an admitted source or meaning finding.",
                rationale="Exercise the context owner with authored fictional text.",
                evidence_refs=deepcopy(refs) if cite else [],
                unresolved_requirements=[] if cite else ["Independent meaning review is absent."],
            )
    return value


def _assert_no_grant(envelope: dict) -> None:
    assert envelope["fabricated"] is False
    assert envelope["legal_review_completed"] is False
    assert envelope["training_mask"] == 0
    assert envelope["evaluation_gold_mask"] == 0
    for key in _DENIED:
        assert envelope["authority_granted"][key] is False
    assert envelope["applicability_granted"] is False
    assert envelope["truth_granted"] is False
    assert envelope["training_authority_granted"] is False
    assert envelope["graph_authority_granted"] is False
    assert envelope["proof_authority_granted"] is False
    authority = envelope["owner_authority"]
    if authority is not None:
        assert authority
        assert all(value is False for value in authority.values())


def _populations():
    definition = _source(
        2024,
        '<p class="statutory-body-1em">(1) The term "café filer" means '
        "registered and either active or not exempt.</p>",
    )
    use = _source(
        2023,
        '<p class="statutory-body-1em">(1) A café filer may submit a fictional request.</p>',
    )
    assert definition["expected_bundle_sha256"] != use["expected_bundle_sha256"]
    definition_head = _guide(definition, '(1) The term "café filer"')
    scope = _guide(definition, "(a) In this title:")
    use_guide = _guide(use, "(1) A café filer may submit")
    attachments = [
        _attachment(definition, definition_head, use, use_guide, "fictional support nomination"),
        _attachment(definition, scope, use, use_guide, "fictional scope nomination"),
        _attachment(use, use_guide, definition, definition_head, "fictional related-use nomination"),
    ]
    return definition, use, definition_head, scope, use_guide, attachments


def _review_inputs(binding_envelope, definition, use, request_raw, context, responses, attachments):
    binding = binding_envelope["result"]
    base = binding["base_binding"]
    sampling = definition["bundle"]["sampling_report"]
    descriptor = definition["replay_inputs"]["descriptor"]
    candidate_inputs = {
        "candidate_raw": _transport(base["candidate"]),
        "report_raw": _wire(base["definition_report"]),
        "request_raw": request_raw,
        "raw_html": definition["raw"],
        "sampling_report_raw": _transport(sampling),
        "descriptor_raw": _transport(descriptor),
    }
    pins = {
        "candidate_sha256": _sha(candidate_inputs["candidate_raw"]),
        "candidate_cid": base["candidate"]["record_cid"],
        "graph_cid": base["candidate"]["graph"]["record_cid"],
        "request_sha256": _sha(request_raw),
        "report_sha256": _sha(candidate_inputs["report_raw"]),
        "raw_sha256": _sha(definition["raw"]),
        "raw_bytes": len(definition["raw"]),
        "extracted_sha256": base["candidate"]["source_version"]["extracted_view"]["sha256"],
        "sampling_report_sha256": _sha(candidate_inputs["sampling_report_raw"]),
        "sampling_report_full_canonical_sha256": definition["replay_inputs"]["expected_sampling_report_sha256"],
        "descriptor_sha256": _sha(candidate_inputs["descriptor_raw"]),
        "descriptor_full_canonical_sha256": definition["replay_inputs"]["expected_descriptor_sha256"],
    }
    trusted = {
        "descriptor": descriptor,
        "expected_descriptor_sha256": definition["replay_inputs"]["expected_descriptor_sha256"],
        "expected_raw_sha256": definition["replay_inputs"]["expected_raw_sha256"],
        "expected_raw_bytes": definition["replay_inputs"]["expected_raw_bytes"],
    }
    packets, population = [], []
    for occurrence in base["candidate"]["source_occurrences"]:
        packet = statutory_context.build_context_packet_v2(
            sampling["document_view_report"],
            definition["raw"],
            char_start=occurrence["start_char"],
            char_end=occurrence["end_char"],
            expected_report_sha256=sampling["document_view_report_sha256"],
            **trusted,
        )
        raw = _wire(packet)
        packets.append({
            "source_occurrence_cid": occurrence["record_cid"],
            "packet_raw": raw,
            "dependency_requests": None,
        })
        population.append({"source_occurrence_cid": occurrence["record_cid"], "packet_sha256": _sha(raw)})
    preparation = definition_review.prepare_definition_review_evidence_v2(
        candidate_inputs,
        expected_candidate_pin=pins,
        context_inputs=packets,
        expected_context_population=population,
    )
    manifest = dependencies.build_dependency_manifest(
        preparation["artifacts"],
        preparation["edges"],
        expected_artifact_ids=preparation["expected_artifact_ids"],
    )
    subject = definition_review.build_definition_review_subject_v2(
        preparation,
        manifest,
        candidate_inputs=candidate_inputs,
        expected_candidate_pin=pins,
        context_inputs=packets,
        expected_context_population=population,
        expected_manifest_sha256=manifest["manifest_sha256"],
        required_dependency_ids=preparation["expected_artifact_ids"],
    )
    replay = {
        "request_raw": request_raw,
        "context": context,
        "responses": responses,
        "sources": [definition, use],
        "attachments": attachments,
        "expected_request_sha256": _sha(request_raw),
        "expected_definition_bundle_sha256": definition["expected_bundle_sha256"],
        "expected_context_sha256": _digest(context),
        "expected_response_sha256s": [_digest(row) for row in responses],
        "expected_attachments_sha256": _digest(attachments),
    }
    return subject, candidate_inputs, pins, packets, population, manifest, preparation["expected_artifact_ids"], replay


@pytest.fixture(scope="module")
def authored():
    definition, use, definition_head, scope, use_guide, attachments = _populations()
    prepared = definition_evidence.prepare_sampling_review_context(
        [definition, use], attachments, expected_attachments_sha256=_digest(attachments),
    )
    assert prepared["status"] == "replayed", prepared["reason"]
    context = prepared["result"]
    request = _request(definition)
    request_raw = _transport(request)
    direct = _declaration(definition, definition_head, context, cite=True)
    scope_declaration = _declaration(definition, scope, context, cite=True)
    responses = []
    declarations = []
    for declaration in (direct, scope_declaration):
        recorded = definition_evidence.record_sampling_review_context_response(
            context, declaration, [definition, use], attachments,
            expected_context_sha256=_digest(context),
            expected_declaration_sha256=_digest(declaration),
            expected_attachments_sha256=_digest(attachments),
        )
        assert recorded["status"] == "replayed", recorded["reason"]
        declarations.append(declaration)
        responses.append(recorded["result"])
    binding = definition_evidence.prepare_contextual_definition_binding(
        request_raw, context, responses, [definition, use], attachments,
        expected_request_sha256=_sha(request_raw),
        expected_definition_bundle_sha256=definition["expected_bundle_sha256"],
        expected_context_sha256=_digest(context),
        expected_response_sha256s=[_digest(row) for row in responses],
        expected_attachments_sha256=_digest(attachments),
    )
    assert binding["status"] == "replayed", binding["reason"]
    return {
        "definition": definition,
        "use": use,
        "definition_head": definition_head,
        "scope": scope,
        "use_guide": use_guide,
        "attachments": attachments,
        "context": context,
        "request_raw": request_raw,
        "direct": direct,
        "declarations": declarations,
        "responses": responses,
        "response": responses[0],
        "binding": binding,
    }


def test_meaningful_cases_are_nonempty():
    cases = meaningful_cases()
    assert cases
    assert tuple(case.label for case in cases) == CASE_LABELS
    assert all(case.case_id for case in cases)


def test_context_replay_keeps_unreviewed_supporting_sources(authored):
    definition, use = authored["definition"], authored["use"]
    attachments, context = authored["attachments"], authored["context"]
    validated = definition_evidence.validate_sampling_review_context(
        context, [definition, use], attachments,
        expected_context_sha256=_digest(context),
        expected_attachments_sha256=_digest(attachments),
    )
    assert validated["status"] == "replayed"
    assert validated["result"] == context
    assert validated["owner_function"] == "validate"
    _assert_no_grant(validated)
    assert validated["states"]["candidate"] == "not_a_definition_candidate"
    assert validated["states"]["source_review"] == "unreviewed"
    assert validated["states"]["meaning_review"] == "unreviewed"
    assert validated["population"]["source_count"] == 2
    assert validated["population"]["attachment_count"] == 3
    assert validated["population"]["unreviewed_supporting_subject_count"] >= 1
    summary = definition_evidence.summarize_sampling_review_context(
        context, authored["responses"], [definition, use], attachments,
        expected_context_sha256=_digest(context),
        expected_response_sha256s=[_digest(row) for row in authored["responses"]],
        expected_attachments_sha256=_digest(attachments),
    )
    assert summary["status"] == "replayed", summary["reason"]
    _assert_no_grant(summary)
    population = summary["result"]
    assert population["review_completed"] is False
    assert population["adjudication_performed"] is False
    assert population["subject_count"] == sum(len(item["bundle"]["guides"]) for item in (definition, use))
    assert any(not row["response_refs"] for row in population["subjects"])
    supporting = summary["population"]["unreviewed_supporting_subjects"]
    assert supporting
    assert all(row["bundle_sha256"] == use["expected_bundle_sha256"] for row in supporting)
    assert summary["states"]["source_review"] == "unreviewed"
    assert summary["states"]["meaning_review"] == "unreviewed"
    assert summary["states"]["candidate"] == "not_a_definition_candidate"
    checked = definition_evidence.validate_sampling_review_context_response(
        authored["response"], context, authored["direct"], [definition, use], attachments,
        expected_response_sha256=_digest(authored["response"]),
        expected_context_sha256=_digest(context),
        expected_declaration_sha256=_digest(authored["direct"]),
        expected_attachments_sha256=_digest(attachments),
    )
    assert checked["status"] == "replayed", checked["reason"]
    assert checked["bound_hashes"]["expected_declaration_sha256"] == _digest(authored["direct"])
    assert checked["states"]["meaning_review"] == "unreviewed"
    assert checked["states"]["meaning_dispositions"]
    assert "proposal" in checked["states"]["meaning_dispositions"]
    _assert_no_grant(checked)


def test_binding_and_review_keep_candidate_source_and_meaning_states(authored):
    definition, use = authored["definition"], authored["use"]
    attachments, context = authored["attachments"], authored["context"]
    responses, binding = authored["responses"], authored["binding"]
    assert binding["bound_hashes"]["expected_request_sha256"] == _sha(authored["request_raw"])
    assert binding["states"]["candidate"] != binding["states"]["meaning_review"]
    assert binding["states"]["meaning_review"] == "unreviewed_caller_declaration"
    assert binding["states"]["source_review"] in {"pending", "declarations_recorded", "unsupported", "disputed"}
    _assert_no_grant(binding)
    contextual = binding["result"]["contextual_binding"]
    assert contextual["related_declarations_close_definition_review"] is False
    assert contextual["declaration_prose_interpreted"] is False
    assert all(row["applicability_verified"] is False for row in contextual["required_support_nominations"])
    assert binding["population"]["unreviewed_supporting_subject_count"] >= 1
    validated = definition_evidence.validate_contextual_definition_binding(
        binding["result"], authored["request_raw"], context, responses, [definition, use], attachments,
        expected_binding_sha256=_digest(binding["result"]),
        expected_request_sha256=_sha(authored["request_raw"]),
        expected_definition_bundle_sha256=definition["expected_bundle_sha256"],
        expected_context_sha256=_digest(context),
        expected_response_sha256s=[_digest(row) for row in responses],
        expected_attachments_sha256=_digest(attachments),
    )
    assert validated["status"] == "replayed", validated["reason"]
    assert validated["result"] == binding["result"]
    _assert_no_grant(validated)

    subject, candidate_inputs, pins, packets, population, manifest, artifact_ids, replay = _review_inputs(
        binding, definition, use, authored["request_raw"], context, responses, attachments,
    )
    prepared = definition_evidence.prepare_contextual_definition_review(
        binding["result"], subject,
        expected_binding_sha256=_digest(binding["result"]),
        expected_subject_sha256=_digest(subject),
        contextual_replay_inputs=replay,
        candidate_inputs=candidate_inputs,
        expected_candidate_pin=pins,
        context_inputs=packets,
        expected_context_population=population,
        dependency_manifest=manifest,
        expected_manifest_sha256=manifest["manifest_sha256"],
        required_dependency_ids=artifact_ids,
    )
    assert prepared["status"] == "replayed", prepared["reason"]
    states = prepared["states"]
    assert states["candidate"] == "candidate"
    assert states["meaning_review"] == "pending"
    assert states["source_review"] != states["meaning_review"]
    assert states["meaning_assessment_created"] is False
    assert states["related_declarations_close_definition_review"] is False
    _assert_no_grant(prepared)
    checked = definition_evidence.validate_contextual_definition_review(
        prepared["result"], binding["result"], subject,
        expected_correspondence_sha256=_digest(prepared["result"]),
        expected_binding_sha256=_digest(binding["result"]),
        expected_subject_sha256=_digest(subject),
        contextual_replay_inputs=replay,
        candidate_inputs=candidate_inputs,
        expected_candidate_pin=pins,
        context_inputs=packets,
        expected_context_population=population,
        dependency_manifest=manifest,
        expected_manifest_sha256=manifest["manifest_sha256"],
        required_dependency_ids=artifact_ids,
    )
    assert checked["status"] == "replayed", checked["reason"]
    assert checked["result"] == prepared["result"]
    assert checked["states"]["meaning_review"] == "pending"
    assert checked["states"]["source_review"] == states["source_review"]
    _assert_no_grant(checked)


def test_malformed_context_and_missing_owner_stay_truthful(authored, monkeypatch):
    definition, use = authored["definition"], authored["use"]
    attachments = authored["attachments"]
    failed = definition_evidence.prepare_sampling_review_context(
        [definition, use], attachments, expected_attachments_sha256="0" * 64,
    )
    assert failed["status"] == "failed"
    assert failed["result"] is None
    assert failed["fabricated"] is False
    assert failed["applicability_granted"] is False
    assert failed["proof_authority_granted"] is False
    assert failed["reason"]

    mismatched = definition_evidence.prepare_contextual_definition_binding(
        authored["request_raw"], authored["context"], authored["responses"],
        [definition, use], attachments,
        expected_request_sha256="ab" * 32,
        expected_definition_bundle_sha256=definition["expected_bundle_sha256"],
        expected_context_sha256=_digest(authored["context"]),
        expected_response_sha256s=[_digest(row) for row in authored["responses"]],
        expected_attachments_sha256=_digest(attachments),
    )
    assert mismatched["status"] == "failed"
    assert mismatched["result"] is None
    assert mismatched["bound_hashes"]["expected_request_sha256"] == "ab" * 32
    assert mismatched["truth_granted"] is False

    monkeypatch.setattr(definition_evidence, "_context_module", None)
    monkeypatch.setattr(definition_evidence, "_binding_module", None)
    monkeypatch.setattr(definition_evidence, "_review_module", None)
    unavailable = definition_evidence.summarize_sampling_review_context(
        authored["context"], [], [definition, use], attachments,
        expected_context_sha256=_digest(authored["context"]),
        expected_response_sha256s=[],
        expected_attachments_sha256=_digest(attachments),
    )
    assert unavailable["status"] == "unavailable"
    assert unavailable["result"] is None
    assert unavailable["reason"] == "owner_unavailable"
    assert unavailable["fabricated"] is False
    assert unavailable["graph_authority_granted"] is False
    review = definition_evidence.prepare_contextual_definition_review(
        {}, {},
        expected_binding_sha256="cd" * 32,
        expected_subject_sha256="ef" * 32,
        contextual_replay_inputs={},
        candidate_inputs={},
        expected_candidate_pin={},
        context_inputs=[],
        expected_context_population=[],
        dependency_manifest={},
        expected_manifest_sha256="11" * 32,
        required_dependency_ids=[],
    )
    assert review["status"] == "unavailable"
    assert review["result"] is None
    assert review["training_authority_granted"] is False
