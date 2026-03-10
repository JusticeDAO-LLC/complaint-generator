from time import time
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
		
		# Store in IPFS
		self.log('evidence_submission', user_id=user_id, type=evidence_type)
		evidence_info = self.evidence_storage.store_evidence(data, evidence_type, metadata)
		
		# Get complaint ID if available
		complaint_id = getattr(self.state, 'complaint_id', None)
		
		# Store state in DuckDB
		record_id = self.evidence_state.add_evidence_record(
			user_id=user_id,
			evidence_info=evidence_info,
			complaint_id=complaint_id,
			claim_type=claim_type,
			description=description
		)
		
		result = {
			**evidence_info,
			'record_id': record_id,
			'user_id': user_id,
			'description': description,
			'claim_type': claim_type,
			'claim_element': claim_element
		}

		if claim_type:
			self.claim_support.add_support_link(
				user_id=user_id,
				complaint_id=complaint_id,
				claim_type=claim_type,
				claim_element_text=claim_element,
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
		
		stored_counts = {}
		for auth_type, auth_list in authorities.items():
			if auth_list:
				# Add type info to each authority
				for auth in auth_list:
					auth['type'] = auth_type.rstrip('s')  # statutes -> statute
				
				record_ids = self.legal_authority_storage.add_authorities_bulk(
					auth_list, user_id, complaint_id, claim_type, search_query
				)
				stored_counts[auth_type] = len(record_ids)
				if claim_type:
					for auth, record_id in zip(auth_list, record_ids):
						support_ref = auth.get('citation') or auth.get('url') or str(record_id)
						self.claim_support.add_support_link(
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

	def summarize_claim_support(self, user_id: str = None, claim_type: str = None):
		"""Summarize persisted evidence and authority support by claim type."""
		if user_id is None:
			user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
		return self.claim_support.summarize_claim_support(user_id, claim_type)
	
	def research_case_automatically(self, user_id: str = None):
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
			'support_summary': {}
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
	
	def discover_evidence_automatically(self, user_id: str = None):
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
		
		return self.web_evidence_integration.discover_evidence_for_case(user_id=user_id)


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
		
		# Add evidence entity to knowledge graph
		from complaint_phases.knowledge_graph import Entity
		evidence_entity = Entity(
			id=f"evidence_{evidence_data.get('id', 'unknown')}",
			type='evidence',
			name=evidence_data.get('name', 'Evidence'),
			attributes=evidence_data,
			confidence=evidence_data.get('confidence', 0.8),
			source='evidence'
		)
		kg.add_entity(evidence_entity)
		
		# Add supporting relationships
		supported_claim_ids = evidence_data.get('supports_claims', [])
		from complaint_phases.knowledge_graph import Relationship
		for claim_id in supported_claim_ids:
			rel = Relationship(
				id=f"rel_{evidence_entity.id}_{claim_id}",
				source_id=evidence_entity.id,
				target_id=claim_id,
				relation_type='supports',
				confidence=evidence_data.get('relevance', 0.7)
			)
			kg.add_relationship(rel)
		
		# Add to dependency graph
		if supported_claim_ids:
			self.dg_builder.add_evidence_to_graph(dg, evidence_data, supported_claim_ids[0])
		
		# Update phase data
		evidence_count = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'evidence_count') or 0
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_count', evidence_count + 1)
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'knowledge_graph_enhanced', True)
		
		# Calculate evidence gap ratio
		readiness = dg.get_claim_readiness()
		gap_ratio = 1.0 - readiness['overall_readiness']
		self.phase_manager.update_phase_data(ComplaintPhase.EVIDENCE, 'evidence_gap_ratio', gap_ratio)
		
		return {
			'evidence_added': True,
			'evidence_count': evidence_count + 1,
			'kg_summary': kg.summary(),
			'dg_readiness': readiness,
			'gap_ratio': gap_ratio,
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