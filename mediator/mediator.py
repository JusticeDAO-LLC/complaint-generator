from time import time
import re
from typing import List, Optional, Dict, Any
from .strings import user_prompts
from .state import State
from .inquiries import Inquiries
from .complaint import Complaint
from .exceptions import UserPresentableException
from .legal_hooks import (
	LegalClassificationHook,
	StatuteRetrievalHook,
	SummaryJudgmentHook,
	QuestionGenerationHook
)
from .evidence_hooks import (
	EvidenceStorageHook,
	EvidenceStateHook,
	EvidenceAnalysisHook
)
from .legal_authority_hooks import (
	LegalAuthoritySearchHook,
	LegalAuthorityStorageHook,
	LegalAuthorityAnalysisHook
)
from .web_evidence_hooks import (
	WebEvidenceSearchHook,
	WebEvidenceIntegrationHook
)
from .claim_support_hooks import ClaimSupportHook
from .formal_document import ComplaintDocumentBuilder
from integrations.ipfs_datasets.capabilities import (
	summarize_ipfs_datasets_startup_payload,
)
from integrations.ipfs_datasets.graphs import persist_graph_snapshot, query_graph_support
from claim_support_review import (
	ClaimSupportFollowUpExecuteRequest,
	ClaimSupportReviewRequest,
	_summarize_follow_up_execution_claim,
	_summarize_follow_up_plan_claim,
	build_claim_support_follow_up_execution_payload,
	build_claim_support_review_payload,
	summarize_follow_up_history_claim,
	summarize_claim_reasoning_review,
	summarize_claim_support_snapshot_lifecycle,
)
from document_pipeline import FormalComplaintDocumentBuilder


ALIGNMENT_TASK_UPDATE_HISTORY_LIMIT = 25

# Import three-phase complaint processing
from complaint_phases import (
	CLAIM_INTAKE_REQUIREMENTS,
	PhaseManager,
	ComplaintPhase,
	KnowledgeGraphBuilder,
	DependencyGraphBuilder,
	ComplaintDenoiser,
	build_intake_case_file,
	match_required_element_id,
	refresh_intake_case_file,
	refresh_intake_sections,
	LegalGraphBuilder,
	LegalGraph,
	LegalElement,
	NeurosymbolicMatcher,
	NodeType
)


