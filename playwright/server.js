const http = require('http');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

const root = path.resolve(__dirname, '..');
const templatesDir = path.join(root, 'templates');
const staticDir = path.join(root, 'static');
const sdkPreviewPath = path.join(root, 'ipfs_datasets_py', 'ipfs_accelerate_py', 'SDK_PLAYGROUND_PREVIEW.html');
const ipfsDatasetsTemplatesDir = path.join(root, 'ipfs_datasets_py', 'ipfs_datasets_py', 'templates');
const ipfsDatasetsStaticDir = path.join(root, 'ipfs_datasets_py', 'ipfs_datasets_py', 'static');
const port = 19000;

function slugifyFilename(value) {
  return String(value || 'complaint-packet')
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'complaint-packet';
}

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

function eventFragment(value, fallback) {
  const text = sentenceFragment(value, fallback);
  return text.startsWith('was ') ? text.slice(4) : text;
}

const dashboardEntries = [
  {
    slug: 'mcp',
    title: 'IPFS Datasets MCP Dashboard',
    templateName: 'mcp_dashboard.html',
    summary: 'Primary MCP datasets console.',
  },
  {
    slug: 'mcp-clean',
    title: 'IPFS Datasets MCP Dashboard Clean',
    templateName: 'mcp_dashboard_clean.html',
    summary: 'Clean MCP datasets management surface.',
  },
  {
    slug: 'mcp-final',
    title: 'IPFS Datasets MCP Dashboard Final',
    templateName: 'mcp_dashboard_final.html',
    summary: 'Final MCP dashboard variant.',
  },
  {
    slug: 'software-mcp',
    title: 'Software Engineering Dashboard',
    templateName: 'software_dashboard_mcp.html',
    summary: 'Software workflow and theorem dashboard.',
  },
  {
    slug: 'investigation',
    title: 'Unified Investigation Dashboard',
    templateName: 'unified_investigation_dashboard.html',
    summary: 'Investigation dashboard template.',
  },
  {
    slug: 'investigation-mcp',
    title: 'Unified Investigation Dashboard MCP',
    templateName: 'unified_investigation_dashboard_mcp.html',
    summary: 'Investigation dashboard with MCP integration.',
  },
  {
    slug: 'news-analysis',
    title: 'News Analysis Dashboard',
    templateName: 'news_analysis_dashboard.html',
    summary: 'Original news analysis dashboard.',
  },
  {
    slug: 'news-analysis-improved',
    title: 'News Analysis Dashboard Improved',
    templateName: 'news_analysis_dashboard_improved.html',
    summary: 'Enhanced news analysis dashboard.',
  },
  {
    slug: 'admin-index',
    title: 'Admin Dashboard Home',
    templateName: 'admin/index.html',
    summary: 'Administrative dashboard landing page.',
  },
  {
    slug: 'admin-login',
    title: 'Admin Dashboard Login',
    templateName: 'admin/login.html',
    summary: 'Administrative authentication surface.',
  },
  {
    slug: 'admin-error',
    title: 'Admin Dashboard Error',
    templateName: 'admin/error.html',
    summary: 'Administrative error surface.',
  },
  {
    slug: 'admin-analytics',
    title: 'Analytics Dashboard',
    templateName: 'admin/analytics_dashboard.html',
    summary: 'Analytics dashboard entry point.',
  },
  {
    slug: 'admin-rag-query',
    title: 'RAG Query Dashboard',
    templateName: 'admin/rag_query_dashboard.html',
    summary: 'RAG query dashboard entry point.',
  },
  {
    slug: 'admin-investigation',
    title: 'Admin Investigation Dashboard',
    templateName: 'admin/investigation_dashboard.html',
    summary: 'Administrative investigation dashboard.',
  },
  {
    slug: 'admin-caselaw',
    title: 'Caselaw Dashboard',
    templateName: 'admin/caselaw_dashboard.html',
    summary: 'Caselaw dashboard entry point.',
  },
  {
    slug: 'admin-caselaw-mcp',
    title: 'Caselaw MCP Dashboard',
    templateName: 'admin/caselaw_dashboard_mcp.html',
    summary: 'Caselaw dashboard with MCP integration.',
  },
  {
    slug: 'admin-finance-mcp',
    title: 'Finance MCP Dashboard',
    templateName: 'admin/finance_dashboard_mcp.html',
    summary: 'Finance dashboard with MCP integration.',
  },
  {
    slug: 'admin-finance-workflow',
    title: 'Finance Workflow Dashboard',
    templateName: 'admin/finance_workflow_dashboard.html',
    summary: 'Finance workflow dashboard entry point.',
  },
  {
    slug: 'admin-medicine-mcp',
    title: 'Medicine MCP Dashboard',
    templateName: 'admin/medicine_dashboard_mcp.html',
    summary: 'Medicine dashboard with MCP integration.',
  },
  {
    slug: 'admin-patent',
    title: 'Patent Dashboard',
    templateName: 'admin/patent_dashboard.html',
    summary: 'Patent dashboard entry point.',
  },
  {
    slug: 'admin-discord',
    title: 'Discord Dashboard',
    templateName: 'admin/discord_dashboard.html',
    summary: 'Discord workflow dashboard.',
  },
  {
    slug: 'admin-graphrag',
    title: 'GraphRAG Dashboard',
    templateName: 'admin/graphrag_dashboard.html',
    summary: 'GraphRAG dashboard entry point.',
  },
  {
    slug: 'admin-mcp',
    title: 'Admin MCP Dashboard',
    templateName: 'admin/mcp_dashboard.html',
    summary: 'Administrative MCP dashboard.',
  },
];

const profileData = {
  hashed_username: 'demo-user',
  hashed_password: 'demo-password',
  username: 'demo-user',
  chat_history: {
    '2026-03-22T09:00:00Z': {
      sender: 'System:',
      message: 'Welcome back to Lex Publicus.',
    },
    '2026-03-22T09:01:00Z': {
      sender: 'demo-user',
      message: 'I need help drafting a retaliation complaint.',
      explanation: {
        summary: 'This anchors the complaint generation workflow.',
      },
    },
  },
  complaint_summary: {
    claim_type: 'retaliation',
    summary_of_facts: [
      'Jane Doe reported discrimination to HR.',
      'Acme terminated Jane Doe shortly after the report.',
    ],
  },
};

const workspaceQuestions = [
  { id: 'party_name', label: 'Your name', prompt: 'Who is bringing the complaint?', placeholder: 'Jane Doe' },
  { id: 'opposing_party', label: 'Opposing party', prompt: 'Who are you filing against?', placeholder: 'Acme Corporation' },
  { id: 'protected_activity', label: 'Protected activity', prompt: 'What did you report, oppose, or request before the retaliation happened?', placeholder: 'Reported discrimination to HR' },
  { id: 'adverse_action', label: 'Adverse action', prompt: 'What happened to you afterward?', placeholder: 'Termination two days later' },
  { id: 'timeline', label: 'Timeline', prompt: 'When did the key events happen?', placeholder: 'Complaint on March 8, termination on March 10' },
  { id: 'harm', label: 'Harm', prompt: 'What harm did you suffer?', placeholder: 'Lost wages, lost benefits, emotional distress' },
];

const claimElements = [
  { id: 'protected_activity', label: 'Protected activity' },
  { id: 'employer_knowledge', label: 'Employer knowledge' },
  { id: 'adverse_action', label: 'Adverse action' },
  { id: 'causation', label: 'Causal link' },
  { id: 'harm', label: 'Damages' },
];

function createWorkspaceState(userId = 'did:key:playwright-demo') {
  return {
    user_id: userId,
    claim_type: 'retaliation',
    case_synopsis: '',
    intake_answers: {},
    evidence: {
      testimony: [],
      documents: [],
    },
    draft: null,
    ui_readiness: null,
  };
}

const workspaceSessions = new Map();

function getWorkspaceState(userId = 'did:key:playwright-demo') {
  if (!workspaceSessions.has(userId)) {
    workspaceSessions.set(userId, createWorkspaceState(userId));
  }
  return workspaceSessions.get(userId);
}

function workspaceReview(workspaceState) {
  const answers = workspaceState.intake_answers;
  const testimony = workspaceState.evidence.testimony;
  const documents = workspaceState.evidence.documents;
  const support_matrix = claimElements.map((element) => {
    const intakeSupported = Boolean(answers[element.id])
      || (element.id === 'employer_knowledge' && Boolean(answers.protected_activity))
      || (element.id === 'causation' && Boolean(answers.timeline));
    const testimonyCount = testimony.filter((item) => item.claim_element_id === element.id).length;
    const documentCount = documents.filter((item) => item.claim_element_id === element.id).length;
    const supportCount = testimonyCount + documentCount + (intakeSupported ? 1 : 0);
    return {
      id: element.id,
      label: element.label,
      supported: supportCount > 0,
      intake_supported: intakeSupported,
      testimony_count: testimonyCount,
      document_count: documentCount,
    };
  });
  return {
    support_matrix,
    overview: {
      supported_elements: support_matrix.filter((item) => item.supported).length,
      missing_elements: support_matrix.filter((item) => !item.supported).length,
      testimony_items: testimony.length,
      document_items: documents.length,
    },
    recommended_actions: [
      {
        title: 'Collect more corroboration',
        detail: support_matrix.some((item) => !item.supported)
          ? 'Add evidence for unsupported claim elements.'
          : 'All core claim elements have support.',
      },
      {
        title: 'Check timing',
        detail: 'Temporal proximity can strengthen causation.',
      },
    ],
    testimony,
    documents,
  };
}

function workspaceSessionPayload(userId = 'did:key:playwright-demo') {
  const workspaceState = getWorkspaceState(userId);
  const nextQuestion = workspaceQuestions.find((question) => !workspaceState.intake_answers[question.id]) || null;
  return {
    session: JSON.parse(JSON.stringify(workspaceState)),
    draft: workspaceState.draft ? JSON.parse(JSON.stringify(workspaceState.draft)) : null,
    questions: workspaceQuestions.map((question) => ({
      ...question,
      answer: workspaceState.intake_answers[question.id] || '',
      is_answered: Boolean(String(workspaceState.intake_answers[question.id] || '').trim()),
    })),
    next_question: nextQuestion,
    review: workspaceReview(workspaceState),
    case_synopsis: String(workspaceState.case_synopsis || '').trim(),
  };
}

