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
from integrations.ipfs_datasets.capabilities import get_ipfs_datasets_capabilities
from integrations.ipfs_datasets.graphs import query_graph_support

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
		self.log(
			'ipfs_datasets_capabilities',
			capabilities={
				name: status.as_dict()
				for name, status in get_ipfs_datasets_capabilities().items()
			},
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
			'record_reused': record_result.get('reused', False),
			'user_id': user_id,
			'description': description,
			'claim_type': claim_type,
			'claim_element': resolved_element.get('claim_element_text'),
			'claim_element_id': resolved_element.get('claim_element_id'),
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
	                            search_all: bool = False):
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
				query, claim_type, jurisdiction
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
	                           user_id: str = None):
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

	def _build_follow_up_task(self, claim_type: str, element: Dict[str, Any], status: str,
			required_support_kinds: List[str]) -> Dict[str, Any]:
		element_text = element.get('element_text') or element.get('claim_element') or 'Unknown element'
		support_by_kind = element.get('support_by_kind', {})
		missing_support_kinds = [
			kind for kind in required_support_kinds
			if support_by_kind.get(kind, 0) == 0
		]
		priority = 'high' if status == 'missing' else 'medium'
		queries: Dict[str, List[str]] = {}
		if 'evidence' in missing_support_kinds:
			queries['evidence'] = [
				f'"{claim_type}" "{element_text}" evidence',
				f'"{element_text}" documentation {claim_type}',
				f'"{element_text}" facts witness records {claim_type}',
			]
		if 'authority' in missing_support_kinds:
			queries['authority'] = [
				f'"{claim_type}" "{element_text}" statute',
				f'"{claim_type}" "{element_text}" case law',
				f'"{element_text}" legal elements {claim_type}',
			]
		return {
			'claim_type': claim_type,
			'claim_element_id': element.get('element_id'),
			'claim_element': element_text,
			'status': status,
			'priority': priority,
			'priority_score': 3 if priority == 'high' else 2,
			'missing_support_kinds': missing_support_kinds,
			'queries': queries,
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
		overview = self.get_claim_overview(
			claim_type=claim_type,
			user_id=user_id,
			required_support_kinds=required_support_kinds,
		)
		plan = {
			'required_support_kinds': required_support_kinds or ['evidence', 'authority'],
			'claims': {},
		}
		for current_claim, claim_data in overview.get('claims', {}).items():
			tasks = []
			for element in claim_data.get('missing', []):
				tasks.append(self._build_follow_up_task(
					current_claim,
					element,
					'missing',
					claim_data.get('required_support_kinds', plan['required_support_kinds']),
				))
			for element in claim_data.get('partially_supported', []):
				tasks.append(self._build_follow_up_task(
					current_claim,
					element,
					'partially_supported',
					claim_data.get('required_support_kinds', plan['required_support_kinds']),
				))
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
				task['graph_support'] = graph_support
				task['has_graph_support'] = bool(graph_support.get('results'))
				task['graph_support_strength'] = graph_support_assessment['strength']
				task['recommended_action'] = graph_support_assessment['recommended_action']
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
					'graph_support': task.get('graph_support', {}),
					'should_suppress_retrieval': task.get('should_suppress_retrieval', False),
					'suppression_reason': task.get('suppression_reason', ''),
					'executed': {},
				}
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
							metadata={'cooldown_seconds': cooldown_seconds},
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
						self.claim_support.record_follow_up_execution(
							user_id=user_id,
							claim_type=current_claim,
							claim_element_id=task.get('claim_element_id'),
							claim_element_text=task.get('claim_element'),
							support_kind='evidence',
							query_text=query_text,
							status='executed',
							metadata={'keywords': keywords},
						)
						execution['executed']['evidence'] = {
							'query': query_text,
							'keywords': keywords,
							'result': discovery_result,
						}
				if support_kind in (None, 'authority') and 'authority' in task.get('missing_support_kinds', []):
					authority_query = task.get('queries', {}).get('authority', [])
					query_text = authority_query[0] if authority_query else f'{current_claim} {task.get("claim_element", "")} statute'
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
							metadata={'cooldown_seconds': cooldown_seconds},
						)
						skipped_tasks.append({
							**execution,
							'skipped': {'authority': {'query': query_text, 'reason': 'duplicate_within_cooldown'}},
						})
					else:
						search_results = self.search_legal_authorities(
							query=query_text,
							claim_type=current_claim,
							search_all=True,
						)
						stored_counts = self.store_legal_authorities(
							search_results,
							claim_type=current_claim,
							search_query=query_text,
							user_id=user_id,
						)
						self.claim_support.record_follow_up_execution(
							user_id=user_id,
							claim_type=current_claim,
							claim_element_id=task.get('claim_element_id'),
							claim_element_text=task.get('claim_element'),
							support_kind='authority',
							query_text=query_text,
							status='executed',
							metadata={'search_results': {key: len(value) for key, value in search_results.items()}},
						)
						execution['executed']['authority'] = {
							'query': query_text,
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

		return {
			'claim_type': claim_type,
			'claim_element_id': target_element_id,
			'claim_element': target_element_text,
			'exists': bool(target_element_id or target_element_text),
			'is_covered': bool(element_summary.get('total_links', 0)),
			'missing_support': element_summary.get('total_links', 0) == 0,
			'support_summary': element_summary,
			'support_facts': support_facts,
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
	) -> Dict[str, Any]:
		if not isinstance(coverage_claim, dict):
			coverage_claim = {}
		if not isinstance(overview_claim, dict):
			overview_claim = {}
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
		return {
			'claim_type': claim_type,
			'total_elements': coverage_claim.get('total_elements', 0),
			'total_links': coverage_claim.get('total_links', 0),
			'total_facts': coverage_claim.get('total_facts', 0),
			'support_by_kind': coverage_claim.get('support_by_kind', {}),
			'status_counts': coverage_claim.get(
				'status_counts',
				{'covered': 0, 'partially_supported': 0, 'missing': 0},
			),
			'missing_elements': missing_elements,
			'partially_supported_elements': partially_supported_elements,
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
			'claim_overview': {},
			'follow_up_plan': {},
			'follow_up_execution': {}
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
			results['claim_coverage_summary'][claim_type] = self._summarize_claim_coverage_claim(
				results['claim_coverage_matrix'][claim_type],
				claim_type,
				results['claim_overview'][claim_type],
			)
			follow_up_plan = self.get_claim_follow_up_plan(claim_type=claim_type, user_id=user_id)
			results['follow_up_plan'][claim_type] = follow_up_plan.get('claims', {}).get(
				claim_type,
				{
					'task_count': 0,
					'tasks': [],
				},
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
		if evidence_data.get('document_graph'):
			projection_summary.update(self._project_document_graph_to_knowledge_graph(kg, evidence_data))
		
		# Add evidence entity to knowledge graph
		from complaint_phases.knowledge_graph import Entity
		artifact_id = evidence_data.get('artifact_id') or evidence_data.get('cid') or f"evidence_{evidence_data.get('id', 'unknown')}"
		artifact_present_before_add = bool(kg and artifact_id in kg.entities)
		projection_summary['artifact_entity_already_present'] = artifact_present_before_add
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
	
	def generate_formal_complaint(self) -> Dict[str, Any]:
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
		
		self.phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint', formal_complaint)
		
		return {
			'formal_complaint': formal_complaint,
			'complete': True,
			'ready_to_file': self._check_filing_readiness(formal_complaint)
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
		required_sections = ['title', 'parties', 'statement_of_claim', 'legal_claims']
		return all(formal_complaint.get(section) for section in required_sections)


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