"""
Tests for complaint_phases module

Tests the three-phase complaint processing system with knowledge graphs,
dependency graphs, and neurosymbolic matching.
"""

from complaint_phases import (
    KnowledgeGraphBuilder, KnowledgeGraph, Entity, Relationship,
    DependencyGraphBuilder, DependencyGraph, DependencyNode, Dependency,
    NodeType, DependencyType,
    ComplaintDenoiser,
    PhaseManager, ComplaintPhase,
    LegalGraphBuilder, LegalGraph, LegalElement,
    NeurosymbolicMatcher
)


class TestKnowledgeGraph:
    """Tests for KnowledgeGraph and KnowledgeGraphBuilder."""
    
    def test_knowledge_graph_creation(self):
        """Test basic knowledge graph creation."""
        kg = KnowledgeGraph()
        assert len(kg.entities) == 0
        assert len(kg.relationships) == 0
    
    def test_add_entity(self):
        """Test adding entities to knowledge graph."""
        kg = KnowledgeGraph()
        entity = Entity(
            id="e1",
            type="person",
            name="John Doe",
            confidence=0.9
        )
        kg.add_entity(entity)
        
        assert len(kg.entities) == 1
        assert kg.get_entity("e1") == entity
    
    def test_add_relationship(self):
        """Test adding relationships to knowledge graph."""
        kg = KnowledgeGraph()
        e1 = Entity(id="e1", type="person", name="John Doe")
        e2 = Entity(id="e2", type="organization", name="Acme Corp")
        kg.add_entity(e1)
        kg.add_entity(e2)
        
        rel = Relationship(
            id="r1",
            source_id="e1",
            target_id="e2",
            relation_type="employed_by"
        )
        kg.add_relationship(rel)
        
        assert len(kg.relationships) == 1
        rels = kg.get_relationships_for_entity("e1")
        assert len(rels) == 1
    
    def test_find_gaps(self):
        """Test gap detection in knowledge graph."""
        kg = KnowledgeGraph()
        
        # Add low confidence entity
        e1 = Entity(id="e1", type="person", name="John Doe", confidence=0.5)
        kg.add_entity(e1)
        
        # Add isolated entity
        e2 = Entity(id="e2", type="organization", name="Acme Corp", confidence=0.9)
        kg.add_entity(e2)
        
        # Add claim without evidence
        claim = Entity(id="c1", type="claim", name="Discrimination")
        kg.add_entity(claim)
        
        gaps = kg.find_gaps()
        assert len(gaps) >= 2
        assert any(g['type'] == 'low_confidence_entity' for g in gaps)
        assert any(g['type'] == 'isolated_entity' for g in gaps)
    
    def test_knowledge_graph_serialization(self):
        """Test serialization and deserialization."""
        kg = KnowledgeGraph()
        e1 = Entity(id="e1", type="person", name="John Doe")
        kg.add_entity(e1)
        
        # Serialize
        data = kg.to_dict()
        assert 'entities' in data
        assert 'e1' in data['entities']
        
        # Deserialize
        kg2 = KnowledgeGraph.from_dict(data)
        assert len(kg2.entities) == 1
        assert kg2.get_entity("e1").name == "John Doe"
    
    def test_knowledge_graph_builder(self):
        """Test building knowledge graph from text."""
        builder = KnowledgeGraphBuilder()
        text = "I was discriminated against by my employer when they fired me."
        
        kg = builder.build_from_text(text)
        assert len(kg.entities) > 0
        summary = kg.summary()
        assert summary['total_entities'] > 0

    def test_knowledge_graph_builder_specializes_employment_discrimination_and_retaliation(self):
        """Heuristic claim extraction should specialize workplace discrimination when employment context is present."""
        builder = KnowledgeGraphBuilder()
        text = (
            "My employer discriminated against me because of my race and retaliated "
            "after I complained to HR by firing me."
        )

        kg = builder.build_from_text(text)
        claim_types = {
            str(entity.attributes.get("claim_type") or "").strip().lower()
            for entity in kg.get_entities_by_type("claim")
        }

        assert "employment_discrimination" in claim_types
        assert "retaliation" in claim_types

    def test_knowledge_graph_builder_specializes_housing_discrimination(self):
        """Housing context should promote generic discrimination language into housing discrimination."""
        builder = KnowledgeGraphBuilder()
        text = (
            "My landlord discriminated against me because of my disability and refused "
            "to renew my lease."
        )

        kg = builder.build_from_text(text)
        claim_types = {
            str(entity.attributes.get("claim_type") or "").strip().lower()
            for entity in kg.get_entities_by_type("claim")
        }

        assert "housing_discrimination" in claim_types