function buildMediatorPromptPayload(userId = 'did:key:playwright-demo') {
  const sessionPayload = workspaceSessionPayload(userId);
  const supportMatrix = ((sessionPayload.review || {}).support_matrix) || [];
  const firstGap = supportMatrix.find((item) => !item.supported) || null;
  const synopsis = String(sessionPayload.case_synopsis || '').trim();
  const gapFocus = firstGap
    ? `Focus especially on clarifying ${String(firstGap.label || '').toLowerCase()} and what proof could corroborate it.`
    : 'Focus on sharpening the strongest testimony, identifying corroboration, and confirming the cleanest sequence of events.';
  return {
    user_id: userId,
    case_synopsis: synopsis,
    target_gap: firstGap,
    prefill_message: `${synopsis}\n\nMediator, help turn this into testimony-ready narrative for the complaint record. Ask the single most useful next follow-up question, keep the tone calm, and explain what support would strengthen the case. ${gapFocus}`,
    return_target_tab: 'review',
  };
}

function complaintReadinessPayload(userId = 'did:key:playwright-demo') {
  const sessionPayload = workspaceSessionPayload(userId);
  const overview = ((sessionPayload.review || {}).overview) || {};
  const questions = sessionPayload.questions || [];
  const answeredQuestions = questions.filter((item) => item.is_answered).length;
  const totalQuestions = questions.length;
  const supportedElements = Number(overview.supported_elements || 0);
  const missingElements = Number(overview.missing_elements || 0);
  const evidenceCount = Number(overview.testimony_items || 0) + Number(overview.document_items || 0);
  const hasDraft = Boolean(sessionPayload.draft);

  let score = 10;
  if (totalQuestions > 0) {
    score += Math.round((answeredQuestions / totalQuestions) * 35);
  }
  score += Math.round((supportedElements / Math.max(supportedElements + missingElements, 1)) * 35);
  if (evidenceCount > 0) {
    score += Math.min(12, evidenceCount * 4);
  }
  if (hasDraft) {
    score += 12;
  }
  score = Math.max(0, Math.min(100, score));

  let verdict = 'Not ready to draft';
  let detail = 'Finish intake and add support before relying on generated complaint text.';
  let recommendedRoute = '/workspace';
  let recommendedAction = 'Continue the guided complaint workflow to complete intake and collect support.';
  if (hasDraft) {
    verdict = 'Draft in progress';
    detail = 'A complaint draft already exists. Compare it against the supported facts and remaining proof gaps before treating it as filing-ready.';
    recommendedRoute = '/document';
    recommendedAction = 'Refine the existing draft and reconcile it with the support review.';
  } else if (totalQuestions > 0 && answeredQuestions === totalQuestions && missingElements === 0 && evidenceCount > 0) {
    verdict = 'Ready for first draft';
    detail = 'The intake record and support posture are coherent enough to generate a first complaint draft.';
    recommendedRoute = '/document';
    recommendedAction = 'Generate the first complaint draft from the current record.';
  } else if (answeredQuestions > 0) {
    verdict = 'Still building the record';
    detail = `${missingElements} claim elements still need support and ${Math.max(totalQuestions - answeredQuestions, 0)} intake answers may still be missing.`;
    recommendedRoute = missingElements > 0 ? '/claim-support-review' : '/workspace';
    recommendedAction = 'Review support gaps and attach stronger evidence before relying on generated complaint language.';
  }

  return {
    user_id: userId,
    score,
    verdict,
    detail,
    recommended_route: recommendedRoute,
    recommended_action: recommendedAction,
    answered_questions: answeredQuestions,
    total_questions: totalQuestions,
    supported_elements: supportedElements,
    missing_elements: missingElements,
    evidence_count: evidenceCount,
    has_draft: hasDraft,
  };
}

function uiReadinessPayload(userId = 'did:key:playwright-demo') {
  const workspaceState = getWorkspaceState(userId);
  return workspaceState.ui_readiness || {
    user_id: userId,
    status: 'unavailable',
    verdict: 'No UI verdict cached',
    score: null,
    summary: '',
    release_blockers: [],
    acceptance_checks: [],
    tested_stages: [],
    sdk_invocations: [],
    actor_path_breaks: [],
    broken_controls: [],
    issue_counts: { high: 0, medium: 0, low: 0 },
    workflow_type: null,
    updated_at: null,
  };
}

function persistUiReadiness(userId = 'did:key:playwright-demo', result = {}) {
  const workspaceState = getWorkspaceState(userId);
  const review = (result && result.review) || {};
  const complaintJourney = review.complaint_journey || result.complaint_journey || {};
  const criticReview = review.critic_review || result.critic_review || {};
  const issues = Array.isArray(review.issues) ? review.issues : Array.isArray(result.issues) ? result.issues : [];
  const actorPathBreaks = Array.isArray(review.actor_path_breaks) ? review.actor_path_breaks : Array.isArray(result.actor_path_breaks) ? result.actor_path_breaks : [];
  const brokenControls = Array.isArray(review.broken_controls) ? review.broken_controls : Array.isArray(result.broken_controls) ? result.broken_controls : [];
  const releaseBlockers = Array.isArray(complaintJourney.release_blockers) ? complaintJourney.release_blockers : [];
  const acceptanceChecks = Array.isArray(criticReview.acceptance_checks) ? criticReview.acceptance_checks : [];
  const testedStages = Array.isArray(complaintJourney.tested_stages) ? complaintJourney.tested_stages : [];
  const sdkInvocations = Array.isArray(complaintJourney.sdk_tool_invocations) ? complaintJourney.sdk_tool_invocations : [];
  const issueCounts = { high: 0, medium: 0, low: 0 };
  for (const item of issues) {
    const severity = String((item || {}).severity || '').trim().toLowerCase();
    if (severity in issueCounts) {
      issueCounts[severity] += 1;
    }
  }
  let score = 100;
  score -= releaseBlockers.length * 14;
  score -= actorPathBreaks.length * 9;
  score -= brokenControls.length * 8;
  score -= issueCounts.high * 12;
  score -= issueCounts.medium * 6;
  score -= issueCounts.low * 3;
  const criticVerdict = String(criticReview.verdict || 'warning').trim().toLowerCase();
  if (criticVerdict === 'fail') {
    score -= 25;
  } else if (criticVerdict === 'warning') {
    score -= 10;
  }
  if (testedStages.length >= 6) {
    score += 4;
  }
  if (sdkInvocations.length >= 2) {
    score += 4;
  }
  if (acceptanceChecks.length >= 3) {
    score += 4;
  }
  score = Math.max(0, Math.min(100, score));
  let verdict = 'Needs repair';
  if (score >= 85 && releaseBlockers.length === 0 && criticVerdict !== 'fail') {
    verdict = 'Client-safe';
  } else if (score < 65 || releaseBlockers.length > 1 || criticVerdict === 'fail') {
    verdict = 'Do not send to clients yet';
  }
  workspaceState.ui_readiness = {
    user_id: userId,
    status: 'cached',
    verdict,
    score,
    summary: String(result.latest_review || review.summary || result.summary || '').trim(),
    release_blockers: releaseBlockers,
    acceptance_checks: acceptanceChecks,
    tested_stages: testedStages,
    sdk_invocations: sdkInvocations,
    actor_path_breaks: actorPathBreaks,
    broken_controls: brokenControls,
    issue_counts: issueCounts,
    workflow_type: String(result.workflow_type || ((result.backend || {}).strategy) || 'review'),
    updated_at: '2026-03-23T00:00:00+00:00',
  };
  return workspaceState.ui_readiness;
}

function workflowCapabilitiesPayload(userId = 'did:key:playwright-demo') {
  const sessionPayload = workspaceSessionPayload(userId);
  const overview = ((sessionPayload.review || {}).overview) || {};
  const questions = sessionPayload.questions || [];
  const answeredCount = questions.filter((item) => item.is_answered).length;
  const claimType = String(((sessionPayload.session || {}).claim_type) || 'retaliation');
  const draftStrategy = String(((sessionPayload.draft || {}).draft_strategy) || 'template');
  return {
    user_id: userId,
    case_synopsis: String(sessionPayload.case_synopsis || '').trim(),
    overview,
    claim_type: claimType,
    claim_type_label: claimType.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
    draft_strategy: draftStrategy,
    complaint_readiness: complaintReadinessPayload(userId),
    ui_readiness: uiReadinessPayload(userId),
    capabilities: [
      { id: 'intake_questions', label: 'Complaint intake questions', available: questions.length > 0, detail: `${answeredCount} of ${questions.length} intake questions answered.` },
      { id: 'mediator_prompt', label: 'Chat mediator handoff', available: true, detail: 'A testimony-ready mediator prompt can be generated from the shared case synopsis and support gaps.' },
      { id: 'evidence_capture', label: 'Evidence capture', available: true, detail: `${(overview.testimony_items || 0) + (overview.document_items || 0)} evidence items saved.` },
      { id: 'support_review', label: 'Claim support review', available: true, detail: `${overview.supported_elements || 0} supported elements, ${overview.missing_elements || 0} gaps remaining.` },
      { id: 'complaint_draft', label: 'Complaint draft', available: true, detail: sessionPayload.draft ? 'A draft already exists and can be edited.' : 'A draft can be generated from the current complaint record.' },
      { id: 'claim_type_alignment', label: 'Claim-type drafting alignment', available: true, detail: `The current complaint type is ${claimType.replace(/_/g, ' ')}.` },
      { id: 'formal_complaint_generation', label: 'Formal complaint generation', available: true, detail: draftStrategy === 'llm_router' ? 'The current draft uses llm_router-backed formal complaint generation.' : 'The current draft is using the deterministic template fallback.' },
      { id: 'complaint_packet', label: 'Complaint packet export', available: true, detail: 'The lawsuit packet can be exported as a structured browser, CLI, or MCP artifact.' },
    ],
  };
}

