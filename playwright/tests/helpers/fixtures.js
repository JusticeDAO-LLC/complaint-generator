const documentGenerationResponse = {
  generated_at: '2026-03-22T12:00:00Z',
  artifacts: {
    txt: {
      filename: 'formal-complaint.txt',
      path: '/tmp/generated_documents/formal-complaint.txt',
      size_bytes: 2048,
      download_url: '/api/documents/download?path=/tmp/generated_documents/formal-complaint.txt',
    },
    packet: {
      filename: 'filing-packet.zip',
      path: '/tmp/generated_documents/filing-packet.zip',
      size_bytes: 4096,
      download_url: '/api/documents/download?path=/tmp/generated_documents/filing-packet.zip',
    },
  },
  review_intent: {
    claim_type: 'retaliation',
    user_id: 'demo-user',
    section: 'claims_for_relief',
    follow_up_support_kind: 'authority',
  },
  review_links: {
    dashboard_url: '/claim-support-review?claim_type=retaliation&user_id=demo-user&section=claims_for_relief&follow_up_support_kind=authority',
  },
  workflow_phase_plan: {
    prioritized_phase_name: 'document_generation',
    prioritized_phase_status: 'ready',
    primary_recommended_action: 'open_review_dashboard',
  },
  drafting_readiness: {
    status: 'ready',
    claims: [
      {
        claim_type: 'retaliation',
        status: 'ready',
        warnings: [],
      },
    ],
  },
  draft: {
    court_header: 'IN THE UNITED STATES DISTRICT COURT',
    case_caption: {
      plaintiffs: ['Jane Doe'],
      defendants: ['Acme Corporation'],
      case_number: '26-cv-1234',
      document_title: 'COMPLAINT',
    },
    nature_of_action: ['This civil action challenges unlawful retaliation.'],
    summary_of_facts: [
      'Jane Doe reported discrimination to human resources.',
      'Acme Corporation terminated Jane Doe days later.',
    ],
    factual_allegation_paragraphs: [
      'Jane Doe worked for Acme Corporation.',
      'After protected activity, Acme terminated Jane Doe.',
    ],
    legal_standards: ['Title VII prohibits retaliation against employees.'],
    claims_for_relief: [
      {
        claim_type: 'retaliation',
        count_title: 'First Claim for Relief',
        legal_standards: ['Protected activity and adverse action establish retaliation.'],
        supporting_facts: [
          'Plaintiff made a protected complaint to HR.',
          'Defendant terminated Plaintiff after the complaint.',
        ],
      },
    ],
    requested_relief: ['Back pay', 'Reinstatement', 'Compensatory damages'],
    draft_text: 'Plaintiff Jane Doe alleges retaliation in violation of Title VII.',
    exhibits: [
      {
        label: 'Exhibit 1',
        title: 'HR Complaint Email',
        summary: 'Email reporting discrimination.',
        link: 'https://example.test/hr-complaint',
      },
    ],
    signature_block: {
      signature_line: '/s/ Jane Doe',
      name: 'Jane Doe',
      title: 'Plaintiff, Pro Se',
      contact: 'jane@example.test',
    },
    verification: {
      title: 'Verification',
      text: 'I declare under penalty of perjury that the foregoing is true and correct.',
    },
    certificate_of_service: {
      title: 'Certificate of Service',
      text: 'I served the complaint by first-class mail.',
    },
  },
};

function normalizeFragment(value, fallback) {
  const text = String(value || '')
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/[.?!,;:]+$/g, '');
  return text || fallback;
}

function sentenceFragment(value, fallback) {
  const text = normalizeFragment(value, fallback);
  if (!text) {
    return fallback;
  }
  return /^[A-Za-z]/.test(text) ? `${text.charAt(0).toLowerCase()}${text.slice(1)}` : text;
}

