"""
Adversarial Harness Module

Orchestrates multiple adversarial sessions with parallel execution.
"""

import logging
from typing import Dict, Any, List, Callable, Optional
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from collections import Counter
import csv
import json
from datetime import UTC, datetime
import os
import inspect
from copy import deepcopy

from .session import AdversarialSession, SessionResult
from .complainant import Complainant, ComplaintContext
from .critic import Critic
from .seed_complaints import SeedComplaintLibrary
from .hacc_evidence import build_hacc_mediator_evidence_packet

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in sorted(value, key=lambda item: str(item))]
    return value


def _sanitize_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, set):
        return [_sanitize_for_json(item) for item in sorted(value, key=lambda item: str(item))]
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "isoformat") and callable(getattr(value, "isoformat")):
        try:
            return value.isoformat()
        except (TypeError, ValueError, OverflowError):
            logger.warning(
                "Could not serialize %s with isoformat(); using fallback JSON representation",
                type(value).__name__,
                exc_info=True,
            )
    if hasattr(value, "__dict__"):
        try:
            attributes = vars(value)
        except TypeError:
            logger.warning(
                "Could not inspect %s attributes for JSON serialization; using string fallback",
                type(value).__name__,
                exc_info=True,
            )
        else:
            # Keep recursive conversion outside the access-error handler. A
            # failure in an attribute serializer is not evidence that the
            # object's attributes are unavailable and must remain observable.
            return _sanitize_for_json(attributes)
    return str(value)


def _seed_search_summary(seed: Dict[str, Any], requested_search_mode: str) -> Dict[str, Any]:
    key_facts = dict(seed.get('key_facts') or {})
    stored = dict(key_facts.get('search_summary') or {})
    requested_mode = str(
        stored.get('requested_search_mode')
        or requested_search_mode
        or 'package'
    )
    effective_mode = str(
        stored.get('effective_search_mode')
        or requested_mode
    )
    fallback_note = str(stored.get('fallback_note') or '')
    return {
        'requested_search_mode': requested_mode,
        'effective_search_mode': effective_mode,
        'fallback_note': fallback_note,
    }