class TestDependencyGraph:
    """Tests for DependencyGraph and DependencyGraphBuilder."""
    
    def test_dependency_graph_creation(self):
        """Test basic dependency graph creation."""
        dg = DependencyGraph()
        assert len(dg.nodes) == 0
        assert len(dg.dependencies) == 0
    
    def test_add_node_and_dependency(self):
        """Test adding nodes and dependencies."""
        dg = DependencyGraph()
        
        claim = DependencyNode(
            id="n1",
            node_type=NodeType.CLAIM,
            name="Discrimination Claim"
        )
        dg.add_node(claim)
        
        req = DependencyNode(
            id="n2",
            node_type=NodeType.REQUIREMENT,
            name="Protected Class"
        )
        dg.add_node(req)
        
        dep = Dependency(
            id="d1",
            source_id="n2",
            target_id="n1",
            dependency_type=DependencyType.REQUIRES
        )
        dg.add_dependency(dep)
        
        assert len(dg.nodes) == 2
        assert len(dg.dependencies) == 1
    
    def test_check_satisfaction(self):
        """Test requirement satisfaction checking."""
        dg = DependencyGraph()
        
        claim = DependencyNode(id="n1", node_type=NodeType.CLAIM, name="Claim")
        dg.add_node(claim)
        
        req1 = DependencyNode(id="n2", node_type=NodeType.REQUIREMENT, 
                             name="Req1", satisfied=True, confidence=1.0)
        dg.add_node(req1)
        
        req2 = DependencyNode(id="n3", node_type=NodeType.REQUIREMENT, 
                             name="Req2", satisfied=False)
        dg.add_node(req2)
        
        dg.add_dependency(Dependency("d1", "n2", "n1", DependencyType.REQUIRES))
        dg.add_dependency(Dependency("d2", "n3", "n1", DependencyType.REQUIRES))
        
        check = dg.check_satisfaction("n1")
        assert not check['satisfied']  # Only 1 of 2 requirements met
        assert check['satisfaction_ratio'] == 0.5
    
    def test_claim_readiness(self):
        """Test claim readiness assessment."""
        dg = DependencyGraph()
        
        claim = DependencyNode(id="n1", node_type=NodeType.CLAIM, name="Claim1")
        dg.add_node(claim)
        
        req = DependencyNode(id="n2", node_type=NodeType.REQUIREMENT, 
                            name="Req1", satisfied=True, confidence=1.0)
        dg.add_node(req)
        dg.add_dependency(Dependency("d1", "n2", "n1", DependencyType.REQUIRES))
        
        readiness = dg.get_claim_readiness()
        assert readiness['total_claims'] == 1
        assert readiness['ready_claims'] == 1
        assert readiness['overall_readiness'] == 1.0
    
    def test_dependency_graph_builder(self):
        """Test building dependency graph from claims."""
        builder = DependencyGraphBuilder()
        claims = [
            {'name': 'Discrimination', 'type': 'employment_discrimination', 'description': 'Test'}
        ]
        legal_reqs = {
            'employment_discrimination': [
                {'name': 'Protected Class', 'description': 'Member of protected class'}
            ]
        }
        
        dg = builder.build_from_claims(claims, legal_reqs)
        assert len(dg.nodes) > 0
        summary = dg.summary()
        assert summary['total_nodes'] >= 2