function exportComplaintPacketPayload(userId = 'did:key:playwright-demo') {
  const sessionPayload = workspaceSessionPayload(userId);
  const draft = sessionPayload.draft || getWorkspaceState(userId).draft || { title: 'Draft not generated', requested_relief: [], body: '' };
  const requestedRelief = Array.isArray(draft.requested_relief) ? draft.requested_relief : [];
  const questionLines = (sessionPayload.questions || []).map((item) => `- **${item.label || item.id || 'Question'}:** ${item.answer || 'Not answered'}`);
  const testimonyLines = (((sessionPayload.session || {}).evidence || {}).testimony || [])
    .map((item) => `- **${item.title || 'Testimony'}** (${item.claim_element_id || 'unmapped'}): ${item.content || ''}`.trim());
  const documentLines = (((sessionPayload.session || {}).evidence || {}).documents || [])
    .map((item) => `- **${item.title || 'Document'}** (${item.claim_element_id || 'unmapped'}): ${item.content || ''}`.trim());
  const markdownContent = [
    draft.body || 'No complaint draft has been generated yet.',
    '',
    'APPENDIX A - CASE SYNOPSIS',
    String(sessionPayload.case_synopsis || '').trim() || 'No shared case synopsis saved yet.',
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
    `- Claim type: ${String(((sessionPayload.session || {}).claim_type) || 'retaliation')}`,
    `- User ID: ${String(userId)}`,
    '- Exported at: 2026-03-23T00:00:00+00:00',
  ].join('\n');
  return {
    packet: {
      title: draft.title,
      user_id: userId,
      claim_type: sessionPayload.session.claim_type,
      case_synopsis: sessionPayload.case_synopsis,
      questions: sessionPayload.questions,
      evidence: sessionPayload.session.evidence,
      review: sessionPayload.review,
      draft,
      exported_at: '2026-03-23T00:00:00+00:00',
    },
    artifacts: {
      json: {
        filename: `${slugifyFilename(draft.title || 'complaint-packet')}.json`,
      },
      markdown: {
        filename: `${slugifyFilename(draft.title || 'complaint-packet')}.md`,
        content: markdownContent,
      },
      docx: {
        filename: `${slugifyFilename(draft.title || 'complaint-packet')}.docx`,
      },
      pdf: {
        filename: `${slugifyFilename(draft.title || 'complaint-packet')}.pdf`,
      },
    },
    packet_summary: {
      question_count: sessionPayload.questions.length,
      answered_question_count: sessionPayload.questions.filter((item) => item.is_answered).length,
      supported_elements: sessionPayload.review.overview.supported_elements || 0,
      missing_elements: sessionPayload.review.overview.missing_elements || 0,
      testimony_items: sessionPayload.review.overview.testimony_items || 0,
      document_items: sessionPayload.review.overview.document_items || 0,
      has_draft: Boolean(sessionPayload.draft),
      complaint_readiness: complaintReadinessPayload(userId),
      artifact_formats: ['json', 'markdown', 'docx', 'pdf'],
    },
    artifact_analysis: {
      draft_word_count: String(draft.body || '').split(/\s+/).filter(Boolean).length,
      evidence_item_count: Number((sessionPayload.session.evidence.testimony || []).length + (sessionPayload.session.evidence.documents || []).length),
      requested_relief_count: Number((draft.requested_relief || []).length),
      supported_elements: sessionPayload.review.overview.supported_elements || 0,
      missing_elements: sessionPayload.review.overview.missing_elements || 0,
      has_case_synopsis: Boolean(String(sessionPayload.case_synopsis || '').trim()),
    },
  };
}

function escapeXml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function createStoredZipBuffer(files) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  for (const [name, content] of files) {
    const nameBuffer = Buffer.from(name, 'utf-8');
    const contentBuffer = Buffer.isBuffer(content) ? content : Buffer.from(content, 'utf-8');
    const localHeader = Buffer.alloc(30 + nameBuffer.length);
    localHeader.writeUInt32LE(0x04034b50, 0);
    localHeader.writeUInt16LE(20, 4);
    localHeader.writeUInt16LE(0, 6);
    localHeader.writeUInt16LE(0, 8);
    localHeader.writeUInt16LE(0, 10);
    localHeader.writeUInt16LE(0, 12);
    localHeader.writeUInt32LE(0, 14);
    localHeader.writeUInt32LE(contentBuffer.length, 18);
    localHeader.writeUInt32LE(contentBuffer.length, 22);
    localHeader.writeUInt16LE(nameBuffer.length, 26);
    localHeader.writeUInt16LE(0, 28);
    nameBuffer.copy(localHeader, 30);

    const centralHeader = Buffer.alloc(46 + nameBuffer.length);
    centralHeader.writeUInt32LE(0x02014b50, 0);
    centralHeader.writeUInt16LE(20, 4);
    centralHeader.writeUInt16LE(20, 6);
    centralHeader.writeUInt16LE(0, 8);
    centralHeader.writeUInt16LE(0, 10);
    centralHeader.writeUInt16LE(0, 12);
    centralHeader.writeUInt16LE(0, 14);
    centralHeader.writeUInt32LE(0, 16);
    centralHeader.writeUInt32LE(contentBuffer.length, 20);
    centralHeader.writeUInt32LE(contentBuffer.length, 24);
    centralHeader.writeUInt16LE(nameBuffer.length, 28);
    centralHeader.writeUInt16LE(0, 30);
    centralHeader.writeUInt16LE(0, 32);
    centralHeader.writeUInt16LE(0, 34);
    centralHeader.writeUInt16LE(0, 36);
    centralHeader.writeUInt32LE(0, 38);
    centralHeader.writeUInt32LE(offset, 42);
    nameBuffer.copy(centralHeader, 46);

    localParts.push(localHeader, contentBuffer);
    centralParts.push(centralHeader);
    offset += localHeader.length + contentBuffer.length;
  }
  const centralDirectory = Buffer.concat(centralParts);
  const endRecord = Buffer.alloc(22);
  endRecord.writeUInt32LE(0x06054b50, 0);
  endRecord.writeUInt16LE(0, 4);
  endRecord.writeUInt16LE(0, 6);
  endRecord.writeUInt16LE(files.length, 8);
  endRecord.writeUInt16LE(files.length, 10);
  endRecord.writeUInt32LE(centralDirectory.length, 12);
  endRecord.writeUInt32LE(offset, 16);
  endRecord.writeUInt16LE(0, 20);
  return Buffer.concat([...localParts, centralDirectory, endRecord]);
}