class AdversarialHarness:
    """
    Orchestrates multiple adversarial training sessions.
    
    Features:
    - Parallel execution using LLM router
    - Progress tracking
    - Result aggregation
    - Failure handling
    """
    
    def __init__(self,
                 llm_backend_complainant,
                 llm_backend_critic,
                 mediator_factory: Callable,
                 seed_library: SeedComplaintLibrary = None,
                 max_parallel: int = 4,
                 session_state_dir: str | None = None,
                 llm_backend_complainant_factory: Optional[Callable[..., Any]] = None,
                 llm_backend_critic_factory: Optional[Callable[..., Any]] = None):
        """
        Initialize adversarial harness.
        
        Args:
            llm_backend_complainant: LLM backend for complainant
            llm_backend_critic: LLM backend for critic
            mediator_factory: Factory function to create mediator instances
            seed_library: Optional seed complaint library
            max_parallel: Maximum parallel sessions
            session_state_dir: Optional directory to persist each session under
                as <session_state_dir>/<session_id>/{chat.jsonl,session.json}.
        """
        self.llm_backend_complainant = llm_backend_complainant
        self.llm_backend_critic = llm_backend_critic
        self.llm_backend_complainant_factory = llm_backend_complainant_factory
        self.llm_backend_critic_factory = llm_backend_critic_factory
        self.mediator_factory = mediator_factory
        self.seed_library = seed_library or SeedComplaintLibrary()
        self.max_parallel = max_parallel
        self.session_state_dir = session_state_dir
        
        self.results = []

    @staticmethod
    def _attach_result_spec_metadata(result: SessionResult, spec: Dict[str, Any]) -> SessionResult:
        if not isinstance(result.seed_complaint, dict):
            return result

        try:
            search_summary = _seed_search_summary(
                result.seed_complaint,
                str(spec.get('hacc_search_mode') or 'package'),
            )
            key_facts = dict(result.seed_complaint.get('key_facts') or {})
            anchor_sections = list(key_facts.get('anchor_sections') or [])
        except (TypeError, ValueError):
            # Seed complaints can originate in external evidence packages. A
            # malformed optional metadata field must not turn an otherwise
            # completed session into a failed one, but it must be observable.
            # Keep unexpected implementation failures outside this recovery
            # path so they are not silently reported as successful enrichment.
            logger.warning(
                "Could not attach optional specification metadata to session %s; "
                "leaving its seed complaint unchanged",
                result.session_id,
                exc_info=True,
            )
            return result

        # Perform the mutation outside the external-data recovery boundary so
        # defects in result assignment or metadata assembly remain visible.
        result.seed_complaint = {
            **result.seed_complaint,
            '_meta': {
                'personality': spec.get('personality'),
                'max_turns': spec.get('max_turns'),
                'include_hacc_evidence': spec.get('include_hacc_evidence', False),
                'hacc_preset': spec.get('hacc_preset'),
                'use_hacc_vector_search': spec.get('use_hacc_vector_search', False),
                'hacc_search_mode': search_summary['requested_search_mode'],
                'hacc_effective_search_mode': search_summary['effective_search_mode'],
                'hacc_search_fallback_note': search_summary['fallback_note'],
                'search_summary': search_summary,
                'seed_source': result.seed_complaint.get('source'),
                'anchor_sections': anchor_sections,
            }
        }
        return result

    @staticmethod
    def _weak_performance_labels(performance: Dict[str, Any], average_score: float, *, limit: int = 3) -> List[str]:
        weak_labels: List[str] = []
        for name, payload in sorted(
            dict(performance or {}).items(),
            key=lambda item: (float((item[1] or {}).get('average_score') or 0.0), int((item[1] or {}).get('count') or 0)),
        ):
            normalized_name = str(name or '').strip()
            if not normalized_name:
                continue
            if float((payload or {}).get('average_score') or 0.0) > float(average_score or 0.0):
                continue
            weak_labels.append(normalized_name)
            if len(weak_labels) >= limit:
                break
        return weak_labels

    @staticmethod
    def _document_theory_priority_text(tag: str) -> str:
        normalized = str(tag or '').strip().lower()
        if normalized == 'notice_review':
            return 'Increase notice-review counts, chronology, and hearing or rescission relief'
        if normalized == 'retaliation':
            return 'Increase retaliation counts, protected-activity chronology, and retaliation-specific relief'
        if normalized == 'accommodation':
            return 'Increase accommodation counts, interactive-process chronology, and accommodation-specific relief'
        if normalized == 'adverse_action':
            return 'Increase adverse-action counts, decision chronology, and restoration or rescission relief'
        return f"Increase theory-specific drafting support for {normalized.replace('_', ' ')}"

    @staticmethod
    def _document_theory_prompt_text(tag: str) -> str:
        normalized = str(tag or '').strip().lower()
        if normalized == 'notice_review':
            return (
                'Emphasize written notice, hearing or review chronology, due-process count language, '
                'and relief requiring rescission, stay, or a proper hearing or review.'
            )
        if normalized == 'retaliation':
            return (
                'Emphasize protected activity, the sequence between complaint and adverse action, retaliation count language, '
                'and relief tied to reversing retaliatory enforcement.'
            )
        if normalized == 'accommodation':
            return (
                'Emphasize the accommodation request, the interactive process, response or denial documents, '
                'accommodation-specific count language, and relief requiring review or approval of the accommodation.'
            )
        if normalized == 'adverse_action':
            return (
                'Emphasize the denial or termination event, the decision chronology, adverse-action count language, '
                'and relief restoring assistance or rescinding the challenged decision.'
            )
        return ''

    def _build_seed_feedback_from_results(self, results: List[SessionResult]) -> Dict[str, Any]:
        successful = [result for result in results if result.success and getattr(result, 'critic_score', None)]
        if not successful:
            return {}
        try:
            from .optimizer import Optimizer

            report = Optimizer().analyze(successful)
        except Exception:
            logger.debug('Could not build optimizer seed feedback from completed results', exc_info=True)
            return {}

        unresolved_intake_objectives = [
            str(value).strip()
            for value in list(
                ((report.coverage_remediation or {}).get('intake_priorities') or {}).get('uncovered_objectives') or []
            )
            if str(value).strip()
        ]
        latest_batch_priorities = [
            str(value).strip()
            for value in list(report.priority_improvements or [])
            if str(value).strip()
        ]
        weak_complaint_types = self._weak_performance_labels(
            dict(report.complaint_type_performance or {}),
            float(report.average_score or 0.0),
        )
        weak_evidence_modalities = self._weak_performance_labels(
            dict(report.evidence_modality_performance or {}),
            float(report.average_score or 0.0),
        )
        document_theory_targets = [
            str(name).strip()
            for name, _count in sorted(
                dict((report.document_theory_alignment_summary or {}).get('missing_tag_counts') or {}).items(),
                key=lambda item: (-int(item[1] or 0), item[0]),
            )[:3]
            if str(name).strip()
        ]
        theory_priority_improvements = [
            text
            for text in (self._document_theory_priority_text(tag) for tag in document_theory_targets)
            if text
        ]
        theory_document_guidance = [
            text
            for text in (self._document_theory_prompt_text(tag) for tag in document_theory_targets)
            if text
        ]
        merged_batch_priorities = latest_batch_priorities + theory_priority_improvements

        actor_critic_optimizer = {
            'num_sessions_analyzed': int(report.num_sessions_analyzed or 0),
            'num_successful_sessions': int(report.num_sessions_analyzed or 0),
            'question_quality_avg': float(report.question_quality_avg or 0.0),
            'empathy_avg': float(report.empathy_avg or 0.0),
            'efficiency_avg': float(report.efficiency_avg or 0.0),
            'coverage_avg': float(report.coverage_avg or 0.0),
            'weak_complaint_types': weak_complaint_types,
            'weak_evidence_modalities': weak_evidence_modalities,
            'unresolved_intake_objectives': unresolved_intake_objectives,
            'latest_batch_priorities': merged_batch_priorities,
            'document_theory_targets': document_theory_targets,
            'document_theory_alignment_summary': dict(report.document_theory_alignment_summary or {}),
            'document_generation_guidance': theory_document_guidance,
            'graph_element_targeting_summary': dict(report.graph_element_targeting_summary or {}),
            'phase_signal_context': {
                'question_quality_avg': float(report.question_quality_avg or 0.0),
                'empathy_avg': float(report.empathy_avg or 0.0),
                'efficiency_avg': float(report.efficiency_avg or 0.0),
                'coverage_avg': float(report.coverage_avg or 0.0),
                'unresolved_intake_objectives': unresolved_intake_objectives,
                'num_sessions_analyzed': int(report.num_sessions_analyzed or 0),
                'num_successful_sessions': int(report.num_sessions_analyzed or 0),
            },
        }
        if merged_batch_priorities:
            actor_critic_optimizer['priority_improvements'] = merged_batch_priorities

        return {
            'actor_critic_optimizer': actor_critic_optimizer,
            'optimization_guidance': {
                'latest_batch_priorities': merged_batch_priorities,
                'priority_improvements': merged_batch_priorities,
                'document_theory_targets': document_theory_targets,
                'document_generation_guidance': theory_document_guidance,
            },
        }

    @staticmethod
    def _merge_optimizer_feedback(seed: Dict[str, Any], feedback: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(seed, dict) or not isinstance(feedback, dict):
            return deepcopy(seed) if isinstance(seed, dict) else {}

        def _merge_unique_strings(existing: Any, new_values: Any) -> List[str]:
            merged: List[str] = []
            seen = set()
            for collection in (existing, new_values):
                for item in list(collection or []):
                    text = str(item or '').strip()
                    if not text:
                        continue
                    key = text.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(text)
            return merged

        merged_seed = deepcopy(seed)
        existing_actor = dict(merged_seed.get('actor_critic_optimizer') or {})
        feedback_actor = dict(feedback.get('actor_critic_optimizer') or {})
        merged_actor = {**existing_actor, **feedback_actor}
        for key in (
            'weak_complaint_types',
            'weak_evidence_modalities',
            'unresolved_intake_objectives',
            'latest_batch_priorities',
            'priority_improvements',
            'document_theory_targets',
            'document_generation_guidance',
        ):
            merged_actor[key] = _merge_unique_strings(existing_actor.get(key), feedback_actor.get(key))
        existing_phase_signal_context = dict(existing_actor.get('phase_signal_context') or {})
        feedback_phase_signal_context = dict(feedback_actor.get('phase_signal_context') or {})
        if existing_phase_signal_context or feedback_phase_signal_context:
            merged_actor['phase_signal_context'] = {
                **existing_phase_signal_context,
                **feedback_phase_signal_context,
                'unresolved_intake_objectives': _merge_unique_strings(
                    existing_phase_signal_context.get('unresolved_intake_objectives'),
                    feedback_phase_signal_context.get('unresolved_intake_objectives'),
                ),
            }
        merged_seed['actor_critic_optimizer'] = merged_actor

        existing_guidance = dict(merged_seed.get('optimization_guidance') or {})
        feedback_guidance = dict(feedback.get('optimization_guidance') or {})
        merged_seed['optimization_guidance'] = {
            **existing_guidance,
            **feedback_guidance,
            'latest_batch_priorities': _merge_unique_strings(
                existing_guidance.get('latest_batch_priorities'),
                feedback_guidance.get('latest_batch_priorities'),
            ),
            'priority_improvements': _merge_unique_strings(
                existing_guidance.get('priority_improvements'),
                feedback_guidance.get('priority_improvements'),
            ),
            'document_theory_targets': _merge_unique_strings(
                existing_guidance.get('document_theory_targets'),
                feedback_guidance.get('document_theory_targets'),
            ),
            'document_generation_guidance': _merge_unique_strings(
                existing_guidance.get('document_generation_guidance'),
                feedback_guidance.get('document_generation_guidance'),
            ),
        }

        key_facts = dict(merged_seed.get('key_facts') or {})
        if key_facts or merged_actor.get('unresolved_intake_objectives') or merged_seed['optimization_guidance'].get('latest_batch_priorities'):
            key_facts['unresolved_intake_objectives'] = _merge_unique_strings(
                key_facts.get('unresolved_intake_objectives'),
                merged_actor.get('unresolved_intake_objectives'),
            )
            key_facts['workflow_phase_priorities'] = _merge_unique_strings(
                key_facts.get('workflow_phase_priorities'),
                merged_seed['optimization_guidance'].get('latest_batch_priorities'),
            )
            key_facts['document_theory_targets'] = _merge_unique_strings(
                key_facts.get('document_theory_targets'),
                merged_seed['optimization_guidance'].get('document_theory_targets'),
            )
            synthetic_prompts = dict(key_facts.get('synthetic_prompts') or {})
            existing_document_generation_prompt = " ".join(
                str(synthetic_prompts.get('document_generation_prompt') or '').split()
            ).strip()
            merged_document_guidance = _merge_unique_strings(
                None,
                merged_seed['optimization_guidance'].get('document_generation_guidance'),
            )
            if merged_document_guidance:
                missing_guidance = [
                    text
                    for text in merged_document_guidance
                    if text and text.lower() not in existing_document_generation_prompt.lower()
                ]
                guidance_text = " ".join(missing_guidance).strip()
                if guidance_text:
                    synthetic_prompts['document_generation_prompt'] = " ".join(
                        part for part in (existing_document_generation_prompt, guidance_text) if part
                    ).strip()
            if synthetic_prompts:
                key_facts['synthetic_prompts'] = synthetic_prompts
            merged_seed['key_facts'] = key_facts

        return merged_seed

    def _preload_hacc_seed_evidence(self, mediator: Any, seed: Dict[str, Any], *, session_id: str) -> List[Dict[str, Any]]:
        save_claim_support_document = getattr(mediator, "save_claim_support_document", None)
        if not callable(save_claim_support_document):
            return []

        packets = build_hacc_mediator_evidence_packet(seed)
        stored: List[Dict[str, Any]] = []
        for packet in packets:
            try:
                result = save_claim_support_document(
                    claim_type=str(seed.get("type") or ""),
                    user_id=session_id,
                    claim_element_text=str(seed.get("summary") or seed.get("description") or "HACC evidence-grounded complaint"),
                    document_text=str(packet.get("document_text") or ""),
                    document_label=str(packet.get("document_label") or "HACC evidence"),
                    source_url=str(packet.get("source_path") or ""),
                    filename=str(packet.get("filename") or ""),
                    mime_type=str(packet.get("mime_type") or "text/plain"),
                    evidence_type="document",
                    metadata=dict(packet.get("metadata") or {}),
                )
            except Exception as exc:
                logger.warning("Unable to preload HACC seed evidence into mediator for %s: %s", session_id, exc)
                continue
            if isinstance(result, dict):
                stored.append(result)
        return stored

    def _safe_session_id(self, text: str) -> str:
        allowed = []
        for ch in text:
            if ch.isalnum() or ch in ('-', '_', '.'):
                allowed.append(ch)
            else:
                allowed.append('_')
        return ''.join(allowed)

    def _get_session_dir(self, session_id: str) -> str | None:
        if not self.session_state_dir:
            return None
        safe = self._safe_session_id(session_id)
        return os.path.join(self.session_state_dir, safe)

    @staticmethod
    def _initialize_session_databases(*database_paths: str | None) -> None:
        """Create each configured session database and surface initialization failures."""
        configured_paths = [path for path in database_paths if path]
        if not configured_paths:
            return

        import duckdb  # type: ignore

        for database_path in configured_paths:
            connection = duckdb.connect(database_path)
            connection.close()

    def _create_mediator_for_session(
        self,
        *,
        evidence_db_path: str | None,
        legal_authority_db_path: str | None,
        claim_support_db_path: str | None,
        session_id: str | None = None,
        session_dir: str | None = None,
    ):
        """Call mediator_factory with optional per-session DB paths if supported."""
        try:
            sig = inspect.signature(self.mediator_factory)
        except (TypeError, ValueError):
            # Some extension and dynamically generated callables do not expose
            # an inspectable signature. Retain no-argument factory compatibility
            # for those callables, while making the loss of session-scoped paths
            # observable. Factory execution deliberately remains outside this
            # recovery boundary so constructor failures are never retried or
            # replaced by a second, argument-less invocation.
            logger.warning(
                "Could not inspect mediator factory %s; calling it without "
                "session-specific arguments",
                type(self.mediator_factory).__name__,
                exc_info=True,
            )
            return self.mediator_factory()

        params = sig.parameters
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in params.values()
        )

        def accepts_keyword(name: str) -> bool:
            parameter = params.get(name)
            return accepts_kwargs or (
                parameter is not None
                and parameter.kind in {
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                }
            )

        kwargs: Dict[str, Any] = {}
        if accepts_keyword("evidence_db_path"):
            kwargs["evidence_db_path"] = evidence_db_path
        if accepts_keyword("legal_authority_db_path"):
            kwargs["legal_authority_db_path"] = legal_authority_db_path
        if accepts_keyword("claim_support_db_path"):
            kwargs["claim_support_db_path"] = claim_support_db_path
        if session_id is not None and accepts_keyword("session_id"):
            kwargs["session_id"] = session_id
        if session_dir is not None and accepts_keyword("session_dir"):
            kwargs["session_dir"] = session_dir

        return self.mediator_factory(**kwargs)

    def _ensure_session_db_paths(
        self,
        mediator: Any,
        *,
        evidence_db_path: str | None,
        legal_authority_db_path: str | None,
        claim_support_db_path: str | None,
    ) -> Any:
        """Force storage hooks onto the session-scoped DuckDB paths when available.

        Some mediator factories ignore the per-session DB kwargs and return a
        Mediator instance still pointed at shared complaint-generator statefiles.
        Rebinding here keeps the session artifacts production-like and isolates
        evidence persistence for each adversarial run.
        """

        hook_targets = [
            ("evidence_state", evidence_db_path),
            ("legal_authority_storage", legal_authority_db_path),
            ("claim_support", claim_support_db_path),
        ]
        for attr_name, expected_path in hook_targets:
            if not expected_path:
                continue
            hook = getattr(mediator, attr_name, None)
            if hook is None:
                continue
            current_path = getattr(hook, "db_path", None)
            if current_path == expected_path:
                continue
            hook_cls = hook.__class__
            try:
                setattr(mediator, attr_name, hook_cls(mediator, db_path=expected_path))
                logger.info(
                    "Rebound mediator %s hook from %s to session DB %s",
                    attr_name,
                    current_path,
                    expected_path,
                )
            except Exception as exc:
                logger.warning(
                    "Unable to rebind mediator %s hook to session DB %s: %s",
                    attr_name,
                    expected_path,
                    exc,
                )
        return mediator

    def _persist_session(self, result: SessionResult) -> None:
        if not self.session_state_dir:
            return

        session_dir = self._get_session_dir(result.session_id)
        if not session_dir:
            return
        os.makedirs(session_dir, exist_ok=True)

        session_json_path = os.path.join(session_dir, 'session.json')
        chat_jsonl_path = os.path.join(session_dir, 'chat.jsonl')

        payload = result.to_dict()

        # Persist full graphs as separate JSON files to keep session.json manageable.
        kg = payload.pop("knowledge_graph", None)
        dg = payload.pop("dependency_graph", None)
        if isinstance(kg, dict):
            with open(os.path.join(session_dir, "knowledge_graph.json"), "w", encoding="utf-8") as f:
                json.dump(kg, f, ensure_ascii=False, indent=2)
        if isinstance(dg, dict):
            with open(os.path.join(session_dir, "dependency_graph.json"), "w", encoding="utf-8") as f:
                json.dump(dg, f, ensure_ascii=False, indent=2)

        # Record artifact paths (if present).
        artifacts: Dict[str, Any] = {}
        evidence_db = os.path.join(session_dir, "evidence.duckdb")
        legal_db = os.path.join(session_dir, "legal_authorities.duckdb")
        claim_support_db = os.path.join(session_dir, "claim_support.duckdb")
        artifacts["evidence_duckdb_expected"] = os.path.abspath(evidence_db)
        artifacts["legal_authorities_duckdb_expected"] = os.path.abspath(legal_db)
        artifacts["claim_support_duckdb_expected"] = os.path.abspath(claim_support_db)
        artifacts["evidence_duckdb_exists"] = os.path.isfile(evidence_db)
        artifacts["legal_authorities_duckdb_exists"] = os.path.isfile(legal_db)
        artifacts["claim_support_duckdb_exists"] = os.path.isfile(claim_support_db)
        if os.path.isfile(evidence_db):
            artifacts["evidence_duckdb"] = os.path.abspath(evidence_db)
        if os.path.isfile(legal_db):
            artifacts["legal_authorities_duckdb"] = os.path.abspath(legal_db)
        if os.path.isfile(claim_support_db):
            artifacts["claim_support_duckdb"] = os.path.abspath(claim_support_db)
        kg_path = os.path.join(session_dir, "knowledge_graph.json")
        dg_path = os.path.join(session_dir, "dependency_graph.json")
        if os.path.isfile(kg_path):
            artifacts["knowledge_graph_json"] = os.path.abspath(kg_path)
        if os.path.isfile(dg_path):
            artifacts["dependency_graph_json"] = os.path.abspath(dg_path)
        payload["artifacts"] = artifacts

        with open(session_json_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        # Persist conversation history as JSONL for easy streaming/grepping.
        # Note: history entries don't include timestamps; include ordering index.
        with open(chat_jsonl_path, 'w', encoding='utf-8') as f:
            for i, msg in enumerate(result.conversation_history or []):
                line = {
                    'session_id': result.session_id,
                    'i': i,
                    'role': msg.get('role', 'unknown'),
                    'type': msg.get('type', ''),
                    'content': msg.get('content', ''),
                }
                f.write(json.dumps(line, ensure_ascii=False) + '\n')

        logger.info('Session artifacts saved to %s', session_dir)

    def _write_session_progress(
        self,
        session_id: str,
        *,
        stage: str,
        status: str,
        session_dir: str | None = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.session_state_dir:
            return
        resolved_session_dir = session_dir or self._get_session_dir(session_id)
        if not resolved_session_dir:
            return
        os.makedirs(resolved_session_dir, exist_ok=True)
        payload = {
            'session_id': session_id,
            'stage': str(stage or ''),
            'status': str(status or ''),
            'timestamp': datetime.now(UTC).isoformat(),
            'metadata': _sanitize_for_json(metadata or {}),
        }
        with open(os.path.join(resolved_session_dir, 'progress.json'), 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _emit_batch_progress(
        self,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
        *,
        status: str,
        total_sessions: int,
        completed_sessions: int,
        successful_sessions: int,
        failed_sessions: int,
        active_session_ids: List[str],
        latest_session: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not callable(progress_callback):
            return
        progress_callback({
            'status': str(status or ''),
            'timestamp': datetime.now(UTC).isoformat(),
            'total_sessions': int(total_sessions or 0),
            'completed_sessions': int(completed_sessions or 0),
            'successful_sessions': int(successful_sessions or 0),
            'failed_sessions': int(failed_sessions or 0),
            'active_session_ids': [str(value) for value in list(active_session_ids or []) if str(value)],
            'latest_session': _sanitize_for_json(dict(latest_session or {})),
        })

    def run_batch(self,
                   num_sessions: int = 10,
                   seed_complaints: List[Dict[str, Any]] = None,
                   personalities: List[str] = None,
                  max_turns_per_session: int = 12,
                  include_hacc_evidence: bool = False,
                  hacc_count: int | None = None,
                  hacc_preset: str | None = None,
                  hacc_query_specs: List[Dict[str, Any]] | None = None,
                  use_hacc_vector_search: bool = False,
                  hacc_search_mode: str = 'package',
                  progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> List[SessionResult]:
        """
        Run a batch of adversarial sessions in parallel.
        
        Args:
            num_sessions: Number of sessions to run
            seed_complaints: Optional list of seed complaints (randomly selected if None)
            personalities: Optional list of personalities for complainants
            max_turns_per_session: Maximum turns per session
            
        Returns:
            List of SessionResults
        """
        logger.info(f"Starting batch of {num_sessions} sessions with {self.max_parallel} parallel")
        
        # Get seed complaints
        if seed_complaints is None:
            seed_complaints = self.seed_library.get_seed_complaints(
                count=num_sessions,
                include_hacc_evidence=include_hacc_evidence,
                hacc_count=hacc_count,
                hacc_preset=hacc_preset,
                hacc_query_specs=hacc_query_specs,
                use_hacc_vector_search=use_hacc_vector_search,
                hacc_search_mode=hacc_search_mode,
            )
        elif len(seed_complaints) < num_sessions:
            # Cycle through provided seeds
            seed_complaints = (seed_complaints * ((num_sessions // len(seed_complaints)) + 1))[:num_sessions]
        
        # Get personalities
        if personalities is None:
            personalities = ['cooperative', 'defensive', 'vague', 'detailed', 'emotional']
        
        # Create session specs
        session_specs = []
        for i in range(num_sessions):
            session_id = f"session_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{i:03d}"
            seed = deepcopy(seed_complaints[i % len(seed_complaints)])
            personality = personalities[i % len(personalities)]
            
            session_specs.append({
                'session_id': session_id,
                'seed': seed,
                'personality': personality,
                'max_turns': max_turns_per_session,
                'include_hacc_evidence': include_hacc_evidence,
                'hacc_preset': hacc_preset,
                'use_hacc_vector_search': use_hacc_vector_search,
                'hacc_search_mode': hacc_search_mode,
            })

        self._emit_batch_progress(
            progress_callback,
            status='running',
            total_sessions=num_sessions,
            completed_sessions=0,
            successful_sessions=0,
            failed_sessions=0,
            active_session_ids=[],
        )

        # Run sessions in parallel while allowing completed results to steer later seeds.
        results = []
        pending_specs = list(session_specs)
        active_session_ids: List[str] = []
        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            future_to_spec = {}

            def submit_next_spec() -> None:
                if not pending_specs:
                    return
                next_spec = pending_specs.pop(0)
                feedback = self._build_seed_feedback_from_results(results)
                if feedback:
                    next_spec = {
                        **next_spec,
                        'seed': self._merge_optimizer_feedback(next_spec['seed'], feedback),
                    }
                future_to_spec[executor.submit(self._run_single_session, next_spec)] = next_spec
                active_session_ids.append(str(next_spec['session_id']))
                self._emit_batch_progress(
                    progress_callback,
                    status='running',
                    total_sessions=num_sessions,
                    completed_sessions=len(results),
                    successful_sessions=len([r for r in results if r.success]),
                    failed_sessions=len([r for r in results if not r.success]),
                    active_session_ids=active_session_ids,
                    latest_session={
                        'session_id': str(next_spec['session_id']),
                        'status': 'started',
                    },
                )

            for _ in range(min(self.max_parallel, len(pending_specs))):
                submit_next_spec()

            completed = 0
            while future_to_spec:
                done, _pending = wait(tuple(future_to_spec.keys()), return_when=FIRST_COMPLETED)
                for future in done:
                    spec = future_to_spec.pop(future)
                    try:
                        result = self._attach_result_spec_metadata(future.result(), spec)
                        results.append(result)
                        self._persist_session(result)
                        completed += 1
                        active_session_ids = [value for value in active_session_ids if value != str(spec['session_id'])]

                        if result.success:
                            logger.info(f"Session {spec['session_id']} completed ({completed}/{num_sessions}). "
                                      f"Score: {result.critic_score.overall_score:.3f}")
                        else:
                            logger.warning(f"Session {spec['session_id']} failed ({completed}/{num_sessions}): "
                                         f"{result.error}")
                        self._emit_batch_progress(
                            progress_callback,
                            status='running' if completed < num_sessions else 'completed',
                            total_sessions=num_sessions,
                            completed_sessions=completed,
                            successful_sessions=len([r for r in results if r.success]),
                            failed_sessions=len([r for r in results if not r.success]),
                            active_session_ids=active_session_ids,
                            latest_session={
                                'session_id': str(spec['session_id']),
                                'status': 'completed',
                                'success': bool(result.success),
                                'error': str(result.error or ''),
                            },
                        )
                    except Exception as e:
                        logger.error(f"Error in session {spec['session_id']}: {e}")
                        completed += 1
                        active_session_ids = [value for value in active_session_ids if value != str(spec['session_id'])]
                        self._emit_batch_progress(
                            progress_callback,
                            status='running' if completed < num_sessions else 'completed',
                            total_sessions=num_sessions,
                            completed_sessions=completed,
                            successful_sessions=len([r for r in results if r.success]),
                            failed_sessions=len([r for r in results if not r.success]) + 1,
                            active_session_ids=active_session_ids,
                            latest_session={
                                'session_id': str(spec['session_id']),
                                'status': 'error',
                                'success': False,
                                'error': str(e),
                            },
                        )
                    submit_next_spec()

        self.results.extend(results)
        logger.info(f"Batch complete. {len([r for r in results if r.success])}/{num_sessions} successful")
        self._emit_batch_progress(
            progress_callback,
            status='completed',
            total_sessions=num_sessions,
            completed_sessions=len(results),
            successful_sessions=len([r for r in results if r.success]),
            failed_sessions=len([r for r in results if not r.success]),
            active_session_ids=[],
        )

        return results
    
    def _run_single_session(self, spec: Dict[str, Any]) -> SessionResult:
        """Run a single session (called in thread pool)."""
        try:
            session_dir = self._get_session_dir(spec['session_id'])
            if session_dir:
                os.makedirs(session_dir, exist_ok=True)
            self._write_session_progress(
                spec['session_id'],
                stage='initializing',
                status='running',
                session_dir=session_dir,
                metadata={'personality': spec.get('personality', ''), 'max_turns': int(spec.get('max_turns', 0) or 0)},
            )

            complainant_backend = self.llm_backend_complainant
            if callable(self.llm_backend_complainant_factory):
                complainant_backend = self.llm_backend_complainant_factory(
                    session_id=spec['session_id'],
                    session_dir=session_dir,
                )

            critic_backend = self.llm_backend_critic
            if callable(self.llm_backend_critic_factory):
                critic_backend = self.llm_backend_critic_factory(
                    session_id=spec['session_id'],
                    session_dir=session_dir,
                )

            # Create instances for this session
            complainant = Complainant(
                complainant_backend,
                personality=spec['personality']
            )
            
            # Set context (maps personality to emotional_state/cooperation/context_depth)
            complainant.set_context(Complainant.build_default_context(spec['seed'], spec['personality']))
            
            critic = Critic(critic_backend)
            evidence_db_path = os.path.join(session_dir, "evidence.duckdb") if session_dir else None
            legal_authority_db_path = os.path.join(session_dir, "legal_authorities.duckdb") if session_dir else None
            claim_support_db_path = os.path.join(session_dir, "claim_support.duckdb") if session_dir else None

            # Proactively create valid DuckDB containers before constructing
            # hooks. A missing or unusable session database is a session
            # initialization failure, not an optional-artifact condition.
            self._initialize_session_databases(
                evidence_db_path,
                legal_authority_db_path,
                claim_support_db_path,
            )

            # Create new mediator instance (thread-safe). If supported, use per-session DuckDB paths.
            mediator = self._create_mediator_for_session(
                evidence_db_path=evidence_db_path,
                legal_authority_db_path=legal_authority_db_path,
                claim_support_db_path=claim_support_db_path,
                session_id=spec['session_id'],
                session_dir=session_dir,
            )
            mediator = self._ensure_session_db_paths(
                mediator,
                evidence_db_path=evidence_db_path,
                legal_authority_db_path=legal_authority_db_path,
                claim_support_db_path=claim_support_db_path,
            )
            self._write_session_progress(
                spec['session_id'],
                stage='mediator_ready',
                status='running',
                session_dir=session_dir,
            )
            preloaded_evidence = self._preload_hacc_seed_evidence(
                mediator,
                spec['seed'],
                session_id=spec['session_id'],
            )
            self._write_session_progress(
                spec['session_id'],
                stage='evidence_preloaded',
                status='running',
                session_dir=session_dir,
                metadata={'preloaded_evidence_count': len(preloaded_evidence)},
            )
            if preloaded_evidence and isinstance(spec['seed'], dict):
                spec['seed'].setdefault('_meta', {})
                spec['seed']['_meta']['preloaded_mediator_evidence'] = [
                    {
                        'cid': item.get('cid'),
                        'record_id': item.get('record_id'),
                        'document_label': item.get('metadata', {}).get('filename') or item.get('metadata', {}).get('source_path') or '',
                    }
                    for item in preloaded_evidence
                ]
            
            # Create and run session
            session = AdversarialSession(
                session_id=spec['session_id'],
                complainant=complainant,
                mediator=mediator,
                critic=critic,
                max_turns=spec['max_turns'],
                progress_callback=lambda payload: self._write_session_progress(
                    spec['session_id'],
                    stage=str((payload or {}).get('stage') or 'session_running'),
                    status='running',
                    session_dir=session_dir,
                    metadata=dict((payload or {}).get('metadata') or {}),
                ),
            )
            self._write_session_progress(
                spec['session_id'],
                stage='session_running',
                status='running',
                session_dir=session_dir,
            )
            result = session.run(spec['seed'])
            self._write_session_progress(
                spec['session_id'],
                stage='completed',
                status='completed',
                session_dir=session_dir,
                metadata={'success': bool(result.success), 'error': str(result.error or '')},
            )
            return result
            
        except Exception as e:
            logger.error(f"Error running session {spec['session_id']}: {e}", exc_info=True)
            self._write_session_progress(
                spec['session_id'],
                stage='failed',
                status='failed',
                session_dir=self._get_session_dir(spec['session_id']),
                metadata={'error': str(e)},
            )
            return SessionResult(
                session_id=spec['session_id'],
                timestamp=datetime.now(UTC).isoformat(),
                seed_complaint=spec['seed'],
                initial_complaint_text="",
                conversation_history=[],
                num_questions=0,
                num_turns=0,
                final_state={},
                success=False,
                error=str(e)
            )
    
    def get_results(self) -> List[SessionResult]:
        """Get all results from this harness."""
        return self.results.copy()
    
    def get_successful_results(self) -> List[SessionResult]:
        """Get only successful results."""
        return [r for r in self.results if r.success]
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics across all results.
        
        Returns:
            Dictionary with aggregate statistics
        """
        if not self.results:
            return {'total_sessions': 0}
        
        successful = self.get_successful_results()
        
        if not successful:
            return {
                'total_sessions': len(self.results),
                'successful_sessions': 0,
                'failed_sessions': len(self.results)
            }
        
        scores = [r.critic_score.overall_score for r in successful]
        question_counts = [r.num_questions for r in successful]
        durations = [r.duration_seconds for r in successful]
        anchor_summary = self._anchor_section_statistics(successful)
        intake_priority_summary = self._intake_priority_statistics(successful)
        phase1_summary = self._phase1_statistics(successful)
        phase2_summary = self._phase2_statistics(successful)
        
        return {
            'total_sessions': len(self.results),
            'successful_sessions': len(successful),
            'failed_sessions': len(self.results) - len(successful),
            'average_score': sum(scores) / len(scores) if scores else 0,
            'min_score': min(scores) if scores else 0,
            'max_score': max(scores) if scores else 0,
            'average_questions': sum(question_counts) / len(question_counts) if question_counts else 0,
            'average_duration': sum(durations) / len(durations) if durations else 0,
            'score_distribution': self._score_distribution(scores),
            'anchor_sections': anchor_summary,
            'intake_priority': intake_priority_summary,
            'phase1_metrics': phase1_summary,
            'phase2_metrics': phase2_summary,
        }
    
    def _score_distribution(self, scores: List[float]) -> Dict[str, int]:
        """Calculate score distribution."""
        if not scores:
            return {}
        
        bins = {
            '0.0-0.2': 0,
            '0.2-0.4': 0,
            '0.4-0.6': 0,
            '0.6-0.8': 0,
            '0.8-1.0': 0
        }
        
        for score in scores:
            if score < 0.2:
                bins['0.0-0.2'] += 1
            elif score < 0.4:
                bins['0.2-0.4'] += 1
            elif score < 0.6:
                bins['0.4-0.6'] += 1
            elif score < 0.8:
                bins['0.6-0.8'] += 1
            else:
                bins['0.8-1.0'] += 1
        
        return bins
    
    def save_results(self, filepath: str):
        """
        Save results to JSON file.
        
        Args:
            filepath: Path to save results
        """
        data = {
            'timestamp': datetime.now(UTC).isoformat(),
            'statistics': self.get_statistics(),
            'results': [r.to_dict() for r in self.results]
        }
        data = _json_safe(data)
        
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Results saved to {filepath}")

    def save_anchor_section_report(self, filepath: str, format: str = "csv") -> None:
        """Save aggregate anchor-section coverage as CSV or Markdown."""
        stats = self.get_statistics()
        anchor_stats = dict(stats.get('anchor_sections') or {})
        coverage_by_section = dict(anchor_stats.get('coverage_by_section') or {})
        rows = [
            {
                'section': section,
                'expected': payload.get('expected', 0),
                'covered': payload.get('covered', 0),
                'missing': payload.get('missing', 0),
                'coverage_rate': payload.get('coverage_rate', 0.0),
            }
            for section, payload in sorted(coverage_by_section.items())
        ]

        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)

        normalized_format = str(format or "csv").strip().lower()
        if normalized_format == "csv":
            with open(filepath, 'w', newline='', encoding='utf-8') as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=['section', 'expected', 'covered', 'missing', 'coverage_rate'],
                )
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)
        elif normalized_format in {"md", "markdown"}:
            lines = [
                "# Anchor Section Coverage",
                "",
                "| Section | Expected | Covered | Missing | Coverage Rate |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
            for row in rows:
                lines.append(
                    f"| {row['section']} | {row['expected']} | {row['covered']} | {row['missing']} | {row['coverage_rate']:.2f} |"
                )
            with open(filepath, 'w', encoding='utf-8') as handle:
                handle.write("\n".join(lines) + "\n")
        else:
            raise ValueError(f"Unsupported report format: {format}")

        logger.info("Anchor section report saved to %s", filepath)

    def _anchor_section_statistics(self, successful_results: List[SessionResult]) -> Dict[str, Any]:
        expected_counter: Counter[str] = Counter()
        covered_counter: Counter[str] = Counter()
        missing_counter: Counter[str] = Counter()

        for result in successful_results:
            critic_score = getattr(result, 'critic_score', None)
            if not critic_score:
                continue
            expected = list(getattr(critic_score, 'anchor_sections_expected', []) or [])
            covered = list(getattr(critic_score, 'anchor_sections_covered', []) or [])
            missing = list(getattr(critic_score, 'anchor_sections_missing', []) or [])
            expected_counter.update(expected)
            covered_counter.update(covered)
            missing_counter.update(missing)

        section_names = sorted(set(expected_counter) | set(covered_counter) | set(missing_counter))
        coverage_by_section = {}
        for name in section_names:
            expected_count = expected_counter.get(name, 0)
            covered_count = covered_counter.get(name, 0)
            missing_count = missing_counter.get(name, 0)
            coverage_by_section[name] = {
                'expected': expected_count,
                'covered': covered_count,
                'missing': missing_count,
                'coverage_rate': (covered_count / expected_count) if expected_count else 0.0,
            }

        return {
            'expected_counts': dict(expected_counter),
            'covered_counts': dict(covered_counter),
            'missing_counts': dict(missing_counter),
            'coverage_by_section': coverage_by_section,
        }

    def _intake_priority_statistics(self, successful_results: List[SessionResult]) -> Dict[str, Any]:
        expected_counter: Counter[str] = Counter()
        covered_counter: Counter[str] = Counter()
        uncovered_counter: Counter[str] = Counter()
        sessions_with_full_coverage = 0

        for result in successful_results:
            final_state = dict(getattr(result, 'final_state', {}) or {})
            summary = dict(final_state.get('adversarial_intake_priority_summary') or {})
            expected = [str(value) for value in list(summary.get('expected_objectives') or []) if str(value)]
            covered = [str(value) for value in list(summary.get('covered_objectives') or []) if str(value)]
            uncovered = [str(value) for value in list(summary.get('uncovered_objectives') or []) if str(value)]
            expected_counter.update(expected)
            covered_counter.update(covered)
            uncovered_counter.update(uncovered)
            if expected and not uncovered:
                sessions_with_full_coverage += 1

        objective_names = sorted(set(expected_counter) | set(covered_counter) | set(uncovered_counter))
        coverage_by_objective = {}
        for name in objective_names:
            expected_count = expected_counter.get(name, 0)
            covered_count = covered_counter.get(name, 0)
            uncovered_count = uncovered_counter.get(name, 0)
            coverage_by_objective[name] = {
                'expected': expected_count,
                'covered': covered_count,
                'uncovered': uncovered_count,
                'coverage_rate': (covered_count / expected_count) if expected_count else 0.0,
            }

        return {
            'expected_counts': dict(expected_counter),
            'covered_counts': dict(covered_counter),
            'uncovered_counts': dict(uncovered_counter),
            'coverage_by_objective': coverage_by_objective,
            'sessions_with_full_coverage': sessions_with_full_coverage,
            'sessions_with_partial_coverage': max(0, len(successful_results) - sessions_with_full_coverage),
        }

    def _phase1_statistics(self, successful_results: List[SessionResult]) -> Dict[str, Any]:
        """Compute Phase 1 (intake) metrics aggregated across sessions.

        Metrics:
        - ``chronology_completeness``: average ratio of anchored events to total
          events, derived from ``intake_chronology_readiness`` in final state.
        - ``contradiction_count``: average number of intake contradictions per
          session, from ``contradiction_summary.count``.
        - ``duplicate_question_rate``: fraction of question candidates that
          share a goal with an earlier candidate in the same session, estimated
          from ``question_candidate_summary.source_counts``.
        - ``proof_lead_density``: average proof leads per candidate claim.
        """
        chronology_completeness_values: List[float] = []
        contradiction_counts: List[int] = []
        duplicate_question_rate_values: List[float] = []
        proof_lead_density_values: List[float] = []

        for result in successful_results:
            final_state = dict(getattr(result, 'final_state', {}) or {})

            # chronology_completeness from intake_chronology_readiness
            chronology_readiness = final_state.get('intake_chronology_readiness')
            if not isinstance(chronology_readiness, dict):
                intake_case_summary = final_state.get('intake_case_summary')
                if isinstance(intake_case_summary, dict):
                    chronology_readiness = intake_case_summary.get('intake_chronology_readiness') or {}
            if isinstance(chronology_readiness, dict) and chronology_readiness:
                anchor_coverage = chronology_readiness.get('anchor_coverage_ratio')
                if anchor_coverage is not None:
                    chronology_completeness_values.append(float(anchor_coverage))
                else:
                    event_count = int(chronology_readiness.get('event_count') or 0)
                    anchored = int(chronology_readiness.get('anchored_event_count') or 0)
                    if event_count > 0:
                        chronology_completeness_values.append(anchored / event_count)

            # contradiction_count from contradiction_summary
            contradiction_summary = final_state.get('contradiction_summary')
            if not isinstance(contradiction_summary, dict):
                intake_case_summary = final_state.get('intake_case_summary')
                if isinstance(intake_case_summary, dict):
                    contradiction_summary = intake_case_summary.get('contradiction_summary') or {}
            if isinstance(contradiction_summary, dict):
                count = int(contradiction_summary.get('count') or 0)
                contradiction_counts.append(count)

            # duplicate_question_rate: estimate from question_candidate_summary
            question_summary = final_state.get('question_candidate_summary')
            if not isinstance(question_summary, dict):
                intake_case_summary = final_state.get('intake_case_summary')
                if isinstance(intake_case_summary, dict):
                    question_summary = intake_case_summary.get('question_candidate_summary') or {}
            if isinstance(question_summary, dict):
                total_candidates = int(question_summary.get('count') or 0)
                goal_counts = dict(question_summary.get('question_goal_counts') or {})
                if total_candidates > 0 and goal_counts:
                    # Count duplicates as (count - 1) per goal: the first candidate per goal is not a duplicate
                    duplicate_count = sum(max(0, cnt - 1) for cnt in goal_counts.values())
                    duplicate_question_rate_values.append(duplicate_count / total_candidates)
                elif total_candidates > 0:
                    duplicate_question_rate_values.append(0.0)

            # proof_lead_density: proof leads per candidate claim
            proof_lead_summary = final_state.get('proof_lead_summary')
            if not isinstance(proof_lead_summary, dict):
                intake_case_summary = final_state.get('intake_case_summary')
                if isinstance(intake_case_summary, dict):
                    proof_lead_summary = intake_case_summary.get('proof_lead_summary') or {}
            candidate_claims = final_state.get('candidate_claims')
            if not isinstance(candidate_claims, list):
                intake_case_summary = final_state.get('intake_case_summary')
                if isinstance(intake_case_summary, dict):
                    candidate_claims = intake_case_summary.get('candidate_claims') or []
            if isinstance(proof_lead_summary, dict):
                lead_count = int(proof_lead_summary.get('count') or 0)
                claim_count = len(candidate_claims) if isinstance(candidate_claims, list) else 0
                if claim_count > 0:
                    proof_lead_density_values.append(lead_count / claim_count)

        def _avg(values: List[float]) -> Optional[float]:
            return sum(values) / len(values) if values else None

        return {
            'average_chronology_completeness': _avg(chronology_completeness_values),
            'average_contradiction_count': (_avg([float(c) for c in contradiction_counts])
                                            if contradiction_counts else None),
            'average_duplicate_question_rate': _avg(duplicate_question_rate_values),
            'average_proof_lead_density': _avg(proof_lead_density_values),
            'sessions_with_chronology_data': len(chronology_completeness_values),
            'sessions_with_contradiction_data': len(contradiction_counts),
            'sessions_with_question_data': len(duplicate_question_rate_values),
            'sessions_with_proof_lead_data': len(proof_lead_density_values),
        }

    def _phase2_statistics(self, successful_results: List[SessionResult]) -> Dict[str, Any]:
        """Compute Phase 2 (evidence) metrics aggregated across sessions.

        Metrics:
        - ``support_sufficiency``: average ``credible_support_ratio`` from the
          claim support packet summary.
        - ``support_quality_rate``: ratio of high-quality support events
          (corroborated / documentary / authority_only) to total support events
          across the ``support_quality_counts`` map.
        - ``proof_readiness``: average ``proof_readiness_score`` from the
          claim support packet summary.
        """
        _HIGH_QUALITY_LABELS = frozenset({
            'corroborated', 'documentary', 'authority_only', 'high', 'strong',
        })

        support_sufficiency_values: List[float] = []
        support_quality_rate_values: List[float] = []
        proof_readiness_values: List[float] = []

        for result in successful_results:
            final_state = dict(getattr(result, 'final_state', {}) or {})

            packet_summary = final_state.get('claim_support_packet_summary')
            if not isinstance(packet_summary, dict):
                intake_case_summary = final_state.get('intake_case_summary')
                if isinstance(intake_case_summary, dict):
                    packet_summary = intake_case_summary.get('claim_support_packet_summary') or {}

            if not isinstance(packet_summary, dict):
                continue

            credible_ratio = packet_summary.get('credible_support_ratio')
            if credible_ratio is not None:
                support_sufficiency_values.append(float(credible_ratio))

            proof_readiness = packet_summary.get('proof_readiness_score')
            if proof_readiness is not None:
                proof_readiness_values.append(float(proof_readiness))

            quality_counts = dict(packet_summary.get('support_quality_counts') or {})
            if quality_counts:
                total_quality = sum(int(v or 0) for v in quality_counts.values())
                high_quality = sum(
                    int(quality_counts.get(label, 0) or 0)
                    for label in _HIGH_QUALITY_LABELS
                )
                if total_quality > 0:
                    support_quality_rate_values.append(high_quality / total_quality)

        def _avg(values: List[float]) -> Optional[float]:
            return sum(values) / len(values) if values else None

        return {
            'average_support_sufficiency': _avg(support_sufficiency_values),
            'average_support_quality_rate': _avg(support_quality_rate_values),
            'average_proof_readiness': _avg(proof_readiness_values),
            'sessions_with_support_data': len(support_sufficiency_values),
            'sessions_with_quality_data': len(support_quality_rate_values),
            'sessions_with_proof_readiness_data': len(proof_readiness_values),
        }