const reviewPayload = {
  claim_coverage_summary: {
    retaliation: {
      status_counts: {
        covered: 1,
        partially_supported: 1,
        missing: 1,
      },
    },
  },
  claim_coverage_matrix: {
    retaliation: {
      elements: [
        {
          element_id: 'retaliation:1',
          element_text: 'Protected activity',
          support_status: 'covered',
          supporting_evidence_count: 1,
          supporting_authority_count: 1,
          cited_authorities: ['Title VII'],
        },
        {
          element_id: 'retaliation:2',
          element_text: 'Adverse action',
          support_status: 'missing',
          missing_support_kinds: ['document'],
        },
      ],
    },
  },
  follow_up_plan: {
    retaliation: {
      tasks: [
        {
          execution_id: 7,
          claim_type: 'retaliation',
          claim_element_id: 'retaliation:2',
          claim_element_text: 'Adverse action',
          support_kind: 'document',
          section_focus: 'summary_of_facts',
          task_status: 'pending',
          summary: 'Collect the termination email and supporting timeline details.',
        },
      ],
    },
  },
  follow_up_plan_summary: {
    retaliation: {
      task_count: 1,
      pending_count: 1,
      completed_count: 0,
      archive_capture_count: 1,
      fallback_authority_count: 0,
      low_quality_record_count: 0,
      parse_quality_task_count: 0,
      supportive_authority_count: 1,
      adverse_authority_count: 0,
      unresolved_temporal_gap_count: 0,
      normalized_task_count: 1,
      follow_up_source_context_count: 1,
    },
  },
  follow_up_history: {
    retaliation: [
      {
        execution_id: 5,
        claim_element_id: 'retaliation:1',
        claim_element_text: 'Protected activity',
        support_kind: 'authority',
        status: 'completed',
        resolution_status: 'resolved_supported',
        notes: 'Authority support already attached.',
      },
    ],
  },
  follow_up_history_summary: {
    retaliation: {
      execution_count: 1,
      normalized_history_count: 1,
    },
  },
  question_recommendations: {
    retaliation: [
      {
        target_claim_element_id: 'retaliation:2',
        target_claim_element_text: 'Adverse action',
        question_text: 'When were you terminated after complaining to HR?',
        question_reason: 'This clarifies temporal proximity.',
        question_lane: 'testimony',
        expected_proof_gain: 'high',
        current_status: 'missing',
        supporting_evidence_summary: '1 HR complaint email on file',
      },
    ],
  },
  testimony_records: {
    retaliation: [
      {
        claim_element_id: 'retaliation:1',
        claim_element_text: 'Protected activity',
        timestamp: '2026-03-22T12:05:00Z',
        event_date: '2026-03-10',
        actor: 'Jane Doe',
        act: 'Reported discrimination',
        target: 'HR department',
        harm: 'Triggered retaliation sequence',
        firsthand_status: 'firsthand',
        source_confidence: 0.95,
        raw_narrative: 'I reported discrimination to HR and kept a copy of my complaint email.',
      },
    ],
  },
  testimony_summary: {
    retaliation: {
      record_count: 1,
      linked_element_count: 1,
      firsthand_status_counts: {
        firsthand: 1,
      },
      confidence_bucket_counts: {
        high: 1,
      },
    },
  },
  document_artifacts: {
    retaliation: [
      {
        description: 'HR complaint email',
        filename: 'hr-complaint-email.txt',
        timestamp: '2026-03-22T12:10:00Z',
        parse_status: 'parsed',
        chunk_count: 2,
        evidence_type: 'document',
        claim_element_text: 'Protected activity',
        graph_status: 'ready',
        fact_count: 1,
        parsed_text_preview: 'Email to HR reporting discrimination and requesting intervention.',
        fact_previews: [
          {
            fact_id: 'fact-1',
            text: 'Jane Doe reported discrimination to HR before termination.',
            quality_tier: 'high',
            confidence: 0.93,
            source_chunk_ids: ['chunk-1'],
          },
        ],
      },
    ],
  },
  document_summary: {
    retaliation: {
      record_count: 1,
      linked_element_count: 1,
      total_chunk_count: 2,
      total_fact_count: 1,
      low_quality_record_count: 0,
      graph_ready_record_count: 1,
      parse_status_counts: {
        parsed: 1,
      },
    },
  },
  claim_reasoning_review: {
    retaliation: {
      flagged_items: [],
    },
  },
  intake_status: {
    overall_status: 'warning',
    readiness_criteria: [
      {
        label: 'Document evidence collected',
        status: 'warning',
      },
    ],
    contradictions: [],
  },
  intake_case_summary: {
    current_summary_snapshot: {
      candidate_claim_count: 1,
      canonical_fact_count: 2,
      proof_lead_count: 1,
    },
  },
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

const workspaceIntakeQuestions = [
  {
    id: 'party_name',
    label: 'Complainant name',
    prompt: 'Who is filing this complaint?',
    placeholder: 'Jane Doe',
  },
  {
    id: 'opposing_party',
    label: 'Opposing party',
    prompt: 'Who is the complaint against?',
    placeholder: 'Acme Corporation',
  },
  {
    id: 'protected_activity',
    label: 'Protected activity',
    prompt: 'What protected activity did the complainant engage in?',
    placeholder: 'Reported discrimination to HR',
  },
  {
    id: 'adverse_action',
    label: 'Adverse action',
    prompt: 'What adverse action followed?',
    placeholder: 'Termination',
  },
  {
    id: 'timeline',
    label: 'Timeline',
    prompt: 'What is the timing between the protected activity and the adverse action?',
    placeholder: 'Complaint on March 8, termination on March 10',
  },
  {
    id: 'harm',
    label: 'Harm',
    prompt: 'What harm did the complainant suffer?',
    placeholder: 'Lost wages and benefits',
  },
];

const workspaceClaimElements = [
  { id: 'protected_activity', label: 'Protected activity' },
  { id: 'employer_knowledge', label: 'Employer knowledge' },
  { id: 'adverse_action', label: 'Adverse action' },
  { id: 'causation', label: 'Causation' },
  { id: 'harm', label: 'Harm' },
];

const workspaceToolList = [
  { name: 'complaint.create_identity', description: 'Create a decentralized identity for browser or CLI use.' },
  { name: 'complaint.list_intake_questions', description: 'List the complaint intake questions used across browser, CLI, and MCP flows.' },
  { name: 'complaint.list_claim_elements', description: 'List the tracked claim elements used for evidence and review.' },
  { name: 'complaint.start_session', description: 'Load or initialize a complaint workspace session.' },
  { name: 'complaint.submit_intake', description: 'Save complaint intake answers.' },
  { name: 'complaint.save_evidence', description: 'Save testimony or document evidence to the workspace.' },
  { name: 'complaint.review_case', description: 'Return the current support matrix and evidence review.' },
  { name: 'complaint.build_mediator_prompt', description: 'Build a testimony-ready chat mediator prompt from the shared case synopsis and support gaps.' },
  { name: 'complaint.get_complaint_readiness', description: 'Estimate whether the current complaint record is ready for drafting, still building, or already in draft refinement.' },
  { name: 'complaint.get_ui_readiness', description: 'Return the latest UI readiness and client-safety posture for the shared complaint workflow.' },
  { name: 'complaint.get_workflow_capabilities', description: 'Summarize which complaint-workflow abilities are currently available for the session.' },
  { name: 'complaint.generate_complaint', description: 'Generate a complaint draft from intake and evidence.' },
  { name: 'complaint.update_draft', description: 'Persist edits to the generated complaint draft.' },
  { name: 'complaint.export_complaint_packet', description: 'Export the current lawsuit complaint packet with intake, evidence, review, and draft content.' },
  { name: 'complaint.export_complaint_markdown', description: 'Export the generated complaint as a downloadable Markdown artifact.' },
  { name: 'complaint.export_complaint_pdf', description: 'Export the generated complaint as a downloadable PDF artifact.' },
  { name: 'complaint.analyze_complaint_output', description: 'Analyze the generated complaint output and turn filing-shape gaps into concrete UI/UX suggestions.' },
  { name: 'complaint.review_generated_exports', description: 'Review generated complaint export artifacts through llm_router and turn filing-output weaknesses into UI/UX repair suggestions.' },
  { name: 'complaint.update_case_synopsis', description: 'Persist a shared case synopsis that stays visible across workspace, CLI, and MCP flows.' },
  { name: 'complaint.reset_session', description: 'Clear the complaint workspace session.' },
  { name: 'complaint.review_ui', description: 'Review Playwright screenshot artifacts, optionally run an iterative UI/UX workflow, and produce a router-backed MCP dashboard critique.' },
  { name: 'complaint.optimize_ui', description: 'Run the closed-loop screenshot, llm_router, actor/critic optimizer, and revalidation workflow for the complaint dashboard UI.' },
  { name: 'complaint.run_browser_audit', description: 'Run the Playwright end-to-end complaint browser audit that drives chat, intake, evidence, review, draft, and builder surfaces.' },
];

function createWorkspaceState(userId) {
  return {
    user_id: userId,
    claim_type: 'retaliation',
    intake_answers: {},
    intake_history: [],
    evidence: {
      testimony: [],
      documents: [],
    },
    draft: null,
    case_synopsis: '',
  };
}

function buildWorkspaceQuestionStatus(state) {
  return workspaceIntakeQuestions.map((question) => {
    const answer = String((state.intake_answers || {})[question.id] || '');
    return {
      ...question,
      answer,
      is_answered: Boolean(answer.trim()),
    };
  });
}

function buildWorkspaceSupportMatrix(state) {
  const answers = state.intake_answers || {};
  const testimony = ((state.evidence || {}).testimony || []);
  const documents = ((state.evidence || {}).documents || []);
  return workspaceClaimElements.map((element) => {
    const intakeSupported = Boolean(answers[element.id])
      || (element.id === 'employer_knowledge' && Boolean(answers.protected_activity))
      || (element.id === 'causation' && Boolean(answers.timeline));
    const testimonyMatches = testimony.filter((item) => item.claim_element_id === element.id);
    const documentMatches = documents.filter((item) => item.claim_element_id === element.id);
    const supportCount = testimonyMatches.length + documentMatches.length + (intakeSupported ? 1 : 0);
    return {
      id: element.id,
      label: element.label,
      supported: supportCount > 0,
      intake_supported: intakeSupported,
      testimony_count: testimonyMatches.length,
      document_count: documentMatches.length,
      support_count: supportCount,
      status: supportCount > 0 ? 'supported' : 'needs_support',
    };
  });
}

function buildWorkspaceCaseSynopsis(state) {
  const customSynopsis = String(state.case_synopsis || '').trim();
  if (customSynopsis) {
    return customSynopsis;
  }
  const answers = state.intake_answers || {};
  const matrix = buildWorkspaceSupportMatrix(state);
  const supportedElements = matrix.filter((item) => item.supported).length;
  const missingElements = matrix.filter((item) => !item.supported).length;
  const evidence = state.evidence || {};
  const evidenceCount = (evidence.testimony || []).length + (evidence.documents || []).length;
  return `${answers.party_name || 'The complainant'} is pursuing a retaliation complaint against ${answers.opposing_party || 'the opposing party'}. The current theory is that ${answers.party_name || 'the complainant'} ${answers.protected_activity || 'engaged in protected activity'}, then experienced ${answers.adverse_action || 'an adverse action'}. The reported harm is ${answers.harm || 'described harm'}. Timeline posture: ${answers.timeline || 'a still-developing timeline'}. Current support posture: ${supportedElements} supported elements, ${missingElements} open gaps, ${evidenceCount} saved evidence items.`;
}

function buildWorkspaceReview(state) {
  const matrix = buildWorkspaceSupportMatrix(state);
  const supported = matrix.filter((item) => item.supported);
  const missing = matrix.filter((item) => !item.supported);
  const evidence = state.evidence || {};
  return {
    claim_type: state.claim_type || 'retaliation',
    case_synopsis: buildWorkspaceCaseSynopsis(state),
    support_matrix: matrix,
    overview: {
      supported_elements: supported.length,
      missing_elements: missing.length,
      testimony_items: (evidence.testimony || []).length,
      document_items: (evidence.documents || []).length,
    },
    recommended_actions: [
      {
        title: 'Collect more corroboration',
        detail: missing.length
          ? 'Add testimony or documents to any unsupported claim element.'
          : 'All core elements have at least one support source.',
      },
      {
        title: 'Check timing',
        detail: 'Close timing between protected activity and adverse action strengthens causation.',
      },
    ],
    testimony: clone(evidence.testimony || []),
    documents: clone(evidence.documents || []),
  };
}

function buildWorkspaceDraft(state, requestedRelief, options = {}) {
  const answers = state.intake_answers || {};
  const existingDraft = state.draft || {};
  const review = buildWorkspaceReview(state);
  const overview = review.overview || {};
  const evidence = state.evidence || { testimony: [], documents: [] };
  const relief = requestedRelief || existingDraft.requested_relief || ['Compensatory damages', 'Back pay', 'Injunctive relief'];
  const synopsis = buildWorkspaceCaseSynopsis(state);
  const claimType = String(state.claim_type || 'retaliation');
  const claimTypeTitle = claimType.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
  const protectedActivity = sentenceFragment(answers.protected_activity, 'engaged in protected activity');
  const adverseAction = sentenceFragment(answers.adverse_action, 'suffered an adverse action');
  const timeline = sentenceFragment(answers.timeline, 'the events occurred close in time');
  const harm = sentenceFragment(answers.harm, 'suffered compensable harm');
  const complaintHeading = claimType === 'retaliation'
    ? 'COMPLAINT FOR RETALIATION'
    : `COMPLAINT FOR ${claimType.replace(/_/g, ' ').toUpperCase()}`;
  const countHeading = claimType === 'retaliation'
    ? 'COUNT I - RETALIATION'
    : `COUNT I - ${claimType.replace(/_/g, ' ').toUpperCase()}`;
  const natureOfAction = {
    retaliation: `1. ${answers.party_name || 'Plaintiff'} brings this retaliation complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from ${answers.opposing_party || 'Defendant'}'s retaliatory response after ${answers.party_name || 'Plaintiff'} ${protectedActivity}.`,
    employment_discrimination: `1. ${answers.party_name || 'Plaintiff'} brings this employment discrimination complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from discriminatory workplace treatment, unequal terms or conditions, and resulting harm.`,
    housing_discrimination: `1. ${answers.party_name || 'Plaintiff'} brings this housing discrimination complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from discriminatory denial, limitation, interference, or retaliation affecting housing rights or benefits.`,
    due_process_failure: `1. ${answers.party_name || 'Plaintiff'} brings this due process complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from adverse action imposed without the notice, hearing, review, or procedural protections required by law.`,
    consumer_protection: `1. ${answers.party_name || 'Plaintiff'} brings this consumer protection complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from unfair, deceptive, fraudulent, or otherwise unlawful business practices that caused injury.`,
  }[claimType] || `1. ${answers.party_name || 'Plaintiff'} brings this ${claimType.replace(/_/g, ' ')} complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from unlawful conduct that injured ${answers.party_name || 'Plaintiff'}.`;
  const reliefParagraph = {
    retaliation: `2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy Defendant's retaliatory acts, restore lost compensation, and address the harm flowing from ${adverseAction}.`,
    employment_discrimination: `2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy discriminatory employment practices, restore lost opportunities, and address the harm flowing from ${adverseAction}.`,
    housing_discrimination: `2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy discriminatory housing practices, preserve housing stability, and address the harm flowing from ${adverseAction}.`,
    due_process_failure: `2. Plaintiff seeks declaratory relief, equitable relief, damages, and such further relief as may be just to remedy the procedural deprivation and the harm flowing from ${adverseAction}.`,
    consumer_protection: `2. Plaintiff seeks damages, restitution, equitable relief, and such further relief as may be just to remedy deceptive or unfair consumer practices and the harm flowing from ${adverseAction}.`,
  }[claimType] || `2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy unlawful conduct and the harm flowing from ${adverseAction}.`;
  const jurisdictionParagraph = {
    retaliation: '3. Jurisdiction is alleged in this Court because the controversy arises from retaliation for protected conduct and from the remedial obligations governing materially adverse acts taken in response to that conduct.',
    employment_discrimination: '3. Jurisdiction is alleged in this Court because the controversy arises from discriminatory employment practices, workplace bias, and related remedies for unlawful employment actions.',
    housing_discrimination: '3. Jurisdiction is alleged in this Court because the controversy arises from discriminatory housing practices, interference with housing rights or benefits, and related remedial obligations.',
    due_process_failure: '3. Jurisdiction is alleged in this Court because the controversy arises from deprivation without constitutionally or statutorily required notice, hearing, review, or other procedural protections.',
    consumer_protection: '3. Jurisdiction is alleged in this Court because the controversy arises from unfair, deceptive, or unlawful consumer-facing conduct and the remedies available for resulting harm.',
  }[claimType] || '3. Jurisdiction is alleged in this Court because the controversy arises from unlawful conduct and the remedies available for resulting harm.';
  const venueParagraph = {
    housing_discrimination: '4. Venue is alleged to be proper because the housing-related events, denial, interference, or threatened loss of housing benefits occurred in this forum and the resulting harm was felt here.',
    employment_discrimination: '4. Venue is alleged to be proper because the workplace events, adverse employment decisions, and resulting economic harm occurred in or were directed into this forum.',
    consumer_protection: '4. Venue is alleged to be proper because the transaction, deceptive practice, or resulting economic loss occurred in this forum or caused injury here.',
  }[claimType] || '4. Venue is alleged to be proper because a substantial part of the events or omissions giving rise to these claims occurred in this forum and the resulting harm was felt here.';
  const plaintiffParagraph = {
    retaliation: `5. Plaintiff ${answers.party_name || 'Plaintiff'} is the person harmed by the retaliation described below.`,
    employment_discrimination: `5. Plaintiff ${answers.party_name || 'Plaintiff'} is the employee, applicant, or worker harmed by the discriminatory employment conduct described below.`,
    housing_discrimination: `5. Plaintiff ${answers.party_name || 'Plaintiff'} is the housing applicant, tenant, resident, or person seeking housing-related rights or benefits who was harmed by the discriminatory conduct described below.`,
    due_process_failure: `5. Plaintiff ${answers.party_name || 'Plaintiff'} is the person deprived of rights, benefits, or protected interests without adequate process.`,
    consumer_protection: `5. Plaintiff ${answers.party_name || 'Plaintiff'} is the consumer or injured person harmed by the deceptive, unfair, or unlawful conduct described below.`,
  }[claimType] || `5. Plaintiff ${answers.party_name || 'Plaintiff'} is the person harmed by the unlawful conduct described below.`;
  const defendantParagraph = {
    retaliation: `6. Defendant ${answers.opposing_party || 'Defendant'} is the party from whom relief is sought and is responsible for the retaliatory actions alleged in this pleading.`,
    employment_discrimination: `6. Defendant ${answers.opposing_party || 'Defendant'} is the employer or responsible actor from whom relief is sought for the discriminatory employment actions alleged in this pleading.`,
    housing_discrimination: `6. Defendant ${answers.opposing_party || 'Defendant'} is the housing provider, landlord, authority, manager, or responsible actor from whom relief is sought for the housing discrimination alleged in this pleading.`,
    due_process_failure: `6. Defendant ${answers.opposing_party || 'Defendant'} is the person or entity responsible for the challenged deprivation and the missing procedural safeguards alleged in this pleading.`,
    consumer_protection: `6. Defendant ${answers.opposing_party || 'Defendant'} is the seller, business, servicer, or responsible actor from whom relief is sought for the consumer-facing conduct alleged in this pleading.`,
  }[claimType] || `6. Defendant ${answers.opposing_party || 'Defendant'} is the party from whom relief is sought and is responsible for the unlawful actions alleged in this pleading.`;
  const factualParagraphs = {
    retaliation: [
      `7. ${answers.party_name || 'Plaintiff'} alleges that they ${protectedActivity}.`,
      '8. Plaintiff provided or attempted to provide protected information, opposition, reporting, or participation activity that should not have triggered reprisal.',
      `9. After that protected activity, ${answers.party_name || 'Plaintiff'} experienced ${adverseAction}.`,
      `10. The chronology currently available in the record shows that ${timeline}.`,
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
    employment_discrimination: [
      `7. ${answers.party_name || 'Plaintiff'} alleges facts showing discriminatory employment treatment, including that they ${protectedActivity}.`,
      `8. Defendant thereafter took or maintained adverse employment action, including ${adverseAction}.`,
      `9. The employment chronology currently available in the record shows that ${timeline}.`,
      '10. The present record supports an inference of discriminatory motive, disparate treatment, prohibited bias, retaliation, or other unlawful employment decision-making.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
    housing_discrimination: [
      `7. ${answers.party_name || 'Plaintiff'} alleges that they sought, used, requested, or protected housing-related rights, accommodations, benefits, tenancy rights, or fair treatment, including that they ${protectedActivity}.`,
      `8. Defendant thereafter denied, burdened, interfered with, or threatened housing-related rights or benefits, including ${adverseAction}.`,
      `9. The housing-related chronology currently available in the record shows that ${timeline}.`,
      '10. The present record supports an inference that Defendant acted in a discriminatory manner, interfered with protected housing rights, or retaliated in connection with protected housing activity.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
    due_process_failure: [
      '7. Plaintiff alleges that Defendant imposed or maintained a deprivation affecting protected rights, interests, status, benefits, or property.',
      `8. The challenged action included ${adverseAction}.`,
      `9. The chronology currently available in the record shows that ${timeline}.`,
      '10. Plaintiff alleges that the deprivation occurred without adequate notice, hearing, review, appeal, or other required procedural protection.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
    consumer_protection: [
      '7. Plaintiff alleges that Defendant engaged in deceptive, misleading, unfair, or otherwise unlawful consumer-facing conduct.',
      `8. That conduct included or resulted in ${adverseAction}.`,
      `9. The chronology currently available in the record shows that ${timeline}.`,
      '10. Plaintiff alleges that the challenged conduct caused consumer harm, financial loss, or other compensable injury in a transactional or service context.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
  }[claimType] || [
    `7. ${answers.party_name || 'Plaintiff'} alleges that they ${protectedActivity}.`,
    `8. Defendant engaged in conduct including ${adverseAction}.`,
    `9. The chronology currently available in the record shows that ${timeline}.`,
    '10. Plaintiff alleges facts supporting a plausible claim for relief.',
    `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
  ];
  const claimParagraphs = {
    retaliation: [
      `${answers.party_name || 'Plaintiff'} engaged in protected activity by ${protectedActivity}, and Defendant knew or should have known of that protected conduct.`,
      `Defendant thereafter subjected Plaintiff to materially adverse action, including ${adverseAction}, under circumstances supporting retaliatory motive and causation.`,
      'The pleaded chronology, evidentiary record, and resulting harm support a plausible retaliation claim because protected activity was followed by materially adverse conduct and damages.',
    ],
    employment_discrimination: [
      `Plaintiff was subjected to adverse employment treatment, including ${adverseAction}, in a manner that was discriminatory, disparate, or otherwise unlawful.`,
      'The pleaded facts support an inference that Defendant\'s conduct was motivated by unlawful bias, protected status, protected conduct, or a prohibited employment practice.',
      'The evidentiary record and resulting harm support a plausible employment discrimination claim.',
    ],
    housing_discrimination: [
      `Defendant denied, limited, burdened, or interfered with housing-related rights, opportunities, services, or benefits, including conduct reflected in ${adverseAction}.`,
      'The pleaded facts support an inference that Defendant acted in a discriminatory manner or retaliated in connection with protected housing activity, status, or rights.',
      'The evidentiary record and resulting harm support a plausible housing discrimination claim.',
    ],
    due_process_failure: [
      'Defendant imposed or maintained adverse consequences without the notice, review, hearing, or procedural protections required by law.',
      `The resulting deprivation included ${adverseAction} and related harms without adequate procedural safeguards.`,
      'The pleaded facts and evidentiary record support a plausible due process claim.',
    ],
    consumer_protection: [
      'Defendant engaged in unfair, deceptive, misleading, or unlawful conduct in connection with a consumer transaction or obligation.',
      `That conduct resulted in ${adverseAction} and caused economic or other compensable harm, including ${harm}.`,
      'The pleaded facts and evidentiary record support a plausible consumer protection claim.',
    ],
  }[claimType] || [
    'Defendant engaged in unlawful conduct causing harm to Plaintiff.',
    'The pleaded facts support a plausible claim for relief.',
    'The evidentiary record and resulting harm warrant judicial relief.',
  ];
  const testimonySummary = (evidence.testimony || []).slice(0, 3)
    .map((item) => `${item.title || 'Untitled testimony'} (${item.claim_element_id || 'unmapped'})`)
    .join('; ') || 'No witness or complainant testimony has been summarized yet';
  const documentSummary = (evidence.documents || []).slice(0, 3)
    .map((item) => `${item.title || 'Untitled document'} (${item.claim_element_id || 'unmapped'})`)
    .join('; ') || 'No documentary exhibits have been summarized yet';
  const testimonyReferenceLines = (evidence.testimony || []).slice(0, 3)
    .map((item) => `Plaintiff testimony or witness account titled '${item.title || 'Untitled testimony'}' supports ${item.claim_element_id || 'an identified claim element'}.`);
  const documentReferenceLines = (evidence.documents || []).slice(0, 3)
    .map((item) => `Documentary exhibit '${item.title || 'Untitled document'}' is presently tied to ${item.claim_element_id || 'an identified claim element'}.`);
  const useLlm = Boolean(options.use_llm);
  const provider = String(options.provider || '').trim() || 'playwright-stub';
  const model = String(options.model || '').trim() || 'stub-formal-complaint';
  return {
    title: `${answers.party_name || 'Plaintiff'} v. ${answers.opposing_party || 'Defendant'} ${claimTypeTitle} Complaint`,
    requested_relief: relief,
    case_synopsis: synopsis,
    claim_type: claimType,
    body: [
      'IN THE UNITED STATES DISTRICT COURT',
      'FOR THE DISTRICT AND DIVISION IN WHICH THE UNLAWFUL PRACTICES OCCURRED',
      '',
      `${answers.party_name || 'Plaintiff'}, Plaintiff,`,
      'v.',
      `${answers.opposing_party || 'Defendant'}, Defendant.`,
      '',
      'Civil Action No. ________________',
      complaintHeading,
      'JURY TRIAL DEMANDED',
      '',
      `Plaintiff ${answers.party_name || 'Plaintiff'}, by and through this Complaint, alleges upon personal knowledge as to their own acts and upon information and belief as to all other matters, as follows:`,
      '',
      'NATURE OF THE ACTION',
      natureOfAction,
      reliefParagraph,
      '',
      'JURISDICTION AND VENUE',
      jurisdictionParagraph,
      venueParagraph,
      '',
      'PARTIES',
      plaintiffParagraph,
      defendantParagraph,
      '',
      'FACTUAL ALLEGATIONS',
      ...factualParagraphs,
      '',
      'EVIDENTIARY SUPPORT AND NOTICE',
      `12. The current complaint record includes ${Number((evidence.testimony || []).length + (evidence.documents || []).length)} saved evidence items, including testimony such as ${testimonySummary}.`,
      `13. The current documentary record includes the following summarized exhibits or records: ${documentSummary}.`,
      `14. The present support review reflects ${Number(overview.supported_elements || 0)} supported claim elements and ${Number(overview.missing_elements || 0)} open support gaps, which Plaintiff identifies so the pleading can be refined rather than to concede any deficiency in the claim.`,
      '15. Plaintiff incorporates the current testimony summaries, documentary exhibits, chronology notes, and support review findings as the preliminary exhibit and notice record for this pleading.',
      ...[...testimonyReferenceLines, ...documentReferenceLines].slice(0, 2).map((line, index) => `${16 + index}. ${line}`),
      '',
      'CLAIM FOR RELIEF',
      countHeading,
      `18. ${answers.party_name || 'Plaintiff'} repeats and realleges the preceding paragraphs as if fully set forth herein.`,
      `19. ${claimParagraphs[0]}`,
      `20. ${claimParagraphs[1]}`,
      `21. ${claimParagraphs[2]}`,
      `22. Plaintiff has suffered damages and other losses including ${harm}.`,
      "23. Defendant's acts were intentional, knowing, reckless, retaliatory, discriminatory, deceptive, or otherwise unlawful under the governing claim theory.",
      '',
      'PRAYER FOR RELIEF',
      'Wherefore, Plaintiff requests judgment against Defendant and the following relief:',
      ...relief.map((item, index) => `${index + 1}. ${item}.`),
      '',
      'JURY DEMAND',
      'Plaintiff demands a trial by jury on all issues so triable.',
      '',
      'SIGNATURE BLOCK',
      'Dated: ____________________',
      '',
      'Respectfully submitted,',
      '',
      `${answers.party_name || 'Plaintiff'}`,
      'Plaintiff, Pro Se',
      'Address: ____________________',
      'Telephone: ____________________',
      'Email: ____________________',
      '',
      'WORKING CASE SYNOPSIS',
      `Working case synopsis: ${synopsis}`,
    ].join('\n\n'),
    generated_at: '2026-03-22T12:00:00Z',
    review_snapshot: review,
    draft_strategy: useLlm ? 'llm_router' : 'template',
    draft_backend: useLlm ? { id: 'complaint-draft', provider, model } : undefined,
  };
}

function buildWorkspaceSessionPayload(state) {
  const questions = buildWorkspaceQuestionStatus(state);
  const nextQuestion = questions.find((question) => !question.is_answered) || null;
  const review = buildWorkspaceReview(state);
  return {
    session: clone(state),
    questions,
    next_question: nextQuestion,
    review,
    case_synopsis: buildWorkspaceCaseSynopsis(state),
    draft: state.draft ? clone(state.draft) : null,
  };
}

function buildWorkspaceMediatorPrompt(state) {
  const sessionPayload = buildWorkspaceSessionPayload(state);
  const supportMatrix = sessionPayload.review.support_matrix || [];
  const firstGap = supportMatrix.find((item) => !item.supported) || null;
  const synopsis = sessionPayload.case_synopsis;
  const gapFocus = firstGap
    ? `Focus especially on clarifying ${String(firstGap.label || '').toLowerCase()} and what proof could corroborate it.`
    : 'Focus on sharpening the strongest testimony, identifying corroboration, and confirming the cleanest sequence of events.';
  return {
    user_id: state.user_id,
    case_synopsis: synopsis,
    target_gap: firstGap ? clone(firstGap) : null,
    prefill_message: `${synopsis}\n\nMediator, help turn this into testimony-ready narrative for the complaint record. Ask the single most useful next follow-up question, keep the tone calm, and explain what support would strengthen the case. ${gapFocus}`,
    return_target_tab: 'review',
  };
}

function buildWorkspaceCapabilities(state) {
  const sessionPayload = buildWorkspaceSessionPayload(state);
  const review = sessionPayload.review || {};
  const overview = review.overview || {};
  const questions = sessionPayload.questions || [];
  const answeredCount = questions.filter((question) => question.is_answered).length;
  return {
    user_id: state.user_id,
    case_synopsis: sessionPayload.case_synopsis,
    overview: clone(overview),
    capabilities: [
      {
        id: 'intake_questions',
        label: 'Complaint intake questions',
        available: questions.length > 0,
        detail: `${answeredCount} of ${questions.length} intake questions answered.`,
      },
      {
        id: 'mediator_prompt',
        label: 'Chat mediator handoff',
        available: true,
        detail: 'A testimony-ready mediator prompt can be generated from the shared case synopsis and support gaps.',
      },
      {
        id: 'evidence_capture',
        label: 'Evidence capture',
        available: true,
        detail: `${Number(overview.testimony_items || 0) + Number(overview.document_items || 0)} evidence items saved.`,
      },
      {
        id: 'support_review',
        label: 'Claim support review',
        available: true,
        detail: `${overview.supported_elements || 0} supported elements, ${overview.missing_elements || 0} gaps remaining.`,
      },
      {
        id: 'complaint_draft',
        label: 'Complaint draft',
        available: true,
        detail: state.draft ? 'A draft already exists and can be edited.' : 'A draft can be generated from the current complaint record.',
      },
      {
        id: 'complaint_packet',
        label: 'Complaint packet export',
        available: true,
        detail: 'The lawsuit packet can be exported as a structured browser, CLI, or MCP artifact.',
      },
    ],
  };
}

function slugifyWorkspaceFilename(value) {
  return String(value || 'complaint-packet')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'complaint-packet';
}

function buildWorkspacePacketExport(state) {
  const sessionPayload = buildWorkspaceSessionPayload(state);
  const draft = state.draft || buildWorkspaceDraft(state, null);
  const requestedRelief = Array.isArray(draft.requested_relief) ? draft.requested_relief : [];
  const questionLines = (sessionPayload.questions || []).map((item) => `- **${item.label || item.id || 'Question'}:** ${item.answer || 'Not answered'}`);
  const testimonyLines = ((state.evidence || {}).testimony || [])
    .map((item) => `- **${item.title || 'Testimony'}** (${item.claim_element_id || 'unmapped'}): ${item.content || ''}`.trim());
  const documentLines = ((state.evidence || {}).documents || [])
    .map((item) => `- **${item.title || 'Document'}** (${item.claim_element_id || 'unmapped'}): ${item.content || ''}`.trim());
  const packet = {
    title: draft.title,
    user_id: state.user_id,
    claim_type: state.claim_type,
    case_synopsis: sessionPayload.case_synopsis,
    questions: clone(sessionPayload.questions),
    evidence: clone(state.evidence),
    review: clone(sessionPayload.review),
    draft: clone(draft),
    exported_at: '2026-03-22T12:30:00Z',
  };
  const filenameRoot = slugifyWorkspaceFilename(draft.title);
  const markdown = [
    draft.body,
    '',
    'APPENDIX A - CASE SYNOPSIS',
    sessionPayload.case_synopsis,
    '',
    'APPENDIX B - REQUESTED RELIEF CHECKLIST',
    requestedRelief.length ? requestedRelief.map((item) => `- ${item}`).join('\n') : '- No requested relief recorded.',
    '',
    'APPENDIX C - INTAKE ANSWERS',
    questionLines.length ? questionLines.join('\n') : '- No intake answers recorded.',
    '',
    'APPENDIX D - EVIDENCE SUMMARY',
    '### Testimony',
    testimonyLines.length ? testimonyLines.join('\n') : '- No testimony saved.',
    '',
    '### Documents',
    documentLines.length ? documentLines.join('\n') : '- No documents saved.',
    '',
    'APPENDIX E - REVIEW OVERVIEW',
    `- Supported elements: ${Number((sessionPayload.review.overview || {}).supported_elements || 0)}`,
    `- Missing elements: ${Number((sessionPayload.review.overview || {}).missing_elements || 0)}`,
    `- Testimony items: ${Number((sessionPayload.review.overview || {}).testimony_items || 0)}`,
    `- Document items: ${Number((sessionPayload.review.overview || {}).document_items || 0)}`,
    '',
    'APPENDIX F - EXPORT METADATA',
    `- Claim type: ${String(state.claim_type || 'retaliation')}`,
    `- User ID: ${String(state.user_id || 'did:key:playwright-demo')}`,
    '- Exported at: 2026-03-22T12:30:00Z',
  ].join('\n');
  return {
    packet,
    packet_summary: {
      question_count: sessionPayload.questions.length,
      answered_question_count: sessionPayload.questions.filter((item) => item.is_answered).length,
      supported_elements: Number((sessionPayload.review.overview || {}).supported_elements || 0),
      missing_elements: Number((sessionPayload.review.overview || {}).missing_elements || 0),
      testimony_items: Number((sessionPayload.review.overview || {}).testimony_items || 0),
      document_items: Number((sessionPayload.review.overview || {}).document_items || 0),
      has_draft: Boolean(state.draft),
      complaint_readiness: buildWorkspaceComplaintReadiness(state),
      artifact_formats: ['json', 'markdown', 'pdf'],
    },
    artifacts: {
      json: {
        filename: `${filenameRoot}.json`,
        content_type: 'application/json',
      },
      markdown: {
        filename: `${filenameRoot}.md`,
        content_type: 'text/markdown',
        content: markdown,
        excerpt: markdown.slice(0, 2000),
      },
      pdf: {
        filename: `${filenameRoot}.pdf`,
        content_type: 'application/pdf',
        header_b64: Buffer.from('%PDF-1.4 mock complaint').toString('base64'),
      },
    },
    artifact_analysis: {
      draft_word_count: String(draft.body || '').split(/\s+/).filter(Boolean).length,
      evidence_item_count: Number((state.evidence.testimony || []).length + (state.evidence.documents || []).length),
      requested_relief_count: Number((draft.requested_relief || []).length),
      supported_elements: Number((sessionPayload.review.overview || {}).supported_elements || 0),
      missing_elements: Number((sessionPayload.review.overview || {}).missing_elements || 0),
      has_case_synopsis: Boolean(String(sessionPayload.case_synopsis || '').trim()),
    },
  };
}

function buildWorkspaceComplaintOutputAnalysis(state) {
  const payload = buildWorkspacePacketExport(state);
  const complaintBody = String((((payload.packet || {}).draft || {}).body || ''));
  const formalSectionsPresent = {
    caption: complaintBody.includes('IN THE UNITED STATES DISTRICT COURT'),
    civil_action_number: complaintBody.includes('Civil Action No. ________________'),
    nature_of_action: complaintBody.includes('NATURE OF THE ACTION'),
    jurisdiction_and_venue: complaintBody.includes('JURISDICTION AND VENUE'),
    parties: complaintBody.includes('PARTIES'),
    factual_allegations: complaintBody.includes('FACTUAL ALLEGATIONS'),
    evidentiary_support: complaintBody.includes('EVIDENTIARY SUPPORT AND NOTICE'),
    claim_count: complaintBody.includes('COUNT I -'),
    prayer_for_relief: complaintBody.includes('PRAYER FOR RELIEF'),
    jury_demand: complaintBody.includes('JURY DEMAND'),
    signature_block: complaintBody.includes('SIGNATURE BLOCK'),
    working_case_synopsis: complaintBody.includes('WORKING CASE SYNOPSIS'),
  };
  const filingShapeScore = Math.min(
    100,
    35
      + (5 * Object.values(formalSectionsPresent).filter(Boolean).length)
      + (Number((payload.artifact_analysis || {}).evidence_item_count || 0) > 0 ? 10 : 0)
      + (Number((payload.artifact_analysis || {}).requested_relief_count || 0) > 0 ? 5 : 0)
      + (Number((payload.artifact_analysis || {}).draft_word_count || 0) >= 180 ? 10 : 0),
  );
  return {
    user_id: state.user_id,
    packet_summary: clone(payload.packet_summary),
    artifact_analysis: clone(payload.artifact_analysis),
    ui_feedback: {
      summary: 'The exported complaint artifact was analyzed to infer which UI steps may still be too weak, hidden, or permissive for a real complainant.',
      filing_shape_score: filingShapeScore,
      formal_sections_present: formalSectionsPresent,
      issues: Number((payload.packet_summary || {}).missing_elements || 0) > 0
        ? [
            {
              severity: 'high',
              source: 'complaint_output',
              finding: `The exported complaint still reflects ${Number((payload.packet_summary || {}).missing_elements || 0)} unsupported claim elements.`,
              ui_implication: 'The review and draft stages need stronger warnings before the user treats the complaint as filing-ready.',
            },
          ]
        : [],
      ui_suggestions: [
        {
          title: 'Tighten review-to-draft gatekeeping',
          recommendation: 'Add stronger blocker language and a more prominent unsupported-elements summary before draft generation or export.',
          target_surface: 'review,draft,integrations',
        },
      ],
      draft_excerpt: String((((payload.packet || {}).draft || {}).body || '')).slice(0, 600),
      complaint_strengths: [
        `Supported elements: ${Number((payload.packet_summary || {}).supported_elements || 0)}`,
        `Evidence items: ${Number((payload.packet_summary || {}).testimony_items || 0) + Number((payload.packet_summary || {}).document_items || 0)}`,
        `Requested relief items: ${Number((payload.artifact_analysis || {}).requested_relief_count || 0)}`,
        `Formal sections present: ${Object.values(formalSectionsPresent).filter(Boolean).length}/${Object.keys(formalSectionsPresent).length}`,
      ],
    },
  };
}

function buildWorkspaceUiReviewResult(state, toolArgs = {}) {
  const analysis = buildWorkspaceComplaintOutputAnalysis(state);
  const suggestion = (((analysis.ui_feedback || {}).ui_suggestions || [])[0]) || {};
  const routerLabel = [toolArgs.provider, toolArgs.model].filter(Boolean).join(' / ') || 'default llm_router multimodal_router path';
  return {
    latest_review: `Complaint-output suggestion carried into router review: ${String(suggestion.title || 'Promote complaint-output blockers')} via ${routerLabel}.`,
    review: {
      summary: `Workspace mock review completed with ${routerLabel}. Complaint-output suggestion: ${String(suggestion.title || 'Promote complaint-output blockers')}.`,
      issues: [],
      playwright_followups: [],
      stage_findings: {
        Review: `Complaint-output suggestion carried into router review: ${String(suggestion.title || 'Promote complaint-output blockers')}.`,
        'Integration Discovery': `${routerLabel} should stay visible from the workspace shortcuts and tool panels.`,
      },
    },
  };
}

function buildWorkspaceUiOptimizationResult(state, toolArgs = {}) {
  const analysis = buildWorkspaceComplaintOutputAnalysis(state);
  const suggestion = (((analysis.ui_feedback || {}).ui_suggestions || [])[0]) || {};
  const routerLabel = [toolArgs.provider, toolArgs.model].filter(Boolean).join(' / ') || 'default llm_router multimodal_router path';
  return {
    workflow_type: 'ui_ux_closed_loop',
    rounds_executed: 1,
    latest_validation_review: `The optimizer path itself should stay discoverable from the shared dashboard shortcuts and tool panels. Complaint-output suggestion carried into optimization: ${String(suggestion.title || 'Promote complaint-output blockers')} via ${routerLabel}.`,
    changed_files: ['templates/workspace.html'],
  };
}

function buildWorkspaceComplaintReadiness(state) {
  const sessionPayload = buildWorkspaceSessionPayload(state);
  const review = sessionPayload.review || {};
  const overview = review.overview || {};
  const questions = sessionPayload.questions || [];
  const answeredCount = questions.filter((question) => question.is_answered).length;
  const totalQuestions = questions.length;
  const supportedElements = Number(overview.supported_elements || 0);
  const missingElements = Number(overview.missing_elements || 0);
  const evidenceCount = Number(overview.testimony_items || 0) + Number(overview.document_items || 0);

  let score = 10;
  if (totalQuestions > 0) {
    score += Math.round((answeredCount / totalQuestions) * 35);
  }
  score += Math.round((supportedElements / Math.max(supportedElements + missingElements, 1)) * 35);
  if (evidenceCount > 0) {
    score += Math.min(12, evidenceCount * 4);
  }
  if (state.draft) {
    score += 12;
  }
  score = Math.max(0, Math.min(100, score));

  let verdict = 'Not ready to draft';
  let detail = 'Finish intake and add support before relying on generated complaint text.';
  let recommendedRoute = '/workspace';
  let recommendedAction = 'Continue the guided complaint workflow to complete intake and collect support.';

  if (state.draft) {
    verdict = 'Draft in progress';
    detail = 'A complaint draft already exists. Compare it against the supported facts, requested relief, and any remaining proof gaps before treating it as filing-ready.';
    recommendedRoute = '/document';
    recommendedAction = 'Refine the existing draft and reconcile it with the support review.';
  } else if (totalQuestions > 0 && answeredCount === totalQuestions && missingElements === 0 && evidenceCount > 0) {
    verdict = 'Ready for first draft';
    detail = 'The intake record and support posture are coherent enough to generate a first complaint draft.';
    recommendedRoute = '/document';
    recommendedAction = 'Generate the first complaint draft from the current record.';
  } else if (answeredCount > 0) {
    verdict = 'Still building the record';
    detail = `${missingElements} claim elements still need support and ${Math.max(totalQuestions - answeredCount, 0)} intake answers may still be missing.`;
    recommendedRoute = missingElements > 0 ? '/claim-support-review' : '/workspace';
    recommendedAction = missingElements > 0
      ? 'Use the review dashboard to close the remaining support gaps.'
      : 'Keep completing the intake and case synopsis before drafting.';
  }

  return {
    user_id: state.user_id,
    score,
    verdict,
    detail,
    recommended_route: recommendedRoute,
    recommended_action: recommendedAction,
    answered_question_count: answeredCount,
    total_question_count: totalQuestions,
    supported_elements: supportedElements,
    missing_elements: missingElements,
    evidence_items: evidenceCount,
    has_draft: Boolean(state.draft),
  };
}

function buildWorkspaceUiReadiness(state) {
  const complaintReadiness = buildWorkspaceComplaintReadiness(state);
  const verdict = state.draft ? 'Client-safe' : 'Needs repair';
  const releaseBlockers = state.draft
    ? []
    : ['Generate a complaint draft before treating the workflow as filing-ready.'];
  return {
    user_id: state.user_id,
    verdict,
    summary: state.draft
      ? 'The browser complaint workflow can generate, edit, and export a draft through the shared MCP tool path.'
      : 'The browser workflow still needs a generated complaint draft before the full filing path feels complete.',
    release_blockers: releaseBlockers,
    sdk_tooling_ready: true,
    complaint_readiness: complaintReadiness,
  };
}

async function installCommonMocks(page, recorder = {}, options = {}) {
  const documentResponses = Array.isArray(options.documentResponses) && options.documentResponses.length
    ? options.documentResponses.map((item) => clone(item))
    : [clone(documentGenerationResponse)];
  const workspaceSessions = new Map();
  let workspaceIdentityCounter = 0;

  function getWorkspaceState(userId) {
    const resolvedUserId = userId || `did:key:playwright-${String(workspaceIdentityCounter + 1).padStart(4, '0')}`;
    if (!workspaceSessions.has(resolvedUserId)) {
      workspaceSessions.set(resolvedUserId, createWorkspaceState(resolvedUserId));
    }
    return workspaceSessions.get(resolvedUserId);
  }

  function jsonRpcSuccess(id, result) {
    return {
      jsonrpc: '2.0',
      id,
      result,
    };
  }

  function jsonRpcError(id, message) {
    return {
      jsonrpc: '2.0',
      id,
      error: {
        code: -32601,
        message,
      },
    };
  }

  function handleWorkspaceToolCall(name, args) {
    const toolArgs = args || {};
    const state = getWorkspaceState(toolArgs.user_id);

    if (name === 'complaint.create_identity') {
      return { did: state.user_id };
    }
    if (name === 'complaint.list_intake_questions') {
      return { questions: clone(workspaceIntakeQuestions) };
    }
    if (name === 'complaint.list_claim_elements') {
      return { claim_elements: clone(workspaceClaimElements) };
    }
    if (name === 'complaint.start_session' || name === 'complaint.review_case') {
      return buildWorkspaceSessionPayload(state);
    }
    if (name === 'complaint.submit_intake') {
      const answers = toolArgs.answers || {};
      workspaceIntakeQuestions.forEach((question) => {
        const value = String(answers[question.id] || '').trim();
        if (!value) {
          return;
        }
        state.intake_answers[question.id] = value;
        state.intake_history.push({
          question_id: question.id,
          answer: value,
          captured_at: '2026-03-22T12:05:00Z',
        });
      });
      return buildWorkspaceSessionPayload(state);
    }
    if (name === 'complaint.save_evidence') {
      const kind = String(toolArgs.kind || 'testimony');
      const collectionKey = kind === 'document' ? 'documents' : 'testimony';
      const collection = state.evidence[collectionKey];
      collection.push({
        id: `${collectionKey}-${collection.length + 1}`,
        kind,
        claim_element_id: String(toolArgs.claim_element_id || 'causation'),
        title: String(toolArgs.title || 'Untitled evidence'),
        content: String(toolArgs.content || ''),
        source: String(toolArgs.source || ''),
        attachment_names: Array.isArray(toolArgs.attachment_names) ? toolArgs.attachment_names.filter(Boolean) : [],
        saved_at: '2026-03-22T12:10:00Z',
      });
      return {
        saved: clone(collection[collection.length - 1]),
        review: buildWorkspaceReview(state),
        session: clone(state),
        case_synopsis: buildWorkspaceCaseSynopsis(state),
      };
    }
    if (name === 'complaint.build_mediator_prompt') {
      return buildWorkspaceMediatorPrompt(state);
    }
    if (name === 'complaint.get_complaint_readiness') {
      return buildWorkspaceComplaintReadiness(state);
    }
    if (name === 'complaint.get_ui_readiness') {
      return buildWorkspaceUiReadiness(state);
    }
    if (name === 'complaint.get_workflow_capabilities') {
      return buildWorkspaceCapabilities(state);
    }
    if (name === 'complaint.generate_complaint') {
      const requestedRelief = Array.isArray(toolArgs.requested_relief)
        ? toolArgs.requested_relief
        : typeof toolArgs.requested_relief === 'string'
          ? toolArgs.requested_relief.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
          : null;
      state.draft = buildWorkspaceDraft(state, requestedRelief, {
        use_llm: Boolean(toolArgs.use_llm),
        provider: toolArgs.provider,
        model: toolArgs.model,
      });
      if (toolArgs.title_override) {
        state.draft.title = String(toolArgs.title_override);
      }
      return {
        draft: clone(state.draft),
        review: buildWorkspaceReview(state),
        session: clone(state),
        case_synopsis: buildWorkspaceCaseSynopsis(state),
      };
    }
    if (name === 'complaint.update_draft') {
      state.draft = state.draft || buildWorkspaceDraft(state, null);
      if (Object.prototype.hasOwnProperty.call(toolArgs, 'title')) {
        state.draft.title = String(toolArgs.title || '');
      }
      if (Object.prototype.hasOwnProperty.call(toolArgs, 'body')) {
        state.draft.body = String(toolArgs.body || '');
      }
      if (Object.prototype.hasOwnProperty.call(toolArgs, 'requested_relief')) {
        state.draft.requested_relief = Array.isArray(toolArgs.requested_relief)
          ? toolArgs.requested_relief
          : [];
      }
      state.draft.updated_at = '2026-03-22T12:20:00Z';
      return {
        draft: clone(state.draft),
        review: buildWorkspaceReview(state),
        session: clone(state),
        case_synopsis: buildWorkspaceCaseSynopsis(state),
      };
    }
    if (name === 'complaint.export_complaint_packet') {
      const payload = buildWorkspacePacketExport(state);
      return Object.assign({}, payload, {
        ui_feedback: buildWorkspaceComplaintOutputAnalysis(state).ui_feedback,
      });
    }
    if (name === 'complaint.export_complaint_markdown') {
      const payload = buildWorkspacePacketExport(state);
      return {
        artifact: {
          format: 'markdown',
          filename: payload.artifacts.markdown.filename,
          media_type: payload.artifacts.markdown.content_type,
          excerpt: payload.artifacts.markdown.excerpt,
        },
        packet_summary: clone(payload.packet_summary),
        artifact_analysis: clone(payload.artifact_analysis),
      };
    }
    if (name === 'complaint.export_complaint_pdf') {
      const payload = buildWorkspacePacketExport(state);
      return {
        artifact: {
          format: 'pdf',
          filename: payload.artifacts.pdf.filename,
          media_type: payload.artifacts.pdf.content_type,
          header_b64: payload.artifacts.pdf.header_b64,
        },
        packet_summary: clone(payload.packet_summary),
        artifact_analysis: clone(payload.artifact_analysis),
      };
    }
    if (name === 'complaint.analyze_complaint_output') {
      return buildWorkspaceComplaintOutputAnalysis(state);
    }
    if (name === 'complaint.review_generated_exports') {
      const analysis = buildWorkspaceComplaintOutputAnalysis(state);
      return {
        artifact_count: 1,
        complaint_output_feedback: {
          export_artifact_count: 1,
          claim_types: [state.claim_type],
          draft_strategies: [state.draft && state.draft.draft_strategy ? state.draft.draft_strategy : 'template'],
          filing_shape_scores: [analysis.ui_feedback.filing_shape_score || 0],
          ui_suggestions: (analysis.ui_feedback.ui_suggestions || []).map((item) => item.title || item.recommendation).filter(Boolean),
        },
        aggregate: {
          average_filing_shape_score: analysis.ui_feedback.filing_shape_score || 0,
          average_claim_type_alignment_score: analysis.ui_feedback.claim_type_alignment_score || 0,
          issue_findings: (analysis.ui_feedback.issues || []).map((item) => item.finding).filter(Boolean),
          ui_suggestions: analysis.ui_feedback.ui_suggestions || [],
        },
        reviews: [
          {
            artifact: {
              claim_type: state.claim_type,
              draft_strategy: state.draft && state.draft.draft_strategy ? state.draft.draft_strategy : 'template',
            },
            review: {
              summary: analysis.ui_feedback.summary,
              filing_shape_score: analysis.ui_feedback.filing_shape_score || 0,
              claim_type_alignment_score: analysis.ui_feedback.claim_type_alignment_score || 0,
              issues: analysis.ui_feedback.issues || [],
              ui_suggestions: analysis.ui_feedback.ui_suggestions || [],
            },
          },
        ],
      };
    }
    if (name === 'complaint.update_case_synopsis') {
      state.case_synopsis = String(toolArgs.synopsis || '').trim();
      return buildWorkspaceSessionPayload(state);
    }
    if (name === 'complaint.reset_session') {
      const freshState = createWorkspaceState(state.user_id);
      workspaceSessions.set(state.user_id, freshState);
      return buildWorkspaceSessionPayload(freshState);
    }
    if (name === 'complaint.review_ui') {
      return buildWorkspaceUiReviewResult(state, toolArgs);
    }
    if (name === 'complaint.optimize_ui') {
      return buildWorkspaceUiOptimizationResult(state, toolArgs);
    }
    if (name === 'complaint.run_browser_audit') {
      return {
        returncode: 0,
        artifact_count: 7,
        screenshot_dir: String(toolArgs.screenshot_dir || 'artifacts/ui-audit/browser-audit'),
        command: ['npx', 'playwright', 'test', String(toolArgs.pytest_target || 'playwright/tests/complaint-flow.spec.js')],
      };
    }

    return null;
  }

  await page.addInitScript(() => {
    window.alert = () => {};
  });

  await page.route('**/api/complaint-workspace/identity', async (route) => {
    workspaceIdentityCounter += 1;
    const did = `did:key:playwright-${String(workspaceIdentityCounter).padStart(4, '0')}`;
    getWorkspaceState(did);
    recorder.workspaceIdentityRequestCount = (recorder.workspaceIdentityRequestCount || 0) + 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ did }),
    });
  });

  await page.route('**/api/complaint-workspace/session**', async (route) => {
    const url = new URL(route.request().url());
    const userId = url.searchParams.get('user_id');
    const payload = buildWorkspaceSessionPayload(getWorkspaceState(userId));
    recorder.workspaceSessionRequestCount = (recorder.workspaceSessionRequestCount || 0) + 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    });
  });

  await page.route('**/api/complaint-workspace/export/download**', async (route) => {
    const url = new URL(route.request().url());
    const userId = url.searchParams.get('user_id');
    const outputFormat = String(url.searchParams.get('output_format') || 'json');
    const payload = buildWorkspacePacketExport(getWorkspaceState(userId));

    if (outputFormat === 'pdf') {
      await route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        headers: {
          'Content-Disposition': `attachment; filename="${payload.artifacts.pdf.filename}"`,
        },
        body: Buffer.from(`%PDF-1.4\n% mock complaint pdf\n${payload.packet.draft.body}\n`),
      });
      return;
    }

    if (outputFormat === 'markdown') {
      await route.fulfill({
        status: 200,
        contentType: 'text/markdown',
        headers: {
          'Content-Disposition': `attachment; filename="${payload.artifacts.markdown.filename}"`,
        },
        body: payload.artifacts.markdown.content,
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Content-Disposition': `attachment; filename="${payload.artifacts.json.filename}"`,
      },
      body: JSON.stringify(payload.packet, null, 2),
    });
  });

  await page.route('**/api/complaint-workspace/mcp/rpc', async (route) => {
    const request = route.request().postDataJSON();
    const { id, method, params } = request;
    recorder.workspaceRpcRequests = recorder.workspaceRpcRequests || [];
    recorder.workspaceRpcRequests.push(request);

    if (method === 'ping') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(jsonRpcSuccess(id, { ok: true })),
      });
      return;
    }

    if (method === 'initialize') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(jsonRpcSuccess(id, {
          protocolVersion: '2026-03-22',
          serverInfo: {
            name: 'complaint-workspace-mock',
            version: '0.1.0',
          },
        })),
      });
      return;
    }

    if (method === 'tools/list') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(jsonRpcSuccess(id, {
          tools: clone(workspaceToolList),
        })),
      });
      return;
    }

    if (method === 'tools/call') {
      const toolName = params && params.name;
      const toolArguments = (params && params.arguments) || {};
      const structuredContent = handleWorkspaceToolCall(toolName, toolArguments);
      if (!structuredContent) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(jsonRpcError(id, 'Method not found')),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(jsonRpcSuccess(id, {
          structuredContent,
        })),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(jsonRpcError(id, 'Method not found')),
    });
  });

  await page.route('**/api/documents/formal-complaint', async (route) => {
    const payload = route.request().postDataJSON();
    recorder.documentRequest = payload;
    if (!Array.isArray(recorder.documentRequests)) {
      recorder.documentRequests = [];
    }
    recorder.documentRequests.push(payload);
    const nextResponse = documentResponses.length > 1
      ? documentResponses.shift()
      : clone(documentResponses[0]);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(nextResponse),
    });
  });

  await page.route('**/api/claim-support/review', async (route) => {
    recorder.reviewRequest = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(clone(reviewPayload)),
    });
  });

  await page.route('**/api/claim-support/save-document', async (route) => {
    recorder.saveDocumentRequest = route.request().postDataJSON();
    const payload = clone(reviewPayload);
    payload.document_artifacts.retaliation = [
      {
        claim_element_id: 'retaliation:2',
        document_label: 'Termination Email',
        filename: 'termination-email.txt',
        evidence_type: 'document',
        created_at: '2026-03-22T12:30:00Z',
      },
    ];
    payload.document_summary.retaliation = {
      artifact_count: 1,
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    });
  });

  await page.route('**/api/claim-support/save-testimony', async (route) => {
    recorder.saveTestimonyRequest = route.request().postDataJSON();
    const payload = clone(reviewPayload);
    payload.testimony_records.retaliation = [
      {
        claim_element_id: 'retaliation:2',
        claim_element_text: 'Adverse action',
        timestamp: '2026-03-22T12:20:00Z',
        event_date: '2026-03-12',
        actor: 'Acme manager',
        act: 'Termination',
        target: 'Jane Doe',
        harm: 'Lost employment',
        firsthand_status: 'firsthand',
        source_confidence: 0.9,
        raw_narrative: 'My manager terminated me two days after I complained to HR.',
      },
    ];
    payload.testimony_summary.retaliation = {
      record_count: 1,
      linked_element_count: 1,
      firsthand_status_counts: {
        firsthand: 1,
      },
      confidence_bucket_counts: {
        high: 1,
      },
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        recorded: true,
        post_save_review: payload,
      }),
    });
  });

  await page.route('**/api/claim-support/execute-follow-up', async (route) => {
    recorder.executeRequest = route.request().postDataJSON();
    const payload = clone(reviewPayload);
    payload.follow_up_history.retaliation.unshift({
      execution_id: 8,
      claim_element_id: 'retaliation:2',
      claim_element_text: 'Adverse action',
      support_kind: 'document',
      status: 'completed',
      resolution_status: 'resolved_supported',
      notes: 'Termination email attached during execution.',
    });
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        execution_id: 8,
        outcome_status: 'completed',
        notes: 'Follow-up execution completed.',
        post_execution_review: payload,
      }),
    });
  });

  await page.route('**/api/claim-support/confirm-intake-summary', async (route) => {
    recorder.confirmRequest = route.request().postDataJSON();
    const payload = clone(reviewPayload);
    payload.intake_case_summary.complainant_summary_confirmation = {
      confirmed: true,
      status: 'confirmed',
      confirmation_source: 'dashboard',
      confirmed_at: '2026-03-22T12:45:00Z',
      current_summary_snapshot: {
        candidate_claim_count: 1,
        canonical_fact_count: 2,
        proof_lead_count: 1,
      },
      confirmed_summary_snapshot: {
        candidate_claim_count: 1,
        canonical_fact_count: 2,
        proof_lead_count: 1,
      },
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        confirmed: true,
        post_confirmation_review: payload,
      }),
    });
  });
}

module.exports = {
  documentGenerationResponse,
  reviewPayload,
  installCommonMocks,
};