function buildComplaintDocxBuffer(packet, markdownContent) {
  const title = String((((packet || {}).draft || {}).title) || packet.title || 'Complaint Packet');
  const paragraphs = [title, '', ...String(markdownContent || '').replace(/\r\n/g, '\n').split('\n')];
  const documentXml = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' +
    paragraphs.map((line) => (
      line ? `<w:p><w:r><w:t xml:space="preserve">${escapeXml(line)}</w:t></w:r></w:p>` : '<w:p/>'
    )).join('') +
    '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>' +
    '</w:body></w:document>'
  );
  return createStoredZipBuffer([
    ['[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>'],
    ['_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'],
    ['docProps/app.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Complaint Workspace Stub</Application></Properties>'],
    ['docProps/core.xml', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>${escapeXml(title)}</dc:title><dc:creator>Complaint Workspace Stub</dc:creator></cp:coreProperties>`],
    ['word/document.xml', documentXml],
  ]);
}

function buildComplaintDownloadArtifact(userId = 'did:key:playwright-demo', outputFormat = 'json') {
  const packetPayload = exportComplaintPacketPayload(userId);
  const packet = packetPayload.packet || {};
  const artifacts = packetPayload.artifacts || {};
  const normalizedFormat = String(outputFormat || 'json').trim().toLowerCase();
  if (normalizedFormat === 'json') {
    return {
      filename: ((artifacts.json || {}).filename) || 'complaint-packet.json',
      mediaType: 'application/json',
      body: Buffer.from(JSON.stringify(packet, null, 2), 'utf-8'),
    };
  }
  if (normalizedFormat === 'markdown' || normalizedFormat === 'md') {
    return {
      filename: ((artifacts.markdown || {}).filename) || 'complaint-packet.md',
      mediaType: 'text/markdown; charset=utf-8',
      body: Buffer.from(String((artifacts.markdown || {}).content || ''), 'utf-8'),
    };
  }
  if (normalizedFormat === 'pdf') {
    const markdownContent = String((artifacts.markdown || {}).content || 'Complaint packet');
    const pdfStub = `%PDF-1.4\n% Complaint packet preview\n1 0 obj\n<< /Type /Catalog >>\nendobj\n% ${markdownContent}\n%%EOF\n`;
    return {
      filename: ((artifacts.pdf || {}).filename) || 'complaint-packet.pdf',
      mediaType: 'application/pdf',
      body: Buffer.from(pdfStub, 'utf-8'),
    };
  }
  if (normalizedFormat === 'docx') {
    const markdownContent = String((artifacts.markdown || {}).content || 'Complaint packet');
    return {
      filename: ((artifacts.docx || {}).filename) || 'complaint-packet.docx',
      mediaType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      body: buildComplaintDocxBuffer(packet, markdownContent),
    };
  }
  return buildComplaintDownloadArtifact(userId, 'json');
}

function buildComplaintOutputAnalysis(userId = 'did:key:playwright-demo') {
  const packetPayload = exportComplaintPacketPayload(userId);
  const packetSummary = packetPayload.packet_summary || {};
  const artifactAnalysis = packetPayload.artifact_analysis || {};
  const claimType = String((((packetPayload.packet || {}).claim_type) || 'retaliation'));
  const draftStrategy = String(((((packetPayload.packet || {}).draft || {}).draft_strategy) || 'template'));
  const complaintBody = String((((packetPayload.packet || {}).draft || {}).body || ''));
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
      + (Number(artifactAnalysis.evidence_item_count || 0) > 0 ? 10 : 0)
      + (Number(artifactAnalysis.requested_relief_count || 0) > 0 ? 5 : 0)
      + (Number(artifactAnalysis.draft_word_count || 0) >= 180 ? 10 : 0)
    ,
  );
  const expectedComplaintHeading = claimType === 'retaliation'
    ? 'COMPLAINT FOR RETALIATION'
    : `COMPLAINT FOR ${claimType.replace(/_/g, ' ').toUpperCase()}`;
  const expectedCountHeading = claimType === 'retaliation'
    ? 'COUNT I - RETALIATION'
    : `COUNT I - ${claimType.replace(/_/g, ' ').toUpperCase()}`;
  const claimTypeAlignment = {
    complaint_heading_matches: complaintBody.includes(expectedComplaintHeading),
    count_heading_matches: complaintBody.includes(expectedCountHeading),
  };
  const claimTypeAlignmentScore = claimTypeAlignment.complaint_heading_matches && claimTypeAlignment.count_heading_matches
    ? 100
    : (claimTypeAlignment.complaint_heading_matches || claimTypeAlignment.count_heading_matches ? 50 : 0);
  let releaseGate = {
    verdict: 'blocked',
    reason: 'The exported complaint is not yet formal or well-aligned enough to treat the current UI flow as safe for real legal clients.',
    claim_type: claimType,
    claim_type_label: claimType.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
    draft_strategy: draftStrategy,
    filing_shape_score: filingShapeScore,
    claim_type_alignment_score: claimTypeAlignmentScore,
    missing_elements: Number(artifactAnalysis.missing_elements || 0),
    evidence_item_count: Number(artifactAnalysis.evidence_item_count || 0),
  };
  if (filingShapeScore >= 85 && claimTypeAlignmentScore >= 85 && Number(artifactAnalysis.missing_elements || 0) === 0 && Number(artifactAnalysis.evidence_item_count || 0) > 0) {
    releaseGate = {
      ...releaseGate,
      verdict: 'pass',
      reason: `The exported complaint currently reads like a filing-ready ${releaseGate.claim_type_label.toLowerCase()} complaint and the record is materially supported.`,
    };
  } else if (filingShapeScore >= 75 && claimTypeAlignmentScore >= 75 && Number(artifactAnalysis.evidence_item_count || 0) > 0) {
    releaseGate = {
      ...releaseGate,
      verdict: 'warning',
      reason: 'The exported complaint is moving in the right direction, but it still needs tighter proof posture, claim alignment, or filing polish before it should be treated as client-safe.',
    };
  }
  return {
    user_id: userId,
    packet_summary: packetSummary,
    artifact_analysis: artifactAnalysis,
    ui_feedback: {
      summary: 'The exported complaint artifact was analyzed to infer which UI steps may still be too weak, hidden, or permissive for a real complainant.',
      filing_shape_score: filingShapeScore,
      formal_sections_present: formalSectionsPresent,
      claim_type_alignment: claimTypeAlignment,
      claim_type_alignment_score: claimTypeAlignmentScore,
      release_gate: releaseGate,
      issues: Number(packetSummary.missing_elements || 0) > 0
        ? [
            {
              severity: 'high',
              source: 'complaint_output',
              finding: `The exported complaint still reflects ${Number(packetSummary.missing_elements || 0)} unsupported claim elements.`,
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
      release_gate: releaseGate,
      draft_excerpt: String((((packetPayload.packet || {}).draft || {}).body || '')).slice(0, 600),
      complaint_strengths: [
        `Supported elements: ${Number(packetSummary.supported_elements || 0)}`,
        `Evidence items: ${Number(packetSummary.testimony_items || 0) + Number(packetSummary.document_items || 0)}`,
        `Requested relief items: ${Number(artifactAnalysis.requested_relief_count || 0)}`,
        `Formal sections present: ${Object.values(formalSectionsPresent).filter(Boolean).length}/${Object.keys(formalSectionsPresent).length}`,
      ],
    },
  };
}

function buildStubUiReviewResult(args = {}, userId = 'did:key:playwright-demo') {
  const analysis = buildComplaintOutputAnalysis(userId);
  const suggestion = (((analysis.ui_feedback || {}).ui_suggestions || [])[0]) || {};
  const routerLabel = [args.provider, args.model].filter(Boolean).join(' / ') || 'default llm_router multimodal_router path';
  if (Number(args.iterations || 0) > 0) {
    return {
      iterations: Number(args.iterations || 0),
      screenshot_dir: args.screenshot_dir || 'artifacts/ui-audit/screenshots',
      output_dir: args.output_path || 'artifacts/ui-audit/reviews',
      latest_review: `# Top Risks\n- ${routerLabel} should keep complaint-output guidance visible while reviewing screenshots.\n\n# High-Impact UX Fixes\n- ${String(suggestion.title || 'Promote complaint-output blockers')} so unsupported claim elements stay visible before export.\n- ${String(suggestion.recommendation || 'Use complaint-output suggestions to tighten review and draft guidance.')}\n\n# Stage Findings\n## Intake\nFirst-time complainants need clearer reassurance that incomplete dates and imperfect wording can still be saved.\n\n## Evidence\nEvidence capture guidance is still too easy to miss for first-time complainants.\n\n## Review\nComplaint-output suggestion carried into router review: ${String(suggestion.title || 'Promote complaint-output blockers')}.\n\n## Draft\nDraft generation should feel like the direct continuation of the case theory, not a separate document tool.\n\n## Integration Discovery\n${routerLabel} should stay visible from the shared dashboard shortcuts and tool panels.`,
      stage_findings: {
        Intake: 'First-time complainants need clearer reassurance that incomplete dates and imperfect wording can still be saved.',
        Evidence: 'The evidence step should explain which documents help prove causation before users are asked to upload or summarize proof.',
        Review: `Complaint-output suggestion carried into router review: ${String(suggestion.title || 'Promote complaint-output blockers')}.`,
        Draft: 'Draft generation should feel like the direct continuation of the case theory, not a separate document tool.',
        'Integration Discovery': `${routerLabel} should stay visible so operators do not miss the shared complaint-generator tooling.`,
      },
      actor_summary: 'The actor can stay on one DID-backed complaint path, but still needs clearer guidance for synopsis, evidence upload, review, and draft transitions.',
      critic_summary: 'The critic expects hard end-to-end assertions around testimony, evidence attachment, support review, and final complaint generation.',
      actor_path_breaks: [
        'Users can still miss the moment when they should save a shared synopsis before moving into review and draft.',
      ],
      critic_test_obligations: [
        'Verify the full workspace journey from intake through mediator synopsis, evidence upload, review, and final complaint draft.',
      ],
      latest_review_markdown_path: 'artifacts/ui-audit/reviews/iteration-01-review.md',
      runs: [
        {
          iteration: 1,
          artifact_count: 1,
          review_excerpt: `Complaint-output suggestion carried into router review: ${String(suggestion.title || 'Promote complaint-output blockers')}.`,
          review_markdown_path: 'artifacts/ui-audit/reviews/iteration-01-review.md',
          review_json_path: 'artifacts/ui-audit/reviews/iteration-01-review.json',
        },
      ],
    };
  }
  return {
    generated_at: '2026-03-23T00:00:00+00:00',
    backend: { strategy: 'playwright-stub' },
    screenshots: [],
    review: {
      summary: `Stub UI review completed with ${routerLabel}. Complaint-output suggestion: ${String(suggestion.title || 'Promote complaint-output blockers')}.`,
      stage_findings: {
        Intake: 'The intake flow should make the first required story fields easier to understand before asking for detail.',
        Evidence: 'Users need clearer cues about what evidence strengthens the current complaint theory.',
        Review: `Complaint-output suggestion carried into router review: ${String(suggestion.title || 'Promote complaint-output blockers')}.`,
      },
      actor_summary: 'The actor can start the complaint, but the transition into evidence and review still needs clearer guidance.',
      critic_summary: 'The critic wants explicit regression checks for buttons and the MCP SDK-backed journey.',
      actor_path_breaks: [
        'The user may not understand when to move from intake to evidence.',
      ],
      critic_test_obligations: [
        'Keep an end-to-end Playwright flow that verifies the MCP SDK path through every complaint stage.',
      ],
      issues: [
        {
          severity: 'medium',
          surface: '/workspace',
          problem: 'The intake-to-evidence transition needs more explicit guidance for real complainants.',
          user_impact: 'Users may not know what kind of support to add next.',
        },
      ],
    },
  };
}

function buildStubUiOptimizationResult(args = {}, userId = 'did:key:playwright-demo') {
  const analysis = buildComplaintOutputAnalysis(userId);
  const suggestion = (((analysis.ui_feedback || {}).ui_suggestions || [])[0]) || {};
  const routerLabel = [args.provider, args.model].filter(Boolean).join(' / ') || 'default llm_router multimodal_router path';
  return {
    workflow_type: 'ui_ux_closed_loop',
    max_rounds: Number(args.max_rounds || 2),
    rounds_executed: 1,
    stop_reason: 'validation_review_stable',
    latest_validation_review: `# Top Risks\n- ${routerLabel} should preserve complaint-output blockers through the closed-loop run.\n\n# Stage Findings\n## Review\nComplaint-output suggestion carried into optimization: ${String(suggestion.title || 'Promote complaint-output blockers')}.`,
    stage_findings: {
      Intake: 'The optimizer should reduce branching language and keep the first story steps calmer and more linear.',
      Evidence: 'The evidence panel still needs stronger claim-element guidance after optimization.',
      Review: `Complaint-output suggestion carried into optimization: ${String(suggestion.title || 'Promote complaint-output blockers')}.`,
      Draft: 'Draft readiness should remain visible after optimization so users know when a first draft is appropriate.',
      'Integration Discovery': `The optimizer path itself should stay discoverable from the shared dashboard shortcuts and tool panels. ${routerLabel} should preserve that visibility during the closed-loop run.`,
    },
    actor_summary: 'The actor can finish the workflow if the optimizer keeps the path linear and support gaps actionable.',
    critic_summary: 'The critic expects the closed-loop run to preserve MCP SDK visibility and catch broken stage transitions.',
    actor_path_breaks: [
      'Evidence collection and support review still need to feel like one continuous action rather than separate tasks.',
    ],
    critic_test_obligations: [
      'Verify the actor can save the mediator synopsis, upload evidence, review support, generate the complaint, and revise the draft.',
    ],
    cycles: [
      {
        round: 1,
        task: {
          target_files: ['templates/workspace.html', 'static/complaint_mcp_sdk.js'],
          metadata: { workflow_type: 'ui_ux_autopatch' },
        },
        optimizer_result: {
          success: true,
          status: 'applied',
          patch_path: 'artifacts/ui-audit/round-01.patch',
          patch_cid: 'bafyuiuxround01',
          changed_files: ['templates/workspace.html', 'static/complaint_mcp_sdk.js'],
          metadata: { changed_files: ['templates/workspace.html', 'static/complaint_mcp_sdk.js'] },
        },
        validation_review: {
          latest_review: `# Top Risks\n- ${routerLabel} kept complaint-output blockers visible during validation.`,
        },
      },
    ],
  };
}

