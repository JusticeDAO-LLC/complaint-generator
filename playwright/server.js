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
const port = Number(process.env.PLAYWRIGHT_TEST_PORT || 19030);

function pathDiagnostics(filePath) {
  const exists = fs.existsSync(filePath);
  return {
    path: filePath,
    exists,
    state: exists ? 'present' : 'missing',
  };
}

function buildEnvironmentPreflight() {
  const sdkPreview = pathDiagnostics(sdkPreviewPath);
  const ipfsTemplates = pathDiagnostics(ipfsDatasetsTemplatesDir);
  const ipfsStatic = pathDiagnostics(ipfsDatasetsStaticDir);
  const allReady = sdkPreview.exists && ipfsTemplates.exists && ipfsStatic.exists;
  return {
    status: allReady ? 'ready' : 'degraded',
    all_ready: allReady,
    checks: {
      sdk_playground_preview: sdkPreview,
      ipfs_templates_dir: ipfsTemplates,
      ipfs_static_dir: ipfsStatic,
    },
  };
}

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

function adverseActionClause(value, fallback) {
  const text = eventFragment(value, fallback);
  const lowered = text.toLowerCase();
  const replacements = [
    ['terminated ', 'terminating Plaintiff '],
    ['fired ', 'firing Plaintiff '],
    ['suspended ', 'suspending Plaintiff '],
    ['disciplined ', 'disciplining Plaintiff '],
    ['demoted ', 'demoting Plaintiff '],
    ['evicted ', 'evicting Plaintiff '],
    ['denied ', 'denying Plaintiff '],
    ['threatened ', 'threatening Plaintiff '],
  ];
  for (const [oldPrefix, newPrefix] of replacements) {
    if (lowered.startsWith(oldPrefix)) {
      return `${newPrefix}${text.slice(oldPrefix.length)}`;
    }
  }
  return text;
}

function pleadingActivityFragment(value, fallback) {
  const text = sentenceFragment(value, fallback);
  const replacements = [
    ['reported ', 'reporting '],
    ['requested ', 'requesting '],
    ['complained about ', 'complaining about '],
    ['complained to ', 'complaining to '],
    ['opposed ', 'opposing '],
    ['filed ', 'filing '],
    ['disclosed ', 'disclosing '],
    ['asked for ', 'asking for '],
    ['sought ', 'seeking '],
  ];
  const lowered = text.toLowerCase();
  for (const [oldPrefix, newPrefix] of replacements) {
    if (lowered.startsWith(oldPrefix)) {
      return `${newPrefix}${text.slice(oldPrefix.length)}`;
    }
  }
  return text;
}

function timelineClauseFragment(value) {
  const text = normalizeFragment(value, 'the relevant event occurred');
  const lowered = text.toLowerCase();
  const replacements = [
    ['report on ', 'Plaintiff made the report on '],
    ['complaint on ', 'Plaintiff made the complaint on '],
    ['accommodation request on ', 'Plaintiff made the accommodation request on '],
    ['requested accommodation in ', 'Plaintiff requested an accommodation in '],
    ['reported discrimination on ', 'Plaintiff reported discrimination on '],
    ['reported retaliation on ', 'Plaintiff reported retaliation on '],
    ['reported wage-and-hour violations on ', 'Plaintiff reported wage-and-hour violations on '],
    ['termination on ', 'the termination occurred on '],
    ['terminated on ', 'Plaintiff was terminated on '],
    ['was terminated on ', 'Plaintiff was terminated on '],
    ['threatened on ', 'Plaintiff was threatened on '],
    ['was threatened on ', 'Plaintiff was threatened on '],
    ['denial notice on ', 'the denial notice issued on '],
    ['eviction threat on ', 'the eviction threat followed on '],
    ['lost the housing opportunity in ', 'the housing opportunity was lost in '],
  ];
  for (const [oldPrefix, newPrefix] of replacements) {
    if (lowered.startsWith(oldPrefix)) {
      return `${newPrefix}${text.slice(oldPrefix.length)}`;
    }
  }
  return text;
}

function pleadingTimelineSentence(value, fallback) {
  const text = normalizeFragment(value, fallback);
  if (!text) {
    return `${fallback}.`;
  }
  const parts = text.split(/,|\band\b/).map((part) => part.trim()).filter(Boolean);
  if (!parts.length) {
    return `${text}.`;
  }
  const fragments = parts.map((part) => timelineClauseFragment(part));
  let sentence = '';
  if (fragments.length === 1) {
    sentence = fragments[0];
  } else if (fragments.length === 2) {
    sentence = `${fragments[0]}, and ${fragments[1]}`;
  } else {
    sentence = `${fragments.slice(0, -1).join(', ')}, and ${fragments[fragments.length - 1]}`;
  }
  sentence = sentence.replace(/\s+/g, ' ').trim();
  if (/^[A-Za-z]/.test(sentence)) {
    sentence = `${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}`;
  }
  return sentence.endsWith('.') ? sentence : `${sentence}.`;
}

function formalizeReliefItem(value) {
  const text = normalizeFragment(value, 'Other appropriate relief');
  const replacements = {
    'back pay': 'Back pay and lost benefits',
    'front pay': 'Front pay in lieu of reinstatement',
    'injunctive relief': 'Appropriate injunctive and equitable relief',
    reinstatement: "Reinstatement to Plaintiff's former position or a comparable position",
    'attorney fees': "Reasonable attorney's fees and costs",
    "attorney's fees": "Reasonable attorney's fees and costs",
    fees: 'Reasonable fees and costs',
    'declaratory relief': 'Declaratory relief as authorized by law',
    'compensatory damages': 'Compensatory damages according to proof',
    damages: 'Damages according to proof',
  };
  return replacements[text.toLowerCase()] || text;
}

function courtHeaderLine(value) {
  const text = normalizeFragment(value, 'FOR THE APPROPRIATE JUDICIAL DISTRICT');
  const upper = text.toUpperCase();
  if (upper.includes('UNITED STATES DISTRICT COURT')) {
    return 'FOR THE APPROPRIATE JUDICIAL DISTRICT';
  }
  if (upper.startsWith('FOR ')) {
    return upper;
  }
  if (upper.includes('DISTRICT OF')) {
    return upper.startsWith('THE ') ? `FOR ${upper}` : `FOR THE ${upper}`;
  }
  return 'FOR THE APPROPRIATE JUDICIAL DISTRICT';
}

function claimElementLabel(value) {
  const normalized = String(value || '').trim();
  const labels = {
    protected_activity: 'Protected activity',
    employer_knowledge: 'Employer knowledge',
    adverse_action: 'Adverse action',
    causation: 'Causal link',
    harm: 'Damages',
  };
  return labels[normalized] || normalized.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()) || 'An identified claim element';
}

function formalEvidenceSummaryItem(item, kind) {
  const title = String((item || {}).title || `Untitled ${kind}`).trim();
  const elementLabel = claimElementLabel((item || {}).claim_element_id).toLowerCase();
  if (kind === 'testimony') {
    return `testimony presently identified as '${title}' on the ${elementLabel} element`;
  }
  return `documentary exhibit presently identified as '${title}' on the ${elementLabel} element`;
}