class TestComplaintDenoiser:
    """Tests for ComplaintDenoiser."""
    
    def test_denoiser_creation(self):
        """Test denoiser creation."""
        denoiser = ComplaintDenoiser()
        assert len(denoiser.questions_asked) == 0
    
    def test_generate_questions(self):
        """Test question generation from graphs."""
        denoiser = ComplaintDenoiser()
        
        kg = KnowledgeGraph()
        kg.add_entity(Entity("e1", "person", "John", confidence=0.5))
        
        dg = DependencyGraph()
        claim = DependencyNode("n1", NodeType.CLAIM, "Claim1")
        dg.add_node(claim)
        
        questions = denoiser.generate_questions(kg, dg)
        assert len(questions) > 0
        assert 'question' in questions[0]
        assert 'type' in questions[0]
        assert 'question_reason' in questions[0]
        assert 'question_objective' in questions[0]
        assert 'expected_proof_gain' in questions[0]
        assert 'phase1_section' in questions[0]
        assert 'blocking_level' in questions[0]
        assert 'expected_update_kind' in questions[0]

    def test_generate_questions_prioritizes_timeline_before_clarification(self):
        """Test proof-directed ranking prefers chronology questions over lower-value clarification."""
        denoiser = ComplaintDenoiser()

        kg = KnowledgeGraph()
        kg.add_entity(Entity("e1", "person", "John", confidence=0.5))

        dg = DependencyGraph()
        claim = DependencyNode("n1", NodeType.CLAIM, "Claim1")
        dg.add_node(claim)

        questions = denoiser.generate_questions(kg, dg, max_questions=5)

        assert questions[0]['type'] == 'timeline'
        assert questions[0]['question_objective'] == 'establish_chronology'
        assert questions[0]['expected_proof_gain'] == 'high'
        assert questions[0]['phase1_section'] == 'chronology'
        assert questions[0]['blocking_level'] == 'blocking'

    def test_requirement_questions_include_proof_objective_metadata(self):
        """Test requirement-driven questions explain the proof objective they serve."""
        denoiser = ComplaintDenoiser()

        kg = KnowledgeGraph()
        claim_entity = Entity("c1", "claim", "Discrimination")
        kg.add_entity(claim_entity)

        dg = DependencyGraph()
        claim = DependencyNode("n1", NodeType.CLAIM, "Discrimination Claim")
        requirement = DependencyNode("n2", NodeType.REQUIREMENT, "Protected Class")
        dg.add_node(claim)
        dg.add_node(requirement)
        dg.add_dependency(Dependency("d1", "n2", "n1", DependencyType.REQUIRES))

        questions = denoiser.generate_questions(kg, dg, max_questions=10)
        requirement_questions = [q for q in questions if q['type'] == 'requirement']

        assert requirement_questions
        assert requirement_questions[0]['question_objective'] == 'satisfy_claim_requirement'
        assert 'Protected Class' in requirement_questions[0]['question_reason']
        assert requirement_questions[0]['phase1_section'] == 'claim_elements'
        assert requirement_questions[0]['target_element_id'] == 'n2'

    def test_generate_questions_emits_contradiction_resolution_prompt_first(self):
        """Test contradiction edges produce contradiction-resolution questions ahead of other intake prompts."""
        denoiser = ComplaintDenoiser()

        kg = KnowledgeGraph()
        kg.add_entity(Entity("c1", "claim", "Retaliation"))

        dg = DependencyGraph()
        left_fact = DependencyNode("n1", NodeType.FACT, "Termination happened before complaint")
        right_fact = DependencyNode("n2", NodeType.FACT, "Complaint happened before termination")
        claim = DependencyNode("n3", NodeType.CLAIM, "Retaliation Claim")
        dg.add_node(left_fact)
        dg.add_node(right_fact)
        dg.add_node(claim)
        dg.add_dependency(Dependency("d1", "n1", "n2", DependencyType.CONTRADICTS, required=False))

        questions = denoiser.generate_questions(kg, dg, max_questions=5)

        assert questions
        assert questions[0]['type'] == 'contradiction'
        assert questions[0]['question_objective'] == 'resolve_factual_contradiction'
        assert 'conflicting information' in questions[0]['question'].lower()
        assert questions[0]['phase1_section'] == 'contradictions'
        assert questions[0]['expected_update_kind'] == 'resolve_contradiction'

    def test_generate_questions_uses_missing_registry_claim_elements(self):
        """Missing required elements in the intake case file should generate requirement questions."""
        denoiser = ComplaintDenoiser()

        kg = KnowledgeGraph()
        kg.add_entity(Entity("claim1", "claim", "Employment Discrimination Claim", attributes={"claim_type": "employment_discrimination"}))

        dg = DependencyGraph()
        claim = DependencyNode("n1", NodeType.CLAIM, "Discrimination Claim")
        dg.add_node(claim)

        intake_case_file = {
            "candidate_claims": [
                {
                    "claim_id": "claim1",
                    "claim_type": "employment_discrimination",
                    "label": "Employment Discrimination Claim",
                    "required_elements": [
                        {
                            "element_id": "protected_trait",
                            "label": "Protected trait or class",
                            "blocking": True,
                            "status": "missing",
                        }
                    ],
                }
            ]
        }

        questions = denoiser.generate_questions(kg, dg, max_questions=5, intake_case_file=intake_case_file)
        requirement_questions = [
            q for q in questions
            if q["type"] == "requirement" and q.get("target_element_id") == "protected_trait"
        ]

        assert requirement_questions
        assert "protected trait or class" in requirement_questions[0]["question"].lower()
        assert requirement_questions[0]["phase1_section"] == "claim_elements"
        assert requirement_questions[0]["blocking_level"] == "blocking"

    def test_generate_questions_uses_employment_specific_claim_element_prompt_text(self):
        """Employment discrimination prompts should ask about workplace-specific facts."""
        denoiser = ComplaintDenoiser()

        kg = KnowledgeGraph()
        dg = DependencyGraph()
        intake_case_file = {
            "candidate_claims": [
                {
                    "claim_id": "claim1",
                    "claim_type": "employment_discrimination",
                    "label": "Employment Discrimination",
                    "required_elements": [
                        {
                            "element_id": "employment_relationship",
                            "label": "Employment relationship or workplace context",
                            "blocking": True,
                            "status": "missing",
                        }
                    ],
                }
            ]
        }

        questions = denoiser.generate_questions(kg, dg, max_questions=5, intake_case_file=intake_case_file)
        requirement_question = next(
            question for question in questions
            if question["type"] == "requirement" and question.get("target_element_id") == "employment_relationship"
        )

        question_text = requirement_question["question"].lower()
        assert "employer or supervisor" in question_text
        assert "workplace relationship" in question_text

    def test_generate_questions_uses_housing_specific_claim_element_prompt_text(self):
        """Housing discrimination prompts should ask about landlord or tenancy context."""
        denoiser = ComplaintDenoiser()

        kg = KnowledgeGraph()
        dg = DependencyGraph()
        intake_case_file = {
            "candidate_claims": [
                {
                    "claim_id": "claim1",
                    "claim_type": "housing_discrimination",
                    "label": "Housing Discrimination",
                    "required_elements": [
                        {
                            "element_id": "housing_context",
                            "label": "Housing relationship or tenancy context",
                            "blocking": True,
                            "status": "missing",
                        }
                    ],
                }
            ]
        }

        questions = denoiser.generate_questions(kg, dg, max_questions=5, intake_case_file=intake_case_file)
        requirement_question = next(
            question for question in questions
            if question["type"] == "requirement" and question.get("target_element_id") == "housing_context"
        )

        question_text = requirement_question["question"].lower()
        assert "landlord" in question_text
        assert "tenancy situation" in question_text

    def test_generate_questions_uses_employment_specific_proof_lead_prompt_text(self):
        """Employment discrimination proof prompts should ask for workplace-specific evidence."""
        denoiser = ComplaintDenoiser()

        kg = KnowledgeGraph()
        dg = DependencyGraph()
        intake_case_file = {
            "candidate_claims": [
                {
                    "claim_id": "claim1",
                    "claim_type": "employment_discrimination",
                    "label": "Employment Discrimination",
                    "required_elements": [],
                }
            ],
            "proof_leads": [],
        }

        questions = denoiser.generate_questions(kg, dg, max_questions=5, intake_case_file=intake_case_file)
        evidence_question = next(question for question in questions if question["type"] == "evidence")

        question_text = evidence_question["question"].lower()
        assert "hr complaint" in question_text
        assert "termination or discipline notice" in question_text

    def test_generate_questions_uses_housing_specific_proof_lead_prompt_text(self):
        """Housing discrimination proof prompts should ask for tenancy-specific evidence."""
        denoiser = ComplaintDenoiser()

        kg = KnowledgeGraph()
        dg = DependencyGraph()
        intake_case_file = {
            "candidate_claims": [
                {
                    "claim_id": "claim1",
                    "claim_type": "housing_discrimination",
                    "label": "Housing Discrimination",
                    "required_elements": [],
                }
            ],
            "proof_leads": [],
        }

        questions = denoiser.generate_questions(kg, dg, max_questions=5, intake_case_file=intake_case_file)
        evidence_question = next(question for question in questions if question["type"] == "evidence")

        question_text = evidence_question["question"].lower()
        assert "lease" in question_text
        assert "landlord messages" in question_text
    
    def test_calculate_noise_level(self):
        """Test noise level calculation."""
        denoiser = ComplaintDenoiser()
        
        kg = KnowledgeGraph()
        kg.add_entity(Entity("e1", "person", "John", confidence=0.8))
        
        dg = DependencyGraph()
        claim = DependencyNode("n1", NodeType.CLAIM, "Claim1", satisfied=True)
        dg.add_node(claim)
        
        noise = denoiser.calculate_noise_level(kg, dg)
        assert 0.0 <= noise <= 1.0

    def test_process_answer_timeline_without_claim_does_not_crash(self):
        denoiser = ComplaintDenoiser()
        kg = KnowledgeGraph()
        dg = DependencyGraph()

        q = {"question": "When did this happen?", "type": "timeline", "context": {}}
        updates = denoiser.process_answer(q, "2020-01-01", kg, dg)
        assert isinstance(updates, dict)


