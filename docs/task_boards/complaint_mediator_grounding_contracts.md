# Grounding role handoff contract

Contract version: `mediator.grounding.role_handoff.v1`

This is a small cross-hook handoff in `mediator/integrations/contracts.py`. It names seven roles and the references a later hook may carry. It does not replace the user-assertion envelope, the dependency graph, interview stop behavior, or any supervisor framework.

## Preserved contracts

| Ref | Owner |
| --- | --- |
| `user_assertion.v1` | `integrations.ipfs_datasets.types.UserAssertionEnvelope` |
| `complaint_phases.dependency_graph.v1.0` | `complaint_phases.dependency_graph.DependencyGraph` metadata version `1.0` |
| `mediator.inquiries.unresolved_target.v1` | Existing unresolved-target / stop behavior on inquiries |

A handoff stamps those refs. A payload that embeds a replacement `assertion_envelope`, `dependency_graph`, or `stop_policy`, or that names a different ref, is rejected. Retrieval records (`NormalizedRetrievalRecord`) stay score-ranked annotations and are not role records.

## Roles

| Role | What it is | Governing law |
| --- | --- | --- |
| `user_assertion` | Pointer to a user statement already admitted by the assertion envelope | Never |
| `extracted_candidate` | Extractor output that is not yet a user assertion | Never |
| `retrieved_public_law` | Retrieved public-law source | Only when `source_decision=admitted` and `edition_decision=pinned`, with source id, version, byte span, and sha256 |
| `applicable_requirement` | Host applicability decision for a requirement | Never the statute text |
| `corroborating_evidence` | Support linked by `corroborates_ref` | Never |
| `conditional_ir` | Conditional intermediate representation status | Never, and not a proof |
| `proof_result` | Actual proof outcome supplied by the caller | Never marked verified or satisfied here |

Omitted `source_decision`, `edition_decision`, `applicability_decision`, and `meaning_decision` stay `unknown`. They are not inferred from a retrieval score or from a user statement.

## References

Every admitted record carries `owner_id`, `case_id`, `source_id`, `source_version`, `span_start`, `span_end`, `content_hash`, and `graph_revision`. Empty owner, case, or graph revision fails closed. An unknown source may omit source id, version, span, and hash. An admitted source must include all four. Spans are byte offsets. Raw prompt, passage, and source text are not handoff fields.

`retrieval_score` is allowed only on `extracted_candidate` and `retrieved_public_law`. `retrieval_score_governs` is always false.

## Proof and conditional IR

`proof_result` with no `actual_proof_outcome` is `unavailable`. Allowed outcomes are `unavailable`, `not_run`, `failed`, and `proved`. `proved` requires a caller-supplied `proof_receipt_ref`. This contract does not mint a receipt, set `verified`, or set `satisfied`.

`conditional_ir` statuses are `unavailable`, `not_compiled`, `conditional`, and `failed`. Conditional IR does not fill `actual_proof_outcome`.

Keys `verified`, `satisfied`, and their aliases are spoofed flags. The admission reason is `spoofed_<flag>_flag` and no record is returned.

## Examples

Synthetic payloads live in `grounding_role_examples()`.

- A user assertion with no decision fields admits with all four decisions `unknown` and `governs_law` false.
- The same shape plus `verified: true` rejects as `spoofed_verified_flag`.
- An applicable-requirement shape plus `satisfied: true` rejects as `spoofed_satisfied_flag`.
- Public law with `retrieval_score: 0.99` and an unknown edition admits and does not govern.
- Public law with an admitted source, pinned edition, span, and hash governs. The score is not the reason.
- `governs_law: true` on a user assertion rejects as `user_statement_cannot_govern`.
- A proof role with no outcome admits as `unavailable`.
- Conditional IR status `conditional` admits with an empty proof outcome.
