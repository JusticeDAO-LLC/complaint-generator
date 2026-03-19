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

    def test_dependency_graph_builder_syncs_intake_timeline_facts_and_temporal_edges(self):
        builder = DependencyGraphBuilder()
        claims = [
            {'name': 'Retaliation', 'type': 'retaliation', 'description': 'Protected activity before adverse action'}
        ]

        dg = builder.build_from_claims(claims, {})
        intake_case_file = {
            'canonical_facts': [
                {
                    'fact_id': 'fact_1',
                    'text': 'Plaintiff complained about discrimination.',
                    'fact_type': 'timeline',
                    'claim_types': ['retaliation'],
                    'confidence': 0.8,
                    'event_date_or_range': 'March 1, 2025',
                    'temporal_context': {
                        'start_date': '2025-03-01',
                        'end_date': '2025-03-01',
                        'relative_markers': [],
                    },
                },
                {
                    'fact_id': 'fact_2',
                    'text': 'Employer terminated Plaintiff.',
                    'fact_type': 'timeline',
                    'claim_types': ['retaliation'],
                    'confidence': 0.9,
                    'event_date_or_range': 'April 15, 2025',
                    'temporal_context': {
                        'start_date': '2025-04-15',
                        'end_date': '2025-04-15',
                        'relative_markers': [],
                    },
                },
            ],
            'timeline_relations': [
                {
                    'source_fact_id': 'fact_1',
                    'target_fact_id': 'fact_2',
                    'relation_type': 'before',
                    'confidence': 'high',
                }
            ],
        }

        builder.sync_intake_timeline_to_graph(dg, intake_case_file)

        temporal_nodes = [
            node for node in dg.nodes.values()
            if node.node_type == NodeType.FACT and node.attributes.get('timeline_fact_node')
        ]
        assert len(temporal_nodes) == 2
        assert {node.attributes['source_fact_id'] for node in temporal_nodes} == {'fact_1', 'fact_2'}

        before_edges = [
            dep for dep in dg.dependencies.values()
            if dep.dependency_type == DependencyType.BEFORE
        ]
        assert len(before_edges) == 1

        support_edges = [
            dep for dep in dg.dependencies.values()
            if dep.dependency_type == DependencyType.SUPPORTS
            and dg.get_node(dep.source_id).attributes.get('timeline_fact_node')
        ]
        assert len(support_edges) == 2

    def test_dependency_graph_detects_temporal_cycles_and_reverse_before_conflicts(self):
        graph = DependencyGraph()
        node_a = DependencyNode(id='fact_a', node_type=NodeType.FACT, name='Complaint made')
        node_b = DependencyNode(id='fact_b', node_type=NodeType.FACT, name='Termination issued')
        graph.add_node(node_a)
        graph.add_node(node_b)
        graph.add_dependency(Dependency('dep_1', 'fact_a', 'fact_b', DependencyType.BEFORE, required=False))
        graph.add_dependency(Dependency('dep_2', 'fact_b', 'fact_a', DependencyType.BEFORE, required=False))

        issues = graph.get_temporal_inconsistency_issues()

        issue_types = {issue['issue_type'] for issue in issues}
        assert 'temporal_cycle' in issue_types
        assert 'temporal_reverse_before' in issue_types


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

    def test_collect_question_candidates_exposes_candidate_sources_and_intents(self):
        """Candidate collection should surface reasoning provenance before final question rendering."""
        denoiser = ComplaintDenoiser()

        kg = KnowledgeGraph()
        kg.add_entity(Entity("claim1", "claim", "Employment Discrimination Claim", attributes={"claim_type": "employment_discrimination"}))

        dg = DependencyGraph()
        claim = DependencyNode("n1", NodeType.CLAIM, "Employment Discrimination Claim")
        dg.add_node(claim)

        intake_case_file = {
            "candidate_claims": [
                {
                    "claim_id": "claim1",
                    "claim_type": "employment_discrimination",
                    "label": "Employment Discrimination",
                    "required_elements": [
                        {
                            "element_id": "adverse_action",
                            "label": "Adverse employment action or harassment",
                            "blocking": True,
                            "status": "missing",
                        }
                    ],
                }
            ],
            "proof_leads": [],
        }

        candidates = denoiser.collect_question_candidates(kg, dg, max_questions=5, intake_case_file=intake_case_file)

        assert candidates
        first_requirement = next(question for question in candidates if question["type"] == "requirement")
        first_evidence = next(question for question in candidates if question["type"] == "evidence")
        assert first_requirement["candidate_source"] == "intake_claim_element_gap"
        assert first_requirement["question_intent"]["intent_type"] == "claim_element_question"
        assert first_requirement["ranking_explanation"]["candidate_source"] == "intake_claim_element_gap"
        assert first_requirement["ranking_explanation"]["question_goal"] == "establish_element"
        assert first_requirement["ranking_explanation"]["phase1_section"] == "claim_elements"
        assert first_evidence["candidate_source"] == "intake_proof_gap"
        assert first_evidence["question_intent"]["intent_type"] == "proof_lead_question"
        assert first_evidence["ranking_explanation"]["question_goal"] == "identify_supporting_proof"

    def test_select_question_candidates_uses_selector_override_when_available(self):
        """Selection should honor an explicit override so routers/provers can choose among candidates."""
        denoiser = ComplaintDenoiser()
        candidates = [
            {
                "type": "timeline",
                "question": "When did this happen?",
                "priority": "high",
                "proof_priority": 0,
                "candidate_source": "knowledge_graph_gap",
            },
            {
                "type": "evidence",
                "question": "What proof do you have?",
                "priority": "high",
                "proof_priority": 1,
                "candidate_source": "intake_proof_gap",
            },
        ]

        def selector(items, max_questions=10):
            return [items[1], items[0]][:max_questions]

        selected = denoiser.select_question_candidates(candidates, max_questions=2, selector=selector)

        assert selected[0]["type"] == "evidence"
        assert selected[1]["type"] == "timeline"

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
        assert requirement_question["question_intent"]["intent_type"] == "claim_element_question"
        assert requirement_question["question_intent"]["question_goal"] == "establish_element"
        assert "employer" in requirement_question["question_intent"]["actor_roles"]
        assert "pay_stub" in requirement_question["question_intent"]["evidence_classes"]

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
        assert requirement_question["question_intent"]["intent_type"] == "claim_element_question"
        assert requirement_question["question_intent"]["question_strategy"] == "ontology_guided_element_probe"
        assert "landlord" in requirement_question["question_intent"]["actor_roles"]

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
        assert evidence_question["question_intent"]["intent_type"] == "proof_lead_question"
        assert evidence_question["question_intent"]["question_goal"] == "identify_supporting_proof"
        assert "hr_complaint" in evidence_question["question_intent"]["evidence_classes"]

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
        assert evidence_question["question_intent"]["intent_type"] == "proof_lead_question"
        assert "landlord" in evidence_question["question_intent"]["actor_roles"]

    def test_generate_evidence_questions_prioritizes_alignment_tasks(self):
        """Evidence questions should prioritize shared unresolved claim-element tasks."""
        denoiser = ComplaintDenoiser()

        kg = KnowledgeGraph()
        dg = DependencyGraph()

        questions = denoiser.generate_evidence_questions(
            kg,
            dg,
            evidence_gaps=[{'id': 'gap_1', 'name': 'causation evidence', 'related_claim': 'retaliation'}],
            alignment_evidence_tasks=[
                {
                    'action': 'fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'protected_activity',
                    'claim_element_label': 'Protected activity',
                    'support_status': 'unsupported',
                    'blocking': True,
                }
            ],
            max_questions=3,
        )

        assert questions
        assert questions[0]['context']['alignment_task'] is True
        assert questions[0]['context']['claim_element_id'] == 'protected_activity'
        assert 'Protected activity' in questions[0]['question']
    
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

    def test_formalization_next_action_builds_legal_graph_first(self):
        """Formalization should start by building the legal graph when it is missing."""
        pm = PhaseManager()
        pm.current_phase = ComplaintPhase.FORMALIZATION

        action = pm.get_next_action()

        assert action['action'] == 'build_legal_graph'

    def test_formalization_next_action_runs_matching_after_legal_graph_exists(self):
        """Formalization should request neurosymbolic matching once the legal graph is available."""
        pm = PhaseManager()
        pm.current_phase = ComplaintPhase.FORMALIZATION
        pm.update_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph', {'nodes': ['rule_1']})

        action = pm.get_next_action()

        assert action['action'] == 'perform_neurosymbolic_matching'

    def test_formalization_next_action_generates_formal_complaint_after_matching(self):
        """Formalization should move to complaint generation after matching completes."""
        pm = PhaseManager()
        pm.current_phase = ComplaintPhase.FORMALIZATION
        pm.update_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph', {'nodes': ['rule_1']})
        pm.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_complete', True)

        action = pm.get_next_action()

        assert action['action'] == 'generate_formal_complaint'

    def test_formalization_next_action_completes_after_complaint_generation(self):
        """Formalization should report completion once a formal complaint exists."""
        pm = PhaseManager()
        pm.current_phase = ComplaintPhase.FORMALIZATION
        pm.update_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph', {'nodes': ['rule_1']})
        pm.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_complete', True)
        pm.update_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint', {'draft_text': 'Complaint draft'})

        action = pm.get_next_action()

        assert action['action'] == 'complete_formalization'

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
        assert 'missing_minimum_proof_path' in readiness['blockers']
        assert readiness['criteria']['case_theory_coherent'] is False
        assert readiness['criteria']['minimum_proof_path_present'] is False

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
                'summary_snapshots': [{'candidate_claim_count': 1, 'proof_lead_count': 1}],
                'complainant_summary_confirmation': {
                    'confirmed': True,
                    'confirmed_summary_snapshot': {'candidate_claim_count': 1, 'proof_lead_count': 1},
                    'current_summary_snapshot': {'candidate_claim_count': 1, 'proof_lead_count': 1},
                },
                'contradiction_queue': [
                    {
                        'contradiction_id': 'ctr_1',
                        'severity': 'blocking',
                        'status': 'open',
                        'recommended_resolution_lane': 'request_document',
                        'external_corroboration_required': True,
                    }
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
        assert readiness['blocking_contradictions'][0]['recommended_resolution_lane'] == 'request_document'
        assert readiness['blocking_contradictions'][0]['external_corroboration_required'] is True
        assert readiness['contradictions'][0]['recommended_resolution_lane'] == 'request_document'
        assert 'blocking_contradiction' in readiness['blockers']
        assert readiness['criteria']['blocking_contradictions_resolved'] is False
        assert readiness['criteria']['blocking_contradictions_resolved_or_escalated'] is False
        assert readiness['criteria']['minimum_proof_path_present'] is True

    def test_intake_readiness_allows_escalated_blocking_contradictions_when_summary_confirmed(self):
        """Escalated blocking contradictions should not block intake handoff once the summary is confirmed."""
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
                'summary_snapshots': [{'candidate_claim_count': 1, 'proof_lead_count': 1}],
                'complainant_summary_confirmation': {
                    'confirmed': True,
                    'confirmed_summary_snapshot': {'candidate_claim_count': 1, 'proof_lead_count': 1},
                    'current_summary_snapshot': {'candidate_claim_count': 1, 'proof_lead_count': 1},
                },
                'contradiction_queue': [
                    {
                        'contradiction_id': 'ctr_2',
                        'severity': 'blocking',
                        'current_resolution_status': 'awaiting_third_party_record',
                        'recommended_resolution_lane': 'seek_external_record',
                    }
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

        assert readiness['blocking_contradictions'] == []
        assert readiness['escalated_blocking_contradictions'][0]['contradiction_id'] == 'ctr_2'
        assert 'blocking_contradiction' not in readiness['blockers']
        assert 'complainant_summary_confirmation_required' not in readiness['blockers']
        assert readiness['criteria']['blocking_contradictions_resolved_or_escalated'] is True
        assert readiness['criteria']['complainant_summary_confirmed'] is True

    def test_intake_readiness_requires_complainant_summary_confirmation_for_structured_case_file(self):
        """Structured intake handoff should stay blocked until the complainant confirms the latest summary snapshot."""
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
                'summary_snapshots': [{'candidate_claim_count': 1, 'proof_lead_count': 1}],
                'complainant_summary_confirmation': {
                    'confirmed': False,
                    'current_summary_snapshot': {'candidate_claim_count': 1, 'proof_lead_count': 1},
                },
                'contradiction_queue': [],
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

        assert readiness['criteria']['complainant_summary_confirmed'] is False
        assert 'complainant_summary_confirmation_required' in readiness['blockers']

    def test_evidence_phase_blocks_on_unresolved_claim_support_packets_without_review_path(self):
        """Unresolved packet elements should block evidence completion until support or escalation is explicit."""
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

        assert pm.is_phase_complete(ComplaintPhase.EVIDENCE) is False
        action = pm.get_next_action()
        assert action['action'] == 'collect_documentary_support'
        assert action['claim_element_id'] == 'causation'
        assert 'collect_documentary_support' in action['recommended_actions']

    def test_evidence_phase_completes_with_reviewable_escalation_path(self):
        """Explicit reviewable escalation paths should allow evidence completion without pretending support is present."""
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
                            'recommended_next_step': 'awaiting_complainant_record',
                            'resolution_status': 'awaiting_complainant_record',
                            'contradiction_count': 0,
                        },
                    ],
                }
            },
        )

        assert pm.is_phase_complete(ComplaintPhase.EVIDENCE)
        action = pm.get_next_action()
        assert action['action'] == 'complete_evidence'
        assert pm.get_phase_data(ComplaintPhase.EVIDENCE, 'claim_support_unresolved_without_review_path_count') == 0
        assert pm.get_phase_data(ComplaintPhase.EVIDENCE, 'reviewable_escalation_ratio') == 0.5

    def test_evidence_phase_completes_with_task_level_awaiting_testimony_status(self):
        """Task-level awaiting_testimony should count as a reviewable escalation even when the packet element is still unsupported."""
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
                            'support_status': 'unsupported',
                            'recommended_next_step': 'collect_witness_support',
                            'contradiction_count': 0,
                        },
                    ],
                }
            },
        )
        pm.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_evidence_tasks',
            [
                {
                    'task_id': 'retaliation:causation:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'causation',
                    'support_status': 'unsupported',
                    'resolution_status': 'awaiting_testimony',
                }
            ],
        )

        assert pm.is_phase_complete(ComplaintPhase.EVIDENCE)
        action = pm.get_next_action()
        assert action['action'] == 'complete_evidence'
        assert pm.get_phase_data(ComplaintPhase.EVIDENCE, 'claim_support_unresolved_without_review_path_count') == 0
        assert pm.get_phase_data(ComplaintPhase.EVIDENCE, 'reviewable_escalation_ratio') == 1.0

    def test_evidence_phase_prioritizes_validation_when_promotion_drift_is_flagged(self):
        """Promotion drift should steer next_action toward validation before generic evidence completion."""
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
                            'support_status': 'unsupported',
                            'recommended_next_step': 'collect_witness_support',
                            'resolution_status': 'awaiting_testimony',
                            'contradiction_count': 0,
                        },
                    ],
                }
            },
        )
        pm.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_evidence_tasks',
            [
                {
                    'task_id': 'retaliation:causation:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'causation',
                    'support_status': 'unsupported',
                    'resolution_status': 'awaiting_testimony',
                }
            ],
        )
        pm.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_promotion_drift_summary',
            {
                'drift_flag': True,
                'promoted_count': 3,
                'resolved_supported_count': 1,
                'pending_conversion_count': 2,
                'drift_ratio': 0.6667,
            },
        )
        pm.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_task_update_history',
            [
                {
                    'task_id': 'retaliation:causation:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'causation',
                    'resolution_status': 'promoted_to_document',
                    'status': 'resolved',
                    'evidence_sequence': 1,
                },
                {
                    'task_id': 'retaliation:causation:fill_evidence_gaps',
                    'claim_type': 'retaliation',
                    'claim_element_id': 'causation',
                    'resolution_status': 'promoted_to_testimony',
                    'status': 'resolved',
                    'evidence_sequence': 2,
                },
            ],
        )

        assert pm.is_phase_complete(ComplaintPhase.EVIDENCE)
        action = pm.get_next_action()
        assert action['action'] == 'validate_promoted_support'
        assert action['pending_conversion_count'] == 2
        assert action['drift_summary']['drift_flag'] is True
        assert action['claim_type'] == 'retaliation'
        assert action['claim_element_id'] == 'causation'

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

    def test_evidence_phase_prioritizes_alignment_tasks_for_shared_unsupported_elements(self):
        """Cross-phase shared unsupported elements should drive evidence next actions."""
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
        pm.update_phase_data(
            ComplaintPhase.EVIDENCE,
            'alignment_evidence_tasks',
            [
                {
                    'action': 'fill_evidence_gaps',
                    'claim_type': 'employment_discrimination',
                    'claim_element_id': 'causation',
                    'claim_element_label': 'Causation',
                    'support_status': 'unsupported',
                    'blocking': True,
                }
            ],
        )

        assert pm.is_phase_complete(ComplaintPhase.EVIDENCE) is False
        action = pm.get_next_action()
        assert action['action'] == 'fill_evidence_gaps'
        assert action['claim_type'] == 'employment_discrimination'
        assert action['claim_element_id'] == 'causation'


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