class TestPhaseManager:
    """Tests for PhaseManager."""
    
    def test_phase_manager_creation(self):
        """Test phase manager creation."""
        pm = PhaseManager()
        assert pm.get_current_phase() == ComplaintPhase.INTAKE
    
    def test_phase_advancement(self):
        """Test phase advancement."""
        pm = PhaseManager()
        
        # Mark intake as complete
        pm.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        pm.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        
        success = pm.advance_to_phase(ComplaintPhase.EVIDENCE)
        assert success
        assert pm.get_current_phase() == ComplaintPhase.EVIDENCE
    
    def test_convergence_detection(self):
        """Test convergence detection."""
        pm = PhaseManager()
        
        # Record iterations with decreasing loss
        for i in range(10):
            pm.record_iteration(0.5 - i * 0.01, {})
        
        assert pm.has_converged(window=5, threshold=0.1)
    
    def test_get_next_action(self):
        """Test next action recommendation."""
        pm = PhaseManager()
        action = pm.get_next_action()
        assert 'action' in action
        assert action['action'] == 'build_knowledge_graph'

    def test_intake_readiness_reports_semantic_blockers(self):
        """Test semantic blockers are included in intake readiness."""
        pm = PhaseManager()

        pm.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        pm.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        pm.update_phase_data(
            ComplaintPhase.INTAKE,
            'current_gaps',
            [
                {'type': 'missing_timeline'},
                {'type': 'unsupported_claim'},
            ],
        )

        readiness = pm.get_intake_readiness()
        action = pm.get_next_action()

        assert readiness['ready'] is False
        assert 'missing_timeline' in readiness['blockers']
        assert 'missing_proof_leads' in readiness['blockers']
        assert action['action'] == 'address_gaps'
        assert action['intake_blockers'] == readiness['blockers']

    def test_intake_readiness_allows_completion_without_blockers(self):
        """Test intake can complete when readiness blockers are absent."""
        pm = PhaseManager()

        pm.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        pm.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        pm.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', [])

        readiness = pm.get_intake_readiness()
        action = pm.get_next_action()

        assert readiness['ready'] is True
        assert readiness['score'] == 1.0
        assert pm.is_phase_complete(ComplaintPhase.INTAKE)
        assert action['action'] == 'complete_intake'

    def test_intake_action_addresses_remaining_gap_count_without_explicit_gap_list(self):
        """Test intake continues gap resolution when remaining gap count is still high."""
        pm = PhaseManager()

        pm.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 5)
        pm.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', False)
        pm.update_phase_data(ComplaintPhase.INTAKE, 'current_gaps', [])

        readiness = pm.get_intake_readiness()
        action = pm.get_next_action()

        assert 'unresolved_gaps' in readiness['blockers']
        assert action['action'] == 'address_gaps'
        assert action['gaps'] == []
        assert action['intake_blockers'] == readiness['blockers']

    def test_intake_readiness_includes_contradiction_details(self):
        """Test intake readiness returns concrete contradiction diagnostics."""
        pm = PhaseManager()

        pm.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        pm.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        pm.update_phase_data(
            ComplaintPhase.INTAKE,
            'intake_contradictions',
            {
                'candidate_count': 1,
                'candidates': [
                    {
                        'left_node_name': 'Termination before complaint',
                        'right_node_name': 'Complaint before termination',
                        'label': 'Termination before complaint vs Complaint before termination',
                    }
                ],
            },
        )

        readiness = pm.get_intake_readiness()

        assert readiness['contradiction_count'] == 1
        assert readiness['contradictions'][0]['left_node_name'] == 'Termination before complaint'
        assert 'contradiction_unresolved' in readiness['blockers']

    def test_intake_readiness_uses_structured_case_file_sections(self):
        """Structured intake sections should produce additive readiness blockers and counters."""
        pm = PhaseManager()

        pm.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        pm.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        pm.update_phase_data(
            ComplaintPhase.INTAKE,
            'intake_case_file',
            {
                'candidate_claims': [{'claim_type': 'employment_discrimination'}],
                'canonical_facts': [{'fact_id': 'fact_1'}],
                'proof_leads': [],
                'contradiction_queue': [],
                'intake_sections': {
                    'chronology': {'status': 'missing', 'missing_items': ['event dates']},
                    'actors': {'status': 'complete', 'missing_items': []},
                    'conduct': {'status': 'complete', 'missing_items': []},
                    'harm': {'status': 'complete', 'missing_items': []},
                    'remedy': {'status': 'missing', 'missing_items': ['requested outcome']},
                    'proof_leads': {'status': 'missing', 'missing_items': ['documents']},
                    'claim_elements': {'status': 'missing', 'missing_items': ['protected class']},
                },
            },
        )

        readiness = pm.get_intake_readiness()

        assert readiness['candidate_claim_count'] == 1
        assert readiness['canonical_fact_count'] == 1
        assert readiness['proof_lead_count'] == 0
        assert readiness['intake_sections']['chronology']['status'] == 'missing'
        assert 'missing_core_chronology' in readiness['blockers']
        assert 'missing_remedy' in readiness['blockers']
        assert 'missing_proof_leads' in readiness['blockers']
        assert 'missing_claim_element_facts' in readiness['blockers']

    def test_intake_readiness_tracks_blocking_contradictions_from_case_file(self):
        """Blocking contradictions in the case file should appear in readiness output."""
        pm = PhaseManager()

        pm.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        pm.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        pm.update_phase_data(
            ComplaintPhase.INTAKE,
            'intake_case_file',
            {
                'candidate_claims': [{'claim_type': 'employment_discrimination'}],
                'canonical_facts': [{'fact_id': 'fact_1'}],
                'proof_leads': [{'lead_id': 'lead_1'}],
                'contradiction_queue': [
                    {'contradiction_id': 'ctr_1', 'severity': 'blocking', 'status': 'open'}
                ],
                'intake_sections': {
                    'chronology': {'status': 'complete', 'missing_items': []},
                    'actors': {'status': 'complete', 'missing_items': []},
                    'conduct': {'status': 'complete', 'missing_items': []},
                    'harm': {'status': 'complete', 'missing_items': []},
                    'remedy': {'status': 'complete', 'missing_items': []},
                    'proof_leads': {'status': 'complete', 'missing_items': []},
                    'claim_elements': {'status': 'complete', 'missing_items': []},
                },
            },
        )

        readiness = pm.get_intake_readiness()

        assert readiness['blocking_contradictions'][0]['contradiction_id'] == 'ctr_1'
        assert 'blocking_contradiction' in readiness['blockers']
        assert readiness['criteria']['blocking_contradictions_resolved'] is False

    def test_evidence_phase_uses_claim_support_packets_for_completion(self):
        """Evidence completeness should be driven by explicit claim-support packet coverage when available."""
        pm = PhaseManager()
        pm.current_phase = ComplaintPhase.EVIDENCE

        pm.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'claim_support_packets',
            {
                'employment_discrimination': {
                    'claim_type': 'employment_discrimination',
                    'elements': [
                        {
                            'element_id': 'adverse_action',
                            'support_status': 'supported',
                            'recommended_next_step': '',
                            'contradiction_count': 0,
                        },
                        {
                            'element_id': 'causation',
                            'support_status': 'unsupported',
                            'recommended_next_step': 'collect_documentary_support',
                            'contradiction_count': 0,
                        },
                    ],
                }
            },
        )

        assert pm.is_phase_complete(ComplaintPhase.EVIDENCE)
        action = pm.get_next_action()
        assert action['action'] == 'complete_evidence'
        assert 'collect_documentary_support' in action['recommended_actions']

    def test_evidence_phase_blocks_on_contradicted_claim_support_packets(self):
        """Contradicted support packets should prevent evidence completion and suggest conflict resolution."""
        pm = PhaseManager()
        pm.current_phase = ComplaintPhase.EVIDENCE

        pm.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'claim_support_packets',
            {
                'retaliation': {
                    'claim_type': 'retaliation',
                    'elements': [
                        {
                            'element_id': 'causation',
                            'support_status': 'contradicted',
                            'recommended_next_step': 'resolve_support_conflicts',
                            'contradiction_count': 1,
                        }
                    ],
                }
            },
        )

        assert pm.is_phase_complete(ComplaintPhase.EVIDENCE) is False
        action = pm.get_next_action()
        assert action['action'] == 'resolve_support_conflicts'


