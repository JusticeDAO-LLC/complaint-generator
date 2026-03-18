"""
Adversarial Harness Module

Orchestrates multiple adversarial sessions with parallel execution.
"""

import logging
from typing import Dict, Any, List, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
import csv
import json
from datetime import UTC, datetime
import os
import inspect

from .session import AdversarialSession, SessionResult
from .complainant import Complainant, ComplaintContext
from .critic import Critic
from .seed_complaints import SeedComplaintLibrary
from .hacc_evidence import build_hacc_mediator_evidence_packet

logger = logging.getLogger(__name__)


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
            params = sig.parameters
            accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            kwargs: Dict[str, Any] = {}
            if accepts_kwargs or "evidence_db_path" in params:
                kwargs["evidence_db_path"] = evidence_db_path
            if accepts_kwargs or "legal_authority_db_path" in params:
                kwargs["legal_authority_db_path"] = legal_authority_db_path
            if accepts_kwargs or "claim_support_db_path" in params:
                kwargs["claim_support_db_path"] = claim_support_db_path
            if session_id is not None and (accepts_kwargs or "session_id" in params):
                kwargs["session_id"] = session_id
            if session_dir is not None and (accepts_kwargs or "session_dir" in params):
                kwargs["session_dir"] = session_dir
            if kwargs:
                return self.mediator_factory(**kwargs)
        except Exception:
            pass
        return self.mediator_factory()

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
                  hacc_search_mode: str = 'package') -> List[SessionResult]:
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
            seed = seed_complaints[i % len(seed_complaints)]
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
        
        # Run sessions in parallel
        results = []
        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            # Submit all tasks
            future_to_spec = {
                executor.submit(self._run_single_session, spec): spec
                for spec in session_specs
            }
            
            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_spec):
                spec = future_to_spec[future]
                try:
                    result = future.result()
                    # Attach spec metadata for downstream optimization.
                    try:
                        if isinstance(result.seed_complaint, dict):
                            search_summary = _seed_search_summary(
                                result.seed_complaint,
                                str(spec.get('hacc_search_mode') or 'package'),
                            )
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
                                    'anchor_sections': list(
                                        (
                                            result.seed_complaint.get('key_facts', {}) or {}
                                        ).get('anchor_sections', [])
                                    ),
                                }
                            }
                    except Exception:
                        pass

                    results.append(result)
                    self._persist_session(result)
                    completed += 1
                    
                    if result.success:
                        logger.info(f"Session {spec['session_id']} completed ({completed}/{num_sessions}). "
                                  f"Score: {result.critic_score.overall_score:.3f}")
                    else:
                        logger.warning(f"Session {spec['session_id']} failed ({completed}/{num_sessions}): "
                                     f"{result.error}")
                except Exception as e:
                    logger.error(f"Error in session {spec['session_id']}: {e}")
                    completed += 1
        
        self.results.extend(results)
        logger.info(f"Batch complete. {len([r for r in results if r.success])}/{num_sessions} successful")
        
        return results
    
    def _run_single_session(self, spec: Dict[str, Any]) -> SessionResult:
        """Run a single session (called in thread pool)."""
        try:
            session_dir = self._get_session_dir(spec['session_id'])
            if session_dir:
                os.makedirs(session_dir, exist_ok=True)

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

            # Proactively create valid DuckDB container files so they are always present
            # in the session folder (hooks will still initialize schemas when DuckDB is available).
            try:
                import duckdb  # type: ignore
                if evidence_db_path:
                    conn = duckdb.connect(evidence_db_path)
                    conn.close()
                if legal_authority_db_path:
                    conn = duckdb.connect(legal_authority_db_path)
                    conn.close()
                if claim_support_db_path:
                    conn = duckdb.connect(claim_support_db_path)
                    conn.close()
            except Exception:
                pass

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
            preloaded_evidence = self._preload_hacc_seed_evidence(
                mediator,
                spec['seed'],
                session_id=spec['session_id'],
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
                max_turns=spec['max_turns']
            )
            
            result = session.run(spec['seed'])
            return result
            
        except Exception as e:
            logger.error(f"Error running session {spec['session_id']}: {e}", exc_info=True)
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