function generateWorkspaceDraft(workspaceState, requestedRelief, options = {}) {
  const answers = workspaceState.intake_answers;
  const review = workspaceReview(workspaceState);
  const overview = (review || {}).overview || {};
  const evidence = workspaceState.evidence || { testimony: [], documents: [] };
  const relief = requestedRelief && requestedRelief.length ? requestedRelief : ['Back pay', 'Injunctive relief'];
  const caseSynopsis = String(workspaceState.case_synopsis || '').trim();
  const claimType = String(workspaceState.claim_type || 'retaliation');
  const claimTypeTitle = claimType.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
  const protectedActivity = sentenceFragment(answers.protected_activity, 'engaged in protected activity');
  const adverseAction = eventFragment(answers.adverse_action, 'suffered an adverse action');
  const timeline = sentenceFragment(answers.timeline, 'the events occurred close in time');
  const harm = sentenceFragment(answers.harm, 'suffered compensable harm');
  const complaintHeading = claimType === 'retaliation'
    ? 'COMPLAINT FOR RETALIATION'
    : `COMPLAINT FOR ${claimType.replace(/_/g, ' ').toUpperCase()}`;
  const countHeading = claimType === 'retaliation'
    ? 'COUNT I - RETALIATION'
    : `COUNT I - ${claimType.replace(/_/g, ' ').toUpperCase()}`;
  const natureOfAction = {
    retaliation: `1. ${answers.party_name || 'Plaintiff'} brings this retaliation complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from ${answers.opposing_party || 'Defendant'}'s retaliatory response after ${answers.party_name || 'Plaintiff'} engaged in protected activity described as ${protectedActivity}.`,
    employment_discrimination: `1. ${answers.party_name || 'Plaintiff'} brings this employment discrimination complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from discriminatory workplace treatment, unequal terms or conditions, and resulting harm.`,
    housing_discrimination: `1. ${answers.party_name || 'Plaintiff'} brings this housing discrimination complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from discriminatory denial, limitation, interference, or retaliation affecting housing rights or benefits.`,
    due_process_failure: `1. ${answers.party_name || 'Plaintiff'} brings this due process complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from adverse action imposed without the notice, hearing, review, or procedural protections required by law.`,
    consumer_protection: `1. ${answers.party_name || 'Plaintiff'} brings this consumer protection complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from unfair, deceptive, fraudulent, or otherwise unlawful business practices that caused injury.`,
  }[claimType] || `1. ${answers.party_name || 'Plaintiff'} brings this ${claimType.replace(/_/g, ' ')} complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from unlawful conduct that injured ${answers.party_name || 'Plaintiff'} and is being framed in the correct claim-specific pleading posture.`;
  const reliefParagraph = {
    retaliation: `2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy Defendant's retaliatory acts, restore lost compensation, and address the harm caused by the following adverse action: ${adverseAction}.`,
    employment_discrimination: `2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy discriminatory employment practices, restore lost opportunities, and address the harm caused by the following adverse action: ${adverseAction}.`,
    housing_discrimination: `2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy discriminatory housing practices, preserve housing stability, and address the harm caused by the following adverse action: ${adverseAction}.`,
    due_process_failure: `2. Plaintiff seeks declaratory relief, equitable relief, damages, and such further relief as may be just to remedy the procedural deprivation and the harm caused by the following challenged action: ${adverseAction}.`,
    consumer_protection: `2. Plaintiff seeks damages, restitution, equitable relief, and such further relief as may be just to remedy deceptive or unfair consumer practices and the harm caused by the following adverse action or consequence: ${adverseAction}.`,
  }[claimType] || `2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy unlawful conduct and the harm caused by the following adverse action: ${adverseAction}.`;
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
      `7. ${answers.party_name || 'Plaintiff'} alleges protected activity described as ${protectedActivity}.`,
      '8. Plaintiff provided or attempted to provide protected information, opposition, reporting, or participation activity that should not have triggered reprisal.',
      `9. After that protected activity, ${answers.party_name || 'Plaintiff'} experienced adverse action described as ${adverseAction}.`,
      `10. The chronology currently available in the record shows the following sequence: ${timeline}.`,
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
    employment_discrimination: [
      `7. ${answers.party_name || 'Plaintiff'} alleges facts showing discriminatory employment treatment, including protected conduct or circumstances described as ${protectedActivity}.`,
      `8. Defendant thereafter took or maintained adverse employment action described as ${adverseAction}.`,
      `9. The employment chronology currently available in the record shows the following sequence: ${timeline}.`,
      '10. The present record supports an inference of discriminatory motive, disparate treatment, prohibited bias, retaliation, or other unlawful employment decision-making.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
    housing_discrimination: [
      `7. ${answers.party_name || 'Plaintiff'} alleges that they sought, used, requested, or protected housing-related rights, accommodations, benefits, tenancy rights, or fair treatment, including conduct described as ${protectedActivity}.`,
      `8. Defendant thereafter denied, burdened, interfered with, or threatened housing-related rights or benefits through adverse action described as ${adverseAction}.`,
      `9. The housing-related chronology currently available in the record shows the following sequence: ${timeline}.`,
      '10. The present record supports an inference that Defendant acted in a discriminatory manner, interfered with protected housing rights, or retaliated in connection with protected housing activity.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
    due_process_failure: [
      '7. Plaintiff alleges that Defendant imposed or maintained a deprivation affecting protected rights, interests, status, benefits, or property.',
      `8. The challenged action is described as ${adverseAction}.`,
      `9. The chronology currently available in the record shows the following sequence: ${timeline}.`,
      '10. Plaintiff alleges that the deprivation occurred without adequate notice, hearing, review, appeal, or other required procedural protection.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
    consumer_protection: [
      '7. Plaintiff alleges that Defendant engaged in deceptive, misleading, unfair, or otherwise unlawful consumer-facing conduct.',
      `8. That conduct included or resulted in adverse action or consequences described as ${adverseAction}.`,
      `9. The chronology currently available in the record shows the following sequence: ${timeline}.`,
      '10. Plaintiff alleges that the challenged conduct caused consumer harm, financial loss, or other compensable injury in a transactional or service context.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
  }[claimType] || [
    `7. ${answers.party_name || 'Plaintiff'} alleges conduct or circumstances described as ${protectedActivity}.`,
    `8. Defendant engaged in conduct including adverse action described as ${adverseAction}.`,
    `9. The chronology currently available in the record shows the following sequence: ${timeline}.`,
    '10. Plaintiff alleges facts supporting a plausible claim for relief.',
    `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
  ];
  const claimParagraphs = {
    retaliation: [
      `${answers.party_name || 'Plaintiff'} engaged in protected activity described as ${protectedActivity}, and Defendant knew or should have known of that protected conduct.`,
      `Defendant thereafter subjected Plaintiff to materially adverse action described as ${adverseAction}, under circumstances supporting retaliatory motive and causation.`,
      'The pleaded chronology, evidentiary record, and resulting harm support a plausible retaliation claim because protected activity was followed by materially adverse conduct and damages.',
    ],
    employment_discrimination: [
      `Plaintiff was subjected to adverse employment treatment described as ${adverseAction}, in a manner that was discriminatory, disparate, or otherwise unlawful.`,
      'The pleaded facts support an inference that Defendant\'s conduct was motivated by unlawful bias, protected status, protected conduct, or a prohibited employment practice.',
      'The evidentiary record and resulting harm support a plausible employment discrimination claim.',
    ],
    housing_discrimination: [
      `Defendant denied, limited, burdened, or interfered with housing-related rights, opportunities, services, or benefits through conduct described as ${adverseAction}.`,
      'The pleaded facts support an inference that Defendant acted in a discriminatory manner or retaliated in connection with protected housing activity, status, or rights.',
      'The evidentiary record and resulting harm support a plausible housing discrimination claim.',
    ],
    due_process_failure: [
      'Defendant imposed or maintained adverse consequences without the notice, review, hearing, or procedural protections required by law.',
      `The resulting deprivation included challenged action described as ${adverseAction} and related harms without adequate procedural safeguards.`,
      'The pleaded facts and evidentiary record support a plausible due process claim.',
    ],
    consumer_protection: [
      'Defendant engaged in unfair, deceptive, misleading, or unlawful conduct in connection with a consumer transaction or obligation.',
      `That conduct resulted in adverse action or consequences described as ${adverseAction} and caused economic or other compensable harm, including ${harm}.`,
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
  const body = [
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
    caseSynopsis ? `Working case synopsis: ${caseSynopsis}.` : 'Working case synopsis: No case synopsis recorded.',
  ].join('\n\n');
  const useLlm = Boolean(options.use_llm);
  const provider = String(options.provider || '').trim() || 'playwright-stub';
  const model = String(options.model || '').trim() || 'stub-formal-complaint';
  workspaceState.draft = {
    title: `${answers.party_name || 'Plaintiff'} v. ${answers.opposing_party || 'Defendant'} ${claimTypeTitle} Complaint`,
    requested_relief: relief,
    body,
    claim_type: claimType,
    draft_strategy: useLlm ? 'llm_router' : 'template',
    draft_backend: useLlm ? { id: 'complaint-draft', provider, model } : undefined,
  };
}

function sendJson(response, payload) {
  response.writeHead(200, { 'Content-Type': 'application/json' });
  response.end(JSON.stringify(payload));
}

function sendText(response, text, contentType = 'text/plain; charset=utf-8') {
  response.writeHead(200, { 'Content-Type': contentType });
  response.end(text);
}

function sendFile(response, filePath) {
  fs.readFile(filePath, (error, data) => {
    if (error) {
      response.writeHead(404);
      response.end('Not found');
      return;
    }
    const extension = path.extname(filePath).toLowerCase();
    const contentType = extension === '.js'
      ? 'application/javascript; charset=utf-8'
      : extension === '.css'
        ? 'text/css; charset=utf-8'
        : 'text/html; charset=utf-8';
    sendText(response, data, contentType);
  });
}

function collectRequestBody(request) {
  return new Promise((resolve) => {
    let body = '';
    request.on('data', (chunk) => {
      body += chunk;
    });
    request.on('end', () => {
      resolve(body);
    });
  });
}

function template(name) {
  return path.join(templatesDir, name);
}

function ipfsTemplate(name) {
  return path.join(ipfsDatasetsTemplatesDir, name);
}

function renderDashboardHub() {
  const links = dashboardEntries.map((entry) => (
    `<li><a href="/dashboards/ipfs-datasets/${entry.slug}">${entry.title}</a><span>${entry.summary}</span></li>`
  )).join('');
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Unified Dashboard Hub</title>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #f7f7f2; color: #122033; }
    main { max-width: 960px; margin: 0 auto; padding: 32px 24px 48px; }
    .card { background: white; border-radius: 18px; padding: 24px; box-shadow: 0 12px 28px rgba(18, 32, 51, 0.08); }
    ul { padding-left: 20px; }
    li { margin: 12px 0; }
    span { display: block; color: #536471; margin-top: 4px; }
    a { color: #0a4f66; font-weight: 600; }
  </style>
</head>
<body>
  <main>
    <section class="card">
      <h1>Unified Dashboard Hub</h1>
      <p>One complaint-generator website entry point for compatibility dashboard previews.</p>
      <ul>${links}</ul>
    </section>
  </main>
</body>
</html>`;
}

function renderDashboardShell(entry) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${entry.title} | Complaint Generator Dashboard Shell</title>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #f6f4ef; color: #122033; }
    header { padding: 20px 24px; background: linear-gradient(135deg, #14324a, #204f6d); color: white; }
    main { max-width: 1200px; margin: 0 auto; padding: 24px; }
    .card { background: white; border-radius: 18px; padding: 20px; box-shadow: 0 12px 28px rgba(18, 32, 51, 0.08); }
    iframe { width: 100%; min-height: 900px; border: 0; border-radius: 18px; background: white; margin-top: 18px; }
    a { color: #0a4f66; font-weight: 600; }
  </style>
</head>
<body>
  <header>Complaint Generator Unified Dashboards</header>
  <main>
    <section class="card">
      <h1>${entry.title}</h1>
      <p>${entry.summary}</p>
      <p><a href="/dashboards/raw/ipfs-datasets/${entry.slug}" target="_blank" rel="noopener">Open raw dashboard</a></p>
      <iframe src="/dashboards/raw/ipfs-datasets/${entry.slug}" title="${entry.title}"></iframe>
    </section>
  </main>
</body>
</html>`;
}

const routes = new Map([
  ['/', template('index.html')],
  ['/home', template('home.html')],
  ['/chat', template('chat.html')],
  ['/profile', template('profile.html')],
  ['/results', template('results.html')],
  ['/workspace', template('workspace.html')],
  ['/wysiwyg', template('MLWYSIWYG.html')],
  ['/mlwysiwyg', template('MLWYSIWYG.html')],
  ['/MLWYSIWYG', template('MLWYSIWYG.html')],
  ['/document', template('document.html')],
  ['/document/optimization-trace', template('optimization_trace.html')],
  ['/claim-support-review', template('claim_support_review.html')],
]);

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, `http://localhost:${port}`);

  if (request.method === 'GET' && url.pathname === '/health') {
    return sendJson(response, { status: 'healthy' });
  }

  if (request.method === 'GET' && url.pathname === '/cookies') {
    return sendText(response, JSON.stringify({
      hashed_username: profileData.hashed_username,
      hashed_password: profileData.hashed_password,
      token: 'playwright-token',
    }));
  }

  if (request.method === 'POST' && url.pathname === '/load_profile') {
    const rawBody = await collectRequestBody(request);
    const parsed = rawBody ? JSON.parse(rawBody) : {};
    const reqPayload = parsed.request || {};
    const result = {
      hashed_username: reqPayload.hashed_username || profileData.hashed_username,
      hashed_password: reqPayload.hashed_password || profileData.hashed_password,
      data: JSON.stringify(profileData),
    };
    return sendJson(response, reqPayload.username ? { results: result } : result);
  }

  if (request.method === 'POST' && url.pathname === '/create_profile') {
    return sendJson(response, {
      hashed_username: profileData.hashed_username,
      hashed_password: profileData.hashed_password,
      data: JSON.stringify(profileData),
    });
  }

  if (request.method === 'GET' && url.pathname === '/api/documents/download') {
    return sendText(response, `download stub for ${url.searchParams.get('path') || ''}`);
  }

  if (request.method === 'GET' && url.pathname === '/api/complaint-workspace/session') {
    return sendJson(response, workspaceSessionPayload(url.searchParams.get('user_id') || 'did:key:playwright-demo'));
  }

  if (request.method === 'GET' && url.pathname === '/api/complaint-workspace/export/download') {
    const artifact = buildComplaintDownloadArtifact(
      url.searchParams.get('user_id') || 'did:key:playwright-demo',
      url.searchParams.get('output_format') || 'json',
    );
    response.writeHead(200, {
      'Content-Type': artifact.mediaType,
      'Content-Disposition': `attachment; filename="${artifact.filename}"`,
      'Content-Length': String(artifact.body.length),
    });
    response.end(artifact.body);
    return;
  }

  if (request.method === 'POST' && url.pathname === '/api/complaint-workspace/identity') {
    return sendJson(response, {
      did: 'did:key:playwright-demo',
      method: 'did:key',
      provider: 'ipfs_datasets_py.processors.auth.ucan.UCANManager',
    });
  }

  if (request.method === 'GET' && url.pathname === '/api/complaint-workspace/mcp/tools') {
    return sendJson(response, {
      tools: [
        { name: 'complaint.create_identity', description: 'Create a decentralized identity for browser or CLI use.', inputSchema: { type: 'object' } },
        { name: 'complaint.list_intake_questions', description: 'List the complaint intake questions used across browser, CLI, and MCP flows.', inputSchema: { type: 'object' } },
        { name: 'complaint.list_claim_elements', description: 'List the tracked claim elements used for evidence and review.', inputSchema: { type: 'object' } },
        { name: 'complaint.start_session', description: 'Load or initialize a complaint workspace session.', inputSchema: { type: 'object' } },
        { name: 'complaint.submit_intake', description: 'Save complaint intake answers.', inputSchema: { type: 'object' } },
        { name: 'complaint.save_evidence', description: 'Save testimony or document evidence to the workspace.', inputSchema: { type: 'object' } },
        { name: 'complaint.review_case', description: 'Return the support matrix and evidence review.', inputSchema: { type: 'object' } },
        { name: 'complaint.build_mediator_prompt', description: 'Build a testimony-ready chat mediator prompt from the shared case synopsis and support gaps.', inputSchema: { type: 'object' } },
        { name: 'complaint.get_complaint_readiness', description: 'Estimate whether the current complaint record is ready for drafting, still building, or already in draft refinement.', inputSchema: { type: 'object' } },
        { name: 'complaint.get_ui_readiness', description: 'Return the latest cached actor/critic UI readiness verdict for this complaint session.', inputSchema: { type: 'object' } },
        { name: 'complaint.get_workflow_capabilities', description: 'Summarize which complaint-workflow abilities are currently available for the session.', inputSchema: { type: 'object' } },
        { name: 'complaint.generate_complaint', description: 'Generate a complaint draft from intake and evidence.', inputSchema: { type: 'object' } },
        { name: 'complaint.update_draft', description: 'Persist edits to the complaint draft.', inputSchema: { type: 'object' } },
        { name: 'complaint.export_complaint_packet', description: 'Export the current lawsuit complaint packet with intake, evidence, review, and draft content.', inputSchema: { type: 'object' } },
        { name: 'complaint.export_complaint_markdown', description: 'Export the generated complaint as a downloadable Markdown artifact.', inputSchema: { type: 'object' } },
        { name: 'complaint.export_complaint_pdf', description: 'Export the generated complaint as a downloadable PDF artifact.', inputSchema: { type: 'object' } },
        { name: 'complaint.analyze_complaint_output', description: 'Analyze the generated complaint output and turn filing-shape gaps into concrete UI/UX suggestions.', inputSchema: { type: 'object' } },
        { name: 'complaint.review_generated_exports', description: 'Review generated complaint export artifacts through llm_router and turn filing-output weaknesses into UI/UX repair suggestions.', inputSchema: { type: 'object' } },
        { name: 'complaint.update_claim_type', description: 'Set the current complaint type so drafting and review stay aligned to the right legal claim shape.', inputSchema: { type: 'object' } },
        { name: 'complaint.update_case_synopsis', description: 'Persist a shared case synopsis that stays visible across workspace, CLI, and MCP flows.', inputSchema: { type: 'object' } },
        { name: 'complaint.reset_session', description: 'Clear the complaint workspace session.', inputSchema: { type: 'object' } },
        { name: 'complaint.review_ui', description: 'Review Playwright screenshot artifacts and produce a UI critique.', inputSchema: { type: 'object' } },
        { name: 'complaint.optimize_ui', description: 'Run the closed-loop screenshot, llm_router, optimizer, and revalidation workflow for the complaint dashboard UI.', inputSchema: { type: 'object' } },
        { name: 'complaint.run_browser_audit', description: 'Run the Playwright end-to-end complaint browser audit that drives chat, intake, evidence, review, draft, and builder surfaces.', inputSchema: { type: 'object' } },
      ],
    });
  }

  if (request.method === 'POST' && url.pathname === '/api/complaint-workspace/mcp/rpc') {
    const rawBody = await collectRequestBody(request);
    const parsed = rawBody ? JSON.parse(rawBody) : {};
    const requestId = Object.prototype.hasOwnProperty.call(parsed, 'id') ? parsed.id : null;
    const method = parsed.method;
    const params = parsed.params || {};

    if (method === 'tools/list') {
      return sendJson(response, {
        jsonrpc: '2.0',
        id: requestId,
        result: {
          tools: [
            { name: 'complaint.create_identity', description: 'Create a decentralized identity for browser or CLI use.', inputSchema: { type: 'object' } },
            { name: 'complaint.list_intake_questions', description: 'List the complaint intake questions used across browser, CLI, and MCP flows.', inputSchema: { type: 'object' } },
            { name: 'complaint.list_claim_elements', description: 'List the tracked claim elements used for evidence and review.', inputSchema: { type: 'object' } },
            { name: 'complaint.start_session', description: 'Load or initialize a complaint workspace session.', inputSchema: { type: 'object' } },
            { name: 'complaint.submit_intake', description: 'Save complaint intake answers.', inputSchema: { type: 'object' } },
            { name: 'complaint.save_evidence', description: 'Save testimony or document evidence to the workspace.', inputSchema: { type: 'object' } },
            { name: 'complaint.review_case', description: 'Return the support matrix and evidence review.', inputSchema: { type: 'object' } },
            { name: 'complaint.build_mediator_prompt', description: 'Build a testimony-ready chat mediator prompt from the shared case synopsis and support gaps.', inputSchema: { type: 'object' } },
            { name: 'complaint.get_complaint_readiness', description: 'Estimate whether the current complaint record is ready for drafting, still building, or already in draft refinement.', inputSchema: { type: 'object' } },
            { name: 'complaint.get_ui_readiness', description: 'Return the latest cached actor/critic UI readiness verdict for this complaint session.', inputSchema: { type: 'object' } },
            { name: 'complaint.get_workflow_capabilities', description: 'Summarize which complaint-workflow abilities are currently available for the session.', inputSchema: { type: 'object' } },
            { name: 'complaint.generate_complaint', description: 'Generate a complaint draft from intake and evidence.', inputSchema: { type: 'object' } },
            { name: 'complaint.update_draft', description: 'Persist edits to the complaint draft.', inputSchema: { type: 'object' } },
            { name: 'complaint.export_complaint_packet', description: 'Export the current lawsuit complaint packet with intake, evidence, review, and draft content.', inputSchema: { type: 'object' } },
            { name: 'complaint.export_complaint_markdown', description: 'Export the generated complaint as a downloadable Markdown artifact.', inputSchema: { type: 'object' } },
            { name: 'complaint.export_complaint_pdf', description: 'Export the generated complaint as a downloadable PDF artifact.', inputSchema: { type: 'object' } },
            { name: 'complaint.analyze_complaint_output', description: 'Analyze the generated complaint output and turn filing-shape gaps into concrete UI/UX suggestions.', inputSchema: { type: 'object' } },
            { name: 'complaint.review_generated_exports', description: 'Review generated complaint export artifacts through llm_router and turn filing-output weaknesses into UI/UX repair suggestions.', inputSchema: { type: 'object' } },
            { name: 'complaint.update_claim_type', description: 'Set the current complaint type so drafting and review stay aligned to the right legal claim shape.', inputSchema: { type: 'object' } },
            { name: 'complaint.update_case_synopsis', description: 'Persist a shared case synopsis that stays visible across workspace, CLI, and MCP flows.', inputSchema: { type: 'object' } },
            { name: 'complaint.reset_session', description: 'Clear the complaint workspace session.', inputSchema: { type: 'object' } },
            { name: 'complaint.review_ui', description: 'Review Playwright screenshot artifacts and produce a UI critique.', inputSchema: { type: 'object' } },
            { name: 'complaint.optimize_ui', description: 'Run the closed-loop screenshot, llm_router, optimizer, and revalidation workflow for the complaint dashboard UI.', inputSchema: { type: 'object' } },
            { name: 'complaint.run_browser_audit', description: 'Run the Playwright end-to-end complaint browser audit that drives chat, intake, evidence, review, draft, and builder surfaces.', inputSchema: { type: 'object' } },
          ],
        },
      });
    }

    if (method === 'tools/call') {
      const toolName = params.name;
      const args = params.arguments || {};
      const userId = args.user_id || 'did:key:playwright-demo';
      const workspaceState = getWorkspaceState(userId);
      let structuredContent = null;

      if (toolName === 'complaint.create_identity') {
        structuredContent = {
          did: userId,
          method: 'did:key',
          provider: 'playwright-stub',
        };
      } else if (toolName === 'complaint.list_intake_questions') {
        structuredContent = { questions: workspaceQuestions };
      } else if (toolName === 'complaint.list_claim_elements') {
        structuredContent = { claim_elements: claimElements };
      } else if (toolName === 'complaint.submit_intake') {
        Object.assign(workspaceState.intake_answers, args.answers || {});
        structuredContent = workspaceSessionPayload(userId);
      } else if (toolName === 'complaint.save_evidence') {
        const collection = args.kind === 'document' ? workspaceState.evidence.documents : workspaceState.evidence.testimony;
        collection.push({
          id: `${args.kind || 'testimony'}-${collection.length + 1}`,
          kind: args.kind || 'testimony',
          claim_element_id: args.claim_element_id,
          title: args.title,
          content: args.content,
          source: args.source || '',
          attachment_names: Array.isArray(args.attachment_names) ? args.attachment_names : [],
        });
        structuredContent = workspaceSessionPayload(userId);
      } else if (toolName === 'complaint.review_case' || toolName === 'complaint.start_session') {
        structuredContent = workspaceSessionPayload(userId);
      } else if (toolName === 'complaint.build_mediator_prompt') {
        structuredContent = buildMediatorPromptPayload(userId);
      } else if (toolName === 'complaint.get_complaint_readiness') {
        structuredContent = complaintReadinessPayload(userId);
      } else if (toolName === 'complaint.get_ui_readiness') {
        structuredContent = uiReadinessPayload(userId);
      } else if (toolName === 'complaint.get_workflow_capabilities') {
        structuredContent = workflowCapabilitiesPayload(userId);
      } else if (toolName === 'complaint.generate_complaint') {
        generateWorkspaceDraft(workspaceState, args.requested_relief || [], {
          use_llm: Boolean(args.use_llm),
          provider: args.provider,
          model: args.model,
        });
        if (args.title_override) {
          workspaceState.draft.title = args.title_override;
        }
        structuredContent = workspaceSessionPayload(userId);
      } else if (toolName === 'complaint.update_draft') {
        workspaceState.draft = workspaceState.draft || { title: '', requested_relief: [], body: '' };
        if (typeof args.title === 'string') workspaceState.draft.title = args.title;
        if (typeof args.body === 'string') workspaceState.draft.body = args.body;
        if (Array.isArray(args.requested_relief)) workspaceState.draft.requested_relief = args.requested_relief;
        structuredContent = workspaceSessionPayload(userId);
      } else if (toolName === 'complaint.update_case_synopsis') {
        workspaceState.case_synopsis = typeof args.synopsis === 'string' ? args.synopsis.trim() : '';
        structuredContent = workspaceSessionPayload(userId);
      } else if (toolName === 'complaint.export_complaint_packet') {
        structuredContent = Object.assign({}, exportComplaintPacketPayload(userId), {
          ui_feedback: buildComplaintOutputAnalysis(userId).ui_feedback,
        });
      } else if (toolName === 'complaint.export_complaint_markdown') {
        const packetPayload = exportComplaintPacketPayload(userId);
        structuredContent = {
          artifact: {
            format: 'markdown',
            filename: packetPayload.artifacts.markdown.filename,
            media_type: 'text/markdown',
            excerpt: packetPayload.artifacts.markdown.excerpt || packetPayload.artifacts.markdown.content.slice(0, 2000),
          },
          packet_summary: packetPayload.packet_summary,
          artifact_analysis: packetPayload.artifact_analysis || {},
        };
      } else if (toolName === 'complaint.export_complaint_pdf') {
        const packetPayload = exportComplaintPacketPayload(userId);
        structuredContent = {
          artifact: {
            format: 'pdf',
            filename: packetPayload.artifacts.pdf.filename,
            media_type: 'application/pdf',
            header_b64: packetPayload.artifacts.pdf.header_b64,
          },
          packet_summary: packetPayload.packet_summary,
          artifact_analysis: packetPayload.artifact_analysis || {},
        };
      } else if (toolName === 'complaint.analyze_complaint_output') {
        structuredContent = buildComplaintOutputAnalysis(userId);
      } else if (toolName === 'complaint.review_generated_exports') {
        const analysis = buildComplaintOutputAnalysis(userId);
        structuredContent = {
          artifact_count: 1,
          complaint_output_feedback: {
            export_artifact_count: 1,
            claim_types: [workspaceState.claim_type || 'retaliation'],
            draft_strategies: [workspaceState.draft && workspaceState.draft.draft_strategy ? workspaceState.draft.draft_strategy : 'template'],
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
                claim_type: workspaceState.claim_type || 'retaliation',
                draft_strategy: workspaceState.draft && workspaceState.draft.draft_strategy ? workspaceState.draft.draft_strategy : 'template',
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
      } else if (toolName === 'complaint.update_claim_type') {
        workspaceState.claim_type = typeof args.claim_type === 'string' && args.claim_type.trim() ? args.claim_type.trim() : 'retaliation';
        structuredContent = workspaceSessionPayload(userId);
      } else if (toolName === 'complaint.reset_session') {
        workspaceSessions.set(userId, createWorkspaceState(userId));
        structuredContent = workspaceSessionPayload(userId);
      } else if (toolName === 'complaint.review_ui') {
        structuredContent = buildStubUiReviewResult(args, userId);
        persistUiReadiness(userId, structuredContent);
      } else if (toolName === 'complaint.optimize_ui') {
        structuredContent = buildStubUiOptimizationResult(args, userId);
        persistUiReadiness(userId, structuredContent);
      } else if (toolName === 'complaint.run_browser_audit') {
        structuredContent = {
          command: ['pytest', '-q', String(args.pytest_target || 'playwright/tests/complaint-flow.spec.js')],
          returncode: 0,
          artifact_count: 6,
          screenshot_dir: String(args.screenshot_dir || 'artifacts/ui-audit/browser-audit'),
        };
      } else {
        return sendJson(response, {
          jsonrpc: '2.0',
          id: requestId,
          error: {
            code: -32601,
            message: 'Method not found',
          },
        });
      }

      return sendJson(response, {
        jsonrpc: '2.0',
        id: requestId,
        result: {
          content: [
            {
              type: 'text',
              text: JSON.stringify(structuredContent),
            },
          ],
          structuredContent,
          isError: false,
        },
      });
    }

    if (method === 'initialize') {
      return sendJson(response, {
        jsonrpc: '2.0',
        id: requestId,
        result: {
          protocolVersion: '2026-03-22',
          serverInfo: { name: 'complaint-workspace-mcp', version: '1.0.0' },
          capabilities: { tools: { listChanged: false } },
        },
      });
    }

    return sendJson(response, {
      jsonrpc: '2.0',
      id: requestId,
      error: {
        code: -32601,
        message: 'Method not found',
      },
    });
  }

  if (request.method === 'POST' && url.pathname === '/api/complaint-workspace/mcp/call') {
    const rawBody = await collectRequestBody(request);
    const parsed = rawBody ? JSON.parse(rawBody) : {};
    const toolName = parsed.tool_name;
    const args = parsed.arguments || {};
    const userId = args.user_id || 'did:key:playwright-demo';
    const workspaceState = getWorkspaceState(userId);

    if (toolName === 'complaint.create_identity') {
      return sendJson(response, {
        did: userId,
        method: 'did:key',
        provider: 'playwright-stub',
      });
    }
    if (toolName === 'complaint.list_intake_questions') {
      return sendJson(response, { questions: workspaceQuestions });
    }
    if (toolName === 'complaint.list_claim_elements') {
      return sendJson(response, { claim_elements: claimElements });
    }
    if (toolName === 'complaint.submit_intake') {
      Object.assign(workspaceState.intake_answers, args.answers || {});
      return sendJson(response, workspaceSessionPayload(userId));
    }
    if (toolName === 'complaint.save_evidence') {
      const collection = args.kind === 'document' ? workspaceState.evidence.documents : workspaceState.evidence.testimony;
      collection.push({
        id: `${args.kind || 'testimony'}-${collection.length + 1}`,
        kind: args.kind || 'testimony',
        claim_element_id: args.claim_element_id,
        title: args.title,
        content: args.content,
        source: args.source || '',
        attachment_names: Array.isArray(args.attachment_names) ? args.attachment_names : [],
      });
      return sendJson(response, workspaceSessionPayload(userId));
    }
    if (toolName === 'complaint.review_case' || toolName === 'complaint.start_session') {
      return sendJson(response, workspaceSessionPayload(userId));
    }
    if (toolName === 'complaint.build_mediator_prompt') {
      return sendJson(response, buildMediatorPromptPayload(userId));
    }
    if (toolName === 'complaint.get_complaint_readiness') {
      return sendJson(response, complaintReadinessPayload(userId));
    }
    if (toolName === 'complaint.get_ui_readiness') {
      return sendJson(response, uiReadinessPayload(userId));
    }
    if (toolName === 'complaint.get_workflow_capabilities') {
      return sendJson(response, workflowCapabilitiesPayload(userId));
    }
    if (toolName === 'complaint.generate_complaint') {
      generateWorkspaceDraft(workspaceState, args.requested_relief || [], {
        use_llm: Boolean(args.use_llm),
        provider: args.provider,
        model: args.model,
      });
      if (args.title_override) {
        workspaceState.draft.title = args.title_override;
      }
      return sendJson(response, workspaceSessionPayload(userId));
    }
    if (toolName === 'complaint.update_draft') {
      workspaceState.draft = workspaceState.draft || { title: '', requested_relief: [], body: '' };
      if (typeof args.title === 'string') workspaceState.draft.title = args.title;
      if (typeof args.body === 'string') workspaceState.draft.body = args.body;
      if (Array.isArray(args.requested_relief)) workspaceState.draft.requested_relief = args.requested_relief;
      return sendJson(response, workspaceSessionPayload(userId));
    }
    if (toolName === 'complaint.update_case_synopsis') {
      workspaceState.case_synopsis = typeof args.synopsis === 'string' ? args.synopsis.trim() : '';
      return sendJson(response, workspaceSessionPayload(userId));
    }
    if (toolName === 'complaint.export_complaint_packet') {
      return sendJson(response, Object.assign({}, exportComplaintPacketPayload(userId), {
        ui_feedback: buildComplaintOutputAnalysis(userId).ui_feedback,
      }));
    }
    if (toolName === 'complaint.export_complaint_markdown') {
      const packetPayload = exportComplaintPacketPayload(userId);
      return sendJson(response, {
        artifact: {
          format: 'markdown',
          filename: packetPayload.artifacts.markdown.filename,
          media_type: 'text/markdown',
          excerpt: packetPayload.artifacts.markdown.excerpt || packetPayload.artifacts.markdown.content.slice(0, 2000),
        },
        packet_summary: packetPayload.packet_summary,
        artifact_analysis: packetPayload.artifact_analysis || {},
      });
    }
    if (toolName === 'complaint.export_complaint_pdf') {
      const packetPayload = exportComplaintPacketPayload(userId);
      return sendJson(response, {
        artifact: {
          format: 'pdf',
          filename: packetPayload.artifacts.pdf.filename,
          media_type: 'application/pdf',
          header_b64: packetPayload.artifacts.pdf.header_b64,
        },
        packet_summary: packetPayload.packet_summary,
        artifact_analysis: packetPayload.artifact_analysis || {},
      });
    }
    if (toolName === 'complaint.analyze_complaint_output') {
      return sendJson(response, buildComplaintOutputAnalysis(userId));
    }
    if (toolName === 'complaint.review_generated_exports') {
      const analysis = buildComplaintOutputAnalysis(userId);
      return sendJson(response, {
        artifact_count: 1,
        complaint_output_feedback: {
          export_artifact_count: 1,
          claim_types: [workspaceState.claim_type || 'retaliation'],
          draft_strategies: [workspaceState.draft && workspaceState.draft.draft_strategy ? workspaceState.draft.draft_strategy : 'template'],
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
              claim_type: workspaceState.claim_type || 'retaliation',
              draft_strategy: workspaceState.draft && workspaceState.draft.draft_strategy ? workspaceState.draft.draft_strategy : 'template',
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
      });
    }
    if (toolName === 'complaint.update_claim_type') {
      workspaceState.claim_type = typeof args.claim_type === 'string' && args.claim_type.trim() ? args.claim_type.trim() : 'retaliation';
      return sendJson(response, workspaceSessionPayload(userId));
    }
    if (toolName === 'complaint.reset_session') {
      workspaceSessions.set(userId, createWorkspaceState(userId));
      return sendJson(response, workspaceSessionPayload(userId));
    }
    if (toolName === 'complaint.review_ui') {
      const result = buildStubUiReviewResult(args, userId);
      persistUiReadiness(userId, result);
      return sendJson(response, result);
    }
    if (toolName === 'complaint.optimize_ui') {
      const result = buildStubUiOptimizationResult(args, userId);
      persistUiReadiness(userId, result);
      return sendJson(response, result);
    }
    response.writeHead(400);
    response.end('Unknown MCP tool');
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/documents/optimization-trace') {
    return sendJson(response, { cid: url.searchParams.get('cid') || '', changes: [] });
  }

  if (request.method === 'GET' && url.pathname === '/ipfs-datasets/sdk-playground') {
    return sendFile(response, sdkPreviewPath);
  }

  if (request.method === 'GET' && url.pathname === '/mcp') {
    return sendText(response, renderDashboardShell(dashboardEntries[0]), 'text/html; charset=utf-8');
  }

  if (request.method === 'GET' && url.pathname === '/api/mcp/analytics/history') {
    return sendJson(response, {
      history: [
        { last_updated: '2026-03-22T09:00:00+00:00', success_rate: 91.2, average_query_time: 1.42 },
        { last_updated: '2026-03-22T10:00:00+00:00', success_rate: 94.8, average_query_time: 1.35 },
        { last_updated: '2026-03-22T11:00:00+00:00', success_rate: 96.4, average_query_time: 1.28 },
      ],
    });
  }

  if (request.method === 'GET' && url.pathname === '/dashboards') {
    return sendText(response, renderDashboardHub(), 'text/html; charset=utf-8');
  }

  if (request.method === 'GET' && url.pathname.startsWith('/dashboards/ipfs-datasets/')) {
    const slug = url.pathname.replace('/dashboards/ipfs-datasets/', '');
    const entry = dashboardEntries.find((item) => item.slug === slug);
    if (!entry) {
      response.writeHead(404);
      response.end('Not found');
      return;
    }
    return sendText(response, renderDashboardShell(entry), 'text/html; charset=utf-8');
  }

  if (request.method === 'GET' && url.pathname.startsWith('/dashboards/raw/ipfs-datasets/')) {
    const slug = url.pathname.replace('/dashboards/raw/ipfs-datasets/', '');
    const entry = dashboardEntries.find((item) => item.slug === slug);
    if (!entry) {
      response.writeHead(404);
      response.end('Not found');
      return;
    }
    return sendFile(response, ipfsTemplate(entry.templateName));
  }

  if (request.method === 'GET' && url.pathname.startsWith('/static/')) {
    return sendFile(response, path.join(staticDir, url.pathname.replace('/static/', '')));
  }

  if (request.method === 'GET' && url.pathname.startsWith('/ipfs-datasets-static/')) {
    return sendFile(response, path.join(ipfsDatasetsStaticDir, url.pathname.replace('/ipfs-datasets-static/', '')));
  }

  if (request.method === 'GET' && routes.has(url.pathname)) {
    return sendFile(response, routes.get(url.pathname));
  }

  if (request.method === 'GET' && url.pathname === '') {
    return sendFile(response, template('index.html'));
  }

  response.writeHead(404);
  response.end('Not found');
});

server.listen(port, '127.0.0.1');