class TestLegalGraph:
    """Tests for LegalGraph and LegalGraphBuilder."""
    
    def test_legal_graph_creation(self):
        """Test legal graph creation."""
        lg = LegalGraph()
        assert len(lg.elements) == 0
        assert len(lg.relations) == 0
    
    def test_add_legal_element(self):
        """Test adding legal elements."""
        lg = LegalGraph()
        elem = LegalElement(
            id="l1",
            element_type="statute",
            name="Title VII",
            citation="42 USC 2000e"
        )
        lg.add_element(elem)
        
        assert len(lg.elements) == 1
        assert lg.get_element("l1") == elem
    
    def test_legal_graph_builder(self):
        """Test building legal graph from statutes."""
        builder = LegalGraphBuilder()
        statutes = [
            {'name': 'Title VII', 'citation': '42 USC 2000e', 'description': 'Test'}
        ]
        claim_types = ['employment_discrimination']
        
        lg = builder.build_from_statutes(statutes, claim_types)
        assert len(lg.elements) > 0
    
    def test_rules_of_procedure(self):
        """Test building rules of civil procedure."""
        builder = LegalGraphBuilder()
        lg = builder.build_rules_of_procedure()
        
        assert len(lg.elements) > 0
        procedural_reqs = lg.get_elements_by_type('procedural_requirement')
        assert len(procedural_reqs) > 0


class TestNeurosymbolicMatcher:
    """Tests for NeurosymbolicMatcher."""
    
    def test_matcher_creation(self):
        """Test matcher creation."""
        matcher = NeurosymbolicMatcher()
        assert len(matcher.matching_results) == 0
    
    def test_match_claims_to_law(self):
        """Test matching claims against legal requirements."""
        matcher = NeurosymbolicMatcher()
        
        # Create simple graphs
        kg = KnowledgeGraph()
        kg.add_entity(Entity("e1", "claim", "Discrimination"))
        
        dg = DependencyGraph()
        claim = DependencyNode("n1", NodeType.CLAIM, "Discrimination", 
                              attributes={'claim_type': 'employment_discrimination'})
        dg.add_node(claim)
        
        lg = LegalGraph()
        req = LegalElement("l1", "requirement", "Protected Class", 
                          attributes={'applicable_claim_types': ['employment_discrimination']})
        lg.add_element(req)
        
        results = matcher.match_claims_to_law(kg, dg, lg)
        assert 'claims' in results
        assert 'overall_satisfaction' in results
        assert results['total_claims'] == 1
    
    def test_assess_claim_viability(self):
        """Test claim viability assessment."""
        matcher = NeurosymbolicMatcher()
        
        matching_results = {
            'total_claims': 2,
            'satisfied_claims': 1,
            'claims': [
                {'claim_name': 'Claim1', 'confidence': 0.9, 'satisfied': True},
                {'claim_name': 'Claim2', 'confidence': 0.3, 'satisfied': False}
            ],
            'gaps': []
        }
        
        viability = matcher.assess_claim_viability(matching_results)
        assert viability['overall_viability'] in ['strong', 'moderate', 'weak']
        assert len(viability['viable_claims']) == 1


class TestIntegration:
    """Integration tests for the complete three-phase system."""
    
    def test_complete_workflow(self):
        """Test complete three-phase workflow."""
        # Phase 1: Build graphs
        kg_builder = KnowledgeGraphBuilder()
        text = "I was discriminated against by my employer."
        kg = kg_builder.build_from_text(text)
        
        dg_builder = DependencyGraphBuilder()
        claims = [{'name': 'Discrimination', 'type': 'employment_discrimination'}]
        dg = dg_builder.build_from_claims(claims, {})
        
        # Phase 2: Denoising
        denoiser = ComplaintDenoiser()
        questions = denoiser.generate_questions(kg, dg, max_questions=5)
        assert len(questions) > 0
        
        noise = denoiser.calculate_noise_level(kg, dg)
        assert 0.0 <= noise <= 1.0
        
        # Phase 3: Legal matching
        lg_builder = LegalGraphBuilder()
        lg = lg_builder.build_rules_of_procedure()
        
        matcher = NeurosymbolicMatcher()
        results = matcher.match_claims_to_law(kg, dg, lg)
        assert 'claims' in results
    
    def test_phase_manager_workflow(self):
        """Test phase manager orchestrating workflow."""
        pm = PhaseManager()
        
        # Start in intake
        assert pm.get_current_phase() == ComplaintPhase.INTAKE
        
        # Get first action
        action = pm.get_next_action()
        assert action['action'] == 'build_knowledge_graph'
        
        # Simulate completing intake
        pm.update_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'dependency_graph', {})
        pm.update_phase_data(ComplaintPhase.INTAKE, 'remaining_gaps', 0)
        pm.update_phase_data(ComplaintPhase.INTAKE, 'denoising_converged', True)
        
        # Advance to evidence
        assert pm.advance_to_phase(ComplaintPhase.EVIDENCE)
        assert pm.get_current_phase() == ComplaintPhase.EVIDENCE