class Mediator:
	def __init__(self, backends, evidence_db_path=None, legal_authority_db_path=None, claim_support_db_path=None):
		self.backends = backends
		# Initialize state early because hooks may log during construction.
		self.state = State()
		startup_payload = summarize_ipfs_datasets_startup_payload()
		self.log(
			'ipfs_datasets_capabilities',
			**startup_payload,
		)
		self.inquiries = Inquiries(self)
		self.complaint = Complaint(self)
		
		# Initialize legal hooks
		self.legal_classifier = LegalClassificationHook(self)
		self.statute_retriever = StatuteRetrievalHook(self)
		self.summary_judgment = SummaryJudgmentHook(self)
		self.question_generator = QuestionGenerationHook(self)
		
		# Initialize evidence hooks
		self.evidence_storage = EvidenceStorageHook(self)
		self.evidence_state = EvidenceStateHook(self, db_path=evidence_db_path)
		self.evidence_analysis = EvidenceAnalysisHook(self)
		self.claim_support = ClaimSupportHook(self, db_path=claim_support_db_path)
		
		# Initialize legal authority hooks
		self.legal_authority_search = LegalAuthoritySearchHook(self)
		self.legal_authority_storage = LegalAuthorityStorageHook(self, db_path=legal_authority_db_path)
		self.legal_authority_analysis = LegalAuthorityAnalysisHook(self)
		
		# Initialize web evidence discovery hooks
		self.web_evidence_search = WebEvidenceSearchHook(self)
		self.web_evidence_integration = WebEvidenceIntegrationHook(self)
		
		# Initialize three-phase complaint processing
		self.phase_manager = PhaseManager(mediator=self)
		self.kg_builder = KnowledgeGraphBuilder(mediator=self)
		self.dg_builder = DependencyGraphBuilder(mediator=self)
		self.denoiser = ComplaintDenoiser(mediator=self)
		self.legal_graph_builder = LegalGraphBuilder(mediator=self)
		self.neurosymbolic_matcher = NeurosymbolicMatcher(mediator=self)
		
		# State is already initialized above; keep reset() for callers that
		# explicitly want a fresh state.
		# self.reset()


	def reset(self):
		self.state = State()
		# self.inquiries.register(user_prompts['genesis_question'])

	def resume(self, state):
		self.state = state


	def get_state(self):
		state = self.state.serialize()
		return self.state.serialize()


	def set_state(self, serialized):
		self.state = State.from_serialized(serialized)

	def response(self):
		return "I'm sorry, I don't understand. Please try again."

	def select_intake_question_candidates(
		self,
		candidates: List[Dict[str, Any]],
		*,
		max_questions: int = 10,
	) -> List[Dict[str, Any]]:
		"""Default intake-question selector using explicit reasoning signals and a fallback heuristic."""
		normalized_candidates = [candidate for candidate in (candidates or []) if isinstance(candidate, dict)]
		if not normalized_candidates:
			return []
		dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
		kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
		intake_case_file = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
		claim_pressure = self._build_intake_claim_pressure_map(dg)
		matching_pressure = self._build_intake_matching_pressure_map(kg, dg, intake_case_file)
		scored_candidates = [
			self._annotate_intake_question_candidate(candidate, claim_pressure, matching_pressure)
			for candidate in normalized_candidates
		]
		scored_candidates.sort(
			key=lambda candidate: (
				-float(candidate.get('selector_score', 0.0) or 0.0),
				int(candidate.get('proof_priority', 99) or 99),
			)
		)
		return scored_candidates[:max_questions]

	def _build_intake_claim_pressure_map(self, dependency_graph) -> Dict[str, Dict[str, Any]]:
		pressure_map: Dict[str, Dict[str, Any]] = {}
		if dependency_graph is None:
			return pressure_map

		for claim in dependency_graph.get_nodes_by_type(NodeType.CLAIM):
			if claim is None:
				continue
			claim_type = str(claim.attributes.get('claim_type') or '').strip().lower()
			if not claim_type:
				continue
			check = dependency_graph.check_satisfaction(claim.id)
			missing_count = int(len(check.get('missing_dependencies', [])) if isinstance(check, dict) else 0)
			pressure_map[claim_type] = {
				'claim_id': claim.id,
				'claim_name': claim.name,
				'missing_count': missing_count,
				'satisfaction_ratio': float(check.get('satisfaction_ratio', 0.0) or 0.0) if isinstance(check, dict) else 0.0,
			}
		return pressure_map

	def _build_intake_selector_legal_graph(self, intake_case_file: Dict[str, Any]) -> LegalGraph:
		legal_graph = LegalGraph()
		candidate_claims = intake_case_file.get('candidate_claims', []) if isinstance(intake_case_file, dict) else []
		for claim in candidate_claims:
			if not isinstance(claim, dict):
				continue
			claim_type = str(claim.get('claim_type') or '').strip().lower()
			if not claim_type:
				continue
			registry = CLAIM_INTAKE_REQUIREMENTS.get(claim_type, {})
			elements = registry.get('elements', []) if isinstance(registry, dict) else []
			for element in elements:
				if not isinstance(element, dict):
					continue
				element_id = str(element.get('element_id') or '').strip()
				if not element_id:
					continue
				legal_graph.add_element(
					LegalElement(
						id=f"intake_req:{claim_type}:{element_id}",
						element_type='requirement',
						name=str(element.get('label') or element_id),
						description=f"Intake ontology requirement for {claim_type}: {element_id}",
						citation='intake_ontology',
						jurisdiction='intake',
						required=bool(element.get('blocking', True)),
						attributes={
							'applicable_claim_types': [claim_type],
							'element_id': element_id,
							'source': 'intake_claim_registry',
						},
					)
				)
		return legal_graph

	def _build_intake_matching_pressure_map(
		self,
		knowledge_graph,
		dependency_graph,
		intake_case_file: Dict[str, Any],
	) -> Dict[str, Dict[str, Any]]:
		pressure_map: Dict[str, Dict[str, Any]] = {}
		if knowledge_graph is None or dependency_graph is None or not isinstance(intake_case_file, dict):
			return pressure_map
		try:
			legal_graph = self._build_intake_selector_legal_graph(intake_case_file)
			if not getattr(legal_graph, 'elements', {}):
				return pressure_map
			matching = self.neurosymbolic_matcher.match_claims_to_law(knowledge_graph, dependency_graph, legal_graph)
		except Exception:
			return pressure_map

		for claim_result in matching.get('claims', []) if isinstance(matching, dict) else []:
			if not isinstance(claim_result, dict):
				continue
			claim_type = str(claim_result.get('claim_type') or '').strip().lower()
			if not claim_type:
				continue
			missing_requirements = claim_result.get('missing_requirements', [])
			missing_requirement_names = [
				str(item.get('requirement_name') or '').strip()
				for item in missing_requirements
				if isinstance(item, dict) and item.get('requirement_name')
			]
			missing_requirement_element_ids: List[str] = []
			for legal_requirement in legal_graph.get_requirements_for_claim_type(claim_type):
				if legal_requirement.name not in missing_requirement_names:
					continue
				element_id = str((legal_requirement.attributes or {}).get('element_id') or '').strip()
				if element_id and element_id not in missing_requirement_element_ids:
					missing_requirement_element_ids.append(element_id)
			pressure_map[claim_type] = {
				'missing_requirement_count': len(missing_requirements) if isinstance(missing_requirements, list) else 0,
				'matcher_confidence': float(claim_result.get('confidence', 0.0) or 0.0),
				'legal_requirements': int(claim_result.get('legal_requirements', 0) or 0),
				'satisfied_requirements': int(claim_result.get('satisfied_requirements', 0) or 0),
				'missing_requirement_names': missing_requirement_names,
				'missing_requirement_element_ids': missing_requirement_element_ids,
			}
		return pressure_map

	def _annotate_intake_question_candidate(
		self,
		candidate: Dict[str, Any],
		claim_pressure: Dict[str, Dict[str, Any]],
		matching_pressure: Dict[str, Dict[str, Any]],
	) -> Dict[str, Any]:
		annotated = dict(candidate)
		explanation = dict(candidate.get('ranking_explanation', {}) if isinstance(candidate.get('ranking_explanation'), dict) else {})
		target_claim_type = str(
			explanation.get('target_claim_type')
			or candidate.get('target_claim_type')
			or ''
		).strip().lower()
		claim_state = claim_pressure.get(target_claim_type, {})
		matching_state = matching_pressure.get(target_claim_type, {})
		missing_count = int(claim_state.get('missing_count', 0) or 0)
		satisfaction_ratio = float(claim_state.get('satisfaction_ratio', 0.0) or 0.0)
		matcher_missing_requirement_count = int(matching_state.get('missing_requirement_count', 0) or 0)
		matcher_confidence = float(matching_state.get('matcher_confidence', 0.0) or 0.0)
		missing_requirement_element_ids = [
			str(item).strip().lower()
			for item in (matching_state.get('missing_requirement_element_ids') or [])
			if item
		]
		blocking_level = str(explanation.get('blocking_level') or candidate.get('blocking_level') or '').strip().lower()
		question_goal = str(explanation.get('question_goal') or candidate.get('question_goal') or '').strip().lower()
		candidate_source = str(explanation.get('candidate_source') or candidate.get('candidate_source') or '').strip().lower()
		proof_priority = int(candidate.get('proof_priority', 99) or 99)
		target_element_id = str(
			explanation.get('target_element_id')
			or candidate.get('target_element_id')
			or ''
		).strip().lower()
		direct_legal_target_match = bool(target_element_id and target_element_id in missing_requirement_element_ids)

		score = 0.0
		score += max(0, 10 - proof_priority) * 2.0
		score += {
			'blocking': 20.0,
			'important': 10.0,
			'informational': 0.0,
		}.get(blocking_level, 0.0)
		score += {
			'dependency_graph_contradiction': 35.0,
			'intake_claim_element_gap': 18.0,
			'intake_proof_gap': 12.0,
			'dependency_graph_requirement': 10.0,
			'knowledge_graph_gap': 6.0,
		}.get(candidate_source, 0.0)
		score += {
			'establish_element': 8.0,
			'identify_supporting_proof': 5.0,
			'resolve_factual_contradiction': 12.0,
		}.get(question_goal, 0.0)
		score += min(missing_count, 5) * 2.0
		score += max(0.0, 1.0 - satisfaction_ratio) * 5.0
		score += min(matcher_missing_requirement_count, 5) * 3.0
		score += max(0.0, 1.0 - matcher_confidence) * 4.0
		if direct_legal_target_match:
			score += 15.0

		selector_signals = {
			'candidate_source': candidate_source,
			'blocking_level': blocking_level,
			'question_goal': question_goal,
			'proof_priority': proof_priority,
			'claim_missing_dependency_count': missing_count,
			'claim_satisfaction_ratio': satisfaction_ratio,
			'matcher_missing_requirement_count': matcher_missing_requirement_count,
			'matcher_confidence': matcher_confidence,
			'matcher_missing_requirement_element_ids': missing_requirement_element_ids,
			'direct_legal_target_match': direct_legal_target_match,
		}
		annotated['selector_score'] = score
		annotated['selector_signals'] = selector_signals
		explanation['selector_score'] = score
		explanation['selector_signals'] = selector_signals
		annotated['ranking_explanation'] = explanation
		return annotated

	def io(self, text):
		self.log('user_input', text=text)

		try:
			output = self.process(text)
			self.log('user_output', text=output)
		except Exception as exception:
			self.log('io_error', error=str(exception))
			raise exception

		return output


	def process(self, text):
		if not self.state:
			raise UserPresentableException(
				'no-context',
				'No internal state given. Either create new, or resume.'
			)

		if text:
			self.inquiries.answer(text)

		if not self.inquiries.get_next():
			self.complaint.generate()
			self.inquiries.generate()

			if self.inquiries.is_complete():
				return self.finalize()

		return self.inquiries.get_next()['question']


	def finalize(self):
		raise UserPresentableException(
			'not-implemented',
			'The Q&A has been completed. The follow-up flow has not yet been implemented.'
		)

	def analyze_complaint_legal_issues(self):
		"""
		Analyze complaint and classify legal issues.
		
		Returns classification, statutes, requirements, and generated questions.
		"""
		if not self.state.complaint:
			raise UserPresentableException(
				'no-complaint',
				'No complaint available to analyze. Generate complaint first.'
			)
		
		# Step 1: Classify the legal issues
		self.log('legal_analysis', step='classification')
		classification = self.legal_classifier.classify_complaint(self.state.complaint)
		self.state.legal_classification = classification
		
		# Step 2: Retrieve applicable statutes
		self.log('legal_analysis', step='statute_retrieval')
		statutes = self.statute_retriever.retrieve_statutes(classification)
		self.state.applicable_statutes = statutes
		
		# Step 3: Generate summary judgment requirements
		self.log('legal_analysis', step='requirements_generation')
		requirements = self.summary_judgment.generate_requirements(classification, statutes)
		self.state.summary_judgment_requirements = requirements
		user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		complaint_id = getattr(self.state, 'complaint_id', None)
		self.claim_support.register_claim_requirements(user_id, requirements, complaint_id=complaint_id)
		support_summary = self.summarize_claim_support(user_id=user_id)
		
		# Step 4: Generate targeted questions
		self.log('legal_analysis', step='question_generation')
		questions = self.question_generator.generate_questions(requirements, classification)
		self.state.legal_questions = questions
		
		return {
			'classification': classification,
			'statutes': statutes,
			'requirements': requirements,
			'support_summary': support_summary,
			'questions': questions
		}
	
	def get_legal_analysis(self):
		"""Get the current legal analysis results."""
		user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return {
			'classification': getattr(self.state, 'legal_classification', None),
			'statutes': getattr(self.state, 'applicable_statutes', None),
			'requirements': getattr(self.state, 'summary_judgment_requirements', None),
			'support_summary': self.summarize_claim_support(user_id=user_id),
			'questions': getattr(self.state, 'legal_questions', None)
		}
	
	def submit_evidence(self, data: bytes, evidence_type: str,
	                   user_id: str = None,
	                   description: str = None,
	                   claim_type: str = None,
	                   claim_element: str = None,
	                   metadata: dict = None):
		"""
		Submit evidence for the user's case.
		
		Args:
			data: Evidence data as bytes
			evidence_type: Type of evidence (document, image, video, text, etc.)
			user_id: User identifier (defaults to state username)
			description: Description of the evidence
			claim_type: Which claim this evidence supports
			metadata: Additional metadata
			
		Returns:
			Dictionary with evidence information including CID and record ID
		"""
		# Use username from state if user_id not provided
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')

		# Get complaint ID if available
		complaint_id = getattr(self.state, 'complaint_id', None)
		resolved_element = {'claim_element_id': None, 'claim_element_text': claim_element}
		if claim_type:
			resolved_element = self.claim_support.resolve_claim_element(
				user_id,
				claim_type,
				claim_element_text=claim_element,
				support_label=description or evidence_type,
				metadata=metadata,
			)

		storage_metadata = dict(metadata or {})
		if claim_type and 'claim_type' not in storage_metadata:
			storage_metadata['claim_type'] = claim_type
		if resolved_element.get('claim_element_id') and 'claim_element_id' not in storage_metadata:
			storage_metadata['claim_element_id'] = resolved_element.get('claim_element_id')
		if resolved_element.get('claim_element_text') and 'claim_element' not in storage_metadata:
			storage_metadata['claim_element'] = resolved_element.get('claim_element_text')
		
		# Store in IPFS
		self.log('evidence_submission', user_id=user_id, type=evidence_type)
		evidence_info = self.evidence_storage.store_evidence(data, evidence_type, storage_metadata)
		
		# Store state in DuckDB
		record_result = self.evidence_state.upsert_evidence_record(
			user_id=user_id,
			evidence_info=evidence_info,
			complaint_id=complaint_id,
			claim_type=claim_type,
			claim_element_id=resolved_element.get('claim_element_id'),
			claim_element=resolved_element.get('claim_element_text'),
			description=description
		)
		record_id = record_result['record_id']
		
		result = {
			**evidence_info,
			'record_id': record_id,
			'record_created': record_result.get('created', False),
			'record_reused': record_result.get('reused', False),
			'claim_element_id': resolved_element.get('claim_element_id'),
			'claim_element_text': resolved_element.get('claim_element_text'),
			'user_id': user_id,
		}

		if claim_type:
			support_link_result = self.claim_support.upsert_support_link(
				user_id=user_id,
				complaint_id=complaint_id,
				claim_type=claim_type,
				claim_element_id=resolved_element.get('claim_element_id'),
				claim_element_text=resolved_element.get('claim_element_text'),
				support_kind='evidence',
				support_ref=evidence_info['cid'],
				support_label=description or evidence_type,
				source_table='evidence',
				support_strength=float(result.get('metadata', {}).get('relevance_score', 0.7)),
				metadata={
					'record_id': record_id,
					'evidence_type': evidence_type,
					'provenance': result.get('metadata', {}).get('provenance', {}),
				},
			)
			result['support_link_id'] = support_link_result.get('record_id')
			result['support_link_created'] = support_link_result.get('created', False)
			result['support_link_reused'] = support_link_result.get('reused', False)

		if self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph'):
			graph_result = self.add_evidence_to_graphs({
				**result,
				'name': description or evidence_type,
				'confidence': 0.8,
			})
			result['graph_projection'] = graph_result.get('graph_projection', {})
		
		self.log('evidence_submitted', cid=evidence_info['cid'], record_id=record_id)
		
		return result
	
	def submit_evidence_file(self, file_path: str, evidence_type: str,
	                        user_id: str = None,
	                        description: str = None,
	                        claim_type: str = None,
	                        claim_element: str = None,
	                        metadata: dict = None):
		"""
		Submit evidence from a file.
		
		Args:
			file_path: Path to evidence file
			evidence_type: Type of evidence
			user_id: User identifier
			description: Description of the evidence
			claim_type: Which claim this evidence supports
			metadata: Additional metadata
			
		Returns:
			Dictionary with evidence information including CID and record ID
		"""
		# Read file and submit
		with open(file_path, 'rb') as f:
			data = f.read()
		
		# Add filename to metadata
		file_metadata = metadata or {}
		file_metadata['filename'] = file_path
		
		return self.submit_evidence(
			data=data,
			evidence_type=evidence_type,
			user_id=user_id,
			description=description,
			claim_type=claim_type,
			claim_element=claim_element,
			metadata=file_metadata
		)
	
	def get_user_evidence(self, user_id: str = None):
		"""
		Get all evidence for a user.
		
		Args:
			user_id: User identifier (defaults to state username)
			
		Returns:
			List of evidence records
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		return self.evidence_state.get_user_evidence(user_id)

	def get_evidence_graph(self, evidence_id: int):
		"""Get stored graph entities and relationships for an evidence record."""
		return self.evidence_state.get_evidence_graph(evidence_id)

	def get_evidence_chunks(self, evidence_id: int):
		"""Get stored chunk rows for an evidence record."""
		return self.evidence_state.get_evidence_chunks(evidence_id)

	def get_evidence_facts(self, evidence_id: int):
		"""Get stored fact records for an evidence record."""
		return self.evidence_state.get_evidence_facts(evidence_id)

	def get_authority_facts(self, authority_id: int):
		"""Get stored fact records for a legal authority."""
		return self.legal_authority_storage.get_authority_facts(authority_id)
	
	def retrieve_evidence(self, cid: str):
		"""
		Retrieve evidence data by CID.
		
		Args:
			cid: Content ID of the evidence
			
		Returns:
			Evidence data as bytes
		"""
		return self.evidence_storage.retrieve_evidence(cid)
	
	def analyze_evidence(self, user_id: str = None, claim_type: str = None):
		"""
		Analyze evidence for a claim.
		
		Args:
			user_id: User identifier (defaults to state username)
			claim_type: Claim type to analyze evidence for
			
		Returns:
			Analysis results
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		if claim_type:
			return self.evidence_analysis.analyze_evidence_for_claim(user_id, claim_type)
		else:
			# Return general evidence stats
			return self.evidence_state.get_evidence_statistics(user_id)

	def get_scraper_runs(self, user_id: str = None, limit: int = 20):
		"""Get persisted scraper run summaries."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.evidence_state.get_scraper_runs(user_id=user_id, limit=limit)

	def get_scraper_run_details(self, run_id: int):
		"""Get one persisted scraper run with iteration and tactic detail."""
		return self.evidence_state.get_scraper_run_details(run_id)

	def get_scraper_tactic_performance(self, user_id: str = None, limit_runs: int = 20):
		"""Get aggregated tactic performance from persisted scraper runs."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.evidence_state.get_scraper_tactic_performance(user_id=user_id, limit_runs=limit_runs)

	def enqueue_agentic_scraper_job(self,
	                              keywords: List[str],
	                              domains: Optional[List[str]] = None,
	                              iterations: int = 3,
	                              sleep_seconds: float = 0.0,
	                              quality_domain: str = 'caselaw',
	                              user_id: str = None,
	                              claim_type: str = None,
	                              min_relevance: float = 0.5,
	                              store_results: bool = True,
	                              priority: int = 100,
	                              available_at = None,
	                              metadata: Dict[str, Any] = None):
		"""Queue an agentic scraper job for later worker execution."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.evidence_state.enqueue_scraper_job(
			user_id=user_id,
			keywords=keywords,
			domains=domains,
			claim_type=claim_type,
			iterations=iterations,
			sleep_seconds=sleep_seconds,
			quality_domain=quality_domain,
			min_relevance=min_relevance,
			store_results=store_results,
			priority=priority,
			available_at=available_at,
			metadata=metadata,
		)

	def get_scraper_queue(self, user_id: str = None, status: str = None, limit: int = 20):
		"""Get queued scraper jobs."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.evidence_state.get_scraper_queue(user_id=user_id, status=status, limit=limit)

	def get_scraper_queue_job(self, job_id: int):
		"""Get one queued scraper job."""
		return self.evidence_state.get_scraper_queue_job(job_id)

	def run_next_agentic_scraper_job(self, worker_id: str = 'agentic-scraper-worker', user_id: str = None):
		"""Claim and execute the next queued scraper job, if one is available."""
		claim_result = self.evidence_state.claim_next_scraper_job(worker_id=worker_id, user_id=user_id)
		if not claim_result.get('claimed'):
			return {
				'claimed': False,
				'ran': False,
				'worker_id': worker_id,
				'job': None,
				'error': claim_result.get('error'),
			}

		job = claim_result.get('job') or {}
		job_user_id = job.get('user_id') or user_id or getattr(self.state, 'username', None)
		if job_user_id:
			self.state.username = job_user_id

		try:
			run_result = self.run_agentic_scraper_cycle(
				keywords=job.get('keywords', []),
				domains=job.get('domains') or None,
				iterations=int(job.get('iterations', 1) or 1),
				sleep_seconds=float(job.get('sleep_seconds', 0.0) or 0.0),
				quality_domain=job.get('quality_domain') or 'caselaw',
				user_id=job_user_id,
				claim_type=job.get('claim_type'),
				min_relevance=float(job.get('min_relevance', 0.5) or 0.5),
				store_results=bool(job.get('store_results', True)),
			)

			completion = self.evidence_state.complete_scraper_job(
				job_id=job['id'],
				run_id=(run_result.get('scraper_run') or {}).get('run_id'),
				metadata={
					'final_result_count': len(run_result.get('final_results', []) or []),
					'storage_summary': run_result.get('storage_summary', {}),
				},
			)
			return {
				'claimed': True,
				'ran': True,
				'worker_id': worker_id,
				'job': completion.get('job', job),
				'run_result': run_result,
			}
		except Exception as exc:
			completion = self.evidence_state.complete_scraper_job(
				job_id=job['id'],
				error=str(exc),
			)
			return {
				'claimed': True,
				'ran': False,
				'worker_id': worker_id,
				'job': completion.get('job', job),
				'error': str(exc),
			}
	
	def search_legal_authorities(self, query: str, claim_type: str = None,
	                            jurisdiction: str = None,
	                            search_all: bool = False,
	                            authority_families: List[str] = None):
		"""
		Search for relevant legal authorities.
		
		Args:
			query: Search query (e.g., "civil rights violations")
			claim_type: Optional claim type to focus search
			jurisdiction: Optional jurisdiction filter
			search_all: If True, search all sources; if False, use targeted search
			
		Returns:
			Dictionary with search results by source type
		"""
		if search_all:
			return self.legal_authority_search.search_all_sources(
				query, claim_type, jurisdiction, authority_families=authority_families
			)
		else:
			# Default to US Code search
			results = {
				'statutes': self.legal_authority_search.search_us_code(query),
				'regulations': [],
				'case_law': [],
				'web_archives': []
			}
			return results
	
	def store_legal_authorities(self, authorities: Dict[str, List[Dict[str, Any]]], 
	                           claim_type: str = None,
	                           search_query: str = None,
	                           user_id: str = None,
	                           search_programs: List[Dict[str, Any]] = None):
		"""
		Store found legal authorities in DuckDB.
		
		Args:
			authorities: Dictionary with authorities by type (from search_legal_authorities)
			claim_type: Optional claim type these authorities support
			search_query: Original search query
			user_id: User identifier (defaults to state username)
			
		Returns:
			Dictionary with count of stored authorities by type
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		complaint_id = getattr(self.state, 'complaint_id', None)
		
		stored_counts = {
			'total_records': 0,
			'total_new': 0,
			'total_reused': 0,
			'total_support_links_added': 0,
			'total_support_links_reused': 0,
		}
		for auth_type, auth_list in authorities.items():
			if auth_list:
				# Add type info to each authority
				for auth in auth_list:
					auth['type'] = auth_type.rstrip('s')  # statutes -> statute
					if search_programs and not auth.get('search_programs'):
						auth['search_programs'] = [
							dict(program)
							for program in search_programs
							if isinstance(program, dict)
						]

				record_ids = []
				created_count = 0
				reused_count = 0
				support_links_added = 0
				support_links_reused = 0
				for auth in auth_list:
					upsert_result = self.legal_authority_storage.upsert_authority(
						auth,
						user_id,
						complaint_id,
						claim_type,
						search_query,
					)
					record_id = upsert_result['record_id']
					record_ids.append(record_id)
					created_count += 1 if upsert_result.get('created') else 0
					reused_count += 1 if upsert_result.get('reused') else 0
					if claim_type:
						support_ref = auth.get('citation') or auth.get('url') or str(record_id)
						support_link_result = self.claim_support.upsert_support_link(
							user_id=user_id,
							complaint_id=complaint_id,
							claim_type=claim_type,
							claim_element_text=auth.get('claim_element'),
							support_kind='authority',
							support_ref=support_ref,
							support_label=auth.get('title') or auth.get('citation') or auth_type,
							source_table='legal_authorities',
							support_strength=float(auth.get('relevance_score', 0.6)),
							metadata={
								'record_id': record_id,
								'authority_type': auth.get('type'),
								'source': auth.get('source'),
								'provenance': auth.get('provenance', auth.get('metadata', {}).get('provenance', {})),
							},
						)
						support_links_added += 1 if support_link_result.get('created') else 0
						support_links_reused += 1 if support_link_result.get('reused') else 0

				stored_counts[auth_type] = len(record_ids)
				stored_counts[f'{auth_type}_new'] = created_count
				stored_counts[f'{auth_type}_reused'] = reused_count
				stored_counts[f'{auth_type}_support_links_added'] = support_links_added
				stored_counts[f'{auth_type}_support_links_reused'] = support_links_reused
				stored_counts['total_records'] += len(record_ids)
				stored_counts['total_new'] += created_count
				stored_counts['total_reused'] += reused_count
				stored_counts['total_support_links_added'] += support_links_added
				stored_counts['total_support_links_reused'] += support_links_reused
				
				self.log('legal_authorities_stored',
					type=auth_type, count=len(record_ids), claim_type=claim_type)
		
		return stored_counts
	
	def get_legal_authorities(self, user_id: str = None, claim_type: str = None):
		"""
		Get stored legal authorities.
		
		Args:
			user_id: User identifier (defaults to state username)
			claim_type: Optional claim type to filter by
			
		Returns:
			List of legal authority records
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		if claim_type:
			return self.legal_authority_storage.get_authorities_by_claim(user_id, claim_type)
		else:
			return self.legal_authority_storage.get_all_authorities(user_id)
	
	def analyze_legal_authorities(self, claim_type: str, user_id: str = None):
		"""
		Analyze stored legal authorities for a claim.
		
		Args:
			claim_type: Claim type to analyze
			user_id: User identifier (defaults to state username)
			
		Returns:
			Analysis with recommendations
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		return self.legal_authority_analysis.analyze_authorities_for_claim(user_id, claim_type)

	def get_claim_support(self, user_id: str = None, claim_type: str = None):
		"""Get persisted claim-support links."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.get_support_links(user_id, claim_type)

	def get_claim_requirements(self, user_id: str = None, claim_type: str = None):
		"""Get persisted claim requirements by claim type."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.get_claim_requirements(user_id, claim_type)

	def summarize_claim_support(self, user_id: str = None, claim_type: str = None):
		"""Summarize persisted evidence and authority support by claim type."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.summarize_claim_support(user_id, claim_type)

	def get_claim_support_facts(
		self,
		claim_type: str = None,
		user_id: str = None,
		claim_element_id: str = None,
		claim_element_text: str = None,
		claim_element: str = None,
	):
		"""Get persisted fact rows attached to evidence and authority support links."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		resolved_claim_element_text = claim_element_text or claim_element
		return self.claim_support.get_claim_support_facts(
			user_id,
			claim_type,
			claim_element_id=claim_element_id,
			claim_element_text=resolved_claim_element_text,
		)

	def get_claim_overview(
		self,
		claim_type: str = None,
		user_id: str = None,
		required_support_kinds: List[str] = None,
	):
		"""Group claim elements into covered, partially supported, and missing buckets."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.get_claim_overview(
			user_id,
			claim_type=claim_type,
			required_support_kinds=required_support_kinds,
		)

	def get_claim_coverage_matrix(
		self,
		claim_type: str = None,
		user_id: str = None,
		required_support_kinds: List[str] = None,
	):
		"""Return a review-oriented coverage matrix for claim elements and support sources."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.get_claim_coverage_matrix(
			user_id,
			claim_type=claim_type,
			required_support_kinds=required_support_kinds,
		)

	def get_claim_support_gaps(
		self,
		claim_type: str = None,
		user_id: str = None,
		required_support_kinds: List[str] = None,
	):
		"""Return unresolved claim elements with current support, facts, and graph-backed context."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		gap_analysis = self.claim_support.get_claim_support_gaps(
			user_id,
			claim_type=claim_type,
			required_support_kinds=required_support_kinds,
		)
		for current_claim, claim_gap in gap_analysis.get('claims', {}).items():
			for element in claim_gap.get('unresolved_elements', []):
				element['graph_support'] = self.query_claim_graph_support(
					claim_type=current_claim,
					claim_element_id=element.get('element_id'),
					claim_element=element.get('element_text'),
					user_id=user_id,
				)
		return gap_analysis

	def get_claim_support_validation(
		self,
		claim_type: str = None,
		user_id: str = None,
		required_support_kinds: List[str] = None,
	):
		"""Return normalized validation and proof-gap diagnostics for each claim element."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.get_claim_support_validation(
			user_id,
			claim_type=claim_type,
			required_support_kinds=required_support_kinds,
		)

	def save_claim_testimony_record(
		self,
		claim_type: str = None,
		user_id: str = None,
		claim_element_id: str = None,
		claim_element_text: str = None,
		raw_narrative: str = None,
		event_date: str = None,
		actor: str = None,
		act: str = None,
		target: str = None,
		harm: str = None,
		firsthand_status: str = None,
		source_confidence: float = None,
		metadata: Dict[str, Any] = None,
	):
		"""Persist a testimony record linked to claim-support review."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		result = self.claim_support.save_testimony_record(
			user_id,
			claim_type=claim_type or '',
			claim_element_id=claim_element_id,
			claim_element_text=claim_element_text,
			raw_narrative=raw_narrative,
			event_date=event_date,
			actor=actor,
			act=act,
			target=target,
			harm=harm,
			firsthand_status=firsthand_status,
			source_confidence=source_confidence,
			metadata=metadata,
		)
		if bool((result or {}).get('recorded')):
			self._promote_alignment_task_update(
				claim_type=claim_type or '',
				claim_element_id=claim_element_id or '',
				promotion_kind='testimony',
				promotion_ref=str((result or {}).get('testimony_id') or ''),
				answer_preview=str(raw_narrative or ''),
			)
		return result

	def get_claim_testimony_records(
		self,
		claim_type: str = None,
		user_id: str = None,
		claim_element_id: str = None,
		limit: int = 50,
	):
		"""Return persisted testimony records for claim-support review."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.get_claim_testimony_records(
			user_id,
			claim_type=claim_type,
			claim_element_id=claim_element_id,
			limit=limit,
		)

	def save_claim_support_document(
		self,
		claim_type: str = None,
		user_id: str = None,
		claim_element_id: str = None,
		claim_element_text: str = None,
		document_text: str = None,
		document_bytes: bytes = None,
		document_label: str = None,
		source_url: str = None,
		filename: str = None,
		mime_type: str = None,
		evidence_type: str = 'document',
		metadata: Dict[str, Any] = None,
	):
		"""Persist a dashboard-provided document through the shared evidence pipeline."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')

		normalized_text = str(document_text or '').strip()
		data_bytes = document_bytes
		if data_bytes is None and normalized_text:
			data_bytes = normalized_text.encode('utf-8')
		if not data_bytes:
			return {
				'recorded': False,
				'error': 'empty_document_payload',
				'claim_type': claim_type,
				'user_id': user_id,
			}

		storage_metadata = dict(metadata or {})
		storage_metadata['parse_document'] = True
		if filename:
			storage_metadata['filename'] = filename
		if mime_type:
			storage_metadata['mime_type'] = mime_type
		if source_url:
			storage_metadata['source_url'] = source_url
			provenance = dict(storage_metadata.get('provenance') or {})
			provenance.setdefault('source_url', source_url)
			provenance.setdefault('acquisition_method', 'claim_support_dashboard')
			storage_metadata['provenance'] = provenance

		result = self.submit_evidence(
			data=data_bytes,
			evidence_type=evidence_type or 'document',
			user_id=user_id,
			description=document_label or filename or source_url or 'Claim support document',
			claim_type=claim_type,
			claim_element=claim_element_text,
			metadata=storage_metadata,
		)
		payload = {
			**result,
			'recorded': bool(result.get('record_id')),
			'claim_element_id': claim_element_id or result.get('claim_element_id'),
			'claim_element_text': claim_element_text or result.get('claim_element_text'),
		}
		if payload['recorded']:
			self._promote_alignment_task_update(
				claim_type=claim_type or '',
				claim_element_id=str(payload.get('claim_element_id') or ''),
				promotion_kind='document',
				promotion_ref=str(payload.get('record_id') or payload.get('artifact_id') or ''),
				answer_preview=normalized_text,
			)
		return payload

	def get_claim_contradiction_candidates(
		self,
		claim_type: str = None,
		user_id: str = None,
	):
		"""Return heuristic contradiction candidates across support facts for each claim element."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.get_claim_contradiction_candidates(
			user_id,
			claim_type=claim_type,
		)

	def persist_claim_support_diagnostics(
		self,
		claim_type: str = None,
		user_id: str = None,
		required_support_kinds: List[str] = None,
		gaps: Dict[str, Any] = None,
		contradictions: Dict[str, Any] = None,
		metadata: Dict[str, Any] = None,
		retention_limit: int = 3,
	):
		"""Persist gap and contradiction diagnostics for later review reuse."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.persist_claim_support_diagnostics(
			user_id,
			claim_type=claim_type,
			required_support_kinds=required_support_kinds,
			gaps=gaps,
			contradictions=contradictions,
			metadata=metadata,
			retention_limit=retention_limit,
		)

	def prune_claim_support_diagnostic_snapshots(
		self,
		claim_type: str = None,
		user_id: str = None,
		required_support_kinds: List[str] = None,
		snapshot_kind: str = None,
		keep_latest: int = 3,
	):
		"""Prune older persisted diagnostic snapshots while retaining the newest rows per scope."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.prune_claim_support_diagnostic_snapshots(
			user_id,
			claim_type=claim_type,
			required_support_kinds=required_support_kinds,
			snapshot_kind=snapshot_kind,
			keep_latest=keep_latest,
		)

	def get_claim_support_diagnostic_snapshots(
		self,
		claim_type: str = None,
		user_id: str = None,
		required_support_kinds: List[str] = None,
	):
		"""Return the latest persisted gap and contradiction diagnostics by claim."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.get_claim_support_diagnostic_snapshots(
			user_id,
			claim_type=claim_type,
			required_support_kinds=required_support_kinds,
		)

	def get_recent_claim_follow_up_execution(
		self,
		claim_type: str = None,
		user_id: str = None,
		claim_element_id: str = None,
		support_kind: str = None,
		limit: int = 10,
	):
		"""Return recent follow-up execution history grouped by claim for operator review."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.get_recent_follow_up_execution(
			user_id,
			claim_type=claim_type,
			claim_element_id=claim_element_id,
			support_kind=support_kind,
			limit=limit,
		)

	def resolve_claim_follow_up_manual_review(
		self,
		claim_type: str = None,
		user_id: str = None,
		claim_element_id: str = None,
		claim_element: str = None,
		resolution_status: str = 'resolved',
		resolution_notes: str = None,
		related_execution_id: int = None,
		metadata: Dict[str, Any] = None,
	):
		"""Record an operator resolution event for a manual-review follow-up item."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.resolve_follow_up_manual_review(
			user_id=user_id,
			claim_type=claim_type,
			claim_element_id=claim_element_id,
			claim_element_text=claim_element,
			resolution_status=resolution_status,
			resolution_notes=resolution_notes,
			related_execution_id=related_execution_id,
			metadata=metadata,
		)

	def build_claim_support_review_payload(
		self,
		claim_type: str = None,
		user_id: str = None,
		required_support_kinds: List[str] = None,
		follow_up_cooldown_seconds: int = 3600,
		include_support_summary: bool = True,
		include_overview: bool = True,
		include_follow_up_plan: bool = True,
		execute_follow_up: bool = False,
		follow_up_support_kind: str = None,
		follow_up_max_tasks_per_claim: int = 3,
	):
		return build_claim_support_review_payload(
			self,
			ClaimSupportReviewRequest(
				user_id=user_id,
				claim_type=claim_type,
				required_support_kinds=required_support_kinds or ['evidence', 'authority'],
				follow_up_cooldown_seconds=follow_up_cooldown_seconds,
				include_support_summary=include_support_summary,
				include_overview=include_overview,
				include_follow_up_plan=include_follow_up_plan,
				execute_follow_up=execute_follow_up,
				follow_up_support_kind=follow_up_support_kind,
				follow_up_max_tasks_per_claim=follow_up_max_tasks_per_claim,
			),
		)

	def build_claim_support_follow_up_execution_payload(
		self,
		claim_type: str = None,
		user_id: str = None,
		required_support_kinds: List[str] = None,
		follow_up_cooldown_seconds: int = 3600,
		follow_up_support_kind: str = None,
		follow_up_max_tasks_per_claim: int = 3,
		follow_up_force: bool = False,
		include_post_execution_review: bool = True,
		include_support_summary: bool = True,
		include_overview: bool = True,
		include_follow_up_plan: bool = True,
	):
		return build_claim_support_follow_up_execution_payload(
			self,
			ClaimSupportFollowUpExecuteRequest(
				user_id=user_id,
				claim_type=claim_type,
				required_support_kinds=required_support_kinds or ['evidence', 'authority'],
				follow_up_cooldown_seconds=follow_up_cooldown_seconds,
				follow_up_support_kind=follow_up_support_kind,
				follow_up_max_tasks_per_claim=follow_up_max_tasks_per_claim,
				follow_up_force=follow_up_force,
				include_post_execution_review=include_post_execution_review,
				include_support_summary=include_support_summary,
				include_overview=include_overview,
				include_follow_up_plan=include_follow_up_plan,
			),
		)

	def _extract_proof_gap_types(self, proof_gaps: List[Dict[str, Any]]) -> List[str]:
		gap_types: List[str] = []
		for gap in proof_gaps or []:
			if not isinstance(gap, dict):
				continue
			gap_type = str(gap.get('gap_type') or '').strip()
			if gap_type and gap_type not in gap_types:
				gap_types.append(gap_type)
		return gap_types

	def _normalize_rule_query_text(self, value: str) -> str:
		text = re.sub(r'\s+', ' ', str(value or '').strip())
		text = re.sub(r'["\']', '', text)
		text = re.sub(r'\s+[\.,;:]+', '', text)
		return text[:120].strip()

	def _extract_rule_candidate_context(self, element: Dict[str, Any]) -> Dict[str, Any]:
		summary = element.get('authority_rule_candidate_summary', {})
		if not isinstance(summary, dict):
			summary = {}
		gap_context = element.get('gap_context', {}) if isinstance(element.get('gap_context'), dict) else {}
		candidates: List[Dict[str, Any]] = []
		seen_candidates = set()
		for link in gap_context.get('links', []) or []:
			if not isinstance(link, dict) or link.get('support_kind') != 'authority':
				continue
			for candidate in link.get('rule_candidates', []) or []:
				if not isinstance(candidate, dict):
					continue
				rule_key = str(candidate.get('rule_id') or candidate.get('rule_text') or '').strip()
				if not rule_key or rule_key in seen_candidates:
					continue
				seen_candidates.add(rule_key)
				candidates.append(
					{
						'rule_id': candidate.get('rule_id'),
						'rule_text': candidate.get('rule_text'),
						'rule_type': candidate.get('rule_type'),
						'claim_element_id': candidate.get('claim_element_id'),
						'claim_element_text': candidate.get('claim_element_text'),
						'extraction_confidence': float(candidate.get('extraction_confidence', 0.0) or 0.0),
						'support_ref': link.get('support_ref'),
					}
				)
		candidates.sort(
			key=lambda candidate: (
				-float(candidate.get('extraction_confidence', 0.0) or 0.0),
				str(candidate.get('rule_type') or ''),
				str(candidate.get('rule_text') or ''),
			)
		)
		top_candidates = candidates[:3]
		by_type = summary.get('rule_type_counts', {}) if isinstance(summary.get('rule_type_counts'), dict) else {}
		top_rule_types: List[str] = []
		for candidate in top_candidates:
			rule_type = str(candidate.get('rule_type') or '').strip()
			if rule_type and rule_type not in top_rule_types:
				top_rule_types.append(rule_type)
		for rule_type in by_type.keys():
			normalized_type = str(rule_type or '').strip()
			if normalized_type and normalized_type not in top_rule_types:
				top_rule_types.append(normalized_type)
		return {
			'summary': summary,
			'rule_candidates': top_candidates,
			'top_rule_texts': [
				self._normalize_rule_query_text(candidate.get('rule_text'))
				for candidate in top_candidates
				if candidate.get('rule_text')
			],
			'top_rule_types': top_rule_types[:3],
			'has_exception_rules': int(by_type.get('exception', 0) or 0) > 0,
			'has_procedural_rules': int(by_type.get('procedural_prerequisite', 0) or 0) > 0,
		}

	def _manual_review_skip_reason(self, task: Dict[str, Any]) -> str:
		focus = str(task.get('follow_up_focus') or '')
		if focus == 'contradiction_resolution':
			return 'contradiction_requires_resolution'
		if focus == 'reasoning_gap_closure':
			return 'reasoning_gap_requires_operator_review'
		if focus == 'adverse_authority_review':
			return 'adverse_authority_requires_review'
		return 'manual_review_required'

	def _build_follow_up_queries(
		self,
		claim_type: str,
		element_text: str,
		missing_support_kinds: List[str],
		support_by_kind: Dict[str, Any] = None,
		recommended_action: str = '',
		validation_status: str = '',
		proof_gaps: List[Dict[str, Any]] = None,
		proof_decision_trace: Dict[str, Any] = None,
		authority_treatment_summary: Dict[str, Any] = None,
		rule_candidate_context: Dict[str, Any] = None,
	) -> Dict[str, List[str]]:
		queries: Dict[str, List[str]] = {}
		proof_gap_types = self._extract_proof_gap_types(proof_gaps or [])
		decision_trace = proof_decision_trace if isinstance(proof_decision_trace, dict) else {}
		support_kind_counts = support_by_kind if isinstance(support_by_kind, dict) else {}
		treatment_summary = authority_treatment_summary if isinstance(authority_treatment_summary, dict) else {}
		rule_context = rule_candidate_context if isinstance(rule_candidate_context, dict) else {}
		rule_texts = list(rule_context.get('top_rule_texts') or [])
		rule_types = [str(value).replace('_', ' ') for value in (rule_context.get('top_rule_types') or []) if value]
		primary_rule_text = rule_texts[0] if rule_texts else ''
		exception_rule_text = ''
		for candidate in rule_context.get('rule_candidates', []) or []:
			if not isinstance(candidate, dict):
				continue
			if str(candidate.get('rule_type') or '') == 'exception' and candidate.get('rule_text'):
				exception_rule_text = self._normalize_rule_query_text(candidate.get('rule_text'))
				break
		gap_focus = ' '.join(
			gap_type.replace('_', ' ')
			for gap_type in proof_gap_types
			if gap_type != 'contradiction_candidates'
		)[:80].strip()

		def _compose_query(*parts: str) -> str:
			return ' '.join(part for part in parts if part).strip()

		contradiction_targeted = validation_status == 'contradicted' and bool(missing_support_kinds)
		reasoning_targeted = self._is_reasoning_gap_follow_up(proof_gap_types, decision_trace)
		fact_gap_targeted = recommended_action == 'collect_fact_support'
		adverse_authority_targeted = recommended_action == 'review_adverse_authority'
		quality_targeted = recommended_action == 'improve_parse_quality' and not contradiction_targeted and not reasoning_targeted
		target_support_kinds = list(missing_support_kinds)
		if quality_targeted and not target_support_kinds:
			target_support_kinds = [
				kind for kind, count in support_kind_counts.items()
				if int(count or 0) > 0
			]
			if not target_support_kinds:
				target_support_kinds = ['evidence']
		if 'evidence' in target_support_kinds:
			if contradiction_targeted:
				queries['evidence'] = [
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'contradictory evidence rebuttal', gap_focus),
					_compose_query(f'"{element_text}"', 'corroborating records inconsistency', claim_type),
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'timeline witness statement conflict'),
				]
			elif adverse_authority_targeted:
				queries['evidence'] = [
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'facts distinguish adverse authority', exception_rule_text or primary_rule_text),
					_compose_query(f'"{element_text}"', 'rebuttal evidence questioned authority', claim_type, exception_rule_text),
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'record facts overcome adverse treatment', ' '.join(rule_types[:2])),
				]
			elif fact_gap_targeted:
				queries['evidence'] = [
					_compose_query(f'"{claim_type}"', f'"{element_text}"', f'"{primary_rule_text}"' if primary_rule_text else '', 'supporting facts evidence'),
					_compose_query(f'"{element_text}"', f'"{exception_rule_text}"' if exception_rule_text else '', 'fact pattern records witness timeline', claim_type),
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'documents showing predicate satisfaction', f'"{primary_rule_text}"' if primary_rule_text else ' '.join(rule_types[:2])),
				]
			elif reasoning_targeted:
				queries['evidence'] = [
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'supporting evidence formal proof', gap_focus),
					_compose_query(f'"{element_text}"', 'corroborating records legal elements', claim_type, gap_focus),
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'evidence burden of proof'),
				]
			elif quality_targeted:
				queries['evidence'] = [
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'clearer copy OCR readable evidence'),
					_compose_query(f'"{element_text}"', 'better scan legible document witness record', claim_type),
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'original PDF attachment readable'),
				]
			else:
				queries['evidence'] = [
					f'"{claim_type}" "{element_text}" evidence',
					f'"{element_text}" documentation {claim_type}',
					f'"{element_text}" facts witness records {claim_type}',
				]
		if 'authority' in target_support_kinds:
			if contradiction_targeted:
				queries['authority'] = [
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'contradiction case law', gap_focus),
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'conflicting evidence burden of proof'),
					_compose_query(f'"{element_text}"', 'inconsistent statements legal standard', claim_type),
				]
			elif adverse_authority_targeted:
				adverse_terms = ' '.join(
					str(name).replace('_', ' ')
					for name, count in (treatment_summary.get('treatment_type_counts') or {}).items()
					if int(count or 0) > 0
				)[:80].strip()
				queries['authority'] = [
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'distinguish questioned authority later treatment', adverse_terms),
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'adverse authority exception limitation', f'"{exception_rule_text}"' if exception_rule_text else ''),
					_compose_query(f'"{element_text}"', 'good law treatment distinguishing case', claim_type),
				]
			elif reasoning_targeted:
				queries['authority'] = [
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'formal proof case law', gap_focus),
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'legal standard burden of proof', gap_focus),
					_compose_query(f'"{element_text}"', 'formal elements precedent', claim_type),
				]
			elif quality_targeted:
				queries['authority'] = [
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'official statute opinion PDF text'),
					_compose_query(f'"{element_text}"', 'authoritative source readable full text', claim_type),
					_compose_query(f'"{claim_type}"', f'"{element_text}"', 'certified opinion clear scan'),
				]
			else:
				queries['authority'] = [
					f'"{claim_type}" "{element_text}" statute',
					f'"{claim_type}" "{element_text}" case law',
					f'"{element_text}" legal elements {claim_type}',
				]
		return queries

	def _is_reasoning_gap_follow_up(
		self,
		proof_gap_types: List[str],
		proof_decision_trace: Dict[str, Any] = None,
	) -> bool:
		decision_trace = proof_decision_trace if isinstance(proof_decision_trace, dict) else {}
		decision_source = str(decision_trace.get('decision_source') or '')
		ontology_validation_signal = str(decision_trace.get('ontology_validation_signal') or '')
		return (
			'logic_unprovable' in (proof_gap_types or [])
			or 'ontology_validation_failed' in (proof_gap_types or [])
			or decision_source in {'logic_unprovable', 'logic_proof_partial', 'ontology_validation_failed'}
			or ontology_validation_signal == 'invalid'
		)

	def _build_follow_up_record_metadata(self, task: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
		graph_summary = ((task.get('graph_support') or {}).get('summary', {})) if isinstance(task.get('graph_support'), dict) else {}
		graph_results = ((task.get('graph_support') or {}).get('results', [])) if isinstance(task.get('graph_support'), dict) else []
		adaptive_retry_state = task.get('adaptive_retry_state', {}) if isinstance(task.get('adaptive_retry_state'), dict) else {}
		rule_candidate_context = task.get('rule_candidate_context', {}) if isinstance(task.get('rule_candidate_context'), dict) else {}

		def _count_result_field(field_name: str) -> Dict[str, int]:
			counts: Dict[str, int] = {}
			for result in graph_results if isinstance(graph_results, list) else []:
				if not isinstance(result, dict):
					continue
				value = str(result.get(field_name) or '').strip()
				if not value:
					continue
				counts[value] = counts.get(value, 0) + 1
			return counts

		def _primary_count_key(counts: Dict[str, int]) -> str:
			if not counts:
				return ''
			return sorted(counts.items(), key=lambda item: (-int(item[1] or 0), str(item[0])))[0][0]

		source_family_counts = _count_result_field('source_family')
		record_scope_counts = _count_result_field('record_scope')
		artifact_family_counts = _count_result_field('artifact_family')
		corpus_family_counts = _count_result_field('corpus_family')
		content_origin_counts = _count_result_field('content_origin')
		metadata = {
			'execution_mode': task.get('execution_mode', 'retrieve_support'),
			'validation_status': task.get('validation_status', ''),
			'recommended_action': task.get('recommended_action', ''),
			'requires_manual_review': task.get('requires_manual_review', False),
			'reasoning_backed': task.get('reasoning_backed', False),
			'resolution_applied': task.get('resolution_applied', ''),
			'proof_decision_source': task.get('proof_decision_source', ''),
			'logic_provable_count': int(task.get('logic_provable_count', 0) or 0),
			'logic_unprovable_count': int(task.get('logic_unprovable_count', 0) or 0),
			'ontology_validation_signal': task.get('ontology_validation_signal', ''),
			'proof_gap_count': int(task.get('proof_gap_count', 0) or 0),
			'proof_gap_types': list(task.get('proof_gap_types') or []),
			'missing_support_kinds': list(task.get('missing_support_kinds') or []),
			'follow_up_focus': task.get('follow_up_focus', ''),
			'query_strategy': task.get('query_strategy', ''),
			'adaptive_retry_applied': bool(adaptive_retry_state.get('applied', False)),
			'adaptive_retry_reason': adaptive_retry_state.get('reason', ''),
			'adaptive_query_strategy': adaptive_retry_state.get('adaptive_query_strategy', ''),
			'adaptive_priority_penalty': int(adaptive_retry_state.get('priority_penalty', 0) or 0),
			'adaptive_zero_result_attempt_count': int(adaptive_retry_state.get('zero_result_attempt_count', 0) or 0),
			'adaptive_successful_result_attempt_count': int(adaptive_retry_state.get('successful_result_attempt_count', 0) or 0),
			'graph_support_strength': task.get('graph_support_strength', ''),
			'graph_support_summary': {
				'total_fact_count': int(graph_summary.get('total_fact_count', 0) or 0),
				'unique_fact_count': int(graph_summary.get('unique_fact_count', 0) or 0),
				'duplicate_fact_count': int(graph_summary.get('duplicate_fact_count', 0) or 0),
				'semantic_cluster_count': int(graph_summary.get('semantic_cluster_count', 0) or 0),
				'semantic_duplicate_count': int(graph_summary.get('semantic_duplicate_count', 0) or 0),
				'support_by_kind': dict(graph_summary.get('support_by_kind') or {}),
				'support_by_source': dict(graph_summary.get('support_by_source') or {}),
				'source_family_counts': source_family_counts,
				'record_scope_counts': record_scope_counts,
				'artifact_family_counts': artifact_family_counts,
				'corpus_family_counts': corpus_family_counts,
				'content_origin_counts': content_origin_counts,
			},
			'source_family': _primary_count_key(source_family_counts),
			'record_scope': _primary_count_key(record_scope_counts),
			'artifact_family': _primary_count_key(artifact_family_counts),
			'corpus_family': _primary_count_key(corpus_family_counts),
			'content_origin': _primary_count_key(content_origin_counts),
			'authority_treatment_summary': task.get('authority_treatment_summary', {}),
			'authority_rule_candidate_summary': task.get('authority_rule_candidate_summary', {}),
			'rule_candidate_focus': {
				'candidate_count': len(rule_candidate_context.get('rule_candidates', []) or []),
				'top_rule_types': list(rule_candidate_context.get('top_rule_types', []) or []),
				'top_rule_texts': list(rule_candidate_context.get('top_rule_texts', []) or []),
			},
		}
		for key, value in extra.items():
			if value is not None:
				metadata[key] = value
		return metadata

	def _build_manual_review_audit_query(self, claim_type: str, task: Dict[str, Any]) -> str:
		element_ref = task.get('claim_element_id') or task.get('claim_element') or 'unknown_element'
		action = task.get('recommended_action') or 'manual_review'
		return f'manual_review::{claim_type}::{element_ref}::{action}'

	def _select_primary_authority_search_program(self, task: Dict[str, Any]) -> Dict[str, Any]:
		for program in (task.get('authority_search_programs') or []):
			if isinstance(program, dict):
				return program
		return {}

	def _normalize_follow_up_history_key(self, value: str) -> str:
		return str(value or '').strip().lower()

	def _resolved_manual_review_gap_types(self, task: Dict[str, Any]) -> set:
		follow_up_focus = str(task.get('follow_up_focus') or '')
		if follow_up_focus == 'contradiction_resolution':
			return {'contradiction_candidates'}
		if follow_up_focus == 'reasoning_gap_closure':
			return {'logic_unprovable', 'ontology_validation_failed'}
		return set()

	def _normalized_support_gap_decision_source(self, task: Dict[str, Any]) -> str:
		if list(task.get('missing_support_kinds') or []):
			return 'missing_support' if str(task.get('status') or '') == 'missing' else 'partial_support'
		return ''

	def _build_manual_review_state_map(self, history_entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
		state_map: Dict[str, Dict[str, Any]] = {}
		for entry in history_entries or []:
			if not isinstance(entry, dict):
				continue
			if str(entry.get('support_kind') or '') != 'manual_review':
				continue
			claim_element_id = str(entry.get('claim_element_id') or '').strip()
			claim_element_text = self._normalize_follow_up_history_key(entry.get('claim_element_text') or '')
			for key in [
				f'id:{claim_element_id}' if claim_element_id else '',
				f'text:{claim_element_text}' if claim_element_text else '',
			]:
				if key and key not in state_map:
					state_map[key] = entry
		return state_map

	def _build_retrieval_feedback_state_map(self, history_entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
		state_map: Dict[str, Dict[str, Any]] = {}
		for entry in history_entries or []:
			if not isinstance(entry, dict):
				continue
			if str(entry.get('support_kind') or '') == 'manual_review':
				continue
			if str(entry.get('status') or '') != 'executed':
				continue
			metadata = entry.get('metadata', {}) if isinstance(entry.get('metadata'), dict) else {}
			follow_up_focus = str(entry.get('follow_up_focus') or metadata.get('follow_up_focus') or '')
			if follow_up_focus != 'reasoning_gap_closure':
				continue
			try:
				result_count = int(metadata.get('result_count', 0) or 0)
			except (TypeError, ValueError):
				result_count = 0
			zero_result = bool(metadata.get('zero_result')) or result_count <= 0
			claim_element_id = str(entry.get('claim_element_id') or '').strip()
			claim_element_text = self._normalize_follow_up_history_key(entry.get('claim_element_text') or '')
			lookup_keys = [
				f'id:{claim_element_id}' if claim_element_id else '',
				f'text:{claim_element_text}' if claim_element_text else '',
			]
			state: Optional[Dict[str, Any]] = None
			for key in lookup_keys:
				if key and key in state_map:
					state = state_map[key]
					break
			if state is None:
				state = {
					'executed_attempt_count': 0,
					'zero_result_attempt_count': 0,
					'successful_result_attempt_count': 0,
					'support_kind_counts': {},
					'latest_attempted_at': entry.get('timestamp'),
					'latest_zero_result_at': None,
				}
			state['executed_attempt_count'] += 1
			support_kind = str(entry.get('support_kind') or 'unknown')
			state['support_kind_counts'][support_kind] = state['support_kind_counts'].get(support_kind, 0) + 1
			if zero_result:
				state['zero_result_attempt_count'] += 1
				if not state.get('latest_zero_result_at'):
					state['latest_zero_result_at'] = entry.get('timestamp')
			else:
				state['successful_result_attempt_count'] += 1
			for key in lookup_keys:
				if key:
					state_map[key] = state
		return state_map

	def _apply_reasoning_gap_execution_feedback(
		self,
		claim_type: str,
		task: Dict[str, Any],
		retrieval_feedback_state_map: Dict[str, Dict[str, Any]],
	) -> Dict[str, Any]:
		if task.get('follow_up_focus') != 'reasoning_gap_closure':
			return task
		if task.get('execution_mode') == 'manual_review':
			return task

		lookup_keys = [
			f'id:{str(task.get("claim_element_id") or "").strip()}' if task.get('claim_element_id') else '',
			f'text:{self._normalize_follow_up_history_key(task.get("claim_element") or "")}' if task.get('claim_element') else '',
		]
		retrieval_state: Optional[Dict[str, Any]] = None
		for key in lookup_keys:
			if key and key in retrieval_feedback_state_map:
				retrieval_state = retrieval_feedback_state_map[key]
				break
		if not retrieval_state:
			return task

		adaptive_retry_state = {
			'executed_attempt_count': int(retrieval_state.get('executed_attempt_count', 0) or 0),
			'zero_result_attempt_count': int(retrieval_state.get('zero_result_attempt_count', 0) or 0),
			'successful_result_attempt_count': int(retrieval_state.get('successful_result_attempt_count', 0) or 0),
			'support_kind_counts': dict(retrieval_state.get('support_kind_counts') or {}),
			'latest_attempted_at': retrieval_state.get('latest_attempted_at'),
			'latest_zero_result_at': retrieval_state.get('latest_zero_result_at'),
			'applied': False,
			'priority_penalty': 0,
			'adaptive_query_strategy': '',
			'reason': '',
		}
		if (
			adaptive_retry_state['zero_result_attempt_count'] >= 2
			and adaptive_retry_state['successful_result_attempt_count'] == 0
		):
			adaptive_retry_state['applied'] = True
			adaptive_retry_state['priority_penalty'] = 1
			adaptive_retry_state['reason'] = 'repeated_zero_result_reasoning_gap'
			if list(task.get('missing_support_kinds') or []):
				adaptive_retry_state['adaptive_query_strategy'] = 'standard_gap_targeted'
				task['query_strategy'] = 'standard_gap_targeted'
				task['queries'] = self._build_follow_up_queries(
					claim_type,
					task.get('claim_element', ''),
					list(task.get('missing_support_kinds') or []),
					validation_status='',
					proof_gaps=[],
					proof_decision_trace={},
				)
		task['adaptive_retry_state'] = adaptive_retry_state
		return task

	def _count_evidence_follow_up_results(self, discovery_result: Dict[str, Any]) -> int:
		if not isinstance(discovery_result, dict):
			return 0
		for key in ['discovered', 'stored', 'total_records']:
			try:
				return int(discovery_result.get(key, 0) or 0)
			except (TypeError, ValueError):
				continue
		return 0

	def _count_authority_follow_up_results(self, search_results: Dict[str, Any]) -> int:
		if not isinstance(search_results, dict):
			return 0
		result_count = 0
		for value in search_results.values():
			if isinstance(value, list):
				result_count += len(value)
		return result_count

	def _apply_manual_review_resolution_state(
		self,
		claim_type: str,
		task: Dict[str, Any],
		manual_review_state_map: Dict[str, Dict[str, Any]],
	) -> Optional[Dict[str, Any]]:
		lookup_keys = [
			f'id:{str(task.get("claim_element_id") or "").strip()}' if task.get('claim_element_id') else '',
			f'text:{self._normalize_follow_up_history_key(task.get("claim_element") or "")}' if task.get('claim_element') else '',
		]
		manual_review_state: Optional[Dict[str, Any]] = None
		for key in lookup_keys:
			if key and key in manual_review_state_map:
				manual_review_state = manual_review_state_map[key]
				break
		if not manual_review_state:
			return task

		resolved_status = str(manual_review_state.get('status') or '')
		resolution_status = str(manual_review_state.get('resolution_status') or '')
		is_resolved = resolved_status == 'resolved_manual_review' or bool(resolution_status)
		task['manual_review_history_state'] = {
			'execution_id': manual_review_state.get('execution_id'),
			'status': resolved_status,
			'resolution_status': resolution_status,
			'timestamp': manual_review_state.get('timestamp'),
		}
		task['manual_review_resolved'] = is_resolved
		if not is_resolved:
			return task

		if task.get('execution_mode') == 'manual_review':
			return None

		if task.get('execution_mode') == 'review_and_retrieve':
			resolved_gap_types = self._resolved_manual_review_gap_types(task)
			filtered_proof_gaps = [
				gap
				for gap in (task.get('proof_gaps') or [])
				if isinstance(gap, dict) and str(gap.get('gap_type') or '') not in resolved_gap_types
			]
			task['execution_mode'] = 'retrieve_support'
			task['requires_manual_review'] = False
			task['follow_up_focus'] = 'support_gap_closure'
			task['query_strategy'] = 'standard_gap_targeted'
			task['proof_gaps'] = filtered_proof_gaps
			task['proof_gap_types'] = self._extract_proof_gap_types(filtered_proof_gaps)
			task['proof_gap_count'] = len(filtered_proof_gaps)
			task['proof_decision_source'] = self._normalized_support_gap_decision_source(task)
			task['logic_provable_count'] = 0
			task['logic_unprovable_count'] = 0
			task['ontology_validation_signal'] = ''
			task['queries'] = self._build_follow_up_queries(
				claim_type,
				task.get('claim_element', ''),
				list(task.get('missing_support_kinds') or []),
				validation_status='',
				proof_gaps=filtered_proof_gaps,
				proof_decision_trace={
					'decision_source': task.get('proof_decision_source', ''),
					'ontology_validation_signal': task.get('ontology_validation_signal', ''),
				},
			)
			task['resolution_applied'] = 'manual_review_resolved'
		return task

	def _build_follow_up_task(self, claim_type: str, element: Dict[str, Any], status: str,
			required_support_kinds: List[str]) -> Dict[str, Any]:
		element_text = element.get('element_text') or element.get('claim_element') or 'Unknown element'
		support_by_kind = element.get('support_by_kind', {})
		recommended_action = str(element.get('recommended_action') or '')
		authority_treatment_summary = element.get('authority_treatment_summary', {}) if isinstance(element.get('authority_treatment_summary'), dict) else {}
		authority_rule_candidate_summary = element.get('authority_rule_candidate_summary', {}) if isinstance(element.get('authority_rule_candidate_summary'), dict) else {}
		rule_candidate_context = self._extract_rule_candidate_context(element)
		missing_support_kinds = [
			kind for kind in required_support_kinds
			if support_by_kind.get(kind, 0) == 0
		]
		priority = 'high' if status == 'missing' else 'medium'
		validation_status = element.get('validation_status', '')
		proof_gaps = element.get('proof_gaps', []) if isinstance(element.get('proof_gaps'), list) else []
		proof_gap_types = self._extract_proof_gap_types(proof_gaps)
		proof_decision_trace = element.get('proof_decision_trace', {}) if isinstance(element.get('proof_decision_trace'), dict) else {}
		reasoning_gap_targeted = self._is_reasoning_gap_follow_up(proof_gap_types, proof_decision_trace)
		queries = self._build_follow_up_queries(
			claim_type,
			element_text,
			missing_support_kinds,
			support_by_kind=support_by_kind,
			recommended_action=recommended_action,
			validation_status=validation_status,
			proof_gaps=proof_gaps,
			proof_decision_trace=proof_decision_trace,
			authority_treatment_summary=authority_treatment_summary,
			rule_candidate_context=rule_candidate_context,
		)
		if validation_status == 'contradicted':
			priority = 'high'
		elif recommended_action == 'review_adverse_authority':
			priority = 'high'
		elif reasoning_gap_targeted:
			priority = 'high'
		elif recommended_action == 'improve_parse_quality':
			priority = 'high'
		execution_mode = 'retrieve_support'
		if validation_status == 'contradicted' and missing_support_kinds:
			execution_mode = 'review_and_retrieve'
		elif validation_status == 'contradicted':
			execution_mode = 'manual_review'
		elif recommended_action == 'review_adverse_authority' and missing_support_kinds:
			execution_mode = 'review_and_retrieve'
		elif recommended_action == 'review_adverse_authority':
			execution_mode = 'manual_review'
		elif reasoning_gap_targeted and missing_support_kinds:
			execution_mode = 'review_and_retrieve'
		elif reasoning_gap_targeted:
			execution_mode = 'manual_review'
		follow_up_focus = 'support_gap_closure'
		if validation_status == 'contradicted':
			follow_up_focus = 'contradiction_resolution'
		elif recommended_action == 'review_adverse_authority':
			follow_up_focus = 'adverse_authority_review'
		elif recommended_action == 'collect_fact_support':
			follow_up_focus = 'fact_gap_closure'
		elif reasoning_gap_targeted:
			follow_up_focus = 'reasoning_gap_closure'
		elif recommended_action == 'improve_parse_quality':
			follow_up_focus = 'parse_quality_improvement'
		query_strategy = 'standard_gap_targeted'
		if follow_up_focus == 'contradiction_resolution' and execution_mode == 'review_and_retrieve':
			query_strategy = 'contradiction_targeted'
		elif follow_up_focus == 'adverse_authority_review':
			query_strategy = 'adverse_authority_targeted'
		elif follow_up_focus == 'fact_gap_closure':
			query_strategy = 'rule_fact_targeted'
		elif follow_up_focus == 'reasoning_gap_closure':
			query_strategy = 'reasoning_gap_targeted'
		elif follow_up_focus == 'parse_quality_improvement':
			query_strategy = 'quality_gap_targeted'
		preferred_support_kind = str(
			element.get('preferred_support_kind')
			or self._default_preferred_support_kind(missing_support_kinds)
		).strip().lower()
		return {
			'claim_type': claim_type,
			'claim_element_id': element.get('element_id'),
			'claim_element': element_text,
			'status': status,
			'validation_status': validation_status,
			'proof_decision_source': str(proof_decision_trace.get('decision_source') or ''),
			'logic_provable_count': int(proof_decision_trace.get('logic_provable_count', 0) or 0),
			'logic_unprovable_count': int(proof_decision_trace.get('logic_unprovable_count', 0) or 0),
			'ontology_validation_signal': str(proof_decision_trace.get('ontology_validation_signal') or ''),
			'proof_gap_count': int(element.get('proof_gap_count', 0) or 0),
			'proof_gaps': proof_gaps,
			'proof_gap_types': proof_gap_types,
			'validation_recommended_action': recommended_action,
			'authority_treatment_summary': authority_treatment_summary,
			'authority_rule_candidate_summary': authority_rule_candidate_summary,
			'rule_candidate_context': rule_candidate_context,
			'execution_mode': execution_mode,
			'requires_manual_review': execution_mode in {'manual_review', 'review_and_retrieve'},
			'reasoning_backed': bool(((element.get('reasoning_diagnostics') or {}).get('backend_available_count', 0) or 0) > 0),
			'follow_up_focus': follow_up_focus,
			'query_strategy': query_strategy,
			'priority': priority,
			'priority_score': 3 if priority == 'high' else 2,
			'recommended_action': recommended_action,
			'missing_support_kinds': missing_support_kinds,
			'preferred_support_kind': preferred_support_kind,
			'preferred_evidence_classes': list(element.get('preferred_evidence_classes', []) or []),
			'fallback_support_kinds': list(element.get('fallback_support_kinds', []) or []),
			'missing_fact_bundle': list(element.get('missing_fact_bundle', []) or []),
			'satisfied_fact_bundle': list(element.get('satisfied_fact_bundle', []) or []),
			'intake_origin_refs': list(element.get('intake_origin_refs', []) or []),
			'success_criteria': list(element.get('success_criteria', []) or []),
			'recommended_queries': list(element.get('recommended_queries', []) or []),
			'queries': queries,
		}

	def _build_authority_search_programs_for_task(
		self,
		claim_type: str,
		task: Dict[str, Any],
	) -> List[Dict[str, Any]]:
		authority_queries = task.get('queries', {}).get('authority', []) if isinstance(task.get('queries'), dict) else []
		if not authority_queries:
			return []
		legal_authority_search = getattr(self, 'legal_authority_search', None)
		if legal_authority_search is None or not hasattr(legal_authority_search, 'build_search_programs'):
			return []
		primary_query = str(authority_queries[0] or '').strip()
		if not primary_query:
			return []
		claim_element_id = str(task.get('claim_element_id') or '').strip()
		claim_element_text = str(task.get('claim_element') or '').strip()
		try:
			programs = legal_authority_search.build_search_programs(
				query=primary_query,
				claim_type=claim_type,
				claim_elements=[
					{
						'claim_element_id': claim_element_id,
						'claim_element_text': claim_element_text,
					}
				],
			)
		except Exception as exc:
			self.log(
				'follow_up_authority_search_program_error',
				claim_type=claim_type,
				claim_element_id=claim_element_id,
				error=str(exc),
			)
			return []
		if not isinstance(programs, list):
			return []

		focus = str(task.get('follow_up_focus') or '')
		priority_by_type: Dict[str, int] = {
			'element_definition_search': 2,
			'fact_pattern_search': 1,
			'procedural_search': 4,
			'adverse_authority_search': 3,
			'treatment_check_search': 5,
		}
		if focus == 'contradiction_resolution':
			priority_by_type.update({
				'adverse_authority_search': 1,
				'treatment_check_search': 2,
				'fact_pattern_search': 3,
			})
		elif focus == 'adverse_authority_review':
			priority_by_type.update({
				'adverse_authority_search': 1,
				'treatment_check_search': 2,
				'fact_pattern_search': 3,
			})
		elif focus == 'fact_gap_closure':
			priority_by_type.update({
				'fact_pattern_search': 1,
				'procedural_search': 2,
				'element_definition_search': 3,
			})
		elif focus == 'reasoning_gap_closure':
			priority_by_type.update({
				'fact_pattern_search': 1,
				'element_definition_search': 2,
				'treatment_check_search': 3,
			})
		elif focus == 'parse_quality_improvement':
			priority_by_type.update({
				'element_definition_search': 1,
				'fact_pattern_search': 2,
				'treatment_check_search': 3,
			})

		rule_candidate_context = task.get('rule_candidate_context', {}) if isinstance(task.get('rule_candidate_context'), dict) else {}
		top_rule_types = [
			str(rule_type or '').strip()
			for rule_type in (rule_candidate_context.get('top_rule_types') or [])
			if str(rule_type or '').strip()
		]
		has_exception_rules = bool(rule_candidate_context.get('has_exception_rules'))
		has_procedural_rules = bool(rule_candidate_context.get('has_procedural_rules'))
		has_element_rules = any(rule_type in {'element', 'definition'} for rule_type in top_rule_types)
		rule_signal_bias = ''
		if has_exception_rules:
			priority_by_type.update({
				'adverse_authority_search': 1,
				'treatment_check_search': 2,
				'fact_pattern_search': 3,
				'element_definition_search': 4,
				'procedural_search': 5,
			})
			rule_signal_bias = 'exception'
		elif has_procedural_rules:
			priority_by_type.update({
				'procedural_search': 1,
				'element_definition_search': 2,
				'fact_pattern_search': 3,
				'treatment_check_search': 4,
				'adverse_authority_search': 5,
			})
			rule_signal_bias = 'procedural_prerequisite'
		elif has_element_rules and focus in {'fact_gap_closure', 'reasoning_gap_closure'}:
			priority_by_type.update({
				'element_definition_search': 1,
				'fact_pattern_search': 2,
				'procedural_search': 3,
				'adverse_authority_search': 4,
				'treatment_check_search': 5,
			})
			rule_signal_bias = 'element'

		treatment_summary = task.get('authority_treatment_summary', {}) if isinstance(task.get('authority_treatment_summary'), dict) else {}
		treatment_type_counts = treatment_summary.get('treatment_type_counts', {}) if isinstance(treatment_summary.get('treatment_type_counts'), dict) else {}
		adverse_authority_count = int(treatment_summary.get('adverse_authority_link_count', 0) or 0)
		uncertain_authority_count = int(treatment_summary.get('uncertain_authority_link_count', 0) or 0)
		concerning_treatment_count = sum(
			int(count or 0)
			for name, count in treatment_type_counts.items()
			if str(name or '') in {'questioned', 'limits', 'superseded', 'good_law_unconfirmed'}
		)
		authority_signal_bias = ''
		if adverse_authority_count > 0:
			priority_by_type.update({
				'adverse_authority_search': 1,
				'treatment_check_search': 2,
				'fact_pattern_search': 3,
				'element_definition_search': 4,
				'procedural_search': 5,
			})
			authority_signal_bias = 'adverse'
		elif uncertain_authority_count > 0 or concerning_treatment_count > 0:
			priority_by_type.update({
				'treatment_check_search': 1,
				'adverse_authority_search': 2,
				'fact_pattern_search': 3,
				'element_definition_search': 4,
				'procedural_search': 5,
			})
			authority_signal_bias = 'uncertain'

		normalized_programs: List[Dict[str, Any]] = []
		for program in programs:
			if not isinstance(program, dict):
				continue
			program_type = str(program.get('program_type') or '')
			metadata = dict(program.get('metadata') or {}) if isinstance(program.get('metadata'), dict) else {}
			existing_authority_signal_bias = str(metadata.get('authority_signal_bias') or '')
			existing_rule_signal_bias = str(metadata.get('rule_signal_bias') or '')
			metadata.update({
				'follow_up_focus': focus,
				'query_strategy': str(task.get('query_strategy') or ''),
				'recommended_action': str(task.get('recommended_action') or ''),
				'validation_status': str(task.get('validation_status') or ''),
				'primary_authority_query': primary_query,
				'query_variants': list(authority_queries),
				'rule_signal_bias': rule_signal_bias or existing_rule_signal_bias,
				'rule_candidate_focus_types': list(top_rule_types[:3]),
				'rule_candidate_focus_texts': list((rule_candidate_context.get('top_rule_texts') or [])[:2]),
				'priority_rank': priority_by_type.get(program_type, 99),
				'authority_signal_bias': authority_signal_bias or existing_authority_signal_bias,
			})
			normalized_programs.append({
				**program,
				'claim_type': str(program.get('claim_type') or claim_type),
				'claim_element_id': str(program.get('claim_element_id') or claim_element_id),
				'claim_element_text': str(program.get('claim_element_text') or claim_element_text),
				'metadata': metadata,
			})

		normalized_programs.sort(
			key=lambda program: (
				int(((program.get('metadata') or {}).get('priority_rank', 99)) or 99),
				str(program.get('program_type') or ''),
				str(program.get('program_id') or ''),
			)
		)
		return normalized_programs

	def _summarize_authority_search_programs(self, programs: List[Dict[str, Any]]) -> Dict[str, Any]:
		program_type_counts: Dict[str, int] = {}
		authority_intent_counts: Dict[str, int] = {}
		for program in programs:
			if not isinstance(program, dict):
				continue
			program_type = str(program.get('program_type') or 'unknown')
			program_type_counts[program_type] = program_type_counts.get(program_type, 0) + 1
			authority_intent = str(program.get('authority_intent') or 'unknown')
			authority_intent_counts[authority_intent] = authority_intent_counts.get(authority_intent, 0) + 1
		primary_program = programs[0] if programs else {}
		primary_metadata = primary_program.get('metadata') or {}
		primary_program_bias = ''
		primary_program_rule_bias = ''
		if isinstance(primary_metadata, dict):
			primary_program_bias = str(primary_metadata.get('authority_signal_bias') or '')
			primary_program_rule_bias = str(primary_metadata.get('rule_signal_bias') or '')
		return {
			'program_count': len(programs),
			'program_type_counts': program_type_counts,
			'authority_intent_counts': authority_intent_counts,
			'primary_program_id': str(primary_program.get('program_id') or ''),
			'primary_program_type': str(primary_program.get('program_type') or ''),
			'primary_program_bias': primary_program_bias,
			'primary_program_rule_bias': primary_program_rule_bias,
		}

	def _classify_graph_support(self, graph_support: Dict[str, Any]) -> Dict[str, Any]:
		summary = graph_support.get('summary', {}) if isinstance(graph_support, dict) else {}
		max_score = float(summary.get('max_score', 0.0) or 0.0)
		semantic_cluster_count = int(
			summary.get('semantic_cluster_count', summary.get('unique_fact_count', summary.get('total_fact_count', 0))) or 0
		)
		if max_score >= 2.0 or semantic_cluster_count >= 3:
			return {
				'strength': 'strong',
				'priority_adjustment': -1,
				'recommended_action': 'review_existing_support',
			}
		if max_score >= 1.0 or semantic_cluster_count >= 1:
			return {
				'strength': 'moderate',
				'priority_adjustment': 0,
				'recommended_action': 'target_missing_support_kind',
			}
		return {
			'strength': 'none',
			'priority_adjustment': 1,
			'recommended_action': 'retrieve_more_support',
		}

	def _priority_from_score(self, score: int) -> str:
		if score >= 3:
			return 'high'
		if score == 2:
			return 'medium'
		return 'low'

	def _should_suppress_follow_up_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
		if task.get('validation_status') == 'contradicted' and not task.get('manual_review_resolved'):
			return {
				'suppress': False,
				'reason': '',
			}
		if task.get('follow_up_focus') in {'reasoning_gap_closure', 'parse_quality_improvement'}:
			return {
				'suppress': False,
				'reason': '',
			}
		if task.get('follow_up_focus') == 'adverse_authority_review':
			return {
				'suppress': False,
				'reason': '',
			}
		graph_summary = (task.get('graph_support') or {}).get('summary', {})
		semantic_cluster_count = int(
			graph_summary.get('semantic_cluster_count', graph_summary.get('unique_fact_count', graph_summary.get('total_fact_count', 0))) or 0
		)
		semantic_duplicate_count = int(graph_summary.get('semantic_duplicate_count', graph_summary.get('duplicate_fact_count', 0)) or 0)
		strength = task.get('graph_support_strength', 'none')
		if strength == 'strong' and semantic_cluster_count > 0 and semantic_duplicate_count >= semantic_cluster_count:
			return {
				'suppress': True,
				'reason': 'existing_support_high_duplication',
			}
		return {
			'suppress': False,
			'reason': '',
		}

	def get_claim_follow_up_plan(
		self,
		claim_type: str = None,
		user_id: str = None,
		required_support_kinds: List[str] = None,
		cooldown_seconds: int = 3600,
	):
		"""Generate targeted follow-up retrieval tasks from claim overview gaps."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		validation = self.get_claim_support_validation(
			claim_type=claim_type,
			user_id=user_id,
			required_support_kinds=required_support_kinds,
		)
		plan = {
			'required_support_kinds': required_support_kinds or ['evidence', 'authority'],
			'claims': {},
		}
		alignment_lookup = self._build_alignment_task_lookup()
		for current_claim, claim_data in validation.get('claims', {}).items():
			manual_review_history = self.claim_support.get_recent_follow_up_execution(
				user_id,
				claim_type=current_claim,
				support_kind='manual_review',
				limit=100,
			)
			manual_review_state_map = self._build_manual_review_state_map(
				(manual_review_history.get('claims', {}) or {}).get(current_claim, [])
				if isinstance(manual_review_history, dict)
				else []
			)
			retrieval_history = self.claim_support.get_recent_follow_up_execution(
				user_id,
				claim_type=current_claim,
				limit=200,
			)
			retrieval_feedback_state_map = self._build_retrieval_feedback_state_map(
				(retrieval_history.get('claims', {}) or {}).get(current_claim, [])
				if isinstance(retrieval_history, dict)
				else []
			)
			tasks = []
			for element in claim_data.get('elements', []):
				if not isinstance(element, dict) or element.get('validation_status') == 'supported':
					continue
				task = self._build_follow_up_task(
					current_claim,
					element,
					element.get('coverage_status', element.get('status', 'missing')),
					claim_data.get('required_support_kinds', plan['required_support_kinds']),
				)
				task = self._apply_manual_review_resolution_state(
					current_claim,
					task,
					manual_review_state_map,
				)
				if task is None:
					continue
				task = self._apply_reasoning_gap_execution_feedback(
					current_claim,
					task,
					retrieval_feedback_state_map,
				)
				task = self._merge_alignment_task_preferences_into_follow_up_task(task, alignment_lookup)
				tasks.append(task)
			for task in tasks:
				execution_status: Dict[str, Any] = {}
				graph_support = self.query_claim_graph_support(
					claim_type=current_claim,
					claim_element_id=task.get('claim_element_id'),
					claim_element=task.get('claim_element'),
					user_id=user_id,
				)
				for kind, queries in task.get('queries', {}).items():
					query_text = queries[0] if queries else ''
					execution_status[kind] = self.claim_support.get_follow_up_execution_status(
						user_id,
						current_claim,
						kind,
						query_text,
						cooldown_seconds=cooldown_seconds,
					)
				graph_support_assessment = self._classify_graph_support(graph_support)
				adjusted_priority_score = max(
					1,
					min(3, int(task.get('priority_score', 2)) + int(graph_support_assessment.get('priority_adjustment', 0))),
				)
				if task.get('validation_status') == 'contradicted' and not task.get('manual_review_resolved'):
					adjusted_priority_score = 3
				if task.get('follow_up_focus') == 'reasoning_gap_closure':
					adjusted_priority_score = max(
						adjusted_priority_score,
						3 if task.get('execution_mode') == 'manual_review' else 2,
					)
				if task.get('follow_up_focus') == 'adverse_authority_review':
					adjusted_priority_score = max(
						adjusted_priority_score,
						3 if task.get('execution_mode') == 'manual_review' else 2,
					)
				if task.get('follow_up_focus') == 'parse_quality_improvement':
					adjusted_priority_score = max(adjusted_priority_score, 3)
				adaptive_retry_state = task.get('adaptive_retry_state', {}) if isinstance(task.get('adaptive_retry_state'), dict) else {}
				adaptive_priority_penalty = int(adaptive_retry_state.get('priority_penalty', 0) or 0)
				if adaptive_priority_penalty:
					minimum_priority = 2 if task.get('follow_up_focus') in {'reasoning_gap_closure', 'parse_quality_improvement'} else 1
					adjusted_priority_score = max(minimum_priority, adjusted_priority_score - adaptive_priority_penalty)
				task['graph_support'] = graph_support
				task['has_graph_support'] = bool(graph_support.get('results'))
				task['graph_support_strength'] = graph_support_assessment['strength']
				if task.get('follow_up_focus') == 'parse_quality_improvement':
					task['recommended_action'] = 'improve_parse_quality'
				elif str(task.get('validation_recommended_action') or '') in {'collect_fact_support', 'review_adverse_authority'}:
					task['recommended_action'] = str(task.get('validation_recommended_action') or '')
				else:
					task['recommended_action'] = graph_support_assessment['recommended_action']
				if task.get('validation_status') == 'contradicted' and not task.get('manual_review_resolved'):
					task['recommended_action'] = 'resolve_contradiction'
				if task.get('execution_mode') == 'manual_review' and not task.get('manual_review_resolved'):
					task['recommended_action'] = (
						'resolve_contradiction'
						if task.get('validation_status') == 'contradicted'
						else (
							'review_adverse_authority'
							if task.get('follow_up_focus') == 'adverse_authority_review'
							else 'review_existing_support'
						)
					)
				authority_search_programs = self._build_authority_search_programs_for_task(
					current_claim,
					task,
				)
				task['authority_search_programs'] = authority_search_programs
				task['authority_search_program_summary'] = self._summarize_authority_search_programs(
					authority_search_programs
				)
				task['priority_score'] = adjusted_priority_score
				task['priority'] = self._priority_from_score(adjusted_priority_score)
				suppression = self._should_suppress_follow_up_task(task)
				task['should_suppress_retrieval'] = suppression['suppress']
				task['suppression_reason'] = suppression['reason']
				task['execution_status'] = execution_status
				task['blocked_by_cooldown'] = any(
					status.get('in_cooldown', False)
					for status in execution_status.values()
				)
			tasks.sort(
				key=lambda item: (
					item.get('blocked_by_cooldown', False),
					-item.get('priority_score', 0),
					item.get('claim_element', ''),
				)
			)

			plan['claims'][current_claim] = {
				'task_count': len(tasks),
				'blocked_task_count': len([task for task in tasks if task.get('blocked_by_cooldown')]),
				'tasks': tasks,
			}
		return plan

	def _keywords_from_follow_up_query(self, query: str, claim_type: str, claim_element: str) -> List[str]:
		parts = re.findall(r'"([^"]+)"|(\S+)', query)
		keywords: List[str] = []
		for quoted, bare in parts:
			value = quoted or bare
			if value and value not in keywords:
				keywords.append(value)
		if not keywords:
			keywords = [claim_type, claim_element]
		return keywords[:5]

	def execute_claim_follow_up_plan(
		self,
		claim_type: str = None,
		user_id: str = None,
		support_kind: str = None,
		max_tasks_per_claim: int = 3,
		min_relevance: float = 0.6,
		cooldown_seconds: int = 3600,
		force: bool = False,
	):
		"""Execute follow-up retrieval tasks for missing or partial claim support."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		plan = self.get_claim_follow_up_plan(claim_type=claim_type, user_id=user_id)
		results = {
			'support_kind': support_kind,
			'claims': {},
		}

		for current_claim, claim_plan in plan.get('claims', {}).items():
			executed_tasks = []
			skipped_tasks = []
			for task in claim_plan.get('tasks', [])[:max_tasks_per_claim]:
				execution = {
					'claim_element_id': task.get('claim_element_id'),
					'claim_element': task.get('claim_element'),
					'status': task.get('status'),
					'priority': task.get('priority'),
					'preferred_support_kind': task.get('preferred_support_kind'),
					'preferred_evidence_classes': list(task.get('preferred_evidence_classes') or []),
					'missing_fact_bundle': list(task.get('missing_fact_bundle') or []),
					'success_criteria': list(task.get('success_criteria') or []),
					'recommended_action': task.get('recommended_action'),
					'execution_mode': task.get('execution_mode', 'retrieve_support'),
					'requires_manual_review': task.get('requires_manual_review', False),
					'reasoning_backed': task.get('reasoning_backed', False),
					'follow_up_focus': task.get('follow_up_focus', ''),
					'query_strategy': task.get('query_strategy', ''),
					'proof_gap_count': int(task.get('proof_gap_count', 0) or 0),
					'proof_gap_types': list(task.get('proof_gap_types') or []),
					'authority_search_program_summary': task.get('authority_search_program_summary', {}),
					'authority_search_programs': list(task.get('authority_search_programs') or []),
					'graph_support': task.get('graph_support', {}),
					'should_suppress_retrieval': task.get('should_suppress_retrieval', False),
					'suppression_reason': task.get('suppression_reason', ''),
					'executed': {},
				}
				if task.get('execution_mode') == 'manual_review':
					manual_review_query = self._build_manual_review_audit_query(current_claim, task)
					skip_reason = self._manual_review_skip_reason(task)
					self.claim_support.record_follow_up_execution(
						user_id=user_id,
						claim_type=current_claim,
						claim_element_id=task.get('claim_element_id'),
						claim_element_text=task.get('claim_element'),
						support_kind='manual_review',
						query_text=manual_review_query,
						status='skipped_manual_review',
						metadata=self._build_follow_up_record_metadata(
							task,
							skip_reason=skip_reason,
							audit_query=manual_review_query,
						),
					)
					skipped_tasks.append({
						**execution,
						'skipped': {
							'manual_review': {
								'reason': skip_reason,
								'audit_query': manual_review_query,
							}
						},
					})
					continue
				if not force and task.get('should_suppress_retrieval'):
					skipped_tasks.append({
						**execution,
						'skipped': {
							'suppressed': {
								'reason': task.get('suppression_reason', 'existing_support_sufficient'),
							}
						},
					})
					continue
				preferred_support_kind = str(task.get('preferred_support_kind') or '').strip().lower()
				run_evidence_lane = (
					support_kind in (None, 'evidence')
					and 'evidence' in task.get('missing_support_kinds', [])
					and not (
						support_kind is None
						and preferred_support_kind == 'authority'
						and 'authority' in task.get('missing_support_kinds', [])
					)
				)
				run_authority_lane = (
					support_kind in (None, 'authority')
					and 'authority' in task.get('missing_support_kinds', [])
					and not (
						support_kind is None
						and preferred_support_kind == 'evidence'
						and 'evidence' in task.get('missing_support_kinds', [])
					)
				)
				if run_evidence_lane:
					evidence_query = task.get('queries', {}).get('evidence', [])
					query_text = evidence_query[0] if evidence_query else f'{current_claim} {task.get("claim_element", "")} evidence'
					if not force and self.claim_support.was_follow_up_executed(
						user_id,
						current_claim,
						'evidence',
						query_text,
						cooldown_seconds=cooldown_seconds,
					):
						self.claim_support.record_follow_up_execution(
							user_id=user_id,
							claim_type=current_claim,
							claim_element_id=task.get('claim_element_id'),
							claim_element_text=task.get('claim_element'),
							support_kind='evidence',
							query_text=query_text,
							status='skipped_duplicate',
							metadata=self._build_follow_up_record_metadata(
								task,
								cooldown_seconds=cooldown_seconds,
								query_variants=task.get('queries', {}).get('evidence', []),
							),
						)
						skipped_tasks.append({
							**execution,
							'skipped': {'evidence': {'query': query_text, 'reason': 'duplicate_within_cooldown'}},
						})
					else:
						keywords = self._keywords_from_follow_up_query(
							query_text,
							current_claim,
							task.get('claim_element', ''),
						)
						discovery_result = self.discover_web_evidence(
							keywords=keywords,
							user_id=user_id,
							claim_type=current_claim,
							min_relevance=min_relevance,
						)
						discovery_result_count = self._count_evidence_follow_up_results(discovery_result)
						self.claim_support.record_follow_up_execution(
							user_id=user_id,
							claim_type=current_claim,
							claim_element_id=task.get('claim_element_id'),
							claim_element_text=task.get('claim_element'),
							support_kind='evidence',
							query_text=query_text,
							status='executed',
							metadata=self._build_follow_up_record_metadata(
								task,
								keywords=keywords,
								query_variants=task.get('queries', {}).get('evidence', []),
								result_count=discovery_result_count,
								stored_result_count=int(discovery_result.get('stored', discovery_result.get('total_records', 0)) or 0)
								if isinstance(discovery_result, dict)
								else 0,
								zero_result=discovery_result_count <= 0,
							),
						)
						execution['executed']['evidence'] = {
							'query': query_text,
							'keywords': keywords,
							'result': discovery_result,
						}
				if run_authority_lane:
					authority_query = task.get('queries', {}).get('authority', [])
					task_query_text = authority_query[0] if authority_query else f'{current_claim} {task.get("claim_element", "")} statute'
					primary_program = self._select_primary_authority_search_program(task)
					program_query_text = str(primary_program.get('query_text') or '').strip() if isinstance(primary_program, dict) else ''
					query_text = program_query_text or task_query_text
					program_jurisdiction = str(primary_program.get('jurisdiction') or '').strip() if isinstance(primary_program, dict) else ''
					program_authority_families = list(primary_program.get('authority_families') or []) if isinstance(primary_program, dict) else []
					primary_program_metadata = primary_program.get('metadata') if isinstance(primary_program, dict) else {}
					if not isinstance(primary_program_metadata, dict):
						primary_program_metadata = {}
					if not force and self.claim_support.was_follow_up_executed(
						user_id,
						current_claim,
						'authority',
						query_text,
						cooldown_seconds=cooldown_seconds,
					):
						self.claim_support.record_follow_up_execution(
							user_id=user_id,
							claim_type=current_claim,
							claim_element_id=task.get('claim_element_id'),
							claim_element_text=task.get('claim_element'),
							support_kind='authority',
							query_text=query_text,
							status='skipped_duplicate',
							metadata=self._build_follow_up_record_metadata(
								task,
								cooldown_seconds=cooldown_seconds,
								query_variants=task.get('queries', {}).get('authority', []),
								task_query=task_query_text,
								effective_query=query_text,
								selected_search_program_id=str(primary_program.get('program_id') or ''),
								selected_search_program_type=str(primary_program.get('program_type') or ''),
								selected_search_program_bias=str(primary_program_metadata.get('authority_signal_bias') or ''),
								selected_search_program_rule_bias=str(primary_program_metadata.get('rule_signal_bias') or ''),
								selected_search_program_families=list(program_authority_families),
								search_program_ids=[
									program.get('program_id')
									for program in (task.get('authority_search_programs') or [])
									if isinstance(program, dict) and program.get('program_id')
								],
								search_program_count=int(
									(task.get('authority_search_program_summary') or {}).get('program_count', 0) or 0
								),
							),
						)
						skipped_tasks.append({
							**execution,
							'skipped': {'authority': {'query': query_text, 'reason': 'duplicate_within_cooldown'}},
						})
					else:
						search_results = self.search_legal_authorities(
							query=query_text,
							claim_type=current_claim,
							jurisdiction=program_jurisdiction or None,
							search_all=True,
							authority_families=program_authority_families or None,
						)
						authority_result_count = self._count_authority_follow_up_results(search_results)
						stored_counts = self.store_legal_authorities(
							search_results,
							claim_type=current_claim,
							search_query=query_text,
							user_id=user_id,
							search_programs=task.get('authority_search_programs', []),
						)
						self.claim_support.record_follow_up_execution(
							user_id=user_id,
							claim_type=current_claim,
							claim_element_id=task.get('claim_element_id'),
							claim_element_text=task.get('claim_element'),
							support_kind='authority',
							query_text=query_text,
							status='executed',
							metadata=self._build_follow_up_record_metadata(
								task,
								search_results={key: len(value) for key, value in search_results.items()},
								query_variants=task.get('queries', {}).get('authority', []),
								task_query=task_query_text,
								effective_query=query_text,
								selected_search_program_id=str(primary_program.get('program_id') or ''),
								selected_search_program_type=str(primary_program.get('program_type') or ''),
								selected_search_program_bias=str(primary_program_metadata.get('authority_signal_bias') or ''),
								selected_search_program_rule_bias=str(primary_program_metadata.get('rule_signal_bias') or ''),
								selected_search_program_families=list(program_authority_families),
								search_program_ids=[
									program.get('program_id')
									for program in (task.get('authority_search_programs') or [])
									if isinstance(program, dict) and program.get('program_id')
								],
								search_program_count=int(
									(task.get('authority_search_program_summary') or {}).get('program_count', 0) or 0
								),
								result_count=authority_result_count,
								stored_result_count=int(stored_counts.get('total_records', 0) or 0),
								zero_result=authority_result_count <= 0,
							),
						)
						execution['executed']['authority'] = {
							'query': query_text,
							'task_query': task_query_text,
							'selected_search_program_id': str(primary_program.get('program_id') or ''),
							'selected_search_program_type': str(primary_program.get('program_type') or ''),
							'selected_search_program_bias': str(primary_program_metadata.get('authority_signal_bias') or ''),
							'selected_search_program_rule_bias': str(primary_program_metadata.get('rule_signal_bias') or ''),
							'selected_search_program_families': list(program_authority_families),
							'search_program_summary': task.get('authority_search_program_summary', {}),
							'search_programs': list(task.get('authority_search_programs') or []),
							'search_results': {key: len(value) for key, value in search_results.items()},
							'stored_counts': stored_counts,
						}
				if execution['executed']:
					executed_tasks.append(execution)

			results['claims'][current_claim] = {
				'task_count': len(executed_tasks),
				'skipped_task_count': len(skipped_tasks),
				'tasks': executed_tasks,
				'skipped_tasks': skipped_tasks,
				'updated_claim_overview': self.get_claim_overview(claim_type=current_claim, user_id=user_id).get('claims', {}).get(current_claim, {}),
				'updated_follow_up_plan': self.get_claim_follow_up_plan(claim_type=current_claim, user_id=user_id).get('claims', {}).get(current_claim, {}),
			}
		return results

	def get_claim_element_view(
		self,
		claim_type: str,
		claim_element_id: str = None,
		claim_element: str = None,
		user_id: str = None,
	):
		"""Get evidence, authorities, and support coverage for one claim element."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')

		element_summary = self.claim_support.get_claim_element_summary(
			user_id,
			claim_type,
			claim_element_id=claim_element_id,
			claim_element_text=claim_element,
		)
		target_element_id = element_summary.get('element_id')
		target_element_text = element_summary.get('element_text')

		evidence_records = []
		for evidence in self.evidence_state.get_user_evidence(user_id):
			if evidence.get('claim_type') != claim_type:
				continue
			if target_element_id and evidence.get('claim_element_id') == target_element_id:
				evidence_records.append(evidence)
			elif target_element_text and evidence.get('claim_element') == target_element_text:
				evidence_records.append(evidence)

		authority_records = []
		for authority in self.legal_authority_storage.get_authorities_by_claim(user_id, claim_type):
			if target_element_id and authority.get('claim_element_id') == target_element_id:
				authority_records.append(authority)
			elif target_element_text and authority.get('claim_element') == target_element_text:
				authority_records.append(authority)

		support_facts = self.claim_support.get_claim_support_facts(
			user_id,
			claim_type,
			claim_element_id=target_element_id,
			claim_element_text=target_element_text,
		)
		support_traces = self.claim_support.get_claim_support_traces(
			user_id,
			claim_type,
			claim_element_id=target_element_id,
			claim_element_text=target_element_text,
		)
		support_packets = [
			self.claim_support._build_support_packet(trace)
			for trace in support_traces
			if isinstance(trace, dict)
		]
		gap_analysis = self.get_claim_support_gaps(
			claim_type=claim_type,
			user_id=user_id,
		)
		current_gap_summary = {
			'element_id': target_element_id,
			'element_text': target_element_text,
			'status': 'covered',
			'missing_support_kinds': [],
			'total_links': element_summary.get('total_links', 0),
			'fact_count': element_summary.get('fact_count', 0),
			'graph_trace_summary': {'traced_link_count': 0, 'snapshot_created_count': 0, 'snapshot_reused_count': 0, 'source_table_counts': {}, 'graph_status_counts': {}, 'graph_id_count': 0},
			'recommended_action': 'review_existing_support',
			'graph_support': self.query_claim_graph_support(
				claim_type=claim_type,
				claim_element_id=target_element_id,
				claim_element=target_element_text,
				user_id=user_id,
			),
		}
		for gap_element in gap_analysis.get('claims', {}).get(claim_type, {}).get('unresolved_elements', []):
			if gap_element.get('element_id') == target_element_id or gap_element.get('element_text') == target_element_text:
				current_gap_summary = gap_element
				break

		contradiction_candidates = self.get_claim_contradiction_candidates(
			claim_type=claim_type,
			user_id=user_id,
		).get('claims', {}).get(claim_type, {}).get('candidates', [])
		contradiction_candidates = [
			candidate
			for candidate in contradiction_candidates
			if candidate.get('claim_element_id') == target_element_id
			or candidate.get('claim_element_text') == target_element_text
		]
		claim_validation = self.get_claim_support_validation(
			claim_type=claim_type,
			user_id=user_id,
		).get('claims', {}).get(claim_type, {})
		current_validation_summary = {
			'element_id': target_element_id,
			'element_text': target_element_text,
			'validation_status': 'missing' if not element_summary.get('total_links', 0) else 'supported',
			'proof_gap_count': 0,
			'proof_gaps': [],
		}
		for validation_element in claim_validation.get('elements', []):
			if validation_element.get('element_id') == target_element_id or validation_element.get('element_text') == target_element_text:
				current_validation_summary = validation_element
				break

		return {
			'claim_type': claim_type,
			'claim_element_id': target_element_id,
			'claim_element': target_element_text,
			'exists': bool(target_element_id or target_element_text),
			'is_covered': bool(element_summary.get('total_links', 0)),
			'missing_support': element_summary.get('total_links', 0) == 0,
			'support_summary': element_summary,
			'graph_support': current_gap_summary.get('graph_support', {}),
			'gap_summary': current_gap_summary,
			'validation_summary': current_validation_summary,
			'contradiction_candidates': contradiction_candidates,
			'support_facts': support_facts,
			'support_traces': support_traces,
			'support_packets': support_packets,
			'support_packet_summary': self.claim_support._summarize_support_packets(support_packets),
			'evidence': evidence_records,
			'authorities': authority_records,
			'total_facts': len(support_facts),
			'total_evidence': len(evidence_records),
			'total_authorities': len(authority_records),
		}

	def get_claim_graph_facts(
		self,
		claim_type: str,
		claim_element_id: str = None,
		claim_element: str = None,
		user_id: str = None,
		max_results: int = 10,
	):
		"""Return persisted claim-support facts together with the fallback graph-support ranking."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')

		element_summary = self.claim_support.get_claim_element_summary(
			user_id,
			claim_type,
			claim_element_id=claim_element_id,
			claim_element_text=claim_element,
		)
		target_element_id = element_summary.get('element_id') or claim_element_id or ''
		target_element_text = element_summary.get('element_text') or claim_element or ''
		support_facts = self.claim_support.get_claim_support_facts(
			user_id,
			claim_type,
			claim_element_id=target_element_id or None,
			claim_element_text=target_element_text or None,
		)
		kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
		graph_result = query_graph_support(
			target_element_id,
			graph_id='intake-knowledge-graph',
			support_facts=support_facts,
			claim_type=claim_type,
			claim_element_text=target_element_text,
			max_results=max_results,
		)
		graph_result['graph_context'] = {
			'knowledge_graph_available': bool(kg),
			'entity_count': len(kg.entities) if kg else 0,
			'relationship_count': len(kg.relationships) if kg else 0,
		}

		support_by_kind: Dict[str, int] = {}
		support_by_source_family: Dict[str, int] = {}
		for fact in support_facts:
			if not isinstance(fact, dict):
				continue
			support_kind = str(fact.get('support_kind') or 'unknown')
			support_by_kind[support_kind] = support_by_kind.get(support_kind, 0) + 1
			source_family = str(fact.get('source_family') or 'unknown')
			support_by_source_family[source_family] = support_by_source_family.get(source_family, 0) + 1

		return {
			'claim_type': claim_type,
			'claim_element_id': target_element_id,
			'claim_element': target_element_text,
			'exists': bool(target_element_id or target_element_text),
			'support_facts': support_facts,
			'total_facts': len(support_facts),
			'support_by_kind': support_by_kind,
			'support_by_source_family': support_by_source_family,
			'graph_support': graph_result,
		}

	def query_claim_graph_support(
		self,
		claim_type: str,
		claim_element_id: str = None,
		claim_element: str = None,
		user_id: str = None,
		max_results: int = 10,
	):
		"""Query fallback graph support using persisted claim-support fact rows."""
		return self.get_claim_graph_facts(
			claim_type=claim_type,
			claim_element_id=claim_element_id,
			claim_element=claim_element,
			user_id=user_id,
			max_results=max_results,
		).get('graph_support', {})

	def _summarize_claim_coverage_claim(
		self,
		coverage_claim: Dict[str, Any],
		claim_type: str,
		overview_claim: Dict[str, Any] = None,
		gap_claim: Dict[str, Any] = None,
		contradiction_claim: Dict[str, Any] = None,
		validation_claim: Dict[str, Any] = None,
	) -> Dict[str, Any]:
		if not isinstance(coverage_claim, dict):
			coverage_claim = {}
		if not isinstance(overview_claim, dict):
			overview_claim = {}
		if not isinstance(gap_claim, dict):
			gap_claim = {}
		if not isinstance(contradiction_claim, dict):
			contradiction_claim = {}
		if not isinstance(validation_claim, dict):
			validation_claim = {}
		reasoning_summary = (
			(validation_claim.get('proof_diagnostics') or {}).get('reasoning', {})
			if isinstance(validation_claim.get('proof_diagnostics'), dict)
			else {}
		)
		decision_summary = (
			(validation_claim.get('proof_diagnostics') or {}).get('decision', {})
			if isinstance(validation_claim.get('proof_diagnostics'), dict)
			else {}
		)
		elements = coverage_claim.get('elements', []) if isinstance(coverage_claim.get('elements', []), list) else []
		if elements:
			missing_elements = [
				element.get('element_text')
				for element in elements
				if element.get('status') == 'missing' and element.get('element_text')
			]
			partially_supported_elements = [
				element.get('element_text')
				for element in elements
				if element.get('status') == 'partially_supported' and element.get('element_text')
			]
		else:
			missing_elements = [
				element.get('element_text')
				for element in overview_claim.get('missing', [])
				if isinstance(element, dict) and element.get('element_text')
			]
			partially_supported_elements = [
				element.get('element_text')
				for element in overview_claim.get('partially_supported', [])
				if isinstance(element, dict) and element.get('element_text')
			]
		unresolved_elements = []
		recommended_gap_actions: Dict[str, int] = {}
		for element in gap_claim.get('unresolved_elements', []):
			if not isinstance(element, dict):
				continue
			element_text = element.get('element_text')
			if element_text:
				unresolved_elements.append(element_text)
			action = str(element.get('recommended_action') or 'unspecified')
			recommended_gap_actions[action] = recommended_gap_actions.get(action, 0) + 1
		contradicted_elements = []
		contradiction_candidate_count = int(contradiction_claim.get('candidate_count', 0) or 0)
		seen_contradicted_elements = set()
		for candidate in contradiction_claim.get('candidates', []):
			if not isinstance(candidate, dict):
				continue
			element_text = candidate.get('claim_element_text')
			if element_text and element_text not in seen_contradicted_elements:
				seen_contradicted_elements.add(element_text)
				contradicted_elements.append(element_text)
		traced_link_count = 0
		snapshot_created_count = 0
		snapshot_reused_count = 0
		source_table_counts: Dict[str, int] = {}
		graph_status_counts: Dict[str, int] = {}
		graph_id_count = 0
		seen_graph_ids = set()
		for element in elements:
			if not isinstance(element, dict):
				continue
			for link in element.get('links', []):
				if not isinstance(link, dict):
					continue
				graph_trace = link.get('graph_trace', {})
				if not isinstance(graph_trace, dict) or not graph_trace:
					continue
				traced_link_count += 1
				source_table = str(graph_trace.get('source_table') or 'unknown')
				source_table_counts[source_table] = source_table_counts.get(source_table, 0) + 1
				summary = graph_trace.get('summary', {})
				if isinstance(summary, dict):
					graph_status = str(summary.get('status') or 'unknown')
					graph_status_counts[graph_status] = graph_status_counts.get(graph_status, 0) + 1
				snapshot = graph_trace.get('snapshot', {})
				if isinstance(snapshot, dict):
					if bool(snapshot.get('created')):
						snapshot_created_count += 1
					if bool(snapshot.get('reused')):
						snapshot_reused_count += 1
					graph_id = str(snapshot.get('graph_id') or '')
					if graph_id and graph_id not in seen_graph_ids:
						seen_graph_ids.add(graph_id)
						graph_id_count += 1
		return {
			'claim_type': claim_type,
			'validation_status': validation_claim.get('validation_status', ''),
			'validation_status_counts': validation_claim.get('validation_status_counts', {}),
			'proof_gap_count': int(validation_claim.get('proof_gap_count', 0) or 0),
			'elements_requiring_follow_up': validation_claim.get('elements_requiring_follow_up', []),
			'reasoning_adapter_status_counts': reasoning_summary.get('adapter_status_counts', {}),
			'reasoning_backend_available_count': int(reasoning_summary.get('backend_available_count', 0) or 0),
			'reasoning_predicate_count': int(reasoning_summary.get('predicate_count', 0) or 0),
			'reasoning_ontology_entity_count': int(reasoning_summary.get('ontology_entity_count', 0) or 0),
			'reasoning_ontology_relationship_count': int(reasoning_summary.get('ontology_relationship_count', 0) or 0),
			'reasoning_fallback_ontology_count': int(reasoning_summary.get('fallback_ontology_count', 0) or 0),
			'decision_source_counts': decision_summary.get('decision_source_counts', {}),
			'adapter_contradicted_element_count': int(decision_summary.get('adapter_contradicted_element_count', 0) or 0),
			'decision_fallback_ontology_element_count': int(decision_summary.get('fallback_ontology_element_count', 0) or 0),
			'proof_supported_element_count': int(decision_summary.get('proof_supported_element_count', 0) or 0),
			'logic_unprovable_element_count': int(decision_summary.get('logic_unprovable_element_count', 0) or 0),
			'ontology_invalid_element_count': int(decision_summary.get('ontology_invalid_element_count', 0) or 0),
			'total_elements': coverage_claim.get('total_elements', 0),
			'total_links': coverage_claim.get('total_links', 0),
			'total_facts': coverage_claim.get('total_facts', 0),
			'support_by_kind': coverage_claim.get('support_by_kind', {}),
			'support_trace_summary': coverage_claim.get('support_trace_summary', {}),
			'status_counts': coverage_claim.get(
				'status_counts',
				{'covered': 0, 'partially_supported': 0, 'missing': 0},
			),
			'missing_elements': missing_elements,
			'partially_supported_elements': partially_supported_elements,
			'unresolved_element_count': int(gap_claim.get('unresolved_count', 0) or 0),
			'unresolved_elements': unresolved_elements,
			'recommended_gap_actions': recommended_gap_actions,
			'contradiction_candidate_count': contradiction_candidate_count,
			'contradicted_elements': contradicted_elements,
			'graph_trace_summary': {
				'traced_link_count': traced_link_count,
				'snapshot_created_count': snapshot_created_count,
				'snapshot_reused_count': snapshot_reused_count,
				'source_table_counts': source_table_counts,
				'graph_status_counts': graph_status_counts,
				'graph_id_count': graph_id_count,
			},
		}
	
	def research_case_automatically(self, user_id: str = None, execute_follow_up: bool = False):
		"""
		Automatically research legal authorities for the case.
		
		This method:
		1. Analyzes the complaint to identify claims
		2. Searches for relevant legal authorities
		3. Stores the authorities in DuckDB
		
		Args:
			user_id: User identifier (defaults to state username)
			
		Returns:
			Dictionary with research results
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		# First, analyze the complaint if not already done
		if not hasattr(self.state, 'legal_classification'):
			if not self.state.complaint:
				return {'error': 'No complaint available. Generate complaint first.'}
			self.analyze_complaint_legal_issues()
		
		classification = self.state.legal_classification
		results = {
			'claim_types': classification.get('claim_types', []),
			'authorities_found': {},
			'authorities_stored': {},
			'support_summary': {},
			'claim_coverage_matrix': {},
			'claim_coverage_summary': {},
			'claim_support_gaps': {},
			'claim_contradiction_candidates': {},
			'claim_support_validation': {},
			'claim_support_snapshots': {},
			'claim_support_snapshot_summary': {},
			'claim_reasoning_review': {},
			'claim_overview': {},
			'follow_up_plan': {},
			'follow_up_plan_summary': {},
			'follow_up_history': {},
			'follow_up_history_summary': {},
			'follow_up_execution': {},
			'follow_up_execution_summary': {},
		}
		
		# Search for authorities for each claim type
		for claim_type in classification.get('claim_types', []):
			self.log('auto_research', claim_type=claim_type)
			
			# Search all sources
			search_results = self.search_legal_authorities(
				query=claim_type,
				claim_type=claim_type,
				search_all=True
			)
			
			# Store results
			stored_counts = self.store_legal_authorities(
				search_results,
				claim_type=claim_type,
				search_query=claim_type,
				user_id=user_id
			)
			
			results['authorities_found'][claim_type] = {
				k: len(v) for k, v in search_results.items()
			}
			results['authorities_stored'][claim_type] = stored_counts
			support_summary = self.summarize_claim_support(user_id, claim_type)
			results['support_summary'][claim_type] = support_summary.get('claims', {}).get(
				claim_type,
				{
					'total_links': 0,
					'support_by_kind': {},
					'links': [],
				},
			)
			coverage_matrix = self.get_claim_coverage_matrix(claim_type=claim_type, user_id=user_id)
			results['claim_coverage_matrix'][claim_type] = coverage_matrix.get('claims', {}).get(
				claim_type,
				{
					'claim_type': claim_type,
					'required_support_kinds': ['evidence', 'authority'],
					'total_elements': 0,
					'status_counts': {
						'covered': 0,
						'partially_supported': 0,
						'missing': 0,
					},
					'total_links': 0,
					'total_facts': 0,
					'support_by_kind': {},
					'elements': [],
					'unassigned_links': [],
				},
			)
			claim_overview = self.get_claim_overview(claim_type=claim_type, user_id=user_id)
			results['claim_overview'][claim_type] = claim_overview.get('claims', {}).get(
				claim_type,
				{
					'required_support_kinds': ['evidence', 'authority'],
					'covered': [],
					'partially_supported': [],
					'missing': [],
					'covered_count': 0,
					'partially_supported_count': 0,
					'missing_count': 0,
					'total_elements': 0,
				},
			)
			claim_support_gaps = self.get_claim_support_gaps(claim_type=claim_type, user_id=user_id)
			results['claim_support_gaps'][claim_type] = claim_support_gaps.get('claims', {}).get(
				claim_type,
				{
					'claim_type': claim_type,
					'required_support_kinds': ['evidence', 'authority'],
					'unresolved_count': 0,
					'unresolved_elements': [],
				},
			)
			claim_contradictions = self.get_claim_contradiction_candidates(claim_type=claim_type, user_id=user_id)
			results['claim_contradiction_candidates'][claim_type] = claim_contradictions.get('claims', {}).get(
				claim_type,
				{
					'claim_type': claim_type,
					'candidate_count': 0,
					'candidates': [],
				},
			)
			claim_validation = self.get_claim_support_validation(claim_type=claim_type, user_id=user_id)
			results['claim_support_validation'][claim_type] = claim_validation.get('claims', {}).get(
				claim_type,
				{
					'claim_type': claim_type,
					'validation_status': 'missing',
					'validation_status_counts': {
						'supported': 0,
						'incomplete': 0,
						'missing': 0,
						'contradicted': 0,
					},
					'proof_gap_count': 0,
					'proof_gaps': [],
					'elements': [],
				},
			)
			persisted_diagnostics = self.persist_claim_support_diagnostics(
				claim_type=claim_type,
				user_id=user_id,
				required_support_kinds=['evidence', 'authority'],
				gaps={'claims': {claim_type: results['claim_support_gaps'][claim_type]}},
				contradictions={'claims': {claim_type: results['claim_contradiction_candidates'][claim_type]}},
				metadata={'source': 'research_case_automatically'},
			)
			results['claim_support_snapshots'][claim_type] = persisted_diagnostics.get('claims', {}).get(
				claim_type,
				{},
			).get('snapshots', {})
			results['claim_support_snapshot_summary'][claim_type] = summarize_claim_support_snapshot_lifecycle(
				results['claim_support_snapshots'][claim_type]
			)
			results['claim_reasoning_review'][claim_type] = summarize_claim_reasoning_review(
				results['claim_support_validation'][claim_type]
			)
			results['claim_coverage_summary'][claim_type] = self._summarize_claim_coverage_claim(
				results['claim_coverage_matrix'][claim_type],
				claim_type,
				results['claim_overview'][claim_type],
				results['claim_support_gaps'][claim_type],
				results['claim_contradiction_candidates'][claim_type],
				results['claim_support_validation'][claim_type],
			)
			follow_up_plan = self.get_claim_follow_up_plan(claim_type=claim_type, user_id=user_id)
			results['follow_up_plan'][claim_type] = follow_up_plan.get('claims', {}).get(
				claim_type,
				{
					'task_count': 0,
					'tasks': [],
				},
			)
			results['follow_up_plan_summary'][claim_type] = _summarize_follow_up_plan_claim(
				results['follow_up_plan'][claim_type]
			)
			follow_up_history = self.get_recent_claim_follow_up_execution(
				claim_type=claim_type,
				user_id=user_id,
			)
			claim_history = follow_up_history.get('claims', {}).get(claim_type, [])
			results['follow_up_history'][claim_type] = claim_history
			results['follow_up_history_summary'][claim_type] = summarize_follow_up_history_claim(
				claim_history
			)
			if execute_follow_up:
				execution = self.execute_claim_follow_up_plan(
					claim_type=claim_type,
					user_id=user_id,
					support_kind='authority',
				)
				results['follow_up_execution'][claim_type] = execution.get('claims', {}).get(
					claim_type,
					{'task_count': 0, 'tasks': []},
				)
				results['follow_up_execution_summary'][claim_type] = _summarize_follow_up_execution_claim(
					results['follow_up_execution'][claim_type]
				)
				refreshed_follow_up_history = self.get_recent_claim_follow_up_execution(
					claim_type=claim_type,
					user_id=user_id,
				)
				refreshed_claim_history = refreshed_follow_up_history.get('claims', {}).get(claim_type, [])
				results['follow_up_history'][claim_type] = refreshed_claim_history
				results['follow_up_history_summary'][claim_type] = summarize_follow_up_history_claim(
					refreshed_claim_history
				)
		
		self.log('auto_research_complete', results=results)
		
		return results
	
	def discover_web_evidence(self, keywords: List[str],
	                         domains: Optional[List[str]] = None,
	                         user_id: str = None,
	                         claim_type: str = None,
	                         min_relevance: float = 0.5):
		"""
		Discover evidence from web sources.
		
		Args:
			keywords: Keywords to search for
			domains: Optional specific domains to search
			user_id: User identifier (defaults to state username)
			claim_type: Optional claim type association
			min_relevance: Minimum relevance score (0.0 to 1.0)
			
		Returns:
			Dictionary with discovered and stored evidence counts
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		return self.web_evidence_integration.discover_and_store_evidence(
			keywords=keywords,
			domains=domains,
			user_id=user_id,
			claim_type=claim_type,
			min_relevance=min_relevance
		)
	
	def search_web_for_evidence(self, keywords: List[str],
	                           domains: Optional[List[str]] = None,
	                           max_results: int = 20):
		"""
		Search web sources for evidence (without storing).
		
		Args:
			keywords: Keywords to search for
			domains: Optional specific domains
			max_results: Maximum results per source
			
		Returns:
			Dictionary with search results from each source
		"""
		return self.web_evidence_search.search_for_evidence(
			keywords=keywords,
			domains=domains,
			max_results=max_results
		)

	def run_agentic_scraper_cycle(self,
	                            keywords: List[str],
	                            domains: Optional[List[str]] = None,
	                            iterations: int = 1,
	                            sleep_seconds: float = 0.0,
	                            quality_domain: str = 'caselaw',
	                            user_id: str = None,
	                            claim_type: str = None,
	                            min_relevance: float = 0.5,
	                            store_results: bool = True):
		"""
		Run the agentic scraper loop for a bounded number of iterations.

		Args:
			keywords: Search keywords to seed discovery
			domains: Optional domains to prioritize for archival sweeps
			iterations: Number of optimizer iterations to run
			sleep_seconds: Delay between iterations for daemon-style use
			quality_domain: Validation domain used by scraper quality checks
			user_id: Optional user identifier override
			claim_type: Optional claim association for stored evidence
			min_relevance: Minimum relevance threshold when storing daemon results
			store_results: Whether to feed accepted daemon results into evidence storage

		Returns:
			Dictionary with iteration reports, final results, and coverage ledger
		"""
		return self.web_evidence_integration.run_agentic_scraper_cycle(
			keywords=keywords,
			domains=domains,
			iterations=iterations,
			sleep_seconds=sleep_seconds,
			quality_domain=quality_domain,
			user_id=user_id,
			claim_type=claim_type,
			min_relevance=min_relevance,
			store_results=store_results,
		)

	def run_agentic_scraper_daemon(self,
	                             keywords: List[str],
	                             domains: Optional[List[str]] = None,
	                             iterations: int = 3,
	                             sleep_seconds: float = 5.0,
	                             quality_domain: str = 'caselaw',
	                             user_id: str = None,
	                             claim_type: str = None,
	                             min_relevance: float = 0.5,
	                             store_results: bool = True):
		"""Convenience alias for a longer-running agentic scraper loop."""
		return self.run_agentic_scraper_cycle(
			keywords=keywords,
			domains=domains,
			iterations=iterations,
			sleep_seconds=sleep_seconds,
			quality_domain=quality_domain,
			user_id=user_id,
			claim_type=claim_type,
			min_relevance=min_relevance,
			store_results=store_results,
		)
	
	def discover_evidence_automatically(self, user_id: str = None, execute_follow_up: bool = False):
		"""
		Automatically discover evidence for all claims in the case.
		
		This method:
		1. Analyzes the complaint to identify claims
		2. Generates search keywords for each claim
		3. Searches web sources (Brave Search, Common Crawl)
		4. Validates and stores relevant evidence
		
		Args:
			user_id: User identifier (defaults to state username)
			
		Returns:
			Dictionary with discovery results for each claim
		"""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		
		return self.web_evidence_integration.discover_evidence_for_case(
			user_id=user_id,
			execute_follow_up=execute_follow_up,
		)


	# ============================================================================
	# THREE-PHASE COMPLAINT PROCESSING METHODS
	# ============================================================================
	
	def start_three_phase_process(self, initial_complaint_text: str) -> Dict[str, Any]:
		"""
		Start the three-phase complaint processing workflow.
		
		Phase 1: Initial intake and denoising
		Phase 2: Evidence gathering  
		Phase 3: Neurosymbolic matching and formalization
		
		Args:
			initial_complaint_text: The user's initial complaint text
			
		Returns:
			Status information about phase 1 initiation
		"""
		self.log('three_phase_start', text=initial_complaint_text)
		
		# Phase 1: Build initial knowledge and dependency graphs
		kg = self.kg_builder.build_from_text(initial_complaint_text)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
		
		# Extract claims from knowledge graph
		claim_entities = kg.get_entities_by_type('claim')
		claims = [
			{
				'name': e.name,
				'type': e.attributes.get('claim_type', 'unknown'),
				'description': e.attributes.get('description', '')
			}
			for e in claim_entities
		]
		
		# Build dependency graph
		dg = self.dg_builder.build_from_claims(claims)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
		self._update_intake_contradiction_state(dg)
		intake_case_file = self._initialize_intake_case_file(kg, initial_complaint_text)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)
		
		# Generate initial denoising questions
		kg_gaps = kg.find_gaps()
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', kg_gaps)
		self.phase_manager.update_phase_data(
			ComplaintPhase.INTAKE,
			'intake_gap_types',
			[gap.get('type') for gap in kg_gaps if isinstance(gap, dict) and gap.get('type')],
		)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', len(kg_gaps))
		intake_matching_pressure = self._build_intake_matching_pressure_map(kg, dg, intake_case_file)
		question_candidates = self.denoiser.collect_question_candidates(
			kg,
			dg,
			max_questions=10,
			intake_case_file=intake_case_file,
		)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_matching_pressure', intake_matching_pressure)
		questions = self.denoiser.generate_questions(
			kg,
			dg,
			max_questions=10,
			intake_case_file=intake_case_file,
		)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'question_candidates', question_candidates)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_questions', questions)
		
		# Calculate initial noise level
		noise = self.denoiser.calculate_noise_level(kg, dg)
		self.phase_manager.record_iteration(noise, {
			'entities': len(kg.entities),
			'relationships': len(kg.relationships),
			'gaps': len(kg.find_gaps())
		})
		
		return {
			'phase': ComplaintPhase.INTAKE.value,
			'knowledge_graph_summary': kg.summary(),
			'dependency_graph_summary': dg.summary(),
			'intake_case_file': intake_case_file,
			'intake_matching_summary': self._summarize_intake_matching_pressure(intake_matching_pressure),
			'intake_legal_targeting_summary': self._summarize_intake_legal_targeting(
				intake_matching_pressure,
				question_candidates,
			),
			'question_candidates': question_candidates,
			'initial_questions': questions,
			'initial_noise_level': noise,
			'intake_readiness': self.phase_manager.get_intake_readiness(),
			'next_action': self.phase_manager.get_next_action()
		}

	def _initialize_intake_case_file(self, knowledge_graph, complaint_text: str) -> Dict[str, Any]:
		"""Build the initial structured intake case file from the current knowledge graph."""
		return build_intake_case_file(knowledge_graph, complaint_text)

	def _normalize_intake_text(self, value: Any) -> str:
		return " ".join(str(value or "").strip().split())

	def _extract_date_or_range_from_text(self, value: str) -> str | None:
		normalized = self._normalize_intake_text(value)
		if not normalized:
			return None
		date_match = re.search(
			r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}',
			normalized,
			re.IGNORECASE,
		)
		if date_match:
			return date_match.group(0)
		year_match = re.search(r'\b(19|20)\d{2}\b', normalized)
		if year_match:
			return year_match.group(0)
		return None

	def _question_materiality(self, question_type: str) -> str:
		if question_type in {'timeline', 'responsible_party', 'requirement', 'contradiction'}:
			return 'high'
		if question_type in {'impact', 'remedy', 'evidence'}:
			return 'high'
		return 'medium'

	def _question_corroboration_priority(self, question_type: str) -> str:
		if question_type in {'timeline', 'requirement', 'evidence', 'contradiction'}:
			return 'high'
		if question_type in {'impact', 'remedy', 'responsible_party'}:
			return 'medium'
		return 'medium'

	def _proof_lead_expected_format(self, lead_type: str) -> str:
		normalized = self._normalize_intake_text(lead_type).lower()
		if 'email' in normalized:
			return 'email'
		if 'text' in normalized or 'message' in normalized:
			return 'message export'
		if 'photo' in normalized or 'picture' in normalized:
			return 'image'
		if 'witness' in normalized:
			return 'testimony'
		return 'document or testimony'

	def _proof_lead_retrieval_path(self, lead_type: str) -> str:
		normalized = self._normalize_intake_text(lead_type).lower()
		if 'email' in normalized:
			return 'complainant_email_account'
		if 'text' in normalized or 'message' in normalized:
			return 'complainant_mobile_device'
		if 'witness' in normalized:
			return 'witness_follow_up'
		return 'complainant_possession'

	def _extract_location_from_text(self, value: str) -> str | None:
		normalized = self._normalize_intake_text(value)
		if not normalized:
			return None
		location_match = re.search(
			r'\b(?:at|in)\s+(?:the\s+)?([A-Za-z0-9][A-Za-z0-9\s\-]{1,60}?(?:office|store|branch|facility|school|hospital|warehouse|workplace|department))\b',
			normalized,
			re.IGNORECASE,
		)
		if location_match:
			return self._normalize_intake_text(location_match.group(1))
		return None

	def _extract_actor_reference_from_text(self, value: str) -> str | None:
		normalized = self._normalize_intake_text(value)
		if not normalized:
			return None
		verb_match = re.search(
			r'\b((?:my|the)\s+[A-Za-z][A-Za-z\s]{1,40}|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\s+(?:fired|terminated|harassed|retaliated|demoted|disciplined|denied|rejected|cut|reported|ignored)\b',
			normalized,
			re.IGNORECASE,
		)
		if verb_match:
			return self._normalize_intake_text(verb_match.group(1))
		by_match = re.search(
			r'\bby\s+((?:my|the)\s+[A-Za-z][A-Za-z\s]{1,40}|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\b',
			normalized,
			re.IGNORECASE,
		)
		if by_match:
			return self._normalize_intake_text(by_match.group(1))
		return None

	def _extract_target_reference_from_text(self, value: str) -> str | None:
		normalized = self._normalize_intake_text(value)
		if not normalized:
			return None
		lower_value = normalized.lower()
		if re.search(r'\b(me|my|mine|us|our|we)\b', lower_value):
			return 'complainant'
		against_match = re.search(
			r'\bagainst\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\b',
			normalized,
		)
		if against_match:
			return self._normalize_intake_text(against_match.group(1))
		return None

	def _extract_fact_participants_from_answer(self, answer: str) -> Dict[str, Any]:
		actor = self._extract_actor_reference_from_text(answer)
		target = self._extract_target_reference_from_text(answer)
		location = self._extract_location_from_text(answer)
		participants: Dict[str, Any] = {}
		if actor:
			participants['actor'] = actor
		if target:
			participants['target'] = target
		if location:
			participants['location'] = location
		return participants

	def _infer_support_kind_from_answer(self, answer: str, lead_type: str) -> str:
		lower_answer = self._normalize_intake_text(answer).lower()
		lower_lead_type = self._normalize_intake_text(lead_type).lower()
		if any(token in lower_answer for token in ('witness', 'coworker', 'co-worker', 'saw it', 'heard it', 'first-hand')):
			return 'testimony'
		if any(token in lower_answer for token in ('policy', 'handbook', 'rule', 'official notice')):
			return 'authority'
		if 'witness' in lower_lead_type:
			return 'testimony'
		return 'evidence'

	def _infer_source_quality_target(self, support_kind: str) -> str:
		if support_kind == 'testimony':
			return 'credible_testimony'
		if support_kind == 'authority':
			return 'authoritative_source'
		return 'high_quality_document'

	def _infer_proof_lead_custodian(self, answer: str, lead_type: str) -> str:
		support_kind = self._infer_support_kind_from_answer(answer, lead_type)
		if support_kind == 'testimony':
			return 'witness_follow_up'
		if 'email' in lead_type.lower():
			return 'complainant_email_account'
		if 'text' in lead_type.lower() or 'message' in lead_type.lower():
			return 'complainant_mobile_device'
		return 'complainant'

	def _resolve_answer_claim_types(self, intake_case_file: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
		claim_types: List[str] = []
		context_claim_type = self._normalize_intake_text(context.get('claim_type') or context.get('target_claim_type')).lower()
		if context_claim_type:
			claim_types.append(context_claim_type)
		for claim in intake_case_file.get('candidate_claims', []) if isinstance(intake_case_file.get('candidate_claims', []), list) else []:
			if not isinstance(claim, dict) or not claim.get('claim_type'):
				continue
			claim_type = str(claim.get('claim_type')).strip().lower()
			if claim_type and claim_type not in claim_types:
				claim_types.append(claim_type)
		return claim_types

	def _resolve_answer_element_targets(self, context: Dict[str, Any]) -> List[str]:
		element_targets: List[str] = []
		for key in ('target_element_id', 'requirement_id', 'claim_element_id'):
			value = self._normalize_intake_text(context.get(key))
			if value and value not in element_targets:
				element_targets.append(value)
		return element_targets

	def _resolve_evidence_classes_for_context(self, intake_case_file: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
		target_claim_type = self._normalize_intake_text(context.get('claim_type') or context.get('target_claim_type')).lower()
		target_element_id = self._normalize_intake_text(context.get('target_element_id') or context.get('requirement_id')).lower()
		for claim in intake_case_file.get('candidate_claims', []) if isinstance(intake_case_file.get('candidate_claims', []), list) else []:
			if not isinstance(claim, dict):
				continue
			claim_type = str(claim.get('claim_type') or '').strip().lower()
			if target_claim_type and claim_type != target_claim_type:
				continue
			for element in claim.get('required_elements', []) or []:
				if not isinstance(element, dict):
					continue
				element_id = str(element.get('element_id') or '').strip().lower()
				if target_element_id and element_id != target_element_id:
					continue
				return list(element.get('evidence_classes', []) or [])
		return []

	def _next_intake_record_id(self, prefix: str, records: List[Dict[str, Any]]) -> str:
		return f"{prefix}_{len(records) + 1:03d}"

	def _find_matching_canonical_fact(
		self,
		canonical_facts: List[Dict[str, Any]],
		*,
		fact_type: str,
		text: str,
	) -> Dict[str, Any] | None:
		normalized_text = self._normalize_intake_text(text).lower()
		for fact in canonical_facts:
			if not isinstance(fact, dict):
				continue
			if str(fact.get('fact_type') or '').strip().lower() != fact_type:
				continue
			existing_text = self._normalize_intake_text(fact.get('text')).lower()
			if existing_text == normalized_text:
				return fact
		return None

	def _append_canonical_fact(
		self,
		intake_case_file: Dict[str, Any],
		*,
		text: str,
		fact_type: str,
		question_type: str,
		event_date_or_range: str | None = None,
		actor_ids: List[str] | None = None,
		target_ids: List[str] | None = None,
		location: str | None = None,
		claim_types: List[str] | None = None,
		element_tags: List[str] | None = None,
		materiality: str | None = None,
		corroboration_priority: str | None = None,
		fact_participants: Dict[str, Any] | None = None,
	) -> Dict[str, Any]:
		canonical_facts = intake_case_file.setdefault('canonical_facts', [])
		if not isinstance(canonical_facts, list):
			canonical_facts = []
			intake_case_file['canonical_facts'] = canonical_facts
		normalized_text = self._normalize_intake_text(text)
		existing = self._find_matching_canonical_fact(canonical_facts, fact_type=fact_type, text=normalized_text)
		if existing is not None:
			existing['confidence'] = max(float(existing.get('confidence', 0.6) or 0.6), 0.75)
			existing['status'] = 'accepted'
			if event_date_or_range and not existing.get('event_date_or_range'):
				existing['event_date_or_range'] = event_date_or_range
			if location and not existing.get('location'):
				existing['location'] = location
			existing['claim_types'] = list(dict.fromkeys(list(existing.get('claim_types', []) or []) + list(claim_types or [])))
			existing['element_tags'] = list(dict.fromkeys(list(existing.get('element_tags', []) or []) + list(element_tags or [])))
			existing['actor_ids'] = list(dict.fromkeys(list(existing.get('actor_ids', []) or []) + list(actor_ids or [])))
			existing['target_ids'] = list(dict.fromkeys(list(existing.get('target_ids', []) or []) + list(target_ids or [])))
			existing['fact_participants'] = {
				**(existing.get('fact_participants') if isinstance(existing.get('fact_participants'), dict) else {}),
				**(fact_participants if isinstance(fact_participants, dict) else {}),
			}
			if materiality:
				existing['materiality'] = materiality
			if corroboration_priority:
				existing['corroboration_priority'] = corroboration_priority
			return existing

		fact_record = {
			'fact_id': self._next_intake_record_id('fact', canonical_facts),
			'text': normalized_text,
			'fact_type': fact_type,
			'claim_types': list(claim_types or []),
			'element_tags': list(element_tags or []),
			'event_date_or_range': event_date_or_range,
			'actor_ids': list(actor_ids or []),
			'target_ids': list(target_ids or []),
			'location': location,
			'source_kind': 'complainant_answer',
			'source_ref': question_type,
			'confidence': 0.75,
			'status': 'accepted',
			'needs_corroboration': True,
			'corroboration_priority': corroboration_priority or self._question_corroboration_priority(question_type),
			'materiality': materiality or self._question_materiality(question_type),
			'fact_participants': fact_participants if isinstance(fact_participants, dict) else {},
			'contradiction_group_id': None,
		}
		canonical_facts.append(fact_record)
		return fact_record

	def _append_proof_lead(
		self,
		intake_case_file: Dict[str, Any],
		*,
		text: str,
		lead_type: str,
		related_fact_ids: List[str] | None = None,
		fact_targets: List[str] | None = None,
		element_targets: List[str] | None = None,
		owner: str | None = None,
		expected_format: str | None = None,
		retrieval_path: str | None = None,
		authenticity_risk: str | None = None,
		privacy_risk: str | None = None,
		priority: str | None = None,
		evidence_classes: List[str] | None = None,
		availability_details: str | None = None,
		custodian: str | None = None,
		recommended_support_kind: str | None = None,
		source_quality_target: str | None = None,
	) -> Dict[str, Any]:
		proof_leads = intake_case_file.setdefault('proof_leads', [])
		if not isinstance(proof_leads, list):
			proof_leads = []
			intake_case_file['proof_leads'] = proof_leads
		normalized_text = self._normalize_intake_text(text)
		for lead in proof_leads:
			if not isinstance(lead, dict):
				continue
			if self._normalize_intake_text(lead.get('description')).lower() == normalized_text.lower():
				lead['related_fact_ids'] = list(dict.fromkeys(list(lead.get('related_fact_ids', []) or []) + list(related_fact_ids or [])))
				lead['fact_targets'] = list(dict.fromkeys(list(lead.get('fact_targets', []) or []) + list(fact_targets or [])))
				lead['element_targets'] = list(dict.fromkeys(list(lead.get('element_targets', []) or []) + list(element_targets or [])))
				lead['evidence_classes'] = list(dict.fromkeys(list(lead.get('evidence_classes', []) or []) + list(evidence_classes or [])))
				if availability_details and not lead.get('availability_details'):
					lead['availability_details'] = availability_details
				if custodian and not lead.get('custodian'):
					lead['custodian'] = custodian
				if recommended_support_kind and not lead.get('recommended_support_kind'):
					lead['recommended_support_kind'] = recommended_support_kind
				if source_quality_target and not lead.get('source_quality_target'):
					lead['source_quality_target'] = source_quality_target
				return lead
		lead_record = {
			'lead_id': self._next_intake_record_id('lead', proof_leads),
			'lead_type': lead_type,
			'description': normalized_text,
			'related_fact_ids': list(related_fact_ids or []),
			'fact_targets': list(fact_targets or []),
			'element_targets': list(element_targets or []),
			'availability': 'claimed_available',
			'availability_details': availability_details or 'Provided by complainant during intake',
			'owner': owner or 'complainant',
			'custodian': custodian or owner or 'complainant',
			'expected_format': expected_format or self._proof_lead_expected_format(lead_type),
			'retrieval_path': retrieval_path or self._proof_lead_retrieval_path(lead_type),
			'authenticity_risk': authenticity_risk or 'review_required',
			'privacy_risk': privacy_risk or 'review_required',
			'priority': priority or 'medium',
			'evidence_classes': list(evidence_classes or []),
			'recommended_support_kind': recommended_support_kind or ('testimony' if 'witness' in lead_type.lower() else 'evidence'),
			'source_quality_target': source_quality_target or ('credible' if 'witness' in lead_type.lower() else 'high_quality_document'),
			'source_kind': 'complainant_answer',
			'source_ref': lead_type,
		}
		proof_leads.append(lead_record)
		return lead_record

	def _record_case_file_contradiction(
		self,
		intake_case_file: Dict[str, Any],
		*,
		topic: str,
		left_fact: Dict[str, Any],
		right_text: str,
		severity: str = 'blocking',
	) -> None:
		contradiction_queue = intake_case_file.setdefault('contradiction_queue', [])
		if not isinstance(contradiction_queue, list):
			contradiction_queue = []
			intake_case_file['contradiction_queue'] = contradiction_queue
		normalized_topic = self._normalize_intake_text(topic) or 'intake fact'
		normalized_right_text = self._normalize_intake_text(right_text)
		for entry in contradiction_queue:
			if not isinstance(entry, dict):
				continue
			if self._normalize_intake_text(entry.get('topic')) == normalized_topic:
				return
		left_fact['status'] = 'contradicted'
		left_fact['needs_corroboration'] = True
		contradiction_id = self._next_intake_record_id('ctr', contradiction_queue)
		left_fact['contradiction_group_id'] = contradiction_id
		contradiction_queue.append({
			'contradiction_id': contradiction_id,
			'severity': severity,
			'fact_ids': [left_fact.get('fact_id')],
			'affected_element_ids': list(left_fact.get('element_tags', []) or []),
			'topic': normalized_topic,
			'status': 'open',
			'existing_text': self._normalize_intake_text(left_fact.get('text')),
			'new_text': normalized_right_text,
		})

	def _extract_proof_lead_type(self, answer: str) -> str:
		lower_answer = (answer or '').lower()
		if 'email' in lower_answer:
			return 'email communication'
		if 'text' in lower_answer:
			return 'text messages'
		if 'letter' in lower_answer:
			return 'letter'
		if 'witness' in lower_answer:
			return 'witness'
		if 'photo' in lower_answer or 'picture' in lower_answer:
			return 'photos'
		return 'supporting evidence'

	def _apply_intake_answer_to_case_file(
		self,
		question: Dict[str, Any],
		answer: str,
		intake_case_file: Dict[str, Any],
		knowledge_graph,
	) -> Dict[str, Any]:
		"""Update the structured intake case file from a denoising answer."""
		if not isinstance(intake_case_file, dict):
			intake_case_file = {}
		normalized_answer = self._normalize_intake_text(answer)
		if not normalized_answer:
			return intake_case_file

		question_type = str(question.get('type') or '').strip().lower()
		context = question.get('context', {}) if isinstance(question.get('context'), dict) else {}
		resolved_claim_types = self._resolve_answer_claim_types(intake_case_file, context)
		resolved_element_targets = self._resolve_answer_element_targets(context)
		created_fact: Dict[str, Any] | None = None
		fact_participants = self._extract_fact_participants_from_answer(normalized_answer)
		actor_ref = str(fact_participants.get('actor') or '').strip()
		target_ref = str(fact_participants.get('target') or '').strip()
		location_ref = str(fact_participants.get('location') or '').strip() or self._extract_location_from_text(normalized_answer)

		if question_type == 'timeline':
			existing_timeline_facts = [
				fact for fact in intake_case_file.get('canonical_facts', [])
				if isinstance(fact, dict) and str(fact.get('fact_type') or '').strip().lower() == 'timeline'
			]
			created_fact = self._append_canonical_fact(
				intake_case_file,
				text=normalized_answer,
				fact_type='timeline',
				question_type=question_type,
				event_date_or_range=self._extract_date_or_range_from_text(normalized_answer),
				actor_ids=[actor_ref] if actor_ref else None,
				target_ids=[target_ref] if target_ref else None,
				location=location_ref,
				claim_types=resolved_claim_types,
				element_tags=resolved_element_targets,
				materiality='high',
				corroboration_priority='high',
				fact_participants=fact_participants,
			)
			for existing_fact in existing_timeline_facts:
				existing_text = self._normalize_intake_text(existing_fact.get('text'))
				if existing_text and existing_text.lower() != normalized_answer.lower():
					self._record_case_file_contradiction(
						intake_case_file,
						topic='timeline',
						left_fact=existing_fact,
						right_text=normalized_answer,
					)
					created_fact['status'] = 'contradicted'
					created_fact['contradiction_group_id'] = existing_fact.get('contradiction_group_id')
					break
		elif question_type in {'impact', 'remedy'}:
			created_fact = self._append_canonical_fact(
				intake_case_file,
				text=normalized_answer,
				fact_type='remedy' if question_type == 'remedy' else 'impact',
				question_type=question_type,
				claim_types=resolved_claim_types,
				element_tags=resolved_element_targets,
				materiality='high',
			)
			if question_type == 'impact' and self._normalize_intake_text(answer):
				lower_answer = normalized_answer.lower()
				if any(token in lower_answer for token in ['seek', 'seeking', 'want', 'request', 'asking for', 'compensation', 'refund']):
					self._append_canonical_fact(
						intake_case_file,
						text=normalized_answer,
						fact_type='remedy',
						question_type='remedy',
					)
		elif question_type == 'evidence':
			support_kind = self._infer_support_kind_from_answer(answer, self._extract_proof_lead_type(answer))
			created_fact = self._append_canonical_fact(
				intake_case_file,
				text=normalized_answer,
				fact_type='supporting_evidence',
				question_type=question_type,
				actor_ids=[actor_ref] if actor_ref else None,
				target_ids=[target_ref] if target_ref else None,
				location=location_ref,
				claim_types=resolved_claim_types,
				element_tags=resolved_element_targets,
				materiality='high',
				corroboration_priority='high',
				fact_participants=fact_participants,
			)
			evidence_classes = self._resolve_evidence_classes_for_context(intake_case_file, context)
			lead_type = self._extract_proof_lead_type(answer)
			self._append_proof_lead(
				intake_case_file,
				text=normalized_answer,
				lead_type=lead_type,
				related_fact_ids=[created_fact['fact_id']],
				fact_targets=[created_fact['fact_id']],
				element_targets=resolved_element_targets,
				priority='high' if question.get('priority') == 'high' else 'medium',
				evidence_classes=evidence_classes,
				custodian=self._infer_proof_lead_custodian(answer, lead_type),
				recommended_support_kind=support_kind,
				source_quality_target=self._infer_source_quality_target(support_kind),
			)
		elif question_type == 'responsible_party':
			created_fact = self._append_canonical_fact(
				intake_case_file,
				text=normalized_answer,
				fact_type='responsible_party',
				question_type=question_type,
				actor_ids=[actor_ref or normalized_answer],
				target_ids=[target_ref] if target_ref else None,
				location=location_ref,
				claim_types=resolved_claim_types,
				element_tags=resolved_element_targets,
				fact_participants={
					**fact_participants,
					'actor': actor_ref or normalized_answer,
				},
				materiality='high',
			)
		elif question_type == 'requirement':
			created_fact = self._append_canonical_fact(
				intake_case_file,
				text=normalized_answer,
				fact_type='claim_element',
				question_type=question_type,
				actor_ids=[actor_ref] if actor_ref else None,
				target_ids=[target_ref] if target_ref else None,
				location=location_ref,
				claim_types=resolved_claim_types,
				element_tags=list(resolved_element_targets),
				materiality='high',
				corroboration_priority='high',
				fact_participants=fact_participants,
			)
			target_element_id = self._normalize_intake_text(context.get('requirement_id'))
			requirement_name = self._normalize_intake_text(context.get('requirement_name'))
			candidate_claim_types = [
				str(claim.get('claim_type') or '').strip().lower()
				for claim in intake_case_file.get('candidate_claims', [])
				if isinstance(claim, dict) and claim.get('claim_type')
			]
			matched_element_tags = []
			for claim_type in candidate_claim_types:
				matched = match_required_element_id(claim_type, requirement_name) or match_required_element_id(claim_type, normalized_answer)
				if matched and matched not in matched_element_tags:
					matched_element_tags.append(matched)
			if target_element_id and target_element_id not in matched_element_tags:
				matched_element_tags.append(target_element_id)
			if matched_element_tags:
				created_fact['element_tags'] = matched_element_tags
		elif question_type == 'clarification':
			created_fact = self._append_canonical_fact(
				intake_case_file,
				text=normalized_answer,
				fact_type='clarification',
				question_type=question_type,
				claim_types=resolved_claim_types,
				element_tags=resolved_element_targets,
			)
		elif question_type == 'contradiction':
			contradiction_queue = intake_case_file.setdefault('contradiction_queue', [])
			if isinstance(contradiction_queue, list):
				contradiction_label = self._normalize_intake_text(context.get('contradiction_label'))
				for entry in contradiction_queue:
					if not isinstance(entry, dict):
						continue
					if contradiction_label and self._normalize_intake_text(entry.get('topic')) == contradiction_label:
						entry['status'] = 'resolved'
						entry['resolution'] = normalized_answer
						break
			created_fact = self._append_canonical_fact(
				intake_case_file,
				text=normalized_answer,
				fact_type='contradiction_resolution',
				question_type=question_type,
				claim_types=resolved_claim_types,
				element_tags=resolved_element_targets,
				materiality='high',
				corroboration_priority='high',
			)

		if created_fact and intake_case_file.get('candidate_claims'):
			created_fact['claim_types'] = list(dict.fromkeys(list(created_fact.get('claim_types', []) or []) + resolved_claim_types))

		return refresh_intake_case_file(intake_case_file, knowledge_graph, append_snapshot=True)
	
	def process_denoising_answer(self, question: Dict[str, Any], answer: str) -> Dict[str, Any]:
		"""
		Process an answer to a denoising question in Phase 1.
		
		Args:
			question: The question that was asked
			answer: The user's answer
			
		Returns:
			Updated status with next questions or phase transition info
		"""
		kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
		dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
		
		# Process the answer
		updates = self.denoiser.process_answer(question, answer, kg, dg)
		self._update_intake_contradiction_state(dg)
		intake_case_file = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
		intake_case_file = self._apply_intake_answer_to_case_file(question, answer, intake_case_file, kg)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_case_file', intake_case_file)
		
		# Generate next questions
		max_questions = 5
		try:
			if hasattr(self.denoiser, "is_stagnating") and self.denoiser.is_stagnating():
				max_questions = 8
		except Exception:
			max_questions = 5
		question_candidates = self.denoiser.collect_question_candidates(
			kg,
			dg,
			max_questions=max_questions,
			intake_case_file=intake_case_file,
		)
		intake_matching_pressure = self._build_intake_matching_pressure_map(kg, dg, intake_case_file)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_matching_pressure', intake_matching_pressure)
		questions = self.denoiser.generate_questions(
			kg,
			dg,
			max_questions=max_questions,
			intake_case_file=intake_case_file,
		)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'question_candidates', question_candidates)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_questions', questions)
		
		# Update graphs in phase data
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
		
		# Calculate new noise level
		noise = self.denoiser.calculate_noise_level(kg, dg)
		kg_gaps = kg.find_gaps()
		gaps = len(kg_gaps)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', kg_gaps)
		self.phase_manager.update_phase_data(
			ComplaintPhase.INTAKE,
			'intake_gap_types',
			[gap.get('type') for gap in kg_gaps if isinstance(gap, dict) and gap.get('type')],
		)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', gaps)
		
		# Record iteration
		self.phase_manager.record_iteration(noise, {
			'entities': len(kg.entities),
			'relationships': len(kg.relationships),
			'gaps': gaps,
			'updates': updates,
			'denoiser_policy': self.denoiser.get_policy_state() if hasattr(self.denoiser, 'get_policy_state') else None,
		})
		
		# Check for convergence
		converged = self.phase_manager.has_converged() or self.denoiser.is_exhausted()
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', converged)
		
		result = {
			'updates': updates,
			'noise_level': noise,
			'gaps_remaining': gaps,
			'converged': converged,
			'intake_matching_summary': self._summarize_intake_matching_pressure(intake_matching_pressure),
			'intake_legal_targeting_summary': self._summarize_intake_legal_targeting(
				intake_matching_pressure,
				question_candidates,
			),
			'question_candidates': question_candidates,
			'next_questions': questions,
			'iteration': self.phase_manager.iteration_count,
			'intake_readiness': self.phase_manager.get_intake_readiness(),
			'next_action': self.phase_manager.get_next_action(),
		}
		
		# Check if ready to advance to Phase 2
		if self.phase_manager.is_phase_complete(ComplaintPhase.INTAKE):
			result['ready_for_evidence_phase'] = True
			result['message'] = 'Initial intake complete. Ready to gather evidence.'
		
		return result

	def _collect_intake_contradictions(self, dependency_graph) -> Dict[str, Any]:
		"""Collect contradiction candidates present in the intake dependency graph."""
		candidates = []
		seen_pairs = set()
		for dependency in getattr(dependency_graph, 'dependencies', {}).values():
			dependency_type = getattr(dependency, 'dependency_type', None)
			dependency_type_value = getattr(dependency_type, 'value', str(dependency_type or '')).lower()
			if dependency_type_value != 'contradicts':
				continue
			left_node = dependency_graph.get_node(dependency.source_id)
			right_node = dependency_graph.get_node(dependency.target_id)
			left_name = left_node.name if left_node else str(dependency.source_id)
			right_name = right_node.name if right_node else str(dependency.target_id)
			pair_key = tuple(sorted((str(left_name), str(right_name))))
			if pair_key in seen_pairs:
				continue
			seen_pairs.add(pair_key)
			candidates.append({
				'dependency_id': dependency.id,
				'left_node_id': dependency.source_id,
				'right_node_id': dependency.target_id,
				'left_node_name': left_name,
				'right_node_name': right_name,
				'label': f'{left_name} vs {right_name}',
			})
		return {
			'candidate_count': len(candidates),
			'candidates': candidates,
		}

	def _update_intake_contradiction_state(self, dependency_graph) -> Dict[str, Any]:
		"""Persist intake contradiction diagnostics derived from the dependency graph."""
		contradiction_snapshot = self._collect_intake_contradictions(dependency_graph)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'intake_contradictions', contradiction_snapshot)
		self.phase_manager.update_phase_data(
			ComplaintPhase.INTAKE,
			'contradictions_unresolved',
			bool(contradiction_snapshot.get('candidate_count', 0)),
		)
		return contradiction_snapshot

	def _current_user_id(self) -> str:
		return getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')

	def _claim_element_registry_entry(
		self,
		intake_case_file: Dict[str, Any],
		claim_type: str,
		element_id: str,
	) -> Dict[str, Any]:
		candidate_claims = intake_case_file.get('candidate_claims', []) if isinstance(intake_case_file, dict) else []
		for claim in candidate_claims if isinstance(candidate_claims, list) else []:
			if not isinstance(claim, dict):
				continue
			if str(claim.get('claim_type') or '').strip().lower() != str(claim_type or '').strip().lower():
				continue
			for element in claim.get('required_elements', []) or []:
				if not isinstance(element, dict):
					continue
				if str(element.get('element_id') or '').strip().lower() == str(element_id or '').strip().lower():
					return element
		registry = CLAIM_INTAKE_REQUIREMENTS.get(str(claim_type or '').strip().lower(), {})
		for element in registry.get('elements', []) if isinstance(registry, dict) else []:
			if not isinstance(element, dict):
				continue
			if str(element.get('element_id') or '').strip().lower() == str(element_id or '').strip().lower():
				return element
		return {}

	def _required_fact_bundle_for_element(
		self,
		claim_type: str,
		element_id: str,
		element_text: str,
	) -> List[str]:
		normalized_element_id = str(element_id or '').strip().lower()
		normalized_claim_type = str(claim_type or '').strip().lower()
		bundle_map = {
			'protected_activity': [
				'What protected activity occurred',
				'When the protected activity occurred',
				'Who received or observed the protected activity',
				'How the protected activity was documented or can be corroborated',
			],
			'adverse_action': [
				'What adverse action or harmful conduct occurred',
				'When the adverse action occurred',
				'Who made or carried out the decision',
				'What concrete harm, status change, or loss resulted',
			],
			'causation': [
				'The timing between the protected activity and the adverse action',
				'Facts showing the decision-maker knew about the protected activity',
				'Statements, sequence, or pattern facts linking the activity to the action',
			],
			'protected_trait': [
				'What protected trait or class applies to the complainant',
				'Facts showing the protected trait is relevant to the alleged conduct',
			],
			'discriminatory_motive': [
				'Facts suggesting bias, differential treatment, or discriminatory intent',
				'Who made biased statements or decisions',
				'Comparator, pattern, or context facts supporting discriminatory motive',
			],
			'employment_relationship': [
				'The employer or workplace relationship',
				'The complainant role, position, or workplace context',
			],
			'housing_context': [
				'The landlord, housing provider, or tenancy relationship',
				'The application, lease, or housing context',
			],
			'accommodation_request': [
				'What accommodation was requested',
				'When the request was made',
				'Who received the request',
			],
			'disability_or_need': [
				'The disability, limitation, or need for accommodation',
				'How that need was communicated or documented',
			],
			'denial_or_failure': [
				'How the request was denied, ignored, or only partially addressed',
				'Who denied or failed to act',
				'When the denial or failure occurred',
			],
			'termination_event': [
				'The termination or dismissal event',
				'When the termination occurred',
				'Who communicated or executed the termination',
			],
			'request_or_application': [
				'What request or application was made',
				'When it was submitted',
				'Who received it',
			],
			'denial_event': [
				'The denial or refusal event',
				'When the denial occurred',
				'Who made the decision',
			],
			'context_or_reason': [
				'The stated reason, criteria, or context around the denial',
				'Facts undermining or explaining that reason',
			],
		}
		bundle = bundle_map.get(normalized_element_id, [])
		if not bundle and normalized_claim_type == 'retaliation' and normalized_element_id == 'causation':
			bundle = bundle_map['causation']
		if bundle:
			return bundle
		fallback_label = str(element_text or normalized_element_id or 'claim element').strip()
		return [f'Facts establishing {fallback_label}']

	def _summarize_supported_fact_bundle(self, support_facts: Any) -> List[str]:
		supported: List[str] = []
		for fact in support_facts if isinstance(support_facts, list) else []:
			if not isinstance(fact, dict):
				continue
			text = self._normalize_intake_text(fact.get('text'))
			if text and text not in supported:
				supported.append(text)
		return supported[:4]

	def _resolve_task_preferred_support_kind(self, missing_support_kinds: List[str], evidence_classes: List[str]) -> str:
		normalized_missing = [str(kind or '').strip().lower() for kind in (missing_support_kinds or []) if str(kind or '').strip()]
		if 'evidence' in normalized_missing:
			return 'evidence'
		if 'authority' in normalized_missing:
			return 'authority'
		if any('testimony' in str(item or '').lower() for item in (evidence_classes or [])):
			return 'testimony'
		return normalized_missing[0] if normalized_missing else 'evidence'

	def _resolve_task_fallback_support_kinds(self, preferred_support_kind: str, evidence_classes: List[str]) -> List[str]:
		fallbacks: List[str] = []
		if preferred_support_kind != 'testimony' and any('testimony' in str(item or '').lower() for item in (evidence_classes or [])):
			fallbacks.append('testimony')
		if preferred_support_kind != 'evidence':
			fallbacks.append('evidence')
		if preferred_support_kind != 'authority':
			fallbacks.append('authority')
		return list(dict.fromkeys(fallbacks))

	def _recommended_task_queries(
		self,
		claim_type: str,
		element_label: str,
		missing_fact_bundle: List[str],
	) -> List[str]:
		queries: List[str] = []
		claim_phrase = str(claim_type or '').replace('_', ' ').strip()
		element_phrase = str(element_label or '').strip()
		if missing_fact_bundle:
			queries.append(f'"{claim_phrase}" "{element_phrase}" {missing_fact_bundle[0]}')
		if len(missing_fact_bundle) > 1:
			queries.append(f'"{element_phrase}" {missing_fact_bundle[1]} {claim_phrase}')
		queries.append(f'"{claim_phrase}" "{element_phrase}" supporting evidence')
		return [query for query in queries if query]

	def _default_preferred_support_kind(self, missing_support_kinds: List[str]) -> str:
		normalized = [
			str(kind or '').strip().lower()
			for kind in (missing_support_kinds or [])
			if str(kind or '').strip()
		]
		if 'evidence' in normalized:
			return 'evidence'
		if 'authority' in normalized:
			return 'authority'
		return normalized[0] if normalized else 'evidence'

	def _build_alignment_task_lookup(self) -> Dict[str, Dict[str, Any]]:
		lookup: Dict[str, Dict[str, Any]] = {}
		alignment_tasks = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_evidence_tasks') or []
		for task in alignment_tasks if isinstance(alignment_tasks, list) else []:
			if not isinstance(task, dict):
				continue
			claim_type = str(task.get('claim_type') or '').strip().lower()
			element_id = str(task.get('claim_element_id') or '').strip().lower()
			if not claim_type or not element_id:
				continue
			lookup[f'{claim_type}:{element_id}'] = task
		return lookup

	def _merge_alignment_task_preferences_into_follow_up_task(
		self,
		task: Dict[str, Any],
		alignment_lookup: Dict[str, Dict[str, Any]],
	) -> Dict[str, Any]:
		claim_type = str(task.get('claim_type') or '').strip().lower()
		element_id = str(task.get('claim_element_id') or '').strip().lower()
		alignment_task = alignment_lookup.get(f'{claim_type}:{element_id}', {}) if isinstance(alignment_lookup, dict) else {}
		if not isinstance(alignment_task, dict) or not alignment_task:
			task['preferred_support_kind'] = str(
				task.get('preferred_support_kind') or self._default_preferred_support_kind(task.get('missing_support_kinds', []))
			).strip().lower()
			return task

		preferred_support_kind = str(
			alignment_task.get('preferred_support_kind')
			or task.get('preferred_support_kind')
			or self._default_preferred_support_kind(task.get('missing_support_kinds', []))
		).strip().lower()
		task['preferred_support_kind'] = preferred_support_kind
		task['preferred_evidence_classes'] = list(alignment_task.get('preferred_evidence_classes', []) or task.get('preferred_evidence_classes', []) or [])
		task['fallback_support_kinds'] = list(alignment_task.get('fallback_support_kinds', []) or task.get('fallback_support_kinds', []) or [])
		task['missing_fact_bundle'] = list(alignment_task.get('missing_fact_bundle', []) or task.get('missing_fact_bundle', []) or [])
		task['satisfied_fact_bundle'] = list(alignment_task.get('satisfied_fact_bundle', []) or task.get('satisfied_fact_bundle', []) or [])
		task['intake_origin_refs'] = list(alignment_task.get('intake_origin_refs', []) or task.get('intake_origin_refs', []) or [])
		task['success_criteria'] = list(alignment_task.get('success_criteria', []) or task.get('success_criteria', []) or [])
		alignment_queries = [
			str(item).strip()
			for item in (alignment_task.get('recommended_queries') or [])
			if str(item).strip()
		]
		if alignment_queries:
			task['recommended_queries'] = alignment_queries
			queries = dict(task.get('queries') or {}) if isinstance(task.get('queries'), dict) else {}
			lane = 'authority' if preferred_support_kind == 'authority' else 'evidence'
			existing_queries = [
				str(item).strip()
				for item in (queries.get(lane) or [])
				if str(item).strip()
			]
			queries[lane] = list(dict.fromkeys(alignment_queries + existing_queries))
			task['queries'] = queries
		return task

	def _build_claim_support_packets(
		self,
		user_id: str = None,
		required_support_kinds: List[str] | None = None,
	) -> Dict[str, Any]:
		"""Build normalized evidence support packets from claim-support diagnostics."""
		resolved_user_id = user_id or self._current_user_id()
		intake_case_file = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
		candidate_claims = intake_case_file.get('candidate_claims', []) if isinstance(intake_case_file, dict) else []

		try:
			validation = self.get_claim_support_validation(
				user_id=resolved_user_id,
				required_support_kinds=required_support_kinds,
			)
		except Exception:
			validation = {'claims': {}}
		try:
			gaps = self.get_claim_support_gaps(
				user_id=resolved_user_id,
				required_support_kinds=required_support_kinds,
			)
		except Exception:
			gaps = {'claims': {}}

		validation_claims = validation.get('claims', {}) if isinstance(validation, dict) else {}
		gap_claims = gaps.get('claims', {}) if isinstance(gaps, dict) else {}
		claim_names = set(validation_claims.keys()) | set(gap_claims.keys())
		for candidate in candidate_claims:
			if isinstance(candidate, dict) and candidate.get('claim_type'):
				claim_names.add(str(candidate.get('claim_type')))

		packets: Dict[str, Any] = {}
		for claim_type in sorted(claim_names):
			validation_claim = validation_claims.get(claim_type, {}) if isinstance(validation_claims, dict) else {}
			gap_claim = gap_claims.get(claim_type, {}) if isinstance(gap_claims, dict) else {}
			elements = []
			validation_elements = validation_claim.get('elements', []) if isinstance(validation_claim, dict) else []
			if isinstance(validation_elements, list) and validation_elements:
				for element in validation_elements:
					if not isinstance(element, dict):
						continue
					gap_context = element.get('gap_context', {}) if isinstance(element.get('gap_context'), dict) else {}
					support_facts = gap_context.get('support_facts', []) if isinstance(gap_context, dict) else []
					support_traces = gap_context.get('support_traces', []) if isinstance(gap_context, dict) else []
					element_id = element.get('element_id')
					element_text = element.get('element_text')
					registry_entry = self._claim_element_registry_entry(intake_case_file, claim_type, element_id)
					evidence_classes = list(registry_entry.get('evidence_classes', []) or [])
					required_fact_bundle = self._required_fact_bundle_for_element(claim_type, element_id, element_text)
					satisfied_fact_bundle = self._summarize_supported_fact_bundle(support_facts)
					support_status = self._normalize_support_status(element.get('validation_status'))
					missing_fact_bundle = [] if support_status == 'supported' else list(required_fact_bundle)
					elements.append({
						'element_id': element_id,
						'element_text': element_text,
						'support_status': support_status,
						'canonical_fact_ids': [
							fact.get('fact_id') for fact in support_facts
							if isinstance(fact, dict) and fact.get('fact_id')
						],
						'supporting_artifact_ids': [
							trace.get('source_ref') for trace in support_traces
							if isinstance(trace, dict) and trace.get('source_ref')
						],
						'supporting_testimony_ids': [
							trace.get('support_ref') for trace in support_traces
							if isinstance(trace, dict) and str(trace.get('source_family') or '').lower() == 'testimony'
							and trace.get('support_ref')
						],
						'supporting_authority_ids': [
							trace.get('support_ref') for trace in support_traces
							if isinstance(trace, dict) and str(trace.get('source_family') or '').lower() == 'authority'
							and trace.get('support_ref')
						],
						'contrary_fact_ids': [
							fact_id
							for item in (element.get('contradiction_candidates', []) or [])
							if isinstance(item, dict)
							for fact_id in (item.get('fact_ids', []) or [])
							if fact_id
						],
						'missing_support_kinds': list(element.get('missing_support_kinds', []) or []),
						'preferred_evidence_classes': evidence_classes,
						'required_fact_bundle': required_fact_bundle,
						'satisfied_fact_bundle': satisfied_fact_bundle,
						'missing_fact_bundle': missing_fact_bundle,
						'parse_quality_flags': self._extract_parse_quality_flags(element),
						'recommended_next_step': str(element.get('recommended_action') or ''),
						'contradiction_count': int(element.get('contradiction_candidate_count', 0) or 0),
					})
			else:
				for gap_element in gap_claim.get('unresolved_elements', []) if isinstance(gap_claim, dict) else []:
					if not isinstance(gap_element, dict):
						continue
					element_id = gap_element.get('element_id')
					element_text = gap_element.get('element_text')
					registry_entry = self._claim_element_registry_entry(intake_case_file, claim_type, element_id)
					evidence_classes = list(registry_entry.get('evidence_classes', []) or [])
					required_fact_bundle = self._required_fact_bundle_for_element(claim_type, element_id, element_text)
					elements.append({
						'element_id': element_id,
						'element_text': element_text,
						'support_status': 'unsupported',
						'canonical_fact_ids': [
							fact.get('fact_id') for fact in (gap_element.get('support_facts', []) or [])
							if isinstance(fact, dict) and fact.get('fact_id')
						],
						'supporting_artifact_ids': [],
						'supporting_testimony_ids': [],
						'supporting_authority_ids': [],
						'contrary_fact_ids': [],
						'missing_support_kinds': list(gap_element.get('missing_support_kinds', []) or []),
						'preferred_evidence_classes': evidence_classes,
						'required_fact_bundle': required_fact_bundle,
						'satisfied_fact_bundle': [],
						'missing_fact_bundle': list(required_fact_bundle),
						'parse_quality_flags': [],
						'recommended_next_step': str(gap_element.get('recommended_action') or ''),
						'contradiction_count': 0,
					})
			packets[claim_type] = {
				'claim_type': claim_type,
				'overall_status': str(validation_claim.get('validation_status') or 'missing'),
				'elements': elements,
			}

		return packets

	def _normalize_support_status(self, validation_status: Any) -> str:
		status = str(validation_status or '').strip().lower()
		if status == 'supported':
			return 'supported'
		if status == 'incomplete':
			return 'partially_supported'
		if status == 'missing':
			return 'unsupported'
		if status == 'contradicted':
			return 'contradicted'
		return 'unsupported'

	def _extract_parse_quality_flags(self, element: Dict[str, Any]) -> List[str]:
		flags: List[str] = []
		if not isinstance(element, dict):
			return flags
		proof_diagnostics = element.get('proof_diagnostics', {})
		if isinstance(proof_diagnostics, dict):
			decision_source = str(proof_diagnostics.get('decision_source') or '').strip()
			if decision_source == 'low_quality_parse':
				flags.append('low_quality_parse')
		recommended_action = str(element.get('recommended_action') or '').strip()
		if recommended_action == 'improve_parse_quality' and 'improve_parse_quality' not in flags:
			flags.append('improve_parse_quality')
		return flags

	def _summarize_claim_support_packets(self, packets: Dict[str, Any]) -> Dict[str, Any]:
		summary = {
			'claim_count': 0,
			'element_count': 0,
			'status_counts': {
				'supported': 0,
				'partially_supported': 0,
				'unsupported': 0,
				'contradicted': 0,
			},
			'recommended_actions': [],
			'credible_support_ratio': 0.0,
			'draft_ready_element_ratio': 0.0,
			'proof_readiness_score': 0.0,
		}
		if not isinstance(packets, dict):
			return summary
		supported_count = 0
		partial_count = 0
		high_quality_supported_count = 0
		for packet in packets.values():
			if not isinstance(packet, dict):
				continue
			summary['claim_count'] += 1
			for element in packet.get('elements', []) or []:
				if not isinstance(element, dict):
					continue
				summary['element_count'] += 1
				status = str(element.get('support_status') or '').strip().lower()
				if status in summary['status_counts']:
					summary['status_counts'][status] += 1
				if status == 'supported':
					supported_count += 1
					parse_quality_flags = element.get('parse_quality_flags', [])
					if not (parse_quality_flags if isinstance(parse_quality_flags, list) else []):
						high_quality_supported_count += 1
				elif status == 'partially_supported':
					partial_count += 1
				next_step = str(element.get('recommended_next_step') or '').strip()
				if next_step and next_step not in summary['recommended_actions']:
					summary['recommended_actions'].append(next_step)
		if summary['element_count']:
			summary['credible_support_ratio'] = round((supported_count + partial_count) / summary['element_count'], 3)
			summary['draft_ready_element_ratio'] = round(supported_count / summary['element_count'], 3)
			high_quality_parse_ratio = high_quality_supported_count / summary['element_count']
			contradiction_penalty = 0.15 if summary['status_counts'].get('contradicted', 0) else 0.0
			summary['proof_readiness_score'] = round(
				max(0.0, min(1.0, (summary['credible_support_ratio'] * 0.45) + (summary['draft_ready_element_ratio'] * 0.4) + (high_quality_parse_ratio * 0.15) - contradiction_penalty)),
				3,
			)
		return summary

	def _summarize_question_candidates(self, candidates: Any) -> Dict[str, Any]:
		summary = {
			'count': 0,
			'candidates': [],
			'source_counts': {},
			'question_goal_counts': {},
			'phase1_section_counts': {},
			'blocking_level_counts': {},
		}
		if not isinstance(candidates, list):
			return summary

		summary['count'] = len(candidates)
		summary['candidates'] = candidates
		for candidate in candidates:
			if not isinstance(candidate, dict):
				continue
			explanation = candidate.get('ranking_explanation', {}) if isinstance(candidate.get('ranking_explanation'), dict) else {}
			source = str(explanation.get('candidate_source') or candidate.get('candidate_source') or '').strip()
			question_goal = str(explanation.get('question_goal') or candidate.get('question_goal') or '').strip()
			phase1_section = str(explanation.get('phase1_section') or candidate.get('phase1_section') or '').strip()
			blocking_level = str(explanation.get('blocking_level') or candidate.get('blocking_level') or '').strip()
			if source:
				summary['source_counts'][source] = summary['source_counts'].get(source, 0) + 1
			if question_goal:
				summary['question_goal_counts'][question_goal] = summary['question_goal_counts'].get(question_goal, 0) + 1
			if phase1_section:
				summary['phase1_section_counts'][phase1_section] = summary['phase1_section_counts'].get(phase1_section, 0) + 1
			if blocking_level:
				summary['blocking_level_counts'][blocking_level] = summary['blocking_level_counts'].get(blocking_level, 0) + 1
		return summary

	def _summarize_intake_matching_pressure(self, pressure_map: Any) -> Dict[str, Any]:
		summary = {
			'claim_count': 0,
			'claims': {},
			'total_missing_requirements': 0,
			'max_missing_requirements': 0,
			'average_matcher_confidence': 0.0,
		}
		if not isinstance(pressure_map, dict):
			return summary

		confidences: List[float] = []
		for claim_type, claim_data in pressure_map.items():
			if not isinstance(claim_data, dict):
				continue
			missing_count = int(claim_data.get('missing_requirement_count', 0) or 0)
			matcher_confidence = float(claim_data.get('matcher_confidence', 0.0) or 0.0)
			summary['claim_count'] += 1
			summary['total_missing_requirements'] += missing_count
			summary['max_missing_requirements'] = max(summary['max_missing_requirements'], missing_count)
			confidences.append(matcher_confidence)
			summary['claims'][str(claim_type)] = {
				'missing_requirement_count': missing_count,
				'matcher_confidence': matcher_confidence,
				'legal_requirements': int(claim_data.get('legal_requirements', 0) or 0),
				'satisfied_requirements': int(claim_data.get('satisfied_requirements', 0) or 0),
				'missing_requirement_names': list(claim_data.get('missing_requirement_names') or []),
				'missing_requirement_element_ids': list(claim_data.get('missing_requirement_element_ids') or []),
			}
		if confidences:
			summary['average_matcher_confidence'] = sum(confidences) / len(confidences)
		return summary

	def _summarize_intake_legal_targeting(
		self,
		pressure_map: Any,
		candidates: Any,
	) -> Dict[str, Any]:
		summary = {
			'claim_count': 0,
			'total_open_elements': 0,
			'mapped_question_count': 0,
			'unmapped_claim_count': 0,
			'claims': {},
		}
		if not isinstance(pressure_map, dict):
			return summary

		normalized_candidates = candidates if isinstance(candidates, list) else []
		for claim_type, claim_data in pressure_map.items():
			if not isinstance(claim_data, dict):
				continue
			missing_element_ids = [
				str(item).strip().lower()
				for item in (claim_data.get('missing_requirement_element_ids') or [])
				if str(item).strip()
			]
			missing_requirement_names = [
				str(item).strip()
				for item in (claim_data.get('missing_requirement_names') or [])
				if str(item).strip()
			]
			mapped_candidates: List[Dict[str, Any]] = []
			mapped_element_ids: List[str] = []
			for candidate in normalized_candidates:
				if not isinstance(candidate, dict):
					continue
				explanation = candidate.get('ranking_explanation', {}) if isinstance(candidate.get('ranking_explanation'), dict) else {}
				selector_signals = candidate.get('selector_signals', {}) if isinstance(candidate.get('selector_signals'), dict) else {}
				target_claim_type = str(
					explanation.get('target_claim_type')
					or candidate.get('target_claim_type')
					or ''
				).strip().lower()
				if target_claim_type and target_claim_type != str(claim_type).strip().lower():
					continue
				target_element_id = str(
					explanation.get('target_element_id')
					or candidate.get('target_element_id')
					or ''
				).strip().lower()
				direct_match = bool(selector_signals.get('direct_legal_target_match'))
				if not direct_match and target_element_id not in missing_element_ids:
					continue
				if target_element_id and target_element_id not in mapped_element_ids:
					mapped_element_ids.append(target_element_id)
				mapped_candidates.append(
					{
						'question': str(candidate.get('question') or '').strip(),
						'type': str(candidate.get('type') or '').strip(),
						'question_goal': str(
							explanation.get('question_goal')
							or candidate.get('question_goal')
							or ''
						).strip(),
						'candidate_source': str(
							explanation.get('candidate_source')
							or candidate.get('candidate_source')
							or ''
						).strip(),
						'target_element_id': target_element_id,
						'blocking_level': str(
							explanation.get('blocking_level')
							or candidate.get('blocking_level')
							or ''
						).strip(),
						'direct_legal_target_match': direct_match,
						'selector_score': float(candidate.get('selector_score', 0.0) or 0.0),
					}
				)
			unmapped_element_ids = [
				element_id
				for element_id in missing_element_ids
				if element_id not in mapped_element_ids
			]
			summary['claim_count'] += 1
			summary['total_open_elements'] += len(missing_element_ids)
			summary['mapped_question_count'] += len(mapped_candidates)
			if not mapped_candidates:
				summary['unmapped_claim_count'] += 1
			summary['claims'][str(claim_type)] = {
				'missing_requirement_count': int(claim_data.get('missing_requirement_count', 0) or 0),
				'matcher_confidence': float(claim_data.get('matcher_confidence', 0.0) or 0.0),
				'missing_requirement_names': missing_requirement_names,
				'missing_requirement_element_ids': missing_element_ids,
				'mapped_candidates': mapped_candidates,
				'unmapped_element_ids': unmapped_element_ids,
			}
		return summary

	def _summarize_intake_evidence_alignment(
		self,
		intake_case_file: Any,
		claim_support_packets: Any,
	) -> Dict[str, Any]:
		summary = {
			'claim_count': 0,
			'aligned_element_count': 0,
			'unsupported_shared_count': 0,
			'claims': {},
		}
		intake_case = intake_case_file if isinstance(intake_case_file, dict) else {}
		packets = claim_support_packets if isinstance(claim_support_packets, dict) else {}
		candidate_claims = intake_case.get('candidate_claims', []) if isinstance(intake_case.get('candidate_claims'), list) else []
		proof_leads = intake_case.get('proof_leads', []) if isinstance(intake_case.get('proof_leads'), list) else []
		open_items = intake_case.get('open_items', []) if isinstance(intake_case.get('open_items'), list) else []

		claim_types = set(packets.keys())
		for claim in candidate_claims:
			if isinstance(claim, dict) and claim.get('claim_type'):
				claim_types.add(str(claim.get('claim_type')))

		for claim_type in sorted(claim_types):
			candidate = next(
				(
					item for item in candidate_claims
					if isinstance(item, dict) and str(item.get('claim_type') or '') == str(claim_type)
				),
				{},
			)
			required_elements = candidate.get('required_elements', []) if isinstance(candidate, dict) else []
			intake_elements = []
			for element in required_elements:
				if not isinstance(element, dict):
					continue
				element_id = str(element.get('element_id') or '').strip()
				if not element_id:
					continue
				intake_elements.append(
					{
						'element_id': element_id,
						'label': str(element.get('label') or element_id).strip(),
						'blocking': bool(element.get('blocking', True)),
						'evidence_classes': list(element.get('evidence_classes', []) or []),
					}
				)
			intake_element_ids = [item['element_id'] for item in intake_elements]

			packet = packets.get(claim_type, {}) if isinstance(packets, dict) else {}
			packet_elements = packet.get('elements', []) if isinstance(packet, dict) else []
			packet_status_by_element: Dict[str, str] = {}
			packet_element_map: Dict[str, Dict[str, Any]] = {}
			for element in packet_elements if isinstance(packet_elements, list) else []:
				if not isinstance(element, dict):
					continue
				element_id = str(element.get('element_id') or '').strip()
				if not element_id:
					continue
				packet_status_by_element[element_id] = str(element.get('support_status') or '').strip().lower()
				packet_element_map[element_id] = element

			shared_elements = []
			for intake_element in intake_elements:
				element_id = intake_element['element_id']
				if element_id not in packet_status_by_element:
					continue
				support_status = packet_status_by_element[element_id]
				packet_element = packet_element_map.get(element_id, {}) if isinstance(packet_element_map.get(element_id), dict) else {}
				matching_open_item_ids = [
					str(item.get('open_item_id') or '')
					for item in open_items
					if isinstance(item, dict)
					and str(item.get('target_claim_type') or '').strip().lower() == str(claim_type).strip().lower()
					and str(item.get('target_element_id') or '').strip().lower() == element_id.lower()
				]
				matching_proof_lead_ids = [
					str(lead.get('lead_id') or '')
					for lead in proof_leads
					if isinstance(lead, dict)
					and (
						element_id.lower() in [str(item).strip().lower() for item in (lead.get('element_targets') or []) if str(item).strip()]
					)
				]
				shared_elements.append(
					{
						'element_id': element_id,
						'label': intake_element['label'],
						'blocking': intake_element['blocking'],
						'support_status': support_status,
						'preferred_evidence_classes': list(packet_element.get('preferred_evidence_classes', []) or intake_element.get('evidence_classes', []) or []),
						'required_fact_bundle': list(packet_element.get('required_fact_bundle', []) or []),
						'satisfied_fact_bundle': list(packet_element.get('satisfied_fact_bundle', []) or []),
						'missing_fact_bundle': list(packet_element.get('missing_fact_bundle', []) or []),
						'missing_support_kinds': list(packet_element.get('missing_support_kinds', []) or []),
						'recommended_next_step': str(packet_element.get('recommended_next_step') or '').strip(),
						'intake_open_item_ids': [item_id for item_id in matching_open_item_ids if item_id],
						'intake_proof_lead_ids': [lead_id for lead_id in matching_proof_lead_ids if lead_id],
					}
				)
				summary['aligned_element_count'] += 1
				if support_status in {'unsupported', 'contradicted', 'partially_supported'}:
					summary['unsupported_shared_count'] += 1

			evidence_only_element_ids = [
				element_id
				for element_id in packet_status_by_element
				if element_id not in intake_element_ids
			]
			intake_only_element_ids = [
				element_id
				for element_id in intake_element_ids
				if element_id not in packet_status_by_element
			]
			summary['claim_count'] += 1
			summary['claims'][str(claim_type)] = {
				'intake_required_element_ids': intake_element_ids,
				'packet_element_statuses': packet_status_by_element,
				'shared_elements': shared_elements,
				'intake_only_element_ids': intake_only_element_ids,
				'evidence_only_element_ids': evidence_only_element_ids,
			}
		return summary

	def _build_alignment_evidence_tasks(self, alignment_summary: Any) -> List[Dict[str, Any]]:
		tasks: List[Dict[str, Any]] = []
		if not isinstance(alignment_summary, dict):
			return tasks
		claims = alignment_summary.get('claims', {})
		if not isinstance(claims, dict):
			return tasks

		for claim_type, claim_data in claims.items():
			if not isinstance(claim_data, dict):
				continue
			for element in claim_data.get('shared_elements', []) or []:
				if not isinstance(element, dict):
					continue
				support_status = str(element.get('support_status') or '').strip().lower()
				if support_status not in {'unsupported', 'partially_supported', 'contradicted'}:
					continue
				action = 'resolve_support_conflicts' if support_status == 'contradicted' else 'fill_evidence_gaps'
				claim_element_id = str(element.get('element_id') or '').strip()
				claim_element_label = str(element.get('label') or element.get('element_id') or '').strip()
				preferred_evidence_classes = list(element.get('preferred_evidence_classes', []) or [])
				missing_fact_bundle = list(element.get('missing_fact_bundle', []) or [])
				satisfied_fact_bundle = list(element.get('satisfied_fact_bundle', []) or [])
				missing_support_kinds = list(element.get('missing_support_kinds', []) or [])
				preferred_support_kind = self._resolve_task_preferred_support_kind(missing_support_kinds, preferred_evidence_classes)
				fallback_support_kinds = self._resolve_task_fallback_support_kinds(preferred_support_kind, preferred_evidence_classes)
				source_quality_target = 'credible_testimony' if preferred_support_kind == 'testimony' else 'high_quality_document'
				task_priority = 'high' if support_status == 'contradicted' or bool(element.get('blocking', False)) else 'medium'
				success_criteria = [
					f'Element {claim_element_label} reaches supported status',
				]
				if missing_fact_bundle:
					success_criteria.append(f'Collect support addressing: {missing_fact_bundle[0]}')
				recommended_witness_prompts = [
					f'Who can give first-hand testimony about {bundle_item} for {claim_element_label}?'
					for bundle_item in missing_fact_bundle[:2]
				]
				resolution_status = self._derive_alignment_task_resolution_status(
					support_status,
					missing_fact_bundle,
				)
				tasks.append(
					{
						'task_id': f'{claim_type}:{claim_element_id}:{action}',
						'action': action,
						'claim_type': str(claim_type),
						'claim_element_id': claim_element_id,
						'claim_element_label': claim_element_label,
						'support_status': support_status,
						'blocking': bool(element.get('blocking', False)),
						'preferred_support_kind': preferred_support_kind,
						'preferred_evidence_classes': preferred_evidence_classes,
						'fallback_support_kinds': fallback_support_kinds,
						'source_quality_target': source_quality_target,
						'task_priority': task_priority,
						'missing_fact_bundle': missing_fact_bundle,
						'satisfied_fact_bundle': satisfied_fact_bundle,
						'intake_origin_refs': [
							f'open_item:{item_id}'
							for item_id in (element.get('intake_open_item_ids', []) or [])
						] + [
							f'proof_lead:{lead_id}'
							for lead_id in (element.get('intake_proof_lead_ids', []) or [])
						],
						'recommended_queries': self._recommended_task_queries(
							str(claim_type),
							claim_element_label,
							missing_fact_bundle,
						),
						'recommended_witness_prompts': recommended_witness_prompts,
						'success_criteria': success_criteria,
						'resolution_status': resolution_status,
					}
				)

		tasks.sort(
			key=lambda task: (
				0 if task.get('support_status') == 'contradicted' else 1,
				0 if task.get('blocking') else 1,
				str(task.get('claim_type') or ''),
				str(task.get('claim_element_id') or ''),
			)
		)
		return tasks

	def _derive_alignment_task_resolution_status(
		self,
		support_status: Any,
		missing_fact_bundle: Any,
	) -> str:
		normalized_support_status = str(support_status or '').strip().lower()
		missing_bundle = [
			str(item).strip()
			for item in (missing_fact_bundle if isinstance(missing_fact_bundle, list) else [])
			if str(item).strip()
		]
		if normalized_support_status == 'contradicted':
			return 'needs_manual_review'
		if normalized_support_status == 'partially_supported':
			return 'partially_addressed'
		if normalized_support_status == 'supported' and not missing_bundle:
			return 'resolved_supported'
		return 'still_open'

	def _alignment_packet_status_map(self, claim_support_packets: Any) -> Dict[tuple, Dict[str, Any]]:
		status_map: Dict[tuple, Dict[str, Any]] = {}
		if not isinstance(claim_support_packets, dict):
			return status_map
		for claim_type, packet in claim_support_packets.items():
			if not isinstance(packet, dict):
				continue
			for element in packet.get('elements', []) or []:
				if not isinstance(element, dict):
					continue
				element_id = str(element.get('element_id') or '').strip()
				if not element_id:
					continue
				status_map[(str(claim_type), element_id)] = element
		return status_map

	def _summarize_alignment_task_updates(
		self,
		prior_tasks: Any,
		refreshed_tasks: Any,
		claim_support_packets: Any,
		evidence_data: Dict[str, Any],
	) -> List[Dict[str, Any]]:
		updates: List[Dict[str, Any]] = []
		previous_tasks = [dict(task) for task in (prior_tasks if isinstance(prior_tasks, list) else []) if isinstance(task, dict)]
		current_tasks = [dict(task) for task in (refreshed_tasks if isinstance(refreshed_tasks, list) else []) if isinstance(task, dict)]
		if not previous_tasks and not current_tasks:
			return updates

		current_task_map = {
			(str(task.get('claim_type') or ''), str(task.get('claim_element_id') or '')): task
			for task in current_tasks
			if str(task.get('claim_type') or '').strip() and str(task.get('claim_element_id') or '').strip()
		}
		packet_status_map = self._alignment_packet_status_map(claim_support_packets)
		seen_keys = set()
		artifact_id = evidence_data.get('artifact_id') or evidence_data.get('cid') or evidence_data.get('id')

		for prior_task in previous_tasks:
			claim_type = str(prior_task.get('claim_type') or '').strip()
			claim_element_id = str(prior_task.get('claim_element_id') or '').strip()
			if not claim_type or not claim_element_id:
				continue
			key = (claim_type, claim_element_id)
			seen_keys.add(key)
			current_task = current_task_map.get(key)
			packet_element = packet_status_map.get(key, {}) if isinstance(packet_status_map.get(key), dict) else {}
			current_support_status = str(
				(current_task or {}).get('support_status')
				or packet_element.get('support_status')
				or prior_task.get('support_status')
				or ''
			).strip().lower()
			current_missing_fact_bundle = list(
				(current_task or {}).get('missing_fact_bundle')
				or packet_element.get('missing_fact_bundle')
				or []
			)
			previous_missing_fact_bundle = list(prior_task.get('missing_fact_bundle') or [])
			resolution_status = self._derive_alignment_task_resolution_status(
				current_support_status,
				current_missing_fact_bundle,
			)
			if resolution_status == 'still_open' and len(current_missing_fact_bundle) < len(previous_missing_fact_bundle):
				resolution_status = 'partially_addressed'
			status = 'resolved' if resolution_status == 'resolved_supported' and current_task is None else 'active'
			updates.append(
				{
					'task_id': str(prior_task.get('task_id') or f'{claim_type}:{claim_element_id}'),
					'claim_type': claim_type,
					'claim_element_id': claim_element_id,
					'action': str(prior_task.get('action') or ''),
					'previous_support_status': str(prior_task.get('support_status') or '').strip().lower(),
					'current_support_status': current_support_status,
					'previous_missing_fact_bundle': previous_missing_fact_bundle,
					'current_missing_fact_bundle': current_missing_fact_bundle,
					'resolution_status': resolution_status,
					'status': status,
					'evidence_artifact_id': artifact_id,
				}
			)

		for current_task in current_tasks:
			claim_type = str(current_task.get('claim_type') or '').strip()
			claim_element_id = str(current_task.get('claim_element_id') or '').strip()
			key = (claim_type, claim_element_id)
			if not claim_type or not claim_element_id or key in seen_keys:
				continue
			updates.append(
				{
					'task_id': str(current_task.get('task_id') or f'{claim_type}:{claim_element_id}'),
					'claim_type': claim_type,
					'claim_element_id': claim_element_id,
					'action': str(current_task.get('action') or ''),
					'previous_support_status': '',
					'current_support_status': str(current_task.get('support_status') or '').strip().lower(),
					'previous_missing_fact_bundle': [],
					'current_missing_fact_bundle': list(current_task.get('missing_fact_bundle') or []),
					'resolution_status': str(current_task.get('resolution_status') or 'still_open'),
					'status': 'active',
					'evidence_artifact_id': artifact_id,
				}
			)

		updates.sort(
			key=lambda update: (
				0 if update.get('status') == 'resolved' else 1,
				str(update.get('claim_type') or ''),
				str(update.get('claim_element_id') or ''),
			)
		)
		return updates

	def _merge_alignment_task_update_history(
		self,
		existing_history: Any,
		updates: Any,
		*,
		evidence_sequence: int,
		max_entries: int = ALIGNMENT_TASK_UPDATE_HISTORY_LIMIT,
	) -> List[Dict[str, Any]]:
		history = [
			dict(entry)
			for entry in (existing_history if isinstance(existing_history, list) else [])
			if isinstance(entry, dict)
		]
		new_updates = [
			{
				**dict(update),
				'evidence_sequence': int(evidence_sequence),
			}
			for update in (updates if isinstance(updates, list) else [])
			if isinstance(update, dict)
		]
		if not new_updates:
			return history[-max_entries:] if max_entries > 0 else []
		merged = history + new_updates
		return merged[-max_entries:] if max_entries > 0 else merged

	def _retire_answered_alignment_evidence_tasks(
		self,
		question: Dict[str, Any],
		answer: str,
		tasks: Any,
	) -> List[Dict[str, Any]]:
		remaining_tasks = [
			dict(task)
			for task in (tasks if isinstance(tasks, list) else [])
			if isinstance(task, dict)
		]
		if not answer or not str(answer).strip():
			return remaining_tasks
		context = question.get('context', {}) if isinstance(question, dict) else {}
		if not isinstance(context, dict) or not context.get('alignment_task'):
			return remaining_tasks

		target_claim_type = str(context.get('claim_type') or '').strip().lower()
		target_element_id = str(context.get('claim_element_id') or '').strip().lower()
		if not target_claim_type and not target_element_id:
			return remaining_tasks

		filtered_tasks: List[Dict[str, Any]] = []
		for task in remaining_tasks:
			task_claim_type = str(task.get('claim_type') or '').strip().lower()
			task_element_id = str(task.get('claim_element_id') or '').strip().lower()
			matches_claim = not target_claim_type or task_claim_type == target_claim_type
			matches_element = not target_element_id or task_element_id == target_element_id
			if matches_claim and matches_element:
				continue
			filtered_tasks.append(task)
		return filtered_tasks

	def _build_answered_alignment_task_updates(
		self,
		prior_tasks: Any,
		remaining_tasks: Any,
		question: Dict[str, Any],
		answer: str,
	) -> List[Dict[str, Any]]:
		updates: List[Dict[str, Any]] = []
		if not answer or not str(answer).strip():
			return updates
		context = question.get('context', {}) if isinstance(question, dict) else {}
		if not isinstance(context, dict) or not context.get('alignment_task'):
			return updates

		target_claim_type = str(context.get('claim_type') or '').strip().lower()
		target_element_id = str(context.get('claim_element_id') or '').strip().lower()
		if not target_claim_type and not target_element_id:
			return updates

		remaining_keys = {
			(
				str(task.get('claim_type') or '').strip().lower(),
				str(task.get('claim_element_id') or '').strip().lower(),
			)
			for task in (remaining_tasks if isinstance(remaining_tasks, list) else [])
			if isinstance(task, dict)
		}
		answer_preview = self._normalize_intake_text(answer)[:160]

		for task in (prior_tasks if isinstance(prior_tasks, list) else []):
			if not isinstance(task, dict):
				continue
			task_claim_type = str(task.get('claim_type') or '').strip().lower()
			task_element_id = str(task.get('claim_element_id') or '').strip().lower()
			key = (task_claim_type, task_element_id)
			matches_claim = not target_claim_type or task_claim_type == target_claim_type
			matches_element = not target_element_id or task_element_id == target_element_id
			if not (matches_claim and matches_element):
				continue
			if key in remaining_keys:
				continue
			updates.append(
				{
					'task_id': str(task.get('task_id') or f'{task_claim_type}:{task_element_id}'),
					'claim_type': str(task.get('claim_type') or ''),
					'claim_element_id': str(task.get('claim_element_id') or ''),
					'action': str(task.get('action') or ''),
					'previous_support_status': str(task.get('support_status') or '').strip().lower(),
					'current_support_status': str(task.get('support_status') or '').strip().lower(),
					'previous_missing_fact_bundle': list(task.get('missing_fact_bundle') or []),
					'current_missing_fact_bundle': list(task.get('missing_fact_bundle') or []),
					'resolution_status': 'answered_pending_review',
					'status': 'resolved',
					'evidence_artifact_id': '',
					'answer_preview': answer_preview,
				}
			)
		return updates

	def _promote_alignment_task_update(
		self,
		*,
		claim_type: str,
		claim_element_id: str,
		promotion_kind: str,
		promotion_ref: str = '',
		answer_preview: str = '',
	) -> Dict[str, Any] | None:
		current_updates = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_updates') or []
		history = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_update_history') or []
		normalized_claim_type = str(claim_type or '').strip().lower()
		normalized_element_id = str(claim_element_id or '').strip().lower()
		if not normalized_claim_type or not normalized_element_id:
			return None

		matched_update = None
		retained_updates: List[Dict[str, Any]] = []
		for update in current_updates if isinstance(current_updates, list) else []:
			if not isinstance(update, dict):
				continue
			update_claim_type = str(update.get('claim_type') or '').strip().lower()
			update_element_id = str(update.get('claim_element_id') or '').strip().lower()
			resolution_status = str(update.get('resolution_status') or '').strip().lower()
			if (
				update_claim_type == normalized_claim_type
				and update_element_id == normalized_element_id
				and resolution_status == 'answered_pending_review'
				and matched_update is None
			):
				matched_update = dict(update)
				continue
			retained_updates.append(dict(update))

		if matched_update is None:
			for update in reversed(history if isinstance(history, list) else []):
				if not isinstance(update, dict):
					continue
				update_claim_type = str(update.get('claim_type') or '').strip().lower()
				update_element_id = str(update.get('claim_element_id') or '').strip().lower()
				resolution_status = str(update.get('resolution_status') or '').strip().lower()
				if (
					update_claim_type == normalized_claim_type
					and update_element_id == normalized_element_id
					and resolution_status == 'answered_pending_review'
				):
					matched_update = dict(update)
					break

		if matched_update is None:
			return None

		promoted_update = {
			**matched_update,
			'resolution_status': f'promoted_to_{promotion_kind}',
			'status': 'resolved',
			'current_support_status': str(matched_update.get('current_support_status') or '').strip().lower(),
			'promotion_kind': promotion_kind,
			'promotion_ref': str(promotion_ref or '').strip(),
			'answer_preview': str(answer_preview or matched_update.get('answer_preview') or '').strip(),
		}
		last_sequence = 0
		for entry in history if isinstance(history, list) else []:
			if not isinstance(entry, dict):
				continue
			try:
				last_sequence = max(last_sequence, int(entry.get('evidence_sequence', 0) or 0))
			except (TypeError, ValueError):
				continue
		updated_history = self._merge_alignment_task_update_history(
			history,
			[promoted_update],
			evidence_sequence=last_sequence + 1,
		)
		self.phase_manager.update_phase_data(
			ComplaintPhase.EVIDENCE,
			'alignment_task_updates',
			[promoted_update] + retained_updates,
		)
		self.phase_manager.update_phase_data(
			ComplaintPhase.EVIDENCE,
			'alignment_task_update_history',
			updated_history,
		)
		return promoted_update

	def _classify_evidence_ingestion_outcomes(
		self,
		evidence_data: Dict[str, Any],
		projection_summary: Dict[str, Any],
		claim_support_packets: Dict[str, Any],
	) -> List[str]:
		"""Classify the main evidence-ingestion outcomes for downstream consumers."""
		outcomes: List[str] = []

		if bool(evidence_data.get('record_reused')) and not projection_summary.get('graph_changed', False):
			outcomes.append('duplicates_existing_support')
		elif projection_summary.get('graph_changed', False) or bool(evidence_data.get('support_link_created')):
			outcomes.append('corroborates_fact')

		if bool(evidence_data.get('contradicts_existing_fact')):
			outcomes.append('contradicts_fact')
		if bool(evidence_data.get('creates_new_fact')):
			outcomes.append('creates_new_fact')

		packet_summary = self._summarize_claim_support_packets(claim_support_packets)
		if packet_summary['status_counts'].get('contradicted', 0) > 0 and 'contradicts_fact' not in outcomes:
			outcomes.append('contradicts_fact')

		parse_quality_flag_found = False
		if isinstance(claim_support_packets, dict):
			for packet in claim_support_packets.values():
				if not isinstance(packet, dict):
					continue
				for element in packet.get('elements', []) or []:
					if not isinstance(element, dict):
						continue
					flags = element.get('parse_quality_flags', []) or []
					if flags:
						parse_quality_flag_found = True
						break
				if parse_quality_flag_found:
					break
		if parse_quality_flag_found:
			outcomes.append('insufficiently_parsed')

		if not outcomes:
			outcomes.append('corroborates_fact')
		return outcomes
	
	def advance_to_evidence_phase(self) -> Dict[str, Any]:
		"""
		Advance to Phase 2: Evidence gathering.
		
		Returns:
			Status of evidence phase initiation
		"""
		if not self.phase_manager.advance_to_phase(ComplaintPhase.EVIDENCE):
			return {
				'error': 'Cannot advance to evidence phase. Complete intake first.',
				'current_phase': self.phase_manager.get_current_phase().value
			}
		
		kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
		dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
		
		# Identify evidence gaps
		unsatisfied = dg.find_unsatisfied_requirements()
		kg_gaps = kg.find_gaps()
		
		# Store in evidence phase data
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gaps', unsatisfied)
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'knowledge_gaps', kg_gaps)
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_count', 0)
		claim_support_packets = self._build_claim_support_packets()
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'claim_support_packets', claim_support_packets)
		intake_case_file = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
		alignment_summary = self._summarize_intake_evidence_alignment(intake_case_file, claim_support_packets)
		alignment_tasks = self._build_alignment_evidence_tasks(alignment_summary)
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'intake_evidence_alignment_summary', alignment_summary)
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'alignment_evidence_tasks', alignment_tasks)
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_updates', [])
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_update_history', [])
		
		return {
			'phase': ComplaintPhase.EVIDENCE.value,
			'evidence_gaps': len(unsatisfied),
			'knowledge_gaps': len(kg_gaps),
			'claim_support_packets': claim_support_packets,
			'intake_evidence_alignment_summary': alignment_summary,
			'alignment_evidence_tasks': alignment_tasks,
			'suggested_evidence_types': self._suggest_evidence_types(unsatisfied, kg_gaps),
			'next_action': self.phase_manager.get_next_action()
		}

	def _find_claim_entities_for_type(self, kg, claim_type: str = None):
		"""Find claim entities in the intake knowledge graph matching a claim type."""
		if not kg:
			return []
		claim_entities = kg.get_entities_by_type('claim')
		if not claim_type:
			return claim_entities
		normalized = ''.join(ch.lower() if ch.isalnum() else '_' for ch in claim_type).strip('_')
		matches = []
		for entity in claim_entities:
			entity_claim_type = str(entity.attributes.get('claim_type', '')).strip().lower()
			entity_normalized = ''.join(ch.lower() if ch.isalnum() else '_' for ch in entity_claim_type).strip('_')
			entity_name = str(entity.name or '').lower()
			if entity_normalized == normalized or entity_claim_type == claim_type.lower() or claim_type.lower() in entity_name:
				matches.append(entity)
		return matches

	def _project_document_graph_to_knowledge_graph(self, kg, evidence_data: Dict[str, Any]) -> Dict[str, Any]:
		"""Project persisted document-graph entities/edges into the complaint knowledge graph."""
		if not kg:
			return {'projected': False, 'entity_count': 0, 'relationship_count': 0, 'claim_links': 0}

		from complaint_phases.knowledge_graph import Entity, Relationship

		document_graph = evidence_data.get('document_graph') or {}
		if not isinstance(document_graph, dict):
			document_graph = {}

		inserted_entities = 0
		inserted_relationships = 0
		claim_links = 0
		entity_id_map = {}

		for graph_entity in document_graph.get('entities', []) or []:
			graph_entity_id = graph_entity.get('id')
			if not graph_entity_id:
				continue
			entity_type = graph_entity.get('type') or 'fact'
			mapped_type = 'evidence' if entity_type == 'artifact' else entity_type
			entity_id_map[graph_entity_id] = graph_entity_id
			if graph_entity_id in kg.entities:
				continue
			kg.add_entity(Entity(
				id=graph_entity_id,
				type=mapped_type,
				name=graph_entity.get('name') or mapped_type.title(),
				attributes=graph_entity.get('attributes', {}),
				confidence=graph_entity.get('confidence', 0.6),
				source='evidence',
			))
			inserted_entities += 1

		for graph_relationship in document_graph.get('relationships', []) or []:
			relationship_id = graph_relationship.get('id')
			if not relationship_id or relationship_id in kg.relationships:
				continue
			source_id = entity_id_map.get(graph_relationship.get('source_id'), graph_relationship.get('source_id'))
			target_id = entity_id_map.get(graph_relationship.get('target_id'), graph_relationship.get('target_id'))
			if not source_id or not target_id:
				continue
			if source_id not in kg.entities or target_id not in kg.entities:
				continue
			kg.add_relationship(Relationship(
				id=relationship_id,
				source_id=source_id,
				target_id=target_id,
				relation_type=graph_relationship.get('relation_type') or 'related_to',
				attributes=graph_relationship.get('attributes', {}),
				confidence=graph_relationship.get('confidence', 0.6),
				source='evidence',
			))
			inserted_relationships += 1

		artifact_id = evidence_data.get('artifact_id') or evidence_data.get('cid')
		claim_entities = self._find_claim_entities_for_type(kg, evidence_data.get('claim_type'))
		if artifact_id and artifact_id in kg.entities:
			for claim_entity in claim_entities:
				rel_id = f"rel_{claim_entity.id}_{artifact_id}_supported_by"
				if rel_id in kg.relationships:
					continue
				kg.add_relationship(Relationship(
					id=rel_id,
					source_id=claim_entity.id,
					target_id=artifact_id,
					relation_type='supported_by',
					attributes={
						'claim_type': evidence_data.get('claim_type'),
						'claim_element_id': evidence_data.get('claim_element_id'),
					},
					confidence=0.75,
					source='evidence',
				))
				inserted_relationships += 1
				claim_links += 1

		return {
			'projected': True,
			'entity_count': inserted_entities,
			'relationship_count': inserted_relationships,
			'claim_links': claim_links,
		}
	
	def add_evidence_to_graphs(self, evidence_data: Dict[str, Any]) -> Dict[str, Any]:
		"""
		Add evidence to knowledge and dependency graphs in Phase 2.
		
		Args:
			evidence_data: Evidence information including type, description, claim support
			
		Returns:
			Updated graph status
		"""
		kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
		dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
		projection_summary = {
			'projected': False,
			'graph_changed': False,
			'entity_count': 0,
			'relationship_count': 0,
			'claim_links': 0,
			'artifact_entity_added': False,
			'artifact_entity_already_present': False,
			'storage_record_created': bool(evidence_data.get('record_created', False)),
			'storage_record_reused': bool(evidence_data.get('record_reused', False)),
			'support_link_created': bool(evidence_data.get('support_link_created', False)),
			'support_link_reused': bool(evidence_data.get('support_link_reused', False)),
		}
		artifact_id = evidence_data.get('artifact_id') or evidence_data.get('cid') or f"evidence_{evidence_data.get('id', 'unknown')}"
		artifact_present_before_projection = bool(kg and artifact_id in kg.entities)
		if evidence_data.get('document_graph'):
			projection_summary.update(self._project_document_graph_to_knowledge_graph(kg, evidence_data))
		
		# Add evidence entity to knowledge graph
		from complaint_phases.knowledge_graph import Entity
		projection_summary['artifact_entity_already_present'] = artifact_present_before_projection
		if kg and artifact_id not in kg.entities:
			evidence_entity = Entity(
				id=artifact_id,
				type='evidence',
				name=evidence_data.get('name', evidence_data.get('description', 'Evidence')),
				attributes=evidence_data,
				confidence=evidence_data.get('confidence', 0.8),
				source='evidence'
			)
			kg.add_entity(evidence_entity)
			projection_summary['entity_count'] += 1
		if kg and not artifact_present_before_projection and artifact_id in kg.entities:
			projection_summary['artifact_entity_added'] = True
		
		# Add supporting relationships
		supported_claim_ids = evidence_data.get('supports_claims', [])
		from complaint_phases.knowledge_graph import Relationship
		if kg:
			for claim_id in supported_claim_ids:
				rel_id = f"rel_{artifact_id}_{claim_id}"
				if rel_id in kg.relationships:
					continue
				rel = Relationship(
					id=rel_id,
					source_id=artifact_id,
					target_id=claim_id,
					relation_type='supports',
					confidence=evidence_data.get('relevance', 0.7),
					source='evidence'
				)
				kg.add_relationship(rel)
				projection_summary['relationship_count'] += 1
		graph_changed = projection_summary['entity_count'] > 0 or projection_summary['relationship_count'] > 0
		graph_snapshot_payload = evidence_data.get('document_graph') if isinstance(evidence_data.get('document_graph'), dict) else {
			'status': 'projected-knowledge-graph' if graph_changed or artifact_present_before_projection else 'unavailable',
			'source_id': artifact_id,
			'entities': [],
			'relationships': [],
			'metadata': {
				'claim_type': evidence_data.get('claim_type', ''),
				'claim_element_id': evidence_data.get('claim_element_id', ''),
				'projection_target': 'complaint_phase_knowledge_graph',
			},
		}
		projection_summary['graph_snapshot'] = persist_graph_snapshot(
			graph_snapshot_payload,
			graph_changed=graph_changed,
			existing_graph=artifact_present_before_projection,
			persistence_metadata={
				'projection_target': 'complaint_phase_knowledge_graph',
				'storage_record_created': bool(evidence_data.get('record_created', False)),
				'storage_record_reused': bool(evidence_data.get('record_reused', False)),
			},
		)
		
		# Add to dependency graph
		should_update_dependency_graph = bool(
			dg and supported_claim_ids and (
				kg is None
				or graph_changed
				or evidence_data.get('record_created', False)
				or evidence_data.get('support_link_created', False)
			)
		)
		if should_update_dependency_graph:
			self.dg_builder.add_evidence_to_graph(dg, evidence_data, supported_claim_ids[0])
		
		# Update phase data
		evidence_count = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'evidence_count') or 0
		projection_summary['graph_changed'] = graph_changed
		existing_enhanced = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'knowledge_graph_enhanced') or False
		updated_evidence_count = evidence_count + 1 if graph_changed else evidence_count
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_count', updated_evidence_count)
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'knowledge_graph_enhanced', existing_enhanced or graph_changed)
		if kg:
			self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
		if dg:
			self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
		
		# Calculate evidence gap ratio
		readiness = dg.get_claim_readiness() if dg else {'overall_readiness': 0.0}
		gap_ratio = 1.0 - readiness['overall_readiness'] if dg else 1.0
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gap_ratio', gap_ratio)
		prior_alignment_tasks = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_evidence_tasks') or []
		prior_alignment_task_history = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_update_history') or []
		claim_support_packets = self._build_claim_support_packets()
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'claim_support_packets', claim_support_packets)
		intake_case_file = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
		alignment_summary = self._summarize_intake_evidence_alignment(intake_case_file, claim_support_packets)
		alignment_tasks = self._build_alignment_evidence_tasks(alignment_summary)
		alignment_task_updates = self._summarize_alignment_task_updates(
			prior_alignment_tasks,
			alignment_tasks,
			claim_support_packets,
			evidence_data,
		)
		alignment_task_update_history = self._merge_alignment_task_update_history(
			prior_alignment_task_history,
			alignment_task_updates,
			evidence_sequence=updated_evidence_count,
		)
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'intake_evidence_alignment_summary', alignment_summary)
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'alignment_evidence_tasks', alignment_tasks)
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_updates', alignment_task_updates)
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_update_history', alignment_task_update_history)
		packet_summary = self._summarize_claim_support_packets(claim_support_packets)
		evidence_outcomes = self._classify_evidence_ingestion_outcomes(
			evidence_data,
			projection_summary,
			claim_support_packets,
		)
		next_action = self.phase_manager.get_next_action()
		
		return {
			'evidence_added': True,
			'evidence_count': updated_evidence_count,
			'kg_summary': kg.summary() if kg else {},
			'dg_readiness': readiness,
			'gap_ratio': gap_ratio,
			'claim_support_packets': claim_support_packets,
			'claim_support_packet_summary': packet_summary,
			'intake_evidence_alignment_summary': alignment_summary,
			'alignment_evidence_tasks': alignment_tasks,
			'alignment_task_updates': alignment_task_updates,
			'alignment_task_update_history': alignment_task_update_history,
			'evidence_outcomes': evidence_outcomes,
			'graph_projection': projection_summary,
			'next_action': next_action,
			'ready_for_formalization': self.phase_manager.is_phase_complete(ComplaintPhase.EVIDENCE)
		}
	
	def process_evidence_denoising(self, question: Dict[str, Any], answer: str) -> Dict[str, Any]:
		"""
		Process denoising questions during evidence phase.
		
		This applies the denoising diffusion pattern to evidence gathering,
		iteratively clarifying evidence gaps.
		
		Args:
			question: Evidence denoising question
			answer: User's answer
			
		Returns:
			Updated evidence phase status
		"""
		kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
		dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
		
		# Process answer (similar to Phase 1 but focused on evidence)
		updates = self.denoiser.process_answer(question, answer, kg, dg)
		
		# If answer describes evidence, add it
		evidence_refreshed = False
		if len(answer) > 20 and question.get('type') in ['evidence_clarification', 'evidence_quality']:
			evidence_data = {
				'id': f"evidence_from_q_{len(self.denoiser.questions_asked)}",
				'name': f"Evidence: {answer[:50]}",
				'type': 'user_provided',
				'description': answer,
				'confidence': 0.7,
				'supports_claims': [question.get('context', {}).get('claim_id')]
			}
			self.add_evidence_to_graphs(evidence_data)
			evidence_refreshed = True
		
		# Generate next evidence questions
		evidence_gaps = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gaps') or []
		alignment_evidence_tasks = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_evidence_tasks') or []
		alignment_task_updates = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_updates') or []
		alignment_task_update_history = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_update_history') or []
		if not evidence_refreshed:
			prior_alignment_tasks = alignment_evidence_tasks
			alignment_evidence_tasks = self._retire_answered_alignment_evidence_tasks(
				question,
				answer,
				alignment_evidence_tasks,
			)
			answer_task_updates = self._build_answered_alignment_task_updates(
				prior_alignment_tasks,
				alignment_evidence_tasks,
				question,
				answer,
			)
			self.phase_manager.update_phase_data(
				ComplaintPhase.EVIDENCE,
				'alignment_evidence_tasks',
				alignment_evidence_tasks,
			)
			if answer_task_updates:
				last_sequence = 0
				for entry in alignment_task_update_history if isinstance(alignment_task_update_history, list) else []:
					if not isinstance(entry, dict):
						continue
					try:
						last_sequence = max(last_sequence, int(entry.get('evidence_sequence', 0) or 0))
					except (TypeError, ValueError):
						continue
				evidence_sequence = max(
					int(self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'evidence_count') or 0),
					last_sequence,
				) + 1
				alignment_task_updates = answer_task_updates
				alignment_task_update_history = self._merge_alignment_task_update_history(
					alignment_task_update_history,
					answer_task_updates,
					evidence_sequence=evidence_sequence,
				)
				self.phase_manager.update_phase_data(
					ComplaintPhase.EVIDENCE,
					'alignment_task_updates',
					alignment_task_updates,
				)
				self.phase_manager.update_phase_data(
					ComplaintPhase.EVIDENCE,
					'alignment_task_update_history',
					alignment_task_update_history,
				)
		questions = self.denoiser.generate_evidence_questions(
			kg,
			dg,
			evidence_gaps,
			alignment_evidence_tasks=alignment_evidence_tasks,
			max_questions=3,
		)
		
		# Calculate evidence noise level
		evidence_count = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'evidence_count') or 0
		gap_ratio = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gap_ratio') or 1.0
		noise = gap_ratio * 0.7 + (1.0 - min(evidence_count / 10.0, 1.0)) * 0.3
		
		self.phase_manager.record_iteration(noise, {
			'phase': 'evidence',
			'evidence_count': evidence_count,
			'gap_ratio': gap_ratio
		})
		
		return {
			'phase': ComplaintPhase.EVIDENCE.value,
			'updates': updates,
			'next_questions': questions,
			'alignment_evidence_tasks': alignment_evidence_tasks,
			'alignment_task_updates': alignment_task_updates,
			'alignment_task_update_history': alignment_task_update_history,
			'next_action': self.phase_manager.get_next_action(),
			'noise_level': noise,
			'ready_for_formalization': self.phase_manager.is_phase_complete(ComplaintPhase.EVIDENCE)
		}
	
	def advance_to_formalization_phase(self) -> Dict[str, Any]:
		"""
		Advance to Phase 3: Neurosymbolic matching and formalization.
		
		Returns:
			Status of formalization phase initiation
		"""
		if not self.phase_manager.advance_to_phase(ComplaintPhase.FORMALIZATION):
			return {
				'error': 'Cannot advance to formalization phase. Complete evidence gathering first.',
				'current_phase': self.phase_manager.get_current_phase().value
			}
		
		kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
		dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
		
		# Build legal graph from applicable statutes
		statutes = getattr(self.state, 'applicable_statutes', [])
		claim_types = [claim.attributes.get('claim_type', 'unknown') 
		              for claim in kg.get_entities_by_type('claim')]
		
		legal_graph = self.legal_graph_builder.build_from_statutes(statutes, claim_types)
		self.phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph', legal_graph)
		
		# Also build procedural requirements
		procedural_graph = self.legal_graph_builder.build_rules_of_procedure()
		self.phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'procedural_graph', procedural_graph)
		
		# Perform neurosymbolic matching
		matching_results = self.neurosymbolic_matcher.match_claims_to_law(kg, dg, legal_graph)
		self.phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_results', matching_results)
		self.phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_complete', True)
		
		# Assess claim viability
		viability = self.neurosymbolic_matcher.assess_claim_viability(matching_results)
		self.phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'viability', viability)
		
		return {
			'phase': ComplaintPhase.FORMALIZATION.value,
			'legal_graph_summary': legal_graph.summary(),
			'procedural_requirements': len(procedural_graph.elements),
			'matching_results': matching_results,
			'viability_assessment': viability,
			'next_action': self.phase_manager.get_next_action()
		}
	
	def generate_formal_complaint(self, court_name: str = None, district: str = None,
						 county: str = None, division: str = None, court_header_override: str = None,
						 case_number: str = None, lead_case_number: str = None,
						 related_case_number: str = None, assigned_judge: str = None,
						 courtroom: str = None, title_override: str = None,
						 plaintiff_names: List[str] = None, defendant_names: List[str] = None,
						 requested_relief: List[str] = None, jury_demand: bool = None,
						 jury_demand_text: str = None, signer_name: str = None,
						 signer_title: str = None, signer_firm: str = None,
						 signer_bar_number: str = None, signer_contact: str = None,
						 additional_signers: List[Dict[str, str]] = None,
						 declarant_name: str = None,
						 service_method: str = None, signature_date: str = None,
						 service_recipients: List[str] = None,
						 service_recipient_details: List[Dict[str, str]] = None,
						 verification_date: str = None, service_date: str = None,
						 affidavit_title: str = None, affidavit_intro: str = None,
						 affidavit_facts: List[str] = None,
						 affidavit_supporting_exhibits: List[Dict[str, str]] = None,
						 affidavit_include_complaint_exhibits: bool = None,
						 affidavit_venue_lines: List[str] = None,
						 affidavit_jurat: str = None,
						 affidavit_notary_block: List[str] = None,
						 user_id: str = None) -> Dict[str, Any]:
		"""
		Generate formal complaint document from graphs.
		
		Returns:
			Formal complaint with all sections
		"""
		kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
		dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
		legal_graph = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph')
		matching_results = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'matching_results')
		
		# Build formal complaint structure
		formal_complaint = {
			'title': self._generate_complaint_title(kg),
			'parties': self._extract_parties(kg),
			'jurisdiction': self._determine_jurisdiction(legal_graph),
			'statement_of_claim': self._generate_statement_of_claim(kg, dg),
			'factual_allegations': self._generate_factual_allegations(kg),
			'legal_claims': self._generate_legal_claims(dg, legal_graph, matching_results),
			'prayer_for_relief': self._generate_relief_request(dg),
			'supporting_documents': self._list_evidence(kg)
		}

		builder = ComplaintDocumentBuilder(self)
		formal_complaint = builder.build(
			court_name=court_name,
			district=district,
			county=county,
			division=division,
			court_header_override=court_header_override,
			case_number=case_number,
			lead_case_number=lead_case_number,
			related_case_number=related_case_number,
			assigned_judge=assigned_judge,
			courtroom=courtroom,
			title_override=title_override,
			plaintiff_names=plaintiff_names,
			defendant_names=defendant_names,
			requested_relief=requested_relief,
			jury_demand=jury_demand,
			jury_demand_text=jury_demand_text,
			signer_name=signer_name,
			signer_title=signer_title,
			signer_firm=signer_firm,
			signer_bar_number=signer_bar_number,
			signer_contact=signer_contact,
			additional_signers=additional_signers,
			declarant_name=declarant_name,
			service_method=service_method,
			service_recipients=service_recipients,
			service_recipient_details=service_recipient_details,
			signature_date=signature_date,
			verification_date=verification_date,
			service_date=service_date,
			affidavit_title=affidavit_title,
			affidavit_intro=affidavit_intro,
			affidavit_facts=affidavit_facts,
			affidavit_supporting_exhibits=affidavit_supporting_exhibits,
				affidavit_include_complaint_exhibits=affidavit_include_complaint_exhibits,
			affidavit_venue_lines=affidavit_venue_lines,
			affidavit_jurat=affidavit_jurat,
			affidavit_notary_block=affidavit_notary_block,
			user_id=user_id,
			base_formal_complaint=formal_complaint,
		)
		
		self.phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint', formal_complaint)
		
		return {
			'formal_complaint': formal_complaint,
			'draft_text': formal_complaint.get('draft_text', ''),
			'complete': True,
			'ready_to_file': self._check_filing_readiness(formal_complaint)
		}

	def export_formal_complaint(self, output_path: str, court_name: str = None,
						  district: str = None, division: str = None,
						  case_number: str = None, user_id: str = None,
						  format: str = None) -> Dict[str, Any]:
		"""Export the generated formal complaint to DOCX, PDF, or text."""
		builder = ComplaintDocumentBuilder(self)
		complaint_result = self.generate_formal_complaint(
			court_name=court_name,
			district=district,
			division=division,
			case_number=case_number,
			user_id=user_id,
		)
		formal_complaint = complaint_result['formal_complaint']
		export_result = builder.export(formal_complaint, output_path, format=format)
		self.phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint_export', export_result)
		return {
			**complaint_result,
			'export': export_result,
		}
	
	def process_legal_denoising(self, question: Dict[str, Any], answer: str) -> Dict[str, Any]:
		"""
		Process denoising questions during formalization phase.
		
		This applies denoising to ensure all legal requirements are satisfied.
		
		Args:
			question: Legal requirement denoising question
			answer: User's answer
			
		Returns:
			Updated formalization status
		"""
		kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
		dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
		legal_graph = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph')
		
		# Process answer to update graphs
		updates = self.denoiser.process_answer(question, answer, kg, dg)
		
		# Re-run neurosymbolic matching with updated information
		matching_results = self.neurosymbolic_matcher.match_claims_to_law(kg, dg, legal_graph)
		self.phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_results', matching_results)
		
		# Generate next legal denoising questions
		questions = self.denoiser.generate_legal_matching_questions(matching_results, max_questions=3)
		
		# Calculate legal matching noise
		viability = self.neurosymbolic_matcher.assess_claim_viability(matching_results)
		avg_confidence = sum(m.get('confidence', 0) for m in matching_results.get('matches', [])) / max(len(matching_results.get('matches', [])), 1)
		unmatched_ratio = len(matching_results.get('unmatched_requirements', [])) / max(len(legal_graph.elements), 1)
		
		noise = (1.0 - avg_confidence) * 0.5 + unmatched_ratio * 0.5
		
		self.phase_manager.record_iteration(noise, {
			'phase': 'formalization',
			'viable_claims': viability.get('viable_count', 0),
			'unmatched_requirements': len(matching_results.get('unmatched_requirements', []))
		})
		
		return {
			'phase': ComplaintPhase.FORMALIZATION.value,
			'updates': updates,
			'matching_results': matching_results,
			'next_questions': questions,
			'noise_level': noise,
			'ready_to_generate': len(questions) == 0 or noise < 0.2
		}
	
	def synthesize_complaint_summary(self, include_conversation: bool = True) -> str:
		"""
		Synthesize a human-readable summary from knowledge graphs, 
		conversation history, and evidence.
		
		This hides the complexity of graphs from end users while providing
		a clear, denoised summary of the complaint status.
		
		Args:
			include_conversation: Whether to include conversation insights
			
		Returns:
			Human-readable complaint summary
		"""
		kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
		
		# Get evidence list
		evidence_entities = kg.get_entities_by_type('evidence') if kg else []
		evidence_list = [
			{
				'name': e.name,
				'type': e.attributes.get('type', 'unknown'),
				'description': e.attributes.get('description', '')
			}
			for e in evidence_entities
		]
		
		# Get conversation history if available
		conversation_history = []
		if include_conversation:
			conversation_history = self.denoiser.questions_asked
		
		# Use denoiser's synthesis method
		summary = self.denoiser.synthesize_complaint_summary(
			kg,
			conversation_history,
			evidence_list
		)
		
		return summary
	
	def get_three_phase_status(self) -> Dict[str, Any]:
		"""Get current status of three-phase process."""
		intake_readiness = self.phase_manager.get_intake_readiness()
		intake_case_file = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
		candidate_claims = intake_case_file.get('candidate_claims', []) if isinstance(intake_case_file, dict) else []
		canonical_facts = intake_case_file.get('canonical_facts', []) if isinstance(intake_case_file, dict) else []
		proof_leads = intake_case_file.get('proof_leads', []) if isinstance(intake_case_file, dict) else []
		question_candidates = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'question_candidates') or []
		intake_matching_pressure = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_matching_pressure') or {}
		claim_support_packets = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'claim_support_packets') or {}
		alignment_evidence_tasks = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_evidence_tasks') or []
		alignment_task_updates = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_updates') or []
		alignment_task_update_history = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_update_history') or []
		timeline_anchors = intake_case_file.get('timeline_anchors', []) if isinstance(intake_case_file, dict) else []
		harm_profile = intake_case_file.get('harm_profile', {}) if isinstance(intake_case_file, dict) else {}
		remedy_profile = intake_case_file.get('remedy_profile', {}) if isinstance(intake_case_file, dict) else {}
		return {
			'current_phase': self.phase_manager.get_current_phase().value,
			'iteration_count': self.phase_manager.iteration_count,
			'convergence_history': self.phase_manager.loss_history[-10:] if self.phase_manager.loss_history else [],
			'loss_history': self.phase_manager.loss_history if self.phase_manager.loss_history else [],
			'intake_readiness': intake_readiness,
			'candidate_claims': candidate_claims,
			'intake_sections': intake_readiness.get('intake_sections', {}),
			'canonical_fact_summary': {
				'count': len(canonical_facts),
				'facts': canonical_facts,
			},
			'proof_lead_summary': {
				'count': len(proof_leads),
				'proof_leads': proof_leads,
			},
			'timeline_anchor_summary': {
				'count': len(timeline_anchors) if isinstance(timeline_anchors, list) else 0,
				'anchors': timeline_anchors if isinstance(timeline_anchors, list) else [],
			},
			'harm_profile': harm_profile if isinstance(harm_profile, dict) else {},
			'remedy_profile': remedy_profile if isinstance(remedy_profile, dict) else {},
			'intake_matching_summary': self._summarize_intake_matching_pressure(intake_matching_pressure),
			'intake_legal_targeting_summary': self._summarize_intake_legal_targeting(
				intake_matching_pressure,
				question_candidates,
			),
			'question_candidate_summary': self._summarize_question_candidates(question_candidates),
			'claim_support_packet_summary': self._summarize_claim_support_packets(claim_support_packets),
			'intake_evidence_alignment_summary': self._summarize_intake_evidence_alignment(
				intake_case_file,
				claim_support_packets,
			),
			'alignment_evidence_tasks': alignment_evidence_tasks if isinstance(alignment_evidence_tasks, list) else [],
			'alignment_task_updates': alignment_task_updates if isinstance(alignment_task_updates, list) else [],
			'alignment_task_update_history': alignment_task_update_history if isinstance(alignment_task_update_history, list) else [],
			'intake_contradictions': {
				'candidate_count': intake_readiness.get('contradiction_count', 0),
				'candidates': intake_readiness.get('contradictions', []),
			},
			'phase_completion': {
				'intake': self.phase_manager.is_phase_complete(ComplaintPhase.INTAKE),
				'evidence': self.phase_manager.is_phase_complete(ComplaintPhase.EVIDENCE),
				'formalization': self.phase_manager.is_phase_complete(ComplaintPhase.FORMALIZATION)
			},
			'next_action': self.phase_manager.get_next_action()
		}
	
	def save_graphs_to_statefiles(self, base_filename: str) -> Dict[str, str]:
		"""
		Save all graphs to the statefiles directory.
		
		Args:
			base_filename: Base name for the files
			
		Returns:
			Paths to saved files
		"""
		import os
		statefiles_dir = os.path.join(os.path.dirname(__file__), '..', 'statefiles')
		os.makedirs(statefiles_dir, exist_ok=True)
		
		saved_files = {}
		
		# Save knowledge graph
		kg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
		if kg:
			kg_path = os.path.join(statefiles_dir, f"{base_filename}_knowledge_graph.json")
			kg.to_json(kg_path)
			saved_files['knowledge_graph'] = kg_path
		
		# Save dependency graph
		dg = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
		if dg:
			dg_path = os.path.join(statefiles_dir, f"{base_filename}_dependency_graph.json")
			dg.to_json(dg_path)
			saved_files['dependency_graph'] = dg_path
		
		# Save legal graph
		legal_graph = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph')
		if legal_graph:
			lg_path = os.path.join(statefiles_dir, f"{base_filename}_legal_graph.json")
			legal_graph.to_json(lg_path)
			saved_files['legal_graph'] = lg_path
		
		# Save phase manager state
		import json
		pm_path = os.path.join(statefiles_dir, f"{base_filename}_phase_state.json")
		with open(pm_path, 'w') as f:
			json.dump(self.phase_manager.to_dict(), f, indent=2)
		saved_files['phase_state'] = pm_path
		
		self.log('graphs_saved', files=saved_files)
		return saved_files
	
	# Helper methods for formal complaint generation
	
	def _suggest_evidence_types(self, unsatisfied, kg_gaps):
		"""Suggest types of evidence needed."""
		suggestions = []
		for req in unsatisfied[:5]:
			suggestions.append({
				'requirement': req['node_name'],
				'suggested_type': 'document' if 'document' in req['node_name'].lower() else 'testimony'
			})
		return suggestions
	
	def _generate_complaint_title(self, kg):
		"""Generate complaint title from parties."""
		persons = kg.get_entities_by_type('person')
		orgs = kg.get_entities_by_type('organization')
		plaintiff = next((p.name for p in persons if 'complainant' in p.attributes.get('role', '')), 'Plaintiff')
		defendant = next((o.name for o in orgs if 'defendant' in o.attributes.get('role', '')), 
		                next((o.name for o in orgs), 'Defendant'))
		return f"{plaintiff} v. {defendant}"
	
	def _extract_parties(self, kg):
		"""Extract parties from knowledge graph."""
		persons = kg.get_entities_by_type('person')
		orgs = kg.get_entities_by_type('organization')
		return {
			'plaintiffs': [p.name for p in persons if 'complainant' in p.attributes.get('role', '')],
			'defendants': [o.name for o in orgs]
		}
	
	def _determine_jurisdiction(self, legal_graph):
		"""Determine jurisdiction from legal graph."""
		elements = list(legal_graph.elements.values())
		if elements:
			return elements[0].jurisdiction
		return 'federal'
	
	def _generate_statement_of_claim(self, kg, dg):
		"""Generate short statement of claim."""
		claims = dg.get_nodes_by_type(NodeType.CLAIM)
		if claims:
			claim_names = ', '.join([c.name for c in claims[:3]])
			return f"Plaintiff brings this action alleging {claim_names}."
		return "Plaintiff brings this action seeking relief."
	
	def _generate_factual_allegations(self, kg):
		"""Generate factual allegations from knowledge graph."""
		allegations = []
		for i, entity in enumerate(kg.entities.values(), 1):
			if entity.type == 'fact':
				allegations.append(f"{i}. {entity.name}")
		return allegations if allegations else ["Facts to be provided."]
	
	def _generate_legal_claims(self, dg, legal_graph, matching_results):
		"""Generate legal claims section."""
		claims = []
		for claim_result in matching_results.get('claims', []):
			claims.append({
				'title': claim_result['claim_name'],
				'elements_satisfied': f"{claim_result['satisfied_requirements']}/{claim_result['legal_requirements']}",
				'description': f"Claim for {claim_result['claim_name']} under applicable law."
			})
		return claims
	
	def _generate_relief_request(self, dg):
		"""Generate prayer for relief."""
		return [
			"Compensatory damages",
			"Injunctive relief",
			"Attorney's fees and costs",
			"Such other relief as the Court deems just and proper"
		]
	
	def _list_evidence(self, kg):
		"""List supporting evidence."""
		evidence = kg.get_entities_by_type('evidence')
		return [{'name': e.name, 'type': e.attributes.get('type', 'unknown')} for e in evidence]
	
	def _check_filing_readiness(self, formal_complaint):
		"""Check if complaint is ready to file."""
		required_sections = [
			'title',
			'court_header',
			'parties',
			'nature_of_action',
			'statement_of_claim',
			'factual_allegations',
			'legal_claims',
			'prayer_for_relief',
		]
		return all(formal_complaint.get(section) for section in required_sections)

	def build_formal_complaint_document_package(
		self,
		user_id: str = None,
		court_name: str = 'United States District Court',
		district: str = '',
		county: str = None,
		division: str = None,
		court_header_override: str = None,
		case_number: str = None,
		lead_case_number: str = None,
		related_case_number: str = None,
		assigned_judge: str = None,
		courtroom: str = None,
		title_override: str = None,
		plaintiff_names: List[str] = None,
		defendant_names: List[str] = None,
		requested_relief: List[str] = None,
		jury_demand: bool = None,
		jury_demand_text: str = None,
		signer_name: str = None,
		signer_title: str = None,
		signer_firm: str = None,
		signer_bar_number: str = None,
		signer_contact: str = None,
		additional_signers: List[Dict[str, str]] = None,
		declarant_name: str = None,
		service_method: str = None,
		service_recipients: List[str] = None,
		service_recipient_details: List[Dict[str, str]] = None,
		signature_date: str = None,
		verification_date: str = None,
		service_date: str = None,
		affidavit_title: str = None,
		affidavit_intro: str = None,
		affidavit_facts: List[str] = None,
		affidavit_supporting_exhibits: List[Dict[str, str]] = None,
		affidavit_include_complaint_exhibits: bool = None,
		affidavit_venue_lines: List[str] = None,
		affidavit_jurat: str = None,
		affidavit_notary_block: List[str] = None,
		enable_agentic_optimization: bool = False,
		optimization_max_iterations: int = 2,
		optimization_target_score: float = 0.9,
		optimization_provider: str = None,
		optimization_model_name: str = None,
		optimization_llm_config: Dict[str, Any] = None,
		optimization_persist_artifacts: bool = False,
		output_dir: str = None,
		output_formats: List[str] = None,
	):
		"""Build a structured formal complaint draft and render DOCX/PDF artifacts."""
		builder = FormalComplaintDocumentBuilder(self)
		return builder.build_package(
			user_id=user_id,
			court_name=court_name,
			district=district,
			county=county,
			division=division,
			court_header_override=court_header_override,
			case_number=case_number,
			lead_case_number=lead_case_number,
			related_case_number=related_case_number,
			assigned_judge=assigned_judge,
			courtroom=courtroom,
			title_override=title_override,
			plaintiff_names=plaintiff_names,
			defendant_names=defendant_names,
			requested_relief=requested_relief,
			jury_demand=jury_demand,
			jury_demand_text=jury_demand_text,
			signer_name=signer_name,
			signer_title=signer_title,
			signer_firm=signer_firm,
			signer_bar_number=signer_bar_number,
			signer_contact=signer_contact,
			additional_signers=additional_signers,
			declarant_name=declarant_name,
			service_method=service_method,
			service_recipients=service_recipients,
			service_recipient_details=service_recipient_details,
			signature_date=signature_date,
			verification_date=verification_date,
			service_date=service_date,
			affidavit_title=affidavit_title,
			affidavit_intro=affidavit_intro,
			affidavit_facts=affidavit_facts,
			affidavit_supporting_exhibits=affidavit_supporting_exhibits,
			affidavit_include_complaint_exhibits=affidavit_include_complaint_exhibits,
			affidavit_venue_lines=affidavit_venue_lines,
			affidavit_jurat=affidavit_jurat,
			affidavit_notary_block=affidavit_notary_block,
			enable_agentic_optimization=enable_agentic_optimization,
			optimization_max_iterations=optimization_max_iterations,
			optimization_target_score=optimization_target_score,
			optimization_provider=optimization_provider,
			optimization_model_name=optimization_model_name,
			optimization_llm_config=optimization_llm_config,
			optimization_persist_artifacts=optimization_persist_artifacts,
			output_dir=output_dir,
			output_formats=output_formats,
		)


	def query_backend(self, prompt):
		backend = self.backends[0]

		try:
			response = backend(prompt)
		except Exception as exception:
			self.log('backend_error', backend=backend.id, prompt=prompt, error=str(exception))
			raise exception

		self.log('backend_query', backend=backend.id, prompt=prompt, response=response)

		return response
		


	def log(self, event_type, **data):
		self.state.log.append({
			'time': int(time()),
			'type': event_type,
			**data
		})
