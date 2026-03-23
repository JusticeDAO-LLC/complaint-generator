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

function buildWorkspaceDraft(state, requestedRelief) {
  const answers = state.intake_answers || {};
  const existingDraft = state.draft || {};
  const relief = requestedRelief || existingDraft.requested_relief || ['Compensatory damages', 'Back pay', 'Injunctive relief'];
  const synopsis = buildWorkspaceCaseSynopsis(state);
  return {
    title: `${answers.party_name || 'Plaintiff'} v. ${answers.opposing_party || 'Defendant'} Retaliation Complaint`,
    requested_relief: relief,
    case_synopsis: synopsis,
    body: [
      `${answers.party_name || 'Plaintiff'} brings this retaliation complaint against ${answers.opposing_party || 'Defendant'}.`,
      `${answers.party_name || 'Plaintiff'} alleges that they ${answers.protected_activity || 'engaged in protected activity'}.`,
      `After that protected activity, ${answers.party_name || 'Plaintiff'} experienced ${answers.adverse_action || 'an adverse action'}.`,
      `The timeline shows that ${answers.timeline || 'the events occurred close in time'}.`,
      `As a result, ${answers.party_name || 'Plaintiff'} suffered ${answers.harm || 'compensable harm'}.`,
      `Requested relief includes: ${relief.join('; ')}.`,
      `Working case synopsis: ${synopsis}`,
    ].join('\n\n'),
    generated_at: '2026-03-22T12:00:00Z',
    review_snapshot: buildWorkspaceReview(state),
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
    `# ${draft.title}`,
    '',
    '## Working Case Synopsis',
    sessionPayload.case_synopsis,
    '',
    '## Complaint Draft',
    draft.body,
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
  return {
    user_id: state.user_id,
    packet_summary: clone(payload.packet_summary),
    artifact_analysis: clone(payload.artifact_analysis),
    ui_feedback: {
      summary: 'The exported complaint artifact was analyzed to infer which UI steps may still be too weak, hidden, or permissive for a real complainant.',
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
      ],
    },
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
      state.draft = buildWorkspaceDraft(state, requestedRelief);
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
      return {
        latest_review: 'Workspace mock review completed.',
        review: {
          summary: 'Workspace mock review completed.',
          issues: [],
          playwright_followups: [],
        },
      };
    }
    if (name === 'complaint.optimize_ui') {
      return {
        latest_validation_review: 'Workspace mock optimization completed.',
        changed_files: ['templates/workspace.html'],
      };
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
