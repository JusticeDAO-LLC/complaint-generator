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

# Import three-phase complaint processing
from complaint_phases import (
	PhaseManager,
	ComplaintPhase,
	KnowledgeGraphBuilder,
	DependencyGraphBuilder,
	ComplaintDenoiser,
	LegalGraphBuilder,
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
			court_header_override=court_header_override,
				support_ref=evidence_info['cid'],
			title_override=title_override,
			plaintiff_names=plaintiff_names,
			defendant_names=defendant_names,
			requested_relief=requested_relief,
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
		claim_element: str = None,
	):
		"""Get persisted fact rows attached to evidence and authority support links."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.get_claim_support_facts(
			user_id,
			claim_type,
			claim_element_id=claim_element_id,
			claim_element_text=claim_element,
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
		adaptive_retry_state = task.get('adaptive_retry_state', {}) if isinstance(task.get('adaptive_retry_state'), dict) else {}
		rule_candidate_context = task.get('rule_candidate_context', {}) if isinstance(task.get('rule_candidate_context'), dict) else {}
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
			},
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
				if support_kind in (None, 'evidence') and 'evidence' in task.get('missing_support_kinds', []):
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
				if support_kind in (None, 'authority') and 'authority' in task.get('missing_support_kinds', []):
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

	def query_claim_graph_support(
		self,
		claim_type: str,
		claim_element_id: str = None,
		claim_element: str = None,
		user_id: str = None,
		max_results: int = 10,
	):
		"""Query fallback graph support using persisted claim-support fact rows."""
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
		return graph_result

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
		
		# Generate initial denoising questions
		questions = self.denoiser.generate_questions(kg, dg, max_questions=10)
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
			'initial_questions': questions,
			'initial_noise_level': noise,
			'next_action': self.phase_manager.get_next_action()
		}
	
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
		
		# Generate next questions
		max_questions = 5
		try:
			if hasattr(self.denoiser, "is_stagnating") and self.denoiser.is_stagnating():
				max_questions = 8
		except Exception:
			max_questions = 5
		questions = self.denoiser.generate_questions(kg, dg, max_questions=max_questions)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'current_questions', questions)
		
		# Update graphs in phase data
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', kg)
		self.phase_manager.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', dg)
		
		# Calculate new noise level
		noise = self.denoiser.calculate_noise_level(kg, dg)
		gaps = len(kg.find_gaps())
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
			'next_questions': questions,
			'iteration': self.phase_manager.iteration_count
		}
		
		# Check if ready to advance to Phase 2
		if self.phase_manager.is_phase_complete(ComplaintPhase.INTAKE):
			result['ready_for_evidence_phase'] = True
			result['message'] = 'Initial intake complete. Ready to gather evidence.'
		
		return result
	
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
		
		return {
			'phase': ComplaintPhase.EVIDENCE.value,
			'evidence_gaps': len(unsatisfied),
			'knowledge_gaps': len(kg_gaps),
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
		
		return {
			'evidence_added': True,
			'evidence_count': updated_evidence_count,
			'kg_summary': kg.summary() if kg else {},
			'dg_readiness': readiness,
			'gap_ratio': gap_ratio,
			'graph_projection': projection_summary,
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
		
		# Generate next evidence questions
		evidence_gaps = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gaps') or []
		questions = self.denoiser.generate_evidence_questions(kg, dg, evidence_gaps, max_questions=3)
		
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
						 division: str = None, court_header_override: str = None,
						 case_number: str = None, title_override: str = None,
						 plaintiff_names: List[str] = None, defendant_names: List[str] = None,
						 requested_relief: List[str] = None, signer_name: str = None,
						 signer_title: str = None, signer_firm: str = None,
						 signer_bar_number: str = None, signer_contact: str = None,
						 declarant_name: str = None,
						 service_method: str = None, signature_date: str = None,
						 service_recipients: List[str] = None,
						 verification_date: str = None, service_date: str = None,
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
			division=division,
			court_header_override=court_header_override,
			case_number=case_number,
			title_override=title_override,
			plaintiff_names=plaintiff_names,
			defendant_names=defendant_names,
			requested_relief=requested_relief,
			signer_name=signer_name,
			signer_title=signer_title,
			signer_firm=signer_firm,
			signer_bar_number=signer_bar_number,
			signer_contact=signer_contact,
			declarant_name=declarant_name,
			service_method=service_method,
			service_recipients=service_recipients,
			signature_date=signature_date,
			verification_date=verification_date,
			service_date=service_date,
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
		return {
			'current_phase': self.phase_manager.get_current_phase().value,
			'iteration_count': self.phase_manager.iteration_count,
			'convergence_history': self.phase_manager.loss_history[-10:] if self.phase_manager.loss_history else [],
			'loss_history': self.phase_manager.loss_history if self.phase_manager.loss_history else [],
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
		division: str = None,
		court_header_override: str = None,
		case_number: str = None,
		title_override: str = None,
		plaintiff_names: List[str] = None,
		defendant_names: List[str] = None,
		requested_relief: List[str] = None,
		signer_name: str = None,
		signer_title: str = None,
		signer_firm: str = None,
		signer_bar_number: str = None,
		signer_contact: str = None,
		declarant_name: str = None,
		service_method: str = None,
		service_recipients: List[str] = None,
		signature_date: str = None,
		verification_date: str = None,
		service_date: str = None,
		output_dir: str = None,
		output_formats: List[str] = None,
	):
		"""Build a structured formal complaint draft and render DOCX/PDF artifacts."""
		builder = FormalComplaintDocumentBuilder(self)
		return builder.build_package(
			user_id=user_id,
			court_name=court_name,
			district=district,
			division=division,
			court_header_override=court_header_override,
			case_number=case_number,
			title_override=title_override,
			plaintiff_names=plaintiff_names,
			defendant_names=defendant_names,
			requested_relief=requested_relief,
			signer_name=signer_name,
			signer_title=signer_title,
			signer_firm=signer_firm,
			signer_bar_number=signer_bar_number,
			signer_contact=signer_contact,
			declarant_name=declarant_name,
			service_method=service_method,
			service_recipients=service_recipients,
			signature_date=signature_date,
			verification_date=verification_date,
			service_date=service_date,
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