function buildDashboardEntriesFixture() {
  return [
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
}

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

function sanitizeProfileDataForClient(value) {
  if (Array.isArray(value)) {
    return value.map(sanitizeProfileDataForClient);
  }
  if (!value || typeof value !== 'object') {
    return value;
  }
  return Object.fromEntries(Object.entries(value).map(([key, nestedValue]) => [
    key,
    /(^|_)(password|hashed_password|password_hash|credential|secret|token|api_key|session_key|private_key)($|_)/i.test(String(key || ''))
      ? '[redacted]'
      : sanitizeProfileDataForClient(nestedValue),
  ]));
}

const workspaceQuestions = [
  { id: 'party_name', label: 'Your name', prompt: 'Who is bringing the complaint?', placeholder: 'Jane Doe' },
  { id: 'opposing_party', label: 'Opposing party', prompt: 'Who are you filing against?', placeholder: 'Acme Corporation' },
  { id: 'protected_activity', label: 'Protected activity', prompt: 'What did you report, oppose, or request before the retaliation happened?', placeholder: 'Reported discrimination to HR' },
  { id: 'adverse_action', label: 'Adverse action', prompt: 'What happened to you afterward?', placeholder: 'Termination two days later' },
  { id: 'timeline', label: 'Timeline', prompt: 'When did the key events happen?', placeholder: 'Complaint on March 8, termination on March 10' },
  { id: 'harm', label: 'Harm', prompt: 'What harm did you suffer?', placeholder: 'Lost wages, lost benefits, emotional distress' },
  { id: 'court_header', label: 'Court caption', prompt: 'If you know the court, what district caption should appear on the complaint?', placeholder: 'FOR THE NORTHERN DISTRICT OF CALIFORNIA' },
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

function releaseGateScoreFromVerdict(verdict) {
  const normalized = String(verdict || '').trim().toLowerCase();
  if (normalized === 'pass' || normalized === 'client_safe') {
    return 100;
  }
  if (normalized === 'warning') {
    return 70;
  }
  if (normalized === 'blocked') {
    return 20;
  }
  return 35;
}

function clientReleaseGatePayload(userId = 'did:key:playwright-demo') {
  const complaintReadiness = complaintReadinessPayload(userId);
  const uiReadiness = uiReadinessPayload(userId);
  const workspaceState = getWorkspaceState(userId);
  const complaintOutputGate = workspaceState.draft
    ? ((exportComplaintPacketPayload(userId).packet_summary || {}).release_gate || {})
    : {
        verdict: 'blocked',
        reason: 'No complaint draft exists yet, so the exported filing quality has not been validated.',
        claim_type: String(workspaceState.claim_type || 'retaliation'),
        claim_type_label: String(workspaceState.claim_type || 'retaliation').replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
        draft_strategy: null,
        filing_shape_score: 0,
        claim_type_alignment_score: 0,
        missing_elements: Number(complaintReadiness.missing_elements || 0),
        evidence_item_count: Number(complaintReadiness.evidence_count || 0),
        status: 'unavailable',
      };

  const complaintScore = Number(complaintReadiness.score || 0);
  const uiScore = uiReadiness.score == null ? 35 : Number(uiReadiness.score || 0);
  const outputScore = releaseGateScoreFromVerdict(complaintOutputGate.verdict);
  const score = Math.max(0, Math.min(100, Math.round((complaintScore * 0.3) + (uiScore * 0.3) + (outputScore * 0.4))));
  const uiVerdict = String(uiReadiness.verdict || '').trim().toLowerCase();
  const outputVerdict = String(complaintOutputGate.verdict || '').trim().toLowerCase();
  const complaintVerdict = String(complaintReadiness.verdict || '').trim().toLowerCase();

  const blockers = [];
  if (outputVerdict === 'blocked') {
    blockers.push(String(complaintOutputGate.reason || 'The exported complaint is not yet client-safe.'));
  }
  if (uiVerdict === 'no ui verdict cached') {
    blockers.push('No actor/critic UI verdict is cached yet. Run the UX Audit before sending legal clients here.');
  } else if (uiVerdict === 'needs repair' || uiVerdict === 'do not send to clients yet') {
    blockers.push(String(uiReadiness.summary || 'The dashboard UI still needs repair before it should be treated as client-safe.'));
  }
  if (complaintVerdict === 'not ready to draft' || complaintVerdict === 'still building the record') {
    blockers.push(String(complaintReadiness.detail || 'The complaint record is not ready for drafting.'));
  }

  let verdict = 'blocked';
  let detail = 'The current combination of UI readiness, complaint readiness, and exported complaint quality is not safe enough to treat this workflow as client-ready.';
  let recommendedRoute = uiVerdict === 'no ui verdict cached'
    ? '/workspace'
    : outputVerdict === 'blocked' && workspaceState.draft
      ? '/document'
      : String(complaintReadiness.recommended_route || '/workspace');
  let recommendedAction = 'Fix the highlighted complaint-output and UI blockers before sending legal clients through this workflow.';

  if (outputVerdict === 'pass' && uiVerdict === 'client-safe' && (complaintVerdict === 'ready for first draft' || complaintVerdict === 'draft in progress')) {
    verdict = 'client_safe';
    detail = 'The complaint workflow has a client-safe UI verdict, a filing-shaped complaint export, and a complaint record strong enough to keep drafting or refinement on track.';
    recommendedRoute = String(complaintReadiness.recommended_route || '/document');
    recommendedAction = 'Continue refining the complaint and review the export artifacts before filing.';
  } else if (score >= 65 && outputVerdict !== 'blocked') {
    verdict = 'warning';
    detail = 'The complaint workflow is usable, but either the UI audit, the complaint record, or the exported filing still needs more work before this should be treated as safe for legal clients.';
    recommendedRoute = uiVerdict === 'no ui verdict cached' ? '/workspace' : String(complaintReadiness.recommended_route || '/workspace');
    recommendedAction = 'Review the blockers, tighten the record, and rerun the UX Audit or export critic before relying on this flow.';
  }

  return {
    user_id: userId,
    score,
    verdict,
    detail,
    recommended_route: recommendedRoute,
    recommended_action: recommendedAction,
    blockers: blockers.slice(0, 6),
    complaint_readiness: complaintReadiness,
    ui_readiness: uiReadiness,
    complaint_output_release_gate: complaintOutputGate,
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
  const environmentPreflight = buildEnvironmentPreflight();
  return {
    user_id: userId,
    case_synopsis: String(sessionPayload.case_synopsis || '').trim(),
    overview,
    claim_type: claimType,
    claim_type_label: claimType.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
    draft_strategy: draftStrategy,
    complaint_readiness: complaintReadinessPayload(userId),
    ui_readiness: uiReadinessPayload(userId),
    client_release_gate: clientReleaseGatePayload(userId),
    tooling_contract: toolingContractPayload(userId),
    environment_preflight: environmentPreflight,
    capabilities: [
      { id: 'intake_questions', label: 'Complaint intake questions', available: questions.length > 0, detail: `${answeredCount} of ${questions.length} intake questions answered.` },
      { id: 'mediator_prompt', label: 'Chat mediator handoff', available: true, detail: 'A testimony-ready mediator prompt can be generated from the shared case synopsis and support gaps.' },
      { id: 'evidence_capture', label: 'Evidence capture', available: true, detail: `${(overview.testimony_items || 0) + (overview.document_items || 0)} evidence items saved.` },
      { id: 'support_review', label: 'Claim support review', available: true, detail: `${overview.supported_elements || 0} supported elements, ${overview.missing_elements || 0} gaps remaining.` },
      { id: 'complaint_draft', label: 'Complaint draft', available: true, detail: sessionPayload.draft ? 'A draft already exists and can be edited.' : 'A draft can be generated from the current complaint record.' },
      { id: 'claim_type_alignment', label: 'Claim-type drafting alignment', available: true, detail: `The current complaint type is ${claimType.replace(/_/g, ' ')}.` },
      { id: 'formal_complaint_generation', label: 'Formal complaint generation', available: true, detail: draftStrategy === 'llm_router' ? 'The current draft uses llm_router-backed formal complaint generation.' : 'The current draft is using the deterministic template fallback.' },
      { id: 'complaint_packet', label: 'Complaint packet export', available: true, detail: 'The lawsuit packet can be exported as a structured browser, CLI, or MCP artifact.' },
      { id: 'ipfs_datasets_py_trace', label: 'Neurosymbolic IPFS trace', available: environmentPreflight.all_ready, detail: environmentPreflight.all_ready ? 'ipfs_datasets_py dashboard and static trace surfaces are present.' : 'ipfs_datasets_py trace surfaces are missing; route-safe fallback guidance should stay visible.' },
    ],
  };
}

function toolingContractPayload(userId = 'did:key:playwright-demo') {
  const packageExports = [
    'create_identity',
    'start_session',
    'submit_intake_answers',
    'save_evidence',
    'import_gmail_evidence',
    'review_case',
    'build_mediator_prompt',
    'get_complaint_readiness',
    'get_ui_readiness',
    'get_client_release_gate',
    'get_workflow_capabilities',
    'get_tooling_contract',
    'generate_complaint',
    'update_claim_type',
    'update_case_synopsis',
    'export_complaint_packet',
    'export_complaint_markdown',
    'export_complaint_docx',
    'export_complaint_pdf',
    'analyze_complaint_output',
    'get_formal_diagnostics',
    'get_filing_provenance',
    'get_provider_diagnostics',
    'review_generated_exports',
    'review_ui',
    'optimize_ui',
    'run_browser_audit',
  ];
  const cliCommands = [
    'identity',
    'session',
    'answer',
    'add-evidence',
    'import-gmail-evidence',
    'review',
    'mediator-prompt',
    'complaint-readiness',
    'ui-readiness',
    'client-release-gate',
    'capabilities',
    'tooling-contract',
    'set-claim-type',
    'update-synopsis',
    'generate',
    'export-packet',
    'export-markdown',
    'export-docx',
    'export-pdf',
    'analyze-output',
    'formal-diagnostics',
    'filing-provenance',
    'provider-diagnostics',
    'review-exports',
    'review-ui',
    'optimize-ui',
    'browser-audit',
  ];
  const mcpTools = [
    'complaint.create_identity',
    'complaint.list_intake_questions',
    'complaint.list_claim_elements',
    'complaint.start_session',
    'complaint.submit_intake',
    'complaint.save_evidence',
    'complaint.import_gmail_evidence',
    'complaint.review_case',
    'complaint.build_mediator_prompt',
    'complaint.get_complaint_readiness',
    'complaint.get_ui_readiness',
    'complaint.get_client_release_gate',
    'complaint.get_workflow_capabilities',
    'complaint.get_tooling_contract',
    'complaint.generate_complaint',
    'complaint.update_draft',
    'complaint.export_complaint_packet',
    'complaint.export_complaint_markdown',
    'complaint.export_complaint_docx',
    'complaint.export_complaint_pdf',
    'complaint.analyze_complaint_output',
    'complaint.get_formal_diagnostics',
    'complaint.get_filing_provenance',
    'complaint.get_provider_diagnostics',
    'complaint.review_generated_exports',
    'complaint.update_claim_type',
    'complaint.update_case_synopsis',
    'complaint.reset_session',
    'complaint.review_ui',
    'complaint.optimize_ui',
    'complaint.run_browser_audit',
  ];
  const browserSdkMethods = [
    'createIdentity',
    'bootstrapWorkspace',
    'getSession',
    'submitIntake',
    'saveEvidence',
    'importGmailEvidence',
    'reviewCase',
    'buildMediatorPrompt',
    'getComplaintReadiness',
    'getUiReadiness',
    'getClientReleaseGate',
    'getWorkflowCapabilities',
    'getToolingContract',
    'generateComplaint',
    'exportComplaintPacket',
    'exportComplaintMarkdown',
    'exportComplaintDocx',
    'exportComplaintPdf',
    'analyzeComplaintOutput',
    'getFormalDiagnostics',
    'getFilingProvenance',
    'getProviderDiagnostics',
    'reviewGeneratedExports',
    'updateClaimType',
    'updateCaseSynopsis',
    'reviewUiArtifacts',
    'optimizeUiArtifacts',
    'runBrowserAudit',
  ];
  const coreFlowSteps = [
    ['intake', 'submit_intake_answers', 'answer', 'complaint.submit_intake', 'submitIntake'],
    ['evidence_capture', 'save_evidence', 'add-evidence', 'complaint.save_evidence', 'saveEvidence'],
    ['gmail_import', 'import_gmail_evidence', 'import-gmail-evidence', 'complaint.import_gmail_evidence', 'importGmailEvidence'],
    ['support_review', 'review_case', 'review', 'complaint.review_case', 'reviewCase'],
    ['mediator_handoff', 'build_mediator_prompt', 'mediator-prompt', 'complaint.build_mediator_prompt', 'buildMediatorPrompt'],
    ['claim_type_alignment', 'update_claim_type', 'set-claim-type', 'complaint.update_claim_type', 'updateClaimType'],
    ['case_synopsis_sync', 'update_case_synopsis', 'update-synopsis', 'complaint.update_case_synopsis', 'updateCaseSynopsis'],
    ['draft_generation', 'generate_complaint', 'generate', 'complaint.generate_complaint', 'generateComplaint'],
    ['complaint_export_markdown', 'export_complaint_markdown', 'export-markdown', 'complaint.export_complaint_markdown', 'exportComplaintMarkdown'],
    ['complaint_export_pdf', 'export_complaint_pdf', 'export-pdf', 'complaint.export_complaint_pdf', 'exportComplaintPdf'],
    ['complaint_export_docx', 'export_complaint_docx', 'export-docx', 'complaint.export_complaint_docx', 'exportComplaintDocx'],
    ['complaint_output_analysis', 'analyze_complaint_output', 'analyze-output', 'complaint.analyze_complaint_output', 'analyzeComplaintOutput'],
    ['formal_diagnostics', 'get_formal_diagnostics', 'formal-diagnostics', 'complaint.get_formal_diagnostics', 'getFormalDiagnostics'],
    ['filing_provenance', 'get_filing_provenance', 'filing-provenance', 'complaint.get_filing_provenance', 'getFilingProvenance'],
    ['provider_diagnostics', 'get_provider_diagnostics', 'provider-diagnostics', 'complaint.get_provider_diagnostics', 'getProviderDiagnostics'],
    ['export_critic', 'review_generated_exports', 'review-exports', 'complaint.review_generated_exports', 'reviewGeneratedExports'],
    ['ui_actor_critic', 'review_ui', 'review-ui', 'complaint.review_ui', 'reviewUiArtifacts'],
    ['ui_closed_loop_optimizer', 'optimize_ui', 'optimize-ui', 'complaint.optimize_ui', 'optimizeUiArtifacts'],
  ].map(([id, packageExport, cliCommand, mcpTool, browserSdkMethod]) => ({
    id,
    package_export: packageExport,
    cli_command: cliCommand,
    mcp_tool: mcpTool,
    browser_sdk_method: browserSdkMethod,
    exposed_everywhere: packageExports.includes(packageExport)
      && cliCommands.includes(cliCommand)
      && mcpTools.includes(mcpTool)
      && browserSdkMethods.includes(browserSdkMethod),
  }));
  return {
    user_id: userId,
    package_exports: packageExports,
    cli_commands: cliCommands,
    mcp_tools: mcpTools,
    browser_sdk_methods: browserSdkMethods,
    core_flow_steps: coreFlowSteps,
    missing_exposures: coreFlowSteps.filter((item) => !item.exposed_everywhere).map((item) => item.id),
    all_core_flow_steps_exposed: coreFlowSteps.every((item) => item.exposed_everywhere),
  };
}

function formalDiagnosticsPayload(userId = 'did:key:playwright-demo') {
  const analysis = buildComplaintOutputAnalysis(userId);
  const uiFeedback = analysis.ui_feedback || {};
  const releaseGate = uiFeedback.release_gate || {};
  const issues = Array.isArray(uiFeedback.issues) ? uiFeedback.issues : [];
  const highSeverityComplaintItems = issues.filter((item) => String((item || {}).severity || '').toLowerCase() === 'high');
  const formalDiagnostics = {
    formal_defect_count: issues.length,
    high_severity_issue_count: highSeverityComplaintItems.length,
    top_formal_findings: issues.slice(0, 5).map((item) => String((item || {}).finding || '').trim()).filter(Boolean),
    top_ui_implications: issues.slice(0, 5).map((item) => String((item || {}).ui_implication || '').trim()).filter(Boolean),
    top_ui_suggestions: Array.isArray(uiFeedback.ui_suggestions)
      ? uiFeedback.ui_suggestions.slice(0, 5).map((item) => String((item || {}).title || '').trim()).filter(Boolean)
      : [],
    release_gate_verdict: String(releaseGate.verdict || 'unknown'),
  };
  return {
    user_id: userId,
    claim_type_alignment_score: Number(uiFeedback.claim_type_alignment_score || 0),
    filing_shape_score: Number(uiFeedback.filing_shape_score || 0),
    release_gate: releaseGate,
    formal_diagnostics: formalDiagnostics,
    router_backend: Object.assign({}, ((uiFeedback.router_review || {}).backend || {})),
    packet_summary: {
      has_draft: Boolean((analysis.packet_summary || {}).has_draft),
      draft_strategy: String((analysis.packet_summary || {}).draft_strategy || 'template'),
      formal_defect_count: Number((analysis.packet_summary || {}).formal_defect_count || formalDiagnostics.formal_defect_count || 0),
      high_severity_issue_count: Number((analysis.packet_summary || {}).high_severity_issue_count || formalDiagnostics.high_severity_issue_count || 0),
      complaint_output_router_backend: Object.assign({}, (((analysis.packet_summary || {}).complaint_output_router_backend) || ((uiFeedback.router_review || {}).backend || {}))),
    },
  };
}

function neurosymbolicTracePayload(userId = 'did:key:playwright-demo') {
  const sessionPayload = workspaceSessionPayload(userId);
  const packetPayload = exportComplaintPacketPayload(userId);
  const analysis = buildComplaintOutputAnalysis(userId);
  const envPreflight = buildEnvironmentPreflight();
  const packet = packetPayload.packet || {};
  const draft = packet.draft || {};
  const review = sessionPayload.review || {};
  const overview = review.overview || {};
  const supportMatrix = Array.isArray(review.support_matrix) ? review.support_matrix : [];
  const evidence = ((sessionPayload.session || {}).evidence) || {};
  const testimonyItems = Array.isArray(evidence.testimony) ? evidence.testimony : [];
  const documentItems = Array.isArray(evidence.documents) ? evidence.documents : [];
  const uiFeedback = analysis.ui_feedback || {};
  const releaseGate = uiFeedback.release_gate || {};
  const formalSections = uiFeedback.formal_sections_present || {};
  const packetSlug = slugifyFilename(draft.title || 'complaint-packet');
  const cidStatus = envPreflight.all_ready ? 'ready_for_car_publish' : 'submodule_or_preview_missing';
  const datasetRefs = [
    {
      ref_id: 'complaint_packet_json',
      piece_id: 'complaint_packet',
      label: 'Complaint packet JSON',
      uri: `workspace://${encodeURIComponent(userId)}/packets/${packetSlug}.json`,
      export_tool: 'complaint.export_complaint_packet',
      artifact_format: 'json',
      cid: null,
      cid_status: cidStatus,
    },
    {
      ref_id: 'complaint_markdown',
      piece_id: 'complaint_markdown',
      label: 'Complaint Markdown artifact',
      uri: `workspace://${encodeURIComponent(userId)}/artifacts/${packetSlug}.md`,
      export_tool: 'complaint.export_complaint_markdown',
      artifact_format: 'markdown',
      cid: null,
      cid_status: cidStatus,
    },
    {
      ref_id: 'evidence_map',
      piece_id: 'evidence_items',
      label: 'Evidence map',
      uri: `workspace://${encodeURIComponent(userId)}/evidence`,
      item_count: testimonyItems.length + documentItems.length,
      testimony_count: testimonyItems.length,
      document_count: documentItems.length,
      cid: null,
      cid_status: cidStatus,
    },
    {
      ref_id: 'support_matrix',
      piece_id: 'claim_support_matrix',
      label: 'Claim support matrix',
      uri: `workspace://${encodeURIComponent(userId)}/review/support-matrix`,
      supported_elements: Number(overview.supported_elements || 0),
      missing_elements: Number(overview.missing_elements || 0),
      cid: null,
      cid_status: cidStatus,
    },
    {
      ref_id: 'filing_release_gate',
      piece_id: 'release_gate',
      label: 'Filing release gate',
      uri: `workspace://${encodeURIComponent(userId)}/release-gate`,
      verdict: String(releaseGate.verdict || 'unknown'),
      cid: null,
      cid_status: cidStatus,
    },
  ];
  const evidenceRefs = testimonyItems.concat(documentItems).map((item, index) => ({
    ref_id: `evidence_${index + 1}`,
    piece_id: 'evidence_item',
    label: String(item.title || item.id || `Evidence ${index + 1}`),
    claim_element_id: String(item.claim_element_id || 'unmapped'),
    kind: String(item.kind || (index < testimonyItems.length ? 'testimony' : 'document')),
    uri: `workspace://${encodeURIComponent(userId)}/evidence/${encodeURIComponent(String(item.id || index + 1))}`,
    source: String(item.source || ''),
    cid: null,
    cid_status: cidStatus,
  }));
  const ruleHits = [
    {
      rule_id: 'pleading.caption.present',
      label: 'Caption and civil action placeholder are visible',
      status: formalSections.caption ? 'pass' : 'fail',
      severity: 'critical',
      evidence_refs: ['complaint_markdown'],
      explanation: formalSections.caption
        ? 'The generated complaint includes a court-style caption.'
        : 'The generated complaint is missing the expected caption structure.',
    },
    {
      rule_id: 'pleading.required_sections.present',
      label: 'Required pleading sections are present',
      status: Object.values(formalSections).filter(Boolean).length >= 9 ? 'pass' : 'warning',
      severity: 'high',
      evidence_refs: ['complaint_markdown'],
      explanation: `${Object.values(formalSections).filter(Boolean).length} formal sections were detected in the complaint output.`,
    },
    {
      rule_id: 'claim.support.coverage',
      label: 'Tracked claim elements have support coverage',
      status: Number(overview.missing_elements || 0) === 0 ? 'pass' : 'warning',
      severity: 'high',
      evidence_refs: ['support_matrix', 'evidence_map'],
      explanation: `${Number(overview.supported_elements || 0)} supported elements and ${Number(overview.missing_elements || 0)} open support gaps are visible.`,
    },
    {
      rule_id: 'claim.support.corroboration',
      label: 'Support is corroborated by saved evidence',
      status: (testimonyItems.length + documentItems.length) > 1 ? 'pass' : 'warning',
      severity: 'medium',
      evidence_refs: evidenceRefs.length ? evidenceRefs.slice(0, 6).map((item) => item.ref_id) : ['evidence_map'],
      explanation: `${testimonyItems.length} testimony item(s) and ${documentItems.length} document item(s) are attached to the record.`,
    },
    {
      rule_id: 'release_gate.verdict',
      label: 'Client filing-readiness release gate',
      status: String(releaseGate.verdict || '').toLowerCase() === 'pass' ? 'pass' : 'block',
      severity: 'critical',
      evidence_refs: ['filing_release_gate'],
      explanation: releaseGate.reason || 'No release-gate reason was provided.',
    },
  ];
  return {
    trace_id: `trace-${packetSlug}`,
    trace_schema: 'complaint_handoff_neurosymbolic_trace.v1',
    trace_backend: 'ipfs_datasets_py',
    ipfs_preflight: envPreflight,
    dataset_refs: datasetRefs.concat(evidenceRefs),
    reasoning_summary: {
      claim_type: String(packet.claim_type || 'retaliation'),
      draft_strategy: String(draft.draft_strategy || 'template'),
      support_summary: `${Number(overview.supported_elements || 0)} supported element(s), ${Number(overview.missing_elements || 0)} open gap(s), ${testimonyItems.length + documentItems.length} saved evidence item(s).`,
      release_gate_verdict: String(releaseGate.verdict || 'unknown'),
      release_gate_reason: String(releaseGate.reason || ''),
      filing_shape_score: Number(uiFeedback.filing_shape_score || 0),
      claim_type_alignment_score: Number(uiFeedback.claim_type_alignment_score || 0),
      route_summary: [
        String((draft.draft_backend || {}).provider || draft.draft_strategy || 'template'),
        String(((uiFeedback.router_review || {}).backend || {}).provider || ''),
        String(((uiFeedback.router_review || {}).backend || {}).model || ''),
      ].filter(Boolean).join(' / ') || 'template',
    },
    rule_hits: ruleHits,
  };
}

function filingProvenancePayload(userId = 'did:key:playwright-demo') {
  const analysis = buildComplaintOutputAnalysis(userId);
  const packetPayload = exportComplaintPacketPayload(userId);
  const draft = (((packetPayload.packet || {}).draft) || {});
  const complaintBackend = Object.assign({}, (((analysis.ui_feedback || {}).router_review || {}).backend || {}));
  const exportCriticBackend = Object.assign({}, complaintBackend);
  const neurosymbolicTrace = neurosymbolicTracePayload(userId);
  return {
    user_id: userId,
    claim_type: String(((packetPayload.packet || {}).claim_type) || 'retaliation'),
    draft_strategy: String((draft.draft_strategy) || 'template'),
    draft_backend: Object.assign({}, (draft.draft_backend || {})),
    complaint_output_router_backend: complaintBackend,
    complaint_output_router_backends: Object.keys(complaintBackend).length ? [complaintBackend] : [],
    export_critic_router_backends: Object.keys(exportCriticBackend).length ? [exportCriticBackend] : [],
    ui_review_backend: {
      strategy: 'multimodal_router',
      provider: 'llm_router',
      model: 'multimodal_router',
    },
    ui_workflow_type: 'ui_ux_closed_loop',
    artifact_formats: Array.isArray((packetPayload.packet_summary || {}).artifact_formats) ? packetPayload.packet_summary.artifact_formats : [],
    has_draft: Boolean((packetPayload.packet_summary || {}).has_draft),
    dataset_refs: neurosymbolicTrace.dataset_refs,
    reasoning_summary: neurosymbolicTrace.reasoning_summary,
    rule_hits: neurosymbolicTrace.rule_hits,
    neurosymbolic_trace: neurosymbolicTrace,
  };
}

function providerDiagnosticsPayload(userId = 'did:key:playwright-demo') {
  return {
    user_id: userId,
    forced_provider: null,
    default_order: ['codex_cli', 'copilot_cli', 'openai', 'hf_inference_api'],
    effective_default_provider: 'codex_cli',
    complaint_draft_default_order: ['codex_cli', 'copilot_cli', 'hf_inference_api'],
    effective_complaint_draft_provider: 'codex_cli',
    ui_review_default_provider: 'codex_cli',
    ui_review_hf_fallback_model: 'Qwen/Qwen2.5-VL-7B-Instruct',
    ui_review_multimodal_rate_limit_fallbacks: {
      codex_cli: ['copilot_cli', 'hf_inference_api'],
      copilot_cli: ['hf_inference_api'],
    },
    providers: [
      {
        name: 'codex_cli',
        available: true,
        reason: 'Codex CLI is installed and available on PATH.',
        binary_path: '/usr/bin/codex',
        credential_source: 'local_codex_auth',
        draft_timeout_seconds: 60,
      },
      {
        name: 'openai',
        available: false,
        reason: 'No OpenAI API key resolved from env, vault, keyring, or local CLI config.',
        credential_source: 'unavailable',
        base_url: 'https://api.openai.com/v1',
        draft_timeout_seconds: 30,
      },
      {
        name: 'copilot_cli',
        available: true,
        reason: 'Copilot fallback is available through the configured command template.',
        binary_path: '/usr/bin/copilot',
        credential_source: 'github_copilot_command_template',
        draft_timeout_seconds: 45,
      },
      {
        name: 'hf_inference_api',
        available: false,
        reason: 'No Hugging Face token resolved from env, vault, keyring, or huggingface_hub CLI login.',
        credential_source: 'unavailable',
        base_url: 'https://router.huggingface.co/hf-inference/models',
        draft_timeout_seconds: 30,
      },
    ],
    summary: {
      codex_available: true,
      openai_available: false,
      copilot_available: true,
      huggingface_available: false,
    },
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
  const packetMarkdown = [
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
  const complaintMarkdown = `${String(draft.body || 'No complaint draft has been generated yet.').trim()}\n`;
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
        content: complaintMarkdown,
        packet_content: packetMarkdown,
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
      draft_strategy: String((draft.draft_strategy || 'template')),
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
  const routerReview = {
    backend: {
      id: 'playwright-complaint-output-review',
      provider: 'llm_router',
      model: 'formal_complaint_reviewer',
      strategy: 'llm_router',
    },
    review: {
      summary: 'Stub complaint-output review confirms the export still needs visible filing-shape and support cues in the dashboard.',
      filing_shape_score: filingShapeScore,
      claim_type_alignment_score: claimTypeAlignmentScore,
      missing_formal_sections: Object.entries(formalSectionsPresent).filter(([, present]) => !present).map(([name]) => name),
      issues: [
        {
          severity: releaseGate.verdict === 'pass' ? 'low' : 'medium',
          finding: 'The operator still needs clearer filing-shape and export-gate cues before treating the complaint as client-safe.',
          complaint_impact: 'The complaint may be exported before the user understands which structural gaps remain.',
          ui_implication: 'Draft and export surfaces should keep the formal diagnostics and release gate visible.',
        },
      ],
      ui_suggestions: [
        {
          title: 'Keep formal diagnostics visible near export',
          target_surface: 'draft,integrations',
          recommendation: 'Show llm_router-backed filing diagnostics next to packet export and download controls.',
          why_it_matters: 'The operator can tell when the export is formal enough to trust.',
        },
      ],
      ui_priority_repairs: [
        {
          priority: 'high',
          target_surface: 'draft,integrations',
          repair: 'Keep routing provenance and filing-shape diagnostics visible before export.',
          filing_benefit: 'The complaint output stays tied to the critic path that judged it.',
        },
      ],
      actor_risk_summary: 'A complainant could mistake the export for a finished filing without seeing the router-backed gate.',
      critic_gate: {
        verdict: releaseGate.verdict === 'pass' ? 'pass' : 'warning',
        blocking_reason: releaseGate.reason,
        required_repairs: ['Preserve visible routing and filing diagnostics before download.'],
      },
    },
  };
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
      router_review: routerReview,
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
      backend: {
        strategy: 'multimodal_router',
        provider: args.provider || 'llm_router',
        model: args.model || 'multimodal_router',
      },
      latest_review: `# Top Risks\n- ${routerLabel} should keep complaint-output guidance visible while reviewing screenshots.\n\n# High-Impact UX Fixes\n- ${String(suggestion.title || 'Promote complaint-output blockers')} so unsupported claim elements stay visible before export.\n- ${String(suggestion.recommendation || 'Use complaint-output suggestions to tighten review and draft guidance.')}\n\n# Stage Findings\n## Intake\nFirst-time complainants need clearer reassurance that incomplete dates and imperfect wording can still be saved.\n\n## Evidence\nEvidence capture guidance is still too easy to miss for first-time complainants.\n\n## Review\nComplaint-output suggestion carried into router review: ${String(suggestion.title || 'Promote complaint-output blockers')}.\n\n## Draft\nDraft generation should feel like the direct continuation of the case theory, not a separate document tool.\n\n## Integration Discovery\n${routerLabel} should stay visible from the shared dashboard shortcuts and tool panels.`,
      review: {
        summary: `Workspace mock review completed with ${routerLabel}. Complaint-output suggestion: ${String(suggestion.title || 'Promote complaint-output blockers')}.`,
        issues: [
          {
            severity: 'medium',
            surface: '/workspace',
            problem: 'Export controls can still visually outrank the release gate and support summary.',
            user_impact: 'A complainant could download a complaint before noticing the formal-filing warnings and readiness cues.',
            recommended_fix: 'Keep the release gate, filing-shape score, and next-step guidance pinned beside the download controls.',
          },
        ],
        broken_controls: [
          {
            surface: '/workspace',
            control: 'Download Markdown',
            failure_mode: 'Export looks like a primary CTA before the complainant reviews filing readiness.',
            repair: 'Keep the release-gate summary visibly adjacent to the export controls.',
          },
        ],
        complaint_journey: {
          tested_stages: ['chat', 'intake', 'evidence', 'review', 'draft', 'integrations', 'optimizer'],
          journey_gaps: ['Keep export blockers and release-gate messaging visible beside the download controls.'],
          sdk_tool_invocations: [
            'complaint.start_session',
            'complaint.submit_intake',
            'complaint.save_evidence',
            'complaint.import_gmail_evidence',
            'complaint.review_case',
            'complaint.generate_complaint',
            'complaint.export_complaint_packet',
            'complaint.review_generated_exports',
            'complaint.review_ui',
            'complaint.optimize_ui',
          ],
          release_blockers: [],
        },
        actor_plan: {
          primary_objective: 'Keep the complainant on a linear path from intake through export without hiding release-gate warnings.',
          repair_sequence: [
            'Keep filing-shape and support warnings visible beside exports',
            'Use the Gmail import affordance to strengthen documentary support earlier in the flow',
            'Preserve the MCP tool contract in the integrations panel',
          ],
        },
        critic_review: {
          verdict: 'warning',
          blocking_findings: ['Export controls still need stronger readiness framing before download.'],
          acceptance_checks: [
            'The release gate must remain visible after complaint generation and before download.',
            'The optimizer must keep the MCP tool contract discoverable from the integrations panel.',
            'The Gmail import route must remain browser-accessible through the JavaScript SDK.',
          ],
        },
        actor_summary: 'The actor can now reach a formal complaint, upload evidence, review support, and hand off to the mediator, but export still needs stronger guardrails.',
        critic_summary: 'The critic accepts the overall complaint journey, while requiring clearer release-gate emphasis near the download controls.',
        actor_path_breaks: [
          'Export still feels slightly too easy relative to the visible readiness messaging.',
        ],
        critic_test_obligations: [
          'Verify the release gate remains visible after export analysis and before download.',
          'Verify Gmail import remains browser-visible through the shared MCP contract.',
        ],
        playwright_followups: [
          'Capture the draft panel after export analysis so the release gate and complaint-output guidance remain visible.',
          'Capture the evidence panel near the Gmail import affordance so evidence-ingestion guidance stays legible.',
        ],
        stage_findings: {
          Intake: 'First-time complainants need clearer reassurance that incomplete dates and imperfect wording can still be saved.',
          Evidence: 'The Gmail import affordance keeps evidence ingestion inside the browser workspace and the shared MCP SDK path.',
          Review: `Complaint-output suggestion carried into router review: ${String(suggestion.title || 'Promote complaint-output blockers')}.`,
          Draft: 'Draft generation should feel like the direct continuation of the case theory, not a separate document tool.',
          'Integration Discovery': `${routerLabel} should stay visible from the shared dashboard shortcuts and tool panels.`,
        },
      },
      stage_findings: {
        Intake: 'First-time complainants need clearer reassurance that incomplete dates and imperfect wording can still be saved.',
        Evidence: 'The Gmail import affordance keeps evidence ingestion inside the browser workspace and the shared MCP SDK path.',
        Review: `Complaint-output suggestion carried into router review: ${String(suggestion.title || 'Promote complaint-output blockers')}.`,
        Draft: 'Draft generation should feel like the direct continuation of the case theory, not a separate document tool.',
        'Integration Discovery': `${routerLabel} should stay visible from the shared dashboard shortcuts and tool panels.`,
      },
      actor_summary: 'The actor can stay on one DID-backed complaint path, but still needs clearer guidance for synopsis, evidence upload, review, and draft transitions.',
      critic_summary: 'The critic expects hard end-to-end assertions around testimony, evidence attachment, support review, and final complaint generation.',
      actor_path_breaks: [
        'Users can still miss the moment when they should save a shared synopsis before moving into review and draft.',
      ],
      critic_test_obligations: [
        'Verify the full workspace journey from intake through mediator synopsis, evidence upload, review, and final complaint draft.',
      ],
      latest_review_json_path: 'artifacts/ui-audit/reviews/iteration-01-review.json',
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
  const selectedPatchBriefTitles = ['UX repair 1', 'UX repair 2', 'UX repair 3'];
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
    recommendation_coverage: {
      rounds_with_selected_patch_briefs: 1,
      selected_patch_briefs_total: 3,
      covered_patch_briefs_total: 3,
      overall_selected_patch_brief_coverage_ratio: 1.0,
      average_selected_patch_brief_coverage_ratio: 1.0,
      latest_selected_patch_brief_titles: selectedPatchBriefTitles,
      latest_covered_patch_brief_titles: selectedPatchBriefTitles,
      latest_uncovered_selected_patch_brief_titles: [],
      latest_changed_files: ['templates/workspace.html', 'static/complaint_mcp_sdk.js'],
      latest_optimizer_status: 'applied',
    },
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
          metadata: {
            changed_files: ['templates/workspace.html', 'static/complaint_mcp_sdk.js'],
            selected_patch_brief_titles: selectedPatchBriefTitles,
            covered_patch_brief_titles: selectedPatchBriefTitles,
            uncovered_selected_patch_brief_titles: [],
            selected_patch_brief_coverage_ratio: 1.0,
          },
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
  const courtHeader = courtHeaderLine(answers.court_header);
  const protectedActivity = sentenceFragment(answers.protected_activity, 'engaged in protected activity');
  const pleadingActivity = pleadingActivityFragment(answers.protected_activity, 'engaging in protected activity');
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
    retaliation: `1. ${answers.party_name || 'Plaintiff'} brings this retaliation complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from ${answers.opposing_party || 'Defendant'}'s retaliatory response after ${answers.party_name || 'Plaintiff'} engaged in protected activity, including ${pleadingActivity}.`,
    employment_discrimination: `1. ${answers.party_name || 'Plaintiff'} brings this employment discrimination complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from discriminatory workplace treatment, unequal terms or conditions, and resulting harm.`,
    housing_discrimination: `1. ${answers.party_name || 'Plaintiff'} brings this housing discrimination complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from discriminatory denial, limitation, interference, or retaliation affecting housing rights or benefits.`,
    due_process_failure: `1. ${answers.party_name || 'Plaintiff'} brings this due process complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from adverse action imposed without the notice, hearing, review, or procedural protections required by law.`,
    consumer_protection: `1. ${answers.party_name || 'Plaintiff'} brings this consumer protection complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from unfair, deceptive, fraudulent, or otherwise unlawful business practices that caused injury.`,
  }[claimType] || `1. ${answers.party_name || 'Plaintiff'} brings this ${claimType.replace(/_/g, ' ')} complaint against ${answers.opposing_party || 'Defendant'}. This civil action arises from unlawful conduct that injured ${answers.party_name || 'Plaintiff'} and is being framed in the correct claim-specific pleading posture.`;
  const reliefParagraph = {
    retaliation: '2. Plaintiff seeks back pay, front pay or reinstatement, compensatory damages, attorney\'s fees and costs, equitable relief, and such further relief as may be just to remedy Defendant\'s retaliatory acts and the losses flowing from them.',
    employment_discrimination: `2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy discriminatory employment practices, restore lost opportunities, and address the harm caused when Plaintiff ${sentenceFragment(answers.adverse_action, 'suffered an adverse employment action')}.`,
    housing_discrimination: `2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy discriminatory housing practices, preserve housing stability, and address the harm caused when Plaintiff ${sentenceFragment(answers.adverse_action, 'suffered a housing-related deprivation')}.`,
    due_process_failure: `2. Plaintiff seeks declaratory relief, equitable relief, damages, and such further relief as may be just to remedy the procedural deprivation and the harm caused when Plaintiff ${sentenceFragment(answers.adverse_action, 'suffered a deprivation without adequate process')}.`,
    consumer_protection: `2. Plaintiff seeks damages, restitution, equitable relief, and such further relief as may be just to remedy deceptive or unfair consumer practices and the harm caused when Plaintiff ${sentenceFragment(answers.adverse_action, 'suffered a consumer-facing injury')}.`,
  }[claimType] || `2. Plaintiff seeks damages, equitable relief, and such further relief as may be just to remedy unlawful conduct and the harm caused when Plaintiff ${sentenceFragment(answers.adverse_action, 'suffered an adverse action')}.`;
  const jurisdictionParagraph = {
    retaliation: '3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges retaliation for protected activity and seeks relief for materially adverse acts taken in response to that activity.',
    employment_discrimination: '3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges discriminatory employment practices, workplace bias, and related unlawful employment actions for which judicial relief is available.',
    housing_discrimination: '3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges discriminatory housing practices, interference with housing rights or benefits, and related misconduct for which judicial relief is available.',
    due_process_failure: '3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges deprivation without constitutionally or statutorily required notice, hearing, review, or other procedural protections.',
    consumer_protection: '3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges unfair, deceptive, or unlawful consumer-facing conduct for which damages, restitution, or equitable relief may be awarded.',
  }[claimType] || '3. This Court has subject-matter jurisdiction over this action because Plaintiff alleges unlawful conduct for which judicial relief is available.';
  const venueParagraph = {
    housing_discrimination: '4. Venue is proper in this District because the housing-related events, denial, interference, or threatened loss of housing benefits occurred in this forum and the resulting harm was felt here.',
    employment_discrimination: '4. Venue is proper in this District because the workplace events, adverse employment decisions, and resulting economic harm occurred in or were directed into this forum.',
    consumer_protection: '4. Venue is proper in this District because the transaction, deceptive practice, or resulting economic loss occurred in this forum or caused injury here.',
  }[claimType] || '4. Venue is proper in this District because a substantial part of the events or omissions giving rise to these claims occurred in this forum and the resulting harm was felt here.';
  const plaintiffParagraph = {
    retaliation: `5. Plaintiff ${answers.party_name || 'Plaintiff'} is an individual who engaged in protected activity and was thereafter harmed by the retaliatory conduct described below.`,
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
      `7. Plaintiff engaged in protected activity by ${pleadingActivity}.`,
      '8. That protected activity constituted protected opposition, reporting, or participation activity under the governing anti-retaliation framework.',
      `9. Within days of that protected activity, Defendant took materially adverse action against Plaintiff by ${adverseActionClause(answers.adverse_action, 'taking materially adverse action against Plaintiff')}.`,
      `10. The relevant chronology is as follows: ${pleadingTimelineSentence(answers.timeline, 'The events occurred in close temporal proximity')}`,
      `11. As a direct and proximate result of Defendant's conduct, Plaintiff ${sentenceFragment(answers.harm, 'suffered compensable harm')}.`,
    ],
    employment_discrimination: [
      `7. ${answers.party_name || 'Plaintiff'} alleges facts showing discriminatory employment treatment, including protected conduct or circumstances such as ${pleadingActivity}.`,
      `8. Defendant thereafter took or maintained adverse employment action described as ${adverseAction}.`,
      `9. The employment chronology is as follows: ${pleadingTimelineSentence(answers.timeline, 'The relevant employment events occurred in close succession')}`,
      '10. The present record supports an inference of discriminatory motive, disparate treatment, prohibited bias, retaliation, or other unlawful employment decision-making.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
    housing_discrimination: [
      `7. ${answers.party_name || 'Plaintiff'} alleges that they sought, used, requested, or protected housing-related rights, accommodations, benefits, tenancy rights, or fair treatment, including ${pleadingActivity}.`,
      `8. Defendant thereafter denied, burdened, interfered with, or threatened housing-related rights or benefits through adverse action described as ${adverseAction}.`,
      `9. The housing-related chronology is as follows: ${pleadingTimelineSentence(answers.timeline, 'The housing-related events occurred in close succession')}`,
      '10. The present record supports an inference that Defendant acted in a discriminatory manner, interfered with protected housing rights, or retaliated in connection with protected housing activity.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
    due_process_failure: [
      '7. Plaintiff alleges that Defendant imposed or maintained a deprivation affecting protected rights, interests, status, benefits, or property.',
      `8. The challenged action is described as ${adverseAction}.`,
      `9. The chronology is as follows: ${pleadingTimelineSentence(answers.timeline, 'The challenged events occurred in close succession')}`,
      '10. Plaintiff alleges that the deprivation occurred without adequate notice, hearing, review, appeal, or other required procedural protection.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
    consumer_protection: [
      '7. Plaintiff alleges that Defendant engaged in deceptive, misleading, unfair, or otherwise unlawful consumer-facing conduct.',
      `8. That conduct included or resulted in adverse action or consequences described as ${adverseAction}.`,
      `9. The chronology is as follows: ${pleadingTimelineSentence(answers.timeline, 'The relevant consumer-facing events occurred in close succession')}`,
      '10. Plaintiff alleges that the challenged conduct caused consumer harm, financial loss, or other compensable injury in a transactional or service context.',
      `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
    ],
  }[claimType] || [
    `7. ${answers.party_name || 'Plaintiff'} alleges conduct or circumstances including ${pleadingActivity}.`,
    `8. Defendant engaged in conduct including adverse action described as ${adverseAction}.`,
    `9. The chronology is as follows: ${pleadingTimelineSentence(answers.timeline, 'The relevant events occurred in close succession')}`,
    '10. Plaintiff alleges facts supporting a plausible claim for relief.',
    `11. As a direct and proximate result of Defendant's conduct, ${answers.party_name || 'Plaintiff'} suffered ${harm}.`,
  ];
  const claimParagraphs = {
    retaliation: [
      `Plaintiff engaged in protected activity by ${pleadingActivity}, and Defendant knew or should have known of that protected conduct.`,
      `Defendant thereafter subjected Plaintiff to materially adverse action by ${adverseActionClause(answers.adverse_action, 'taking materially adverse action against Plaintiff')}, under circumstances supporting a causal inference of retaliation.`,
      'The close temporal proximity, Defendant\'s knowledge of the protected activity, the evidentiary record, and the resulting harm plausibly support a retaliation claim and entitle Plaintiff to relief.',
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
    .map((item) => formalEvidenceSummaryItem(item, 'testimony'))
    .join('; ') || 'No witness or complainant testimony is presently identified';
  const documentSummary = (evidence.documents || []).slice(0, 3)
    .map((item) => formalEvidenceSummaryItem(item, 'document'))
    .join('; ') || 'No documentary exhibits are presently identified';
  const testimonyReferenceLines = (evidence.testimony || []).slice(0, 3)
    .map((item) => `Plaintiff expects to offer testimony presently identified as '${item.title || 'Untitled testimony'}' in support of the ${claimElementLabel(item.claim_element_id).toLowerCase()} element.`);
  const documentReferenceLines = (evidence.documents || []).slice(0, 3)
    .map((item) => `Plaintiff expects to offer documentary exhibit '${item.title || 'Untitled document'}' in support of the ${claimElementLabel(item.claim_element_id).toLowerCase()} element.`);
  const body = [
    'IN THE UNITED STATES DISTRICT COURT',
    courtHeader,
    '',
    `${answers.party_name || 'Plaintiff'}, Plaintiff,`,
    'v.',
    `${answers.opposing_party || 'Defendant'}, Defendant.`,
    '',
    'Civil Action No. ________________',
    complaintHeading,
    'JURY TRIAL DEMANDED',
    '',
    `Plaintiff ${answers.party_name || 'Plaintiff'}, proceeding pro se, alleges upon personal knowledge as to their own acts and upon information and belief as to all other matters as follows:`,
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
    (evidence.testimony || []).length
      ? `12. Plaintiff presently relies on ${Number((evidence.testimony || []).length + (evidence.documents || []).length)} identified evidentiary items. The witness proof currently identified includes: ${testimonySummary}.`
      : '12. Plaintiff presently relies on the evidentiary materials identified below and anticipates that testimonial proof may be supplemented through discovery, amendment, or sworn declarations.',
    (evidence.documents || []).length
      ? `13. Plaintiff presently identifies the following documents, exhibits, or records in support of this pleading: ${documentSummary}.`
      : '13. Plaintiff has not yet attached documentary exhibits to this export, but preserves the right to supplement the pleading with records, correspondence, or other supporting materials.',
    `14. Based on the information presently available, Plaintiff contends that the evidentiary record presently supports ${Number(overview.supported_elements || 0)} core claim elements and that ${Number(overview.missing_elements || 0)} areas, if any, may be further corroborated through discovery, amendment, or additional evidentiary development.`,
      '15. Plaintiff gives notice that the identified testimony, documentary exhibits, and chronology materials constitute part of the evidentiary basis for this pleading and may be supplemented, authenticated, or amended as discovery proceeds.',
    ...[...testimonyReferenceLines, ...documentReferenceLines].slice(0, 2).map((line, index) => `${16 + index}. ${line}`),
    '',
    'CLAIM FOR RELIEF',
    countHeading,
    '17. Plaintiff repeats and realleges the preceding paragraphs as if fully set forth herein.',
    `18. ${claimParagraphs[0]}`,
    `19. ${claimParagraphs[1]}`,
    `20. ${claimParagraphs[2]}`,
    `21. Plaintiff has sustained damages and losses including ${harm}.`,
    claimType === 'retaliation'
      ? "22. As a direct and proximate result of Defendant's retaliatory conduct, Plaintiff is entitled to recover damages, equitable relief, fees and costs where available, and such further relief as the Court deems just and proper."
      : "22. Defendant's acts were intentional, knowing, reckless, retaliatory, discriminatory, deceptive, or otherwise unlawful under the governing claim theory.",
    '',
    'PRAYER FOR RELIEF',
    claimType === 'retaliation'
      ? 'Wherefore, Plaintiff respectfully requests judgment against Defendant on the retaliation claim alleged herein and seeks the following relief:'
      : 'Wherefore, Plaintiff requests judgment against Defendant and the following relief:',
    ...relief.map((item, index) => `${index + 1}. ${formalizeReliefItem(item)}.`),
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
  ].join('\n\n');
  const useLlm = Boolean(options.use_llm);
  const provider = String(options.provider || '').trim() || 'codex_cli';
  const model = String(options.model || '').trim() || 'gpt-5.3-codex';
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

function buildLaypersonDashboardCardsFixture() {
  return [
  {
    stepNumber: 1,
    stage: 'Step 1',
    workflowStage: 'Intake',
    stepLabel: 'Step 1: Intake',
    title: 'Start your complaint',
    description: 'Answer guided questions so the workspace has the story, people, dates, harms, and possible claims.',
    primaryLabel: 'Start Intake Questions',
    primaryHref: '/chat',
    detailLabel: 'See intake details',
    stateLabel: 'Current',
    stateKind: 'current',
    stepperText: 'Step 1: Intake',
    statusText: 'Current: start here',
    unlockReason: 'Ready now',
    prerequisites: [
      ['Current', 'Ready now'],
      ['Next', 'Save facts before evidence or draft work'],
    ],
    links: [
      ['Check proof gaps later', '/claim-support-review'],
      ['Build a draft later', '/document'],
    ],
  },
  {
    stepNumber: 2,
    stage: 'Step 2',
    workflowStage: 'Evidence',
    stepLabel: 'Step 2: Evidence',
    title: 'Continue your complaint',
    description: 'Resume saved work and add documents, laws, or court cases.',
    primaryLabel: 'Resume evidence workspace',
    primaryHref: '/workspace',
    detailLabel: 'See evidence and saved-work details',
    stateLabel: 'Locked',
    stateKind: 'locked',
    stepperText: 'Step 2: Evidence',
    statusText: 'Locked: complete Step 1 first',
    locked: true,
    lockedLabel: 'Locked',
    lockedActionLabel: 'Disabled: complete Step 1 first',
    unlockReason: 'Complete Step 1: Intake to unlock Evidence',
    prerequisites: [
      ['Locked', 'Complete Step 1: Intake to unlock Evidence'],
    ],
    links: [
      ['Add evidence', '/workspace?stage=evidence'],
      ['Organize materials', '/workspace?stage=integrations'],
      ['Review support', '/claim-support-review'],
    ],
  },
  {
    stepNumber: 3,
    stage: 'Step 3',
    workflowStage: 'Review',
    stepLabel: 'Step 3: Review',
    title: 'Review a court docket or response',
    description: 'Inspect filings, deadlines, orders, or a response document.',
    primaryLabel: 'Open docket review',
    primaryHref: '/workspace?stage=docket&intent=review_docket',
    detailLabel: 'See docket review details',
    stateLabel: 'Locked',
    stateKind: 'locked',
    stepperText: 'Step 3: Review',
    statusText: 'Locked: add a docket file',
    locked: true,
    lockedLabel: 'Locked',
    lockedActionLabel: 'Disabled: add a docket file',
    unlockReason: 'Add a docket file to unlock Review',
    prerequisites: [
      ['Locked', 'Add a docket file to unlock Review'],
    ],
    links: [
      ['Ask about a filing', '/chat?chat_context=docket_document'],
      ['Add labels or notes', '/workspace?stage=integrations&intent=annotate_documents'],
      ['Open docket tools', '#dashboard-advanced-tools'],
    ],
  },
  ];
}

function buildDashboardUtilityCardsFixture() {
  return [
  {
    stage: 'Utility',
    workflowStage: 'Profile',
    title: 'Manage your profile',
    description: 'Check personal and session information used to resume work.',
    primaryLabel: 'Open profile',
    primaryHref: '/profile',
    detailLabel: 'See profile and session details',
    stateLabel: 'Optional',
    stateKind: 'utility',
    prerequisites: [
      ['Optional', 'Use for identity and saved context'],
      ['Next', 'Check session information'],
    ],
    links: [
      ['Cookies', '/cookies'],
      ['Saved work', '/workspace'],
      ['Technical tools', '#dashboard-advanced-tools'],
    ],
  },
  ];
}

function buildDashboardSubsectionCardsFixture() {
  return [
  {
    title: 'Start and Review',
    description: 'Guided questions, proof checks, next recommended action, and draft handoff.',
    links: [['Guided questions', '/chat'], ['Proof review', '/claim-support-review'], ['Build draft', '/document']],
  },
  {
    title: 'Evidence, Laws, and Court Cases',
    description: 'Resume work, upload files, organize source materials, find connections, and check duties or conflicts.',
    links: [['Saved complaint', '/workspace'], ['Add evidence', '/workspace?stage=evidence'], ['Find connections', '/workspace?stage=integrations']],
  },
  {
    title: 'Court Dockets and Responses',
    description: 'Load docket records, search filings, preview calendar events, and save useful notes.',
    links: [['Review docket', '/workspace?stage=docket'], ['Ask document question', '/chat?chat_context=docket_document'], ['Add notes', '/workspace?stage=integrations&intent=annotate_documents']],
  },
  {
    title: 'Profile and Technical Tools',
    description: 'Profile, cookies, session tools, and optional package consoles for administrators.',
    links: [['Profile', '/profile'], ['Session tools', '/mcp'], ['Advanced consoles', '#dashboard-advanced-tools']],
  },
  ];
}

function buildDashboardFixtures({
  dashboardEntries = buildDashboardEntriesFixture(),
  laypersonDashboardCards = buildLaypersonDashboardCardsFixture(),
  dashboardUtilityCards = buildDashboardUtilityCardsFixture(),
  dashboardSubsectionCards = buildDashboardSubsectionCardsFixture(),
  advancedDashboardSlugs = ['mcp', 'admin-caselaw', 'admin-caselaw-mcp', 'admin-graphrag', 'admin-mcp'],
} = {}) {
  const entries = [...dashboardEntries];
  const entryMap = new Map();
  entries.forEach((entry) => {
    if (!entry || !entry.slug) {
      throw new TypeError('Every dashboard fixture entry must define a slug');
    }
    if (entryMap.has(entry.slug)) {
      throw new Error(`Duplicate dashboard fixture slug: ${entry.slug}`);
    }
    entryMap.set(entry.slug, entry);
  });
  return {
    dashboardEntries: entries,
    dashboardEntryMap: entryMap,
    laypersonDashboardCards: [...laypersonDashboardCards],
    dashboardUtilityCards: [...dashboardUtilityCards],
    dashboardSubsectionCards: [...dashboardSubsectionCards],
    advancedDashboardSlugs: [...advancedDashboardSlugs],
  };
}

const defaultDashboardFixtures = buildDashboardFixtures();

function getDashboardFixtures() {
  return defaultDashboardFixtures;
}

function getDashboardEntry(slug, fixtures = getDashboardFixtures()) {
  return fixtures.dashboardEntryMap.get(String(slug || '')) || null;
}

function getDefaultDashboardEntry(fixtures = getDashboardFixtures()) {
  const entry = getDashboardEntry('mcp', fixtures) || fixtures.dashboardEntries[0];
  if (!entry) {
    throw new Error('Dashboard fixtures must define at least one dashboard entry');
  }
  return entry;
}

function withDashboardContext(href, searchParams) {
  const userId = searchParams && searchParams.get('user_id');
  if (!userId || href.startsWith('#') || href.startsWith('/cookies')) {
    return href;
  }
  const separator = href.includes('?') ? '&' : '?';
  return `${href}${separator}user_id=${encodeURIComponent(userId)}`;
}

function renderLinkRow(links, searchParams) {
  return links.map(([label, href]) => (
    `<a class="jump-link" href="${escapeXml(withDashboardContext(href, searchParams))}">${escapeXml(label)}</a>`
  )).join('');
}

function renderDashboardHub(searchParams = new URLSearchParams(), fixtures = getDashboardFixtures()) {
  const stageControls = fixtures.laypersonDashboardCards.map((card) => {
    if (card.locked) {
      return `<article class="stage-control is-locked" data-path-state="${escapeXml(card.stateKind || 'locked')}" aria-label="${escapeXml(card.stepLabel)} locked">
        <div class="stage-label">${escapeXml(card.stepLabel)}</div>
        <h3>${escapeXml(card.workflowStage)}</h3>
        <p><strong>To unlock:</strong> ${escapeXml(card.unlockReason || card.statusText || 'Locked')}</p>
        <button class="stage-control-action" type="button" disabled aria-disabled="true">${escapeXml(card.lockedActionLabel || 'Disabled until prerequisite is complete')}</button>
      </article>`;
    }
    return `<article class="stage-control is-current recommended-action-panel" id="dashboard-recommended-action-panel" data-path-state="${escapeXml(card.stateKind || 'current')}" aria-label="Recommended next action">
      <div>
        <div class="stage-label">${escapeXml(card.stepLabel || 'Step 1: Intake')}</div>
        <h3 id="dashboard-recommended-action-title">Explain what happened</h3>
        <p id="dashboard-recommended-action-reason">${escapeXml(card.description)}</p>
      </div>
      <div class="primary-action-stack">
        <a class="primary-action" id="dashboard-recommended-action-link" href="${escapeXml(withDashboardContext(card.primaryHref, searchParams))}">${escapeXml(card.primaryLabel)}</a>
        <span class="primary-action-note">Opens guided questions and creates your workspace session</span>
      </div>
    </article>`;
  }).join('');
  const utilityCards = fixtures.dashboardUtilityCards.map((card) => {
    const prerequisiteMarkup = (card.prerequisites || []).map(([label, text]) => (
      `<div class="prerequisite-next-line"><strong>${escapeXml(label)}</strong>${escapeXml(text)}</div>`
    )).join('');
    const extraMarkup = card.links.length
      ? `<details class="card-more-actions"><summary><span>${escapeXml(card.detailLabel)}</span><span class="disclosure-cue">Expand</span></summary><div class="link-row">${renderLinkRow(card.links, searchParams)}</div></details>`
      : '';
    return `<article class="entry-card is-utility" data-path-state="utility">
      <div class="stage-label">${escapeXml(card.stage)}</div>
      <span class="path-state-label">${escapeXml(card.stateLabel || 'Optional')}</span>
      <span class="path-stage-chip">Stage: ${escapeXml(card.workflowStage)}</span>
      <h3>${escapeXml(card.title)}</h3>
      <p>${escapeXml(card.description)}</p>
      <div class="prerequisite-row" aria-label="${escapeXml(card.title)} prerequisites">${prerequisiteMarkup}</div>
      <div class="card-action-row">
        <a class="switch-action" href="${escapeXml(withDashboardContext(card.primaryHref, searchParams))}">${escapeXml(card.primaryLabel)}</a>
      </div>
      ${extraMarkup}
    </article>`;
  }).join('');
  const subsectionCards = fixtures.dashboardSubsectionCards.map((card) => (
    `<article class="subsection-card">
      <h3>${escapeXml(card.title)}</h3>
      <p>${escapeXml(card.description)}</p>
      <div class="link-row">${renderLinkRow(card.links, searchParams)}</div>
    </article>`
  )).join('');
  const advancedEntries = fixtures.advancedDashboardSlugs
    .map((slug) => getDashboardEntry(slug, fixtures))
    .filter(Boolean);
  const advancedLinks = advancedEntries.map((entry) => (
    `<li><a href="/dashboards/ipfs-datasets/${escapeXml(entry.slug)}">${escapeXml(entry.title)}</a><span>${escapeXml(entry.summary)}</span></li>`
  )).join('');
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Unified Dashboard Hub</title>
  <style>
    :root {
      --bg: #f5f3ec;
      --surface: #fffefa;
      --ink: #172231;
      --muted: #394958;
      --line: rgba(23, 34, 49, 0.13);
      --accent: #125c63;
      --accent-strong: #0d4449;
      --warn: #9a4b19;
      --good: #226a4b;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, sans-serif; background: var(--bg); color: var(--ink); }
    header { background: #18384f; color: white; padding: 22px 32px; }
    header p { color: rgba(255,255,255,0.9); max-width: 58ch; }
    main { max-width: 1240px; margin: 0 auto; padding: 28px 24px 48px; display: grid; gap: 22px; }
    h1, h2, h3, p { margin-top: 0; }
    p, span { color: var(--muted); line-height: 1.45; }
    a { color: var(--accent-strong); font-weight: 700; }
    .section, details { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 22px; box-shadow: 0 12px 26px rgba(23, 34, 49, 0.07); }
    .hero { display: grid; gap: 14px; padding: 0; background: transparent; border: 0; box-shadow: none; }
    .safety-note { border-left: 4px solid rgba(154, 75, 25, 0.70); background: rgba(154, 75, 25, 0.07); border-radius: 8px; padding: 10px 12px; font-size: 0.94rem; color: var(--ink); }
    .recommended-action-panel { display: grid; gap: 14px; grid-template-columns: 1fr; align-items: start; background: white; border: 3px solid rgba(18, 92, 99, 0.45); border-radius: 8px; padding: 20px; box-shadow: 0 14px 30px rgba(18, 92, 99, 0.13); }
    .recommended-action-panel h3 { margin: 0; }
    .recommended-action-panel p { margin: 6px 0 0; }
    .stage-control-grid { display: grid; gap: 12px; grid-template-columns: minmax(320px, 1.3fr) repeat(2, minmax(220px, 0.85fr)); align-items: stretch; }
    .stage-control { display: grid; gap: 10px; align-content: start; border-radius: 8px; padding: 18px; border: 1px solid var(--line); background: white; }
    .stage-control h3 { margin: 0; }
    .stage-control p { margin: 0; }
    .stage-control.is-locked { background: rgba(244, 244, 245, 0.82); color: #52525b; border-color: rgba(82, 82, 91, 0.28); box-shadow: none; }
    .stage-control.is-locked h3,
    .stage-control.is-locked p,
    .stage-control.is-locked .stage-label { color: #52525b; }
    .stage-control-action { width: 100%; min-height: 38px; border-radius: 999px; padding: 8px 12px; border: 1px solid rgba(82, 82, 91, 0.32); background: #e4e4e7; color: #3f3f46; font-weight: 900; cursor: not-allowed; }
    .entry-grid { display: grid; gap: 14px; grid-template-columns: repeat(2, minmax(260px, 1fr)); }
    .subsection-grid { display: grid; gap: 14px; grid-template-columns: repeat(2, minmax(240px, 1fr)); }
    .entry-card, .subsection-card { display: grid; gap: 10px; align-content: start; background: white; border: 1px solid var(--line); border-radius: 8px; padding: 18px; }
    .entry-card.is-current { border: 2px solid rgba(18, 92, 99, 0.34); background: rgba(18, 92, 99, 0.045); }
    .entry-card.is-available, .entry-card.is-utility, .entry-card.is-waiting, .entry-card.is-locked { background: rgba(255, 255, 255, 0.72); }
    .entry-card.is-waiting { border-color: rgba(82, 82, 91, 0.18); background: rgba(250, 250, 250, 0.72); box-shadow: none; }
    .entry-card.is-waiting h3,
    .entry-card.is-waiting .path-stage-chip { color: #3f3f46; }
    .entry-card.is-waiting .path-state-label { background: rgba(82, 82, 91, 0.12); color: #3f3f46; }
    .entry-card.is-locked { border-color: rgba(82, 82, 91, 0.20); background: rgba(250, 250, 250, 0.72); box-shadow: none; }
    .entry-card.later-step { opacity: 0.82; }
    .entry-card.is-locked h3,
    .entry-card.is-locked .path-stage-chip { color: #3f3f46; }
    .entry-card.is-locked .path-state-label { background: rgba(82, 82, 91, 0.12); color: #3f3f46; }
    .path-state-label { width: fit-content; border-radius: 999px; padding: 5px 9px; background: rgba(23, 34, 49, 0.10); color: var(--ink); font-size: 0.84rem; font-weight: 900; }
    .entry-card.is-current .path-state-label { background: rgba(18, 92, 99, 0.12); color: var(--accent-strong); }
    .path-stage-chip { width: fit-content; border-radius: 999px; padding: 4px 8px; background: rgba(18, 92, 99, 0.09); color: var(--accent-strong); font-size: 0.88rem; font-weight: 900; }
    .prerequisite-row { display: grid; gap: 5px; }
    .prerequisite-status-line, .prerequisite-next-line { display: block; color: var(--ink); font-size: 0.95rem; line-height: 1.35; }
    .prerequisite-status-line { padding: 10px 12px; border-radius: 8px; background: rgba(18, 92, 99, 0.11); border: 2px solid rgba(18, 92, 99, 0.20); font-weight: 700; }
    .entry-card.is-waiting .prerequisite-status-line { background: rgba(244, 244, 245, 0.95); border-color: rgba(82, 82, 91, 0.16); }
    .prerequisite-next-line { color: var(--muted); }
    .prerequisite-status-line strong, .prerequisite-next-line strong { color: var(--accent-strong); margin-right: 6px; }
    .entry-card.is-locked .prerequisite-status-line strong { color: #7c2d12; }
    .card-status-copy { color: var(--ink); font-weight: 800; margin: 0; }
    .stage-label { color: var(--accent-strong); font-size: 0.76rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; }
    .primary-action, .jump-link { display: inline-flex; align-items: center; justify-content: center; min-height: 40px; border-radius: 999px; padding: 10px 14px; text-decoration: none; }
    .primary-action { background: var(--accent-strong); color: white; width: fit-content; min-width: 270px; min-height: 54px; font-size: 1.05rem; box-shadow: 0 16px 28px rgba(13, 68, 73, 0.30); }
    .primary-action-stack { display: grid; justify-items: end; gap: 7px; }
    .primary-action-note { color: var(--accent-strong); font-size: 0.9rem; font-weight: 800; }
    .jump-link { background: rgba(18, 92, 99, 0.08); border: 1px solid rgba(18, 92, 99, 0.16); }
    .switch-action { display: inline-flex; align-items: center; justify-content: center; min-height: 40px; border-radius: 999px; padding: 10px 14px; text-decoration: none; background: white; border: 1px solid rgba(18, 92, 99, 0.34); color: var(--accent-strong); width: fit-content; }
    .switch-action.is-disabled { border-color: rgba(82, 82, 91, 0.24); background: rgba(244, 244, 245, 0.96); color: #52525b; cursor: not-allowed; font-weight: 800; }
    .locked-action { margin: 0; color: #52525b; font-size: 0.9rem; font-weight: 900; }
    .locked-action::before { content: 'Locked: '; }
    .unlock-line { flex-basis: 100%; color: #7c2d12; font-size: 0.9rem; font-weight: 800; line-height: 1.35; }
    .link-row, .card-action-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .card-more-actions { padding: 0; border: 0; box-shadow: none; background: transparent; }
    .card-more-actions > summary { justify-content: space-between; font-size: 0.95rem; color: var(--accent-strong); min-height: 44px; border: 2px solid rgba(18, 92, 99, 0.22); border-radius: 8px; padding: 8px 12px; width: 100%; background: rgba(18, 92, 99, 0.07); }
    .card-more-actions > summary::before, #dashboard-subsection-index > summary::before, #dashboard-advanced-tools > summary::before { content: '>'; font-weight: 900; color: var(--accent-strong); }
    .card-more-actions[open] > summary::before, #dashboard-subsection-index[open] > summary::before, #dashboard-advanced-tools[open] > summary::before { transform: rotate(90deg); }
    .card-more-actions .link-row { margin-top: 8px; }
    details > summary { cursor: pointer; font-size: 1.08rem; font-weight: 900; color: var(--ink); min-height: 48px; display: flex; align-items: center; gap: 10px; }
    details > summary:hover, details > summary:focus-visible { outline: 2px solid rgba(18, 92, 99, 0.28); outline-offset: 2px; }
    .disclosure-cue { margin-left: auto; border-radius: 999px; padding: 3px 8px; background: white; border: 1px solid rgba(18, 92, 99, 0.18); color: var(--accent-strong); font-size: 0.78rem; font-weight: 900; }
    .summary-count { display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 8px; background: rgba(18, 92, 99, 0.10); color: var(--accent-strong); font-size: 0.78rem; font-weight: 800; }
    .summary-preview { margin: 0 0 14px; max-width: 76ch; }
    ul { margin-bottom: 0; padding-left: 20px; }
    li { margin: 10px 0; }
    li span { display: block; margin-top: 3px; }
    .mode-chip { display: inline-flex; width: fit-content; border-radius: 999px; padding: 6px 10px; background: rgba(240, 253, 244, 0.18); color: #d7ffe9; font-weight: 900; }
    @media (max-width: 760px) {
      header { padding: 22px 20px; }
      main { padding: 14px 12px 30px; gap: 14px; }
      .entry-grid, .subsection-grid { grid-template-columns: 1fr; }
      .stage-control-grid { grid-template-columns: 1fr; }
      .recommended-action-panel { grid-template-columns: 1fr; padding: 14px; gap: 10px; }
      .stage-control { padding: 12px; gap: 7px; }
      .stage-control.is-locked { gap: 6px; }
      .stage-control h3 { font-size: 1rem; }
      .stage-control p { font-size: 0.92rem; line-height: 1.32; }
      .stage-control-action { min-height: 34px; padding: 6px 10px; border-radius: 8px; }
      .primary-action-stack { justify-items: stretch; }
      .primary-action { width: 100%; min-height: 46px; }
      .progress-rule-strip { display: grid; grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <span class="mode-chip">Layperson complaint workspace</span>
    <h1>Unified Dashboard Hub</h1>
    <p>Start Intake, then unlock Evidence and Review.</p>
  </header>
  <main>
    <section class="hero" id="dashboard-start-here">
      <h2>Start your complaint</h2>
      <div class="stage-control-grid" id="dashboard-entry-paths" aria-label="Complaint stage controls">${stageControls}</div>
      <div class="safety-note"><strong>Important:</strong> This tool helps organize facts, documents, and draft text. It does not provide legal advice or decide whether you should file.</div>
    </section>
    <section class="section" aria-label="Profile and saved context">
      <h2>Profile and saved context</h2>
      <div class="entry-grid utility-grid" id="dashboard-utility-paths">${utilityCards}</div>
    </section>
    <details class="section" id="dashboard-subsection-index" open>
      <summary>Find the right tool <span class="summary-count">4 tool groups</span></summary>
      <p class="summary-preview">Use these shortcuts when you already know which part of the complaint workflow needs attention, including AI-assisted questions about docket documents.</p>
      <div class="subsection-grid">${subsectionCards}</div>
    </details>
    <details id="dashboard-advanced-tools">
      <summary>Advanced Operations <span class="summary-count">5 admin consoles</span></summary>
      <p>These package consoles and MCP diagnostics are for administrators, developers, or operators. They are hidden from the default complaint path so users are not asked to choose between internal variants.</p>
      <ul>${advancedLinks}</ul>
    </details>
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

function renderSdkPlaygroundShell() {
  const preflight = buildEnvironmentPreflight();
  if (!preflight.checks.sdk_playground_preview.exists) {
    return renderSdkPlaygroundFallback(preflight);
  }
  const rawHtml = fs.readFileSync(sdkPreviewPath, 'utf-8');
  const nav = `
    <nav class="surface-links" data-surface-nav="primary" aria-label="Complaint Generator Navigation" style="display:flex;flex-wrap:wrap;gap:12px;margin:16px auto 0;max-width:1200px;padding:0 20px;">
      <a class="surface-link" href="/">Landing</a>
      <a class="surface-link" href="/home">Account</a>
      <a class="surface-link" href="/chat">Chat</a>
      <a class="surface-link" href="/profile">Profile</a>
      <a class="surface-link" href="/results">Results</a>
      <a class="surface-link" href="/workspace">Workspace</a>
      <a class="surface-link" href="/claim-support-review">Review</a>
      <a class="surface-link" href="/document">Builder</a>
      <a class="surface-link" href="/mlwysiwyg">Editor</a>
      <a class="surface-link" href="/document/optimization-trace">Trace</a>
      <a class="surface-link" href="/ipfs-datasets/sdk-playground" aria-current="page">SDK</a>
      <a class="surface-link" href="/dashboards">Dashboards</a>
    </nav>
  `;
  const headInjected = rawHtml.includes('</head>')
    ? rawHtml.replace(
        '</head>',
        '\n<link rel="stylesheet" href="/static/complaint_app_shell.css">\n</head>',
      )
    : rawHtml;
  const bodyWithNav = headInjected.replace(/<body([^>]*)>/i, `<body$1>\n${nav}\n`);
  const scripts = `
    <script src="/static/complaint_mcp_sdk.js"></script>
    <script src="/static/complaint_app_shell.js"></script>
  `;
  return bodyWithNav.includes('</body>')
    ? bodyWithNav.replace('</body>', `${scripts}\n</body>`)
    : `${bodyWithNav}\n${scripts}`;
}

function renderSdkPlaygroundFallback(preflight) {
  const sdkState = preflight && preflight.checks && preflight.checks.sdk_playground_preview
    ? preflight.checks.sdk_playground_preview
    : { path: sdkPreviewPath, state: 'missing' };
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SDK Playground Unavailable</title>
  <link rel="stylesheet" href="/static/complaint_app_shell.css">
  <style>
    :root {
      --bg: #f7f2e8;
      --card: #fffdf8;
      --ink: #1c1f24;
      --muted: #505760;
      --line: rgba(28, 31, 36, 0.16);
      --warn: #8f3c16;
      --warn-bg: #fde8dd;
      --ok: #1f6f4a;
      --ok-bg: #e6f6ee;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    main {
      max-width: 980px;
      margin: 0 auto;
      padding: 28px 18px 40px;
      display: grid;
      gap: 16px;
    }
    .card {
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--card);
      padding: 18px;
    }
    .banner {
      border-color: rgba(143, 60, 22, 0.36);
      background: var(--warn-bg);
      color: var(--warn);
      font-weight: 700;
    }
    h1, h2, p { margin: 0 0 10px; }
    p { color: var(--muted); line-height: 1.5; }
    pre {
      margin: 8px 0 0;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #fff;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .state-ok {
      border-color: rgba(31, 111, 74, 0.26);
      background: var(--ok-bg);
      color: var(--ok);
      font-weight: 700;
    }
    a {
      color: #0d4f63;
      font-weight: 700;
      text-decoration: none;
    }
  </style>
</head>
<body>
  <nav class="surface-links" data-surface-nav="primary" aria-label="Complaint Generator Navigation" style="display:flex;flex-wrap:wrap;gap:12px;margin:16px auto 0;max-width:980px;padding:0 18px;">
    <a class="surface-link" href="/">Landing</a>
    <a class="surface-link" href="/home">Account</a>
    <a class="surface-link" href="/chat">Chat</a>
    <a class="surface-link" href="/profile">Profile</a>
    <a class="surface-link" href="/results">Results</a>
    <a class="surface-link" href="/workspace">Workspace</a>
    <a class="surface-link" href="/claim-support-review">Review</a>
    <a class="surface-link" href="/document">Builder</a>
    <a class="surface-link" href="/mlwysiwyg">Editor</a>
    <a class="surface-link" href="/document/optimization-trace">Trace</a>
    <a class="surface-link" href="/ipfs-datasets/sdk-playground" aria-current="page">SDK</a>
    <a class="surface-link" href="/dashboards">Dashboards</a>
  </nav>
  <main>
    <section class="card banner">
      SDK playground preview is unavailable. The server stayed online and returned this fallback page so other complaint routes continue to work.
    </section>
    <section class="card">
      <h1>Missing Submodule Asset</h1>
      <p>The SDK preview file was not found at runtime. This usually means the submodule or preview artifact was not initialized in this workspace.</p>
      <pre>${escapeXml(String(sdkState.path || sdkPreviewPath))}</pre>
    </section>
    <section class="card">
      <h2>Recommended Setup</h2>
      <pre>git submodule update --init --recursive
# then make sure SDK_PLAYGROUND_PREVIEW.html is generated in ipfs_datasets_py/ipfs_accelerate_py/</pre>
      <p>Diagnostics endpoint: <a href="/api/environment/preflight">/api/environment/preflight</a></p>
    </section>
    <section class="card state-ok">
      Other complaint surfaces remain available: /workspace, /chat, /profile, /results, /document, /claim-support-review.
    </section>
  </main>
  <script src="/static/complaint_mcp_sdk.js"></script>
  <script src="/static/complaint_app_shell.js"></script>
</body>
</html>`;
}

function renderRawDashboardFallback(entry) {
  const missingPath = ipfsTemplate(entry.templateName);
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeXml(entry.title)} Fallback Dashboard</title>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #f7f2e8; color: #1c1f24; }
    main { max-width: 960px; margin: 0 auto; padding: 32px 18px; }
    section { background: #fffdf8; border: 1px solid rgba(28, 31, 36, 0.14); border-radius: 16px; padding: 22px; box-shadow: 0 14px 30px rgba(28, 31, 36, 0.08); }
    h1 { margin: 0 0 10px; }
    p { line-height: 1.55; color: #505760; }
    code, pre { background: #fff; border: 1px solid rgba(28, 31, 36, 0.14); border-radius: 10px; }
    code { padding: 2px 6px; }
    pre { padding: 12px; overflow: auto; white-space: pre-wrap; word-break: break-word; }
  </style>
</head>
<body>
  <main>
    <section>
      <h1>${escapeXml(entry.title)}</h1>
      <p>${escapeXml(entry.summary)}</p>
      <p>This raw dashboard route is mounted, but the corresponding <code>ipfs_datasets_py</code> template asset is missing in this checkout. The Playwright server returns this fallback so the complaint-generator navigation remains testable while the submodule is unavailable.</p>
      <pre>${escapeXml(missingPath)}</pre>
      <p>Initialize the submodule assets to restore the full Dashboard, Admin, Investigation, News, Software, Analytics, GraphRAG, Patent, Discord, Finance, Medicine, Caselaw, or RAG experience.</p>
    </section>
  </main>
</body>
</html>`;
}

function handleDashboardFixtureRoute(
  request,
  response,
  url,
  fixtures = getDashboardFixtures(),
) {
  if (request.method !== 'GET') {
    return false;
  }

  if (url.pathname === '/mcp') {
    sendText(
      response,
      renderDashboardShell(getDefaultDashboardEntry(fixtures)),
      'text/html; charset=utf-8',
    );
    return true;
  }

  if (url.pathname === '/dashboards') {
    sendText(
      response,
      renderDashboardHub(url.searchParams, fixtures),
      'text/html; charset=utf-8',
    );
    return true;
  }

  if (url.pathname.startsWith('/dashboards/ipfs-datasets/')) {
    const slug = url.pathname.replace('/dashboards/ipfs-datasets/', '');
    const entry = getDashboardEntry(slug, fixtures);
    if (!entry) {
      response.writeHead(404);
      response.end('Not found');
      return true;
    }
    sendText(response, renderDashboardShell(entry), 'text/html; charset=utf-8');
    return true;
  }

  if (url.pathname.startsWith('/dashboards/raw/ipfs-datasets/')) {
    const slug = url.pathname.replace('/dashboards/raw/ipfs-datasets/', '');
    const entry = getDashboardEntry(slug, fixtures);
    if (!entry) {
      response.writeHead(404);
      response.end('Not found');
      return true;
    }
    const dashboardPath = ipfsTemplate(entry.templateName);
    if (!fs.existsSync(dashboardPath)) {
      sendText(response, renderRawDashboardFallback(entry), 'text/html; charset=utf-8');
      return true;
    }
    sendFile(response, dashboardPath);
    return true;
  }

  return false;
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

async function handlePlaywrightRequest(
  request,
  response,
  dashboardFixtures = getDashboardFixtures(),
) {
  const url = new URL(request.url, `http://localhost:${port}`);

  if (request.method === 'GET' && url.pathname === '/health') {
    return sendJson(response, {
      status: 'healthy',
      preflight: buildEnvironmentPreflight(),
    });
  }

  if (request.method === 'GET' && url.pathname === '/api/environment/preflight') {
    return sendJson(response, buildEnvironmentPreflight());
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
      data: JSON.stringify(sanitizeProfileDataForClient(profileData)),
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
        { name: 'complaint.import_gmail_evidence', description: 'Import matching Gmail messages and attachments into the complaint evidence workspace.', inputSchema: { type: 'object' } },
        { name: 'complaint.review_case', description: 'Return the support matrix and evidence review.', inputSchema: { type: 'object' } },
        { name: 'complaint.build_mediator_prompt', description: 'Build a testimony-ready chat mediator prompt from the shared case synopsis and support gaps.', inputSchema: { type: 'object' } },
        { name: 'complaint.get_complaint_readiness', description: 'Estimate whether the current complaint record is ready for drafting, still building, or already in draft refinement.', inputSchema: { type: 'object' } },
        { name: 'complaint.get_ui_readiness', description: 'Return the latest cached actor/critic UI readiness verdict for this complaint session.', inputSchema: { type: 'object' } },
        { name: 'complaint.get_client_release_gate', description: 'Combine complaint readiness, UI readiness, and complaint-output quality into one client-safety release gate.', inputSchema: { type: 'object' } },
        { name: 'complaint.get_workflow_capabilities', description: 'Summarize which complaint-workflow abilities are currently available for the session.', inputSchema: { type: 'object' } },
        { name: 'complaint.get_tooling_contract', description: 'Show how the core complaint workflow is exposed across package exports, CLI commands, MCP tools, and browser SDK methods.', inputSchema: { type: 'object' } },
        { name: 'complaint.generate_complaint', description: 'Generate a complaint draft from intake and evidence.', inputSchema: { type: 'object' } },
        { name: 'complaint.update_draft', description: 'Persist edits to the complaint draft.', inputSchema: { type: 'object' } },
        { name: 'complaint.export_complaint_packet', description: 'Export the current lawsuit complaint packet with intake, evidence, review, and draft content.', inputSchema: { type: 'object' } },
        { name: 'complaint.export_complaint_markdown', description: 'Export the generated complaint as a downloadable Markdown artifact.', inputSchema: { type: 'object' } },
        { name: 'complaint.export_complaint_docx', description: 'Export the generated complaint as a downloadable DOCX artifact.', inputSchema: { type: 'object' } },
        { name: 'complaint.export_complaint_pdf', description: 'Export the generated complaint as a downloadable PDF artifact.', inputSchema: { type: 'object' } },
        { name: 'complaint.analyze_complaint_output', description: 'Analyze the generated complaint output and turn filing-shape gaps into concrete UI/UX suggestions.', inputSchema: { type: 'object' } },
        { name: 'complaint.get_formal_diagnostics', description: 'Return the compact formal-complaint diagnostics summary for the current complaint draft and export state.', inputSchema: { type: 'object' } },
        { name: 'complaint.get_filing_provenance', description: 'Return the shared routing provenance for complaint generation, filing critique, export critique, and cached UI review workflows.', inputSchema: { type: 'object' } },
        { name: 'complaint.get_provider_diagnostics', description: 'Report which llm_router providers are actually usable on this machine, in the same order the router will prefer them.', inputSchema: { type: 'object' } },
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
            { name: 'complaint.import_gmail_evidence', description: 'Import matching Gmail messages and attachments into the complaint evidence workspace.', inputSchema: { type: 'object' } },
            { name: 'complaint.review_case', description: 'Return the support matrix and evidence review.', inputSchema: { type: 'object' } },
            { name: 'complaint.build_mediator_prompt', description: 'Build a testimony-ready chat mediator prompt from the shared case synopsis and support gaps.', inputSchema: { type: 'object' } },
            { name: 'complaint.get_complaint_readiness', description: 'Estimate whether the current complaint record is ready for drafting, still building, or already in draft refinement.', inputSchema: { type: 'object' } },
            { name: 'complaint.get_ui_readiness', description: 'Return the latest cached actor/critic UI readiness verdict for this complaint session.', inputSchema: { type: 'object' } },
            { name: 'complaint.get_client_release_gate', description: 'Combine complaint readiness, UI readiness, and complaint-output quality into one client-safety release gate.', inputSchema: { type: 'object' } },
            { name: 'complaint.get_workflow_capabilities', description: 'Summarize which complaint-workflow abilities are currently available for the session.', inputSchema: { type: 'object' } },
            { name: 'complaint.get_tooling_contract', description: 'Show how the core complaint workflow is exposed across package exports, CLI commands, MCP tools, and browser SDK methods.', inputSchema: { type: 'object' } },
            { name: 'complaint.generate_complaint', description: 'Generate a complaint draft from intake and evidence.', inputSchema: { type: 'object' } },
            { name: 'complaint.update_draft', description: 'Persist edits to the complaint draft.', inputSchema: { type: 'object' } },
            { name: 'complaint.export_complaint_packet', description: 'Export the current lawsuit complaint packet with intake, evidence, review, and draft content.', inputSchema: { type: 'object' } },
            { name: 'complaint.export_complaint_markdown', description: 'Export the generated complaint as a downloadable Markdown artifact.', inputSchema: { type: 'object' } },
            { name: 'complaint.export_complaint_docx', description: 'Export the generated complaint as a downloadable DOCX artifact.', inputSchema: { type: 'object' } },
            { name: 'complaint.export_complaint_pdf', description: 'Export the generated complaint as a downloadable PDF artifact.', inputSchema: { type: 'object' } },
            { name: 'complaint.analyze_complaint_output', description: 'Analyze the generated complaint output and turn filing-shape gaps into concrete UI/UX suggestions.', inputSchema: { type: 'object' } },
            { name: 'complaint.get_formal_diagnostics', description: 'Return the compact formal-complaint diagnostics summary for the current complaint draft and export state.', inputSchema: { type: 'object' } },
            { name: 'complaint.get_filing_provenance', description: 'Return the shared routing provenance for complaint generation, filing critique, export critique, and cached UI review workflows.', inputSchema: { type: 'object' } },
            { name: 'complaint.get_provider_diagnostics', description: 'Report which llm_router providers are actually usable on this machine, in the same order the router will prefer them.', inputSchema: { type: 'object' } },
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
      } else if (toolName === 'complaint.import_gmail_evidence') {
        const addresses = Array.isArray(args.addresses) ? args.addresses.filter(Boolean) : [];
        const importedRecords = addresses.map((address, index) => {
          const record = {
            id: `document-${workspaceState.evidence.documents.length + 1}`,
            kind: 'document',
            claim_element_id: args.claim_element_id || 'causation',
            title: `Imported Gmail message ${index + 1}`,
            content: `Imported evidence matched from ${String(address)}.`,
            source: `gmail:${String(address)}`,
            attachment_names: [`message-${index + 1}.eml`],
          };
          workspaceState.evidence.documents.push(record);
          return record;
        });
        structuredContent = {
          user_id: userId,
          imported_count: importedRecords.length,
          imported_records: importedRecords,
          review: workspaceReview(workspaceState),
          session: JSON.parse(JSON.stringify(workspaceState)),
          case_synopsis: String(workspaceState.case_synopsis || '').trim(),
        };
      } else if (toolName === 'complaint.review_case' || toolName === 'complaint.start_session') {
        structuredContent = workspaceSessionPayload(userId);
      } else if (toolName === 'complaint.build_mediator_prompt') {
        structuredContent = buildMediatorPromptPayload(userId);
      } else if (toolName === 'complaint.get_complaint_readiness') {
        structuredContent = complaintReadinessPayload(userId);
      } else if (toolName === 'complaint.get_ui_readiness') {
        structuredContent = uiReadinessPayload(userId);
      } else if (toolName === 'complaint.get_client_release_gate') {
        structuredContent = clientReleaseGatePayload(userId);
      } else if (toolName === 'complaint.get_workflow_capabilities') {
        structuredContent = workflowCapabilitiesPayload(userId);
      } else if (toolName === 'complaint.get_tooling_contract') {
        structuredContent = toolingContractPayload(userId);
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
      } else if (toolName === 'complaint.export_complaint_docx') {
        const packetPayload = exportComplaintPacketPayload(userId);
        structuredContent = {
          artifact: {
            format: 'docx',
            filename: packetPayload.artifacts.docx.filename,
            media_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
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
      } else if (toolName === 'complaint.get_formal_diagnostics') {
        structuredContent = formalDiagnosticsPayload(userId);
      } else if (toolName === 'complaint.get_filing_provenance') {
        structuredContent = filingProvenancePayload(userId);
      } else if (toolName === 'complaint.get_provider_diagnostics') {
        structuredContent = providerDiagnosticsPayload(userId);
      } else if (toolName === 'complaint.review_generated_exports') {
        const analysis = buildComplaintOutputAnalysis(userId);
        const formalSectionGaps = Object.entries(analysis.ui_feedback.formal_sections_present || {})
          .filter(([, present]) => !present)
          .map(([name]) => name);
        structuredContent = {
          artifact_count: 1,
          complaint_output_feedback: {
            export_artifact_count: 1,
            claim_types: [workspaceState.claim_type || 'retaliation'],
            draft_strategies: [workspaceState.draft && workspaceState.draft.draft_strategy ? workspaceState.draft.draft_strategy : 'template'],
            filing_shape_scores: [analysis.ui_feedback.filing_shape_score || 0],
            release_gate_verdicts: [((analysis.ui_feedback.release_gate || {}).verdict || 'warning')],
            formal_section_gaps: formalSectionGaps,
            ui_suggestions: (analysis.ui_feedback.ui_suggestions || []).map((item) => item.title || item.recommendation).filter(Boolean),
            router_backends: [Object.assign({}, (((analysis.ui_feedback || {}).router_review || {}).backend || {}))].filter((item) => Object.keys(item).length),
          },
          aggregate: {
            average_filing_shape_score: analysis.ui_feedback.filing_shape_score || 0,
            average_claim_type_alignment_score: analysis.ui_feedback.claim_type_alignment_score || 0,
            issue_findings: (analysis.ui_feedback.issues || []).map((item) => item.finding).filter(Boolean),
            missing_formal_sections: formalSectionGaps,
            ui_suggestions: analysis.ui_feedback.ui_suggestions || [],
            router_backends: [Object.assign({}, (((analysis.ui_feedback || {}).router_review || {}).backend || {}))].filter((item) => Object.keys(item).length),
            ui_priority_repairs: [
              {
                priority: 'high',
                target_surface: 'draft,review,integrations',
                repair: 'Keep filing-shape warnings and export blockers visible until the complaint looks like a formal pleading.',
                filing_benefit: 'The actor sees exactly which UI surfaces to revisit before trusting the export.',
              },
            ],
            actor_risk_summaries: [
              'The actor can generate and download a complaint before understanding which filing-shape gaps or support warnings still need attention.',
            ],
            critic_gates: [
              {
                verdict: ((analysis.ui_feedback.release_gate || {}).verdict || 'warning'),
                blocking_reason: ((analysis.ui_feedback.release_gate || {}).reason || 'Formal complaint posture still needs visible validation.'),
              },
            ],
            optimizer_repair_brief: {
              top_formal_section_gaps: formalSectionGaps.slice(0, 6),
              top_issue_findings: (analysis.ui_feedback.issues || []).map((item) => item.finding).filter(Boolean).slice(0, 6),
              recommended_surface_targets: ['draft,review,integrations'],
              actor_risk_summary: 'The actor can export a complaint without clear UI guidance about whether the filing is truly ready.',
              critic_gate_verdict: ((analysis.ui_feedback.release_gate || {}).verdict || 'warning'),
              router_path_summary: 'llm_router / formal_complaint_reviewer',
            },
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
                missing_formal_sections: formalSectionGaps,
                issues: analysis.ui_feedback.issues || [],
                ui_suggestions: analysis.ui_feedback.ui_suggestions || [],
                ui_priority_repairs: [
                  {
                    priority: 'high',
                    target_surface: 'draft,review,integrations',
                    repair: 'Keep filing-shape warnings and export blockers visible until the complaint reads like a formal pleading.',
                    filing_benefit: 'Helps the exported complaint preserve formal structure and clear gatekeeping.',
                  },
                ],
                actor_risk_summary: 'The actor needs clearer filing-readiness signals before relying on the exported complaint.',
                critic_gate: {
                  verdict: ((analysis.ui_feedback.release_gate || {}).verdict || 'warning'),
                  blocking_reason: ((analysis.ui_feedback.release_gate || {}).reason || 'Formal complaint posture still needs visible validation.'),
                  required_repairs: ['Keep filing-shape guidance visible in the draft and export surfaces.'],
                },
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
    if (toolName === 'complaint.import_gmail_evidence') {
      const addresses = Array.isArray(args.addresses) ? args.addresses.filter(Boolean) : [];
      const importedRecords = addresses.map((address, index) => {
        const record = {
          id: `document-${workspaceState.evidence.documents.length + 1}`,
          kind: 'document',
          claim_element_id: args.claim_element_id || 'causation',
          title: `Imported Gmail message ${index + 1}`,
          content: `Imported evidence matched from ${String(address)}.`,
          source: `gmail:${String(address)}`,
          attachment_names: [`message-${index + 1}.eml`],
        };
        workspaceState.evidence.documents.push(record);
        return record;
      });
      return sendJson(response, {
        user_id: userId,
        imported_count: importedRecords.length,
        imported_records: importedRecords,
        review: workspaceReview(workspaceState),
        session: JSON.parse(JSON.stringify(workspaceState)),
        case_synopsis: String(workspaceState.case_synopsis || '').trim(),
      });
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
    if (toolName === 'complaint.get_client_release_gate') {
      return sendJson(response, clientReleaseGatePayload(userId));
    }
    if (toolName === 'complaint.get_workflow_capabilities') {
      return sendJson(response, workflowCapabilitiesPayload(userId));
    }
    if (toolName === 'complaint.get_tooling_contract') {
      return sendJson(response, toolingContractPayload(userId));
    }
    if (toolName === 'complaint.get_formal_diagnostics') {
      return sendJson(response, formalDiagnosticsPayload(userId));
    }
    if (toolName === 'complaint.get_filing_provenance') {
      return sendJson(response, filingProvenancePayload(userId));
    }
    if (toolName === 'complaint.get_provider_diagnostics') {
      return sendJson(response, providerDiagnosticsPayload(userId));
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
      const formalSectionGaps = Object.entries(analysis.ui_feedback.formal_sections_present || {})
        .filter(([, present]) => !present)
        .map(([name]) => name);
      return sendJson(response, {
        artifact_count: 1,
        complaint_output_feedback: {
          export_artifact_count: 1,
          claim_types: [workspaceState.claim_type || 'retaliation'],
          draft_strategies: [workspaceState.draft && workspaceState.draft.draft_strategy ? workspaceState.draft.draft_strategy : 'template'],
          filing_shape_scores: [analysis.ui_feedback.filing_shape_score || 0],
          release_gate_verdicts: [((analysis.ui_feedback.release_gate || {}).verdict || 'warning')],
          formal_section_gaps: formalSectionGaps,
          ui_suggestions: (analysis.ui_feedback.ui_suggestions || []).map((item) => item.title || item.recommendation).filter(Boolean),
          router_backends: [Object.assign({}, (((analysis.ui_feedback || {}).router_review || {}).backend || {}))].filter((item) => Object.keys(item).length),
        },
        aggregate: {
          average_filing_shape_score: analysis.ui_feedback.filing_shape_score || 0,
          average_claim_type_alignment_score: analysis.ui_feedback.claim_type_alignment_score || 0,
          issue_findings: (analysis.ui_feedback.issues || []).map((item) => item.finding).filter(Boolean),
          missing_formal_sections: formalSectionGaps,
          ui_suggestions: analysis.ui_feedback.ui_suggestions || [],
          router_backends: [Object.assign({}, (((analysis.ui_feedback || {}).router_review || {}).backend || {}))].filter((item) => Object.keys(item).length),
          ui_priority_repairs: [
            {
              priority: 'high',
              target_surface: 'draft,review,integrations',
              repair: 'Keep filing-shape warnings and export blockers visible until the complaint looks like a formal pleading.',
              filing_benefit: 'The actor sees exactly which UI surfaces to revisit before trusting the export.',
            },
          ],
          actor_risk_summaries: [
            'The actor can generate and download a complaint before understanding which filing-shape gaps or support warnings still need attention.',
          ],
          critic_gates: [
            {
              verdict: ((analysis.ui_feedback.release_gate || {}).verdict || 'warning'),
              blocking_reason: ((analysis.ui_feedback.release_gate || {}).reason || 'Formal complaint posture still needs visible validation.'),
            },
          ],
          optimizer_repair_brief: {
            top_formal_section_gaps: formalSectionGaps.slice(0, 6),
            top_issue_findings: (analysis.ui_feedback.issues || []).map((item) => item.finding).filter(Boolean).slice(0, 6),
            recommended_surface_targets: ['draft,review,integrations'],
            actor_risk_summary: 'The actor can export a complaint without clear UI guidance about whether the filing is truly ready.',
            critic_gate_verdict: ((analysis.ui_feedback.release_gate || {}).verdict || 'warning'),
            router_path_summary: 'llm_router / formal_complaint_reviewer',
          },
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
              missing_formal_sections: formalSectionGaps,
              issues: analysis.ui_feedback.issues || [],
              ui_suggestions: analysis.ui_feedback.ui_suggestions || [],
              ui_priority_repairs: [
                {
                  priority: 'high',
                  target_surface: 'draft,review,integrations',
                  repair: 'Keep filing-shape warnings and export blockers visible until the complaint reads like a formal pleading.',
                  filing_benefit: 'Helps the exported complaint preserve formal structure and clear gatekeeping.',
                },
              ],
              actor_risk_summary: 'The actor needs clearer filing-readiness signals before relying on the exported complaint.',
              critic_gate: {
                verdict: ((analysis.ui_feedback.release_gate || {}).verdict || 'warning'),
                blocking_reason: ((analysis.ui_feedback.release_gate || {}).reason || 'Formal complaint posture still needs visible validation.'),
                required_repairs: ['Keep filing-shape guidance visible in the draft and export surfaces.'],
              },
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
    return sendText(response, renderSdkPlaygroundShell(), 'text/html; charset=utf-8');
  }

  if (handleDashboardFixtureRoute(request, response, url, dashboardFixtures)) {
    return;
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
}

function createPlaywrightServer({ dashboardFixtures = getDashboardFixtures() } = {}) {
  return http.createServer((request, response) => (
    handlePlaywrightRequest(request, response, dashboardFixtures)
  ));
}

if (require.main === module) {
  createPlaywrightServer().listen(port, '127.0.0.1');
}

module.exports = {
  buildDashboardEntriesFixture,
  buildLaypersonDashboardCardsFixture,
  buildDashboardUtilityCardsFixture,
  buildDashboardSubsectionCardsFixture,
  buildDashboardFixtures,
  getDashboardFixtures,
  getDashboardEntry,
  getDefaultDashboardEntry,
  renderDashboardHub,
  handleDashboardFixtureRoute,
  handlePlaywrightRequest,
  createPlaywrightServer,
};
