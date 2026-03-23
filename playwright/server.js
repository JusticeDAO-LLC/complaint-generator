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

function workflowCapabilitiesPayload(userId = 'did:key:playwright-demo') {
  const sessionPayload = workspaceSessionPayload(userId);
  const overview = ((sessionPayload.review || {}).overview) || {};
  const questions = sessionPayload.questions || [];
  const answeredCount = questions.filter((item) => item.is_answered).length;
  return {
    user_id: userId,
    case_synopsis: String(sessionPayload.case_synopsis || '').trim(),
    overview,
    complaint_readiness: complaintReadinessPayload(userId),
    capabilities: [
      { id: 'intake_questions', label: 'Complaint intake questions', available: questions.length > 0, detail: `${answeredCount} of ${questions.length} intake questions answered.` },
      { id: 'mediator_prompt', label: 'Chat mediator handoff', available: true, detail: 'A testimony-ready mediator prompt can be generated from the shared case synopsis and support gaps.' },
      { id: 'evidence_capture', label: 'Evidence capture', available: true, detail: `${(overview.testimony_items || 0) + (overview.document_items || 0)} evidence items saved.` },
      { id: 'support_review', label: 'Claim support review', available: true, detail: `${overview.supported_elements || 0} supported elements, ${overview.missing_elements || 0} gaps remaining.` },
      { id: 'complaint_draft', label: 'Complaint draft', available: true, detail: sessionPayload.draft ? 'A draft already exists and can be edited.' : 'A draft can be generated from the current complaint record.' },
      { id: 'complaint_packet', label: 'Complaint packet export', available: true, detail: 'The lawsuit packet can be exported as a structured browser, CLI, or MCP artifact.' },
    ],
  };
}

function exportComplaintPacketPayload(userId = 'did:key:playwright-demo') {
  const sessionPayload = workspaceSessionPayload(userId);
  const draft = sessionPayload.draft || getWorkspaceState(userId).draft || { title: 'Draft not generated', requested_relief: [], body: '' };
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
    packet_summary: {
      question_count: sessionPayload.questions.length,
      answered_question_count: sessionPayload.questions.filter((item) => item.is_answered).length,
      supported_elements: sessionPayload.review.overview.supported_elements || 0,
      missing_elements: sessionPayload.review.overview.missing_elements || 0,
      testimony_items: sessionPayload.review.overview.testimony_items || 0,
      document_items: sessionPayload.review.overview.document_items || 0,
      has_draft: Boolean(sessionPayload.draft),
      complaint_readiness: complaintReadinessPayload(userId),
    },
  };
}

function generateWorkspaceDraft(workspaceState, requestedRelief) {
  const answers = workspaceState.intake_answers;
  const relief = requestedRelief && requestedRelief.length ? requestedRelief : ['Back pay', 'Injunctive relief'];
  const caseSynopsis = String(workspaceState.case_synopsis || '').trim();
  const body = [
    `${answers.party_name || 'Plaintiff'} brings this retaliation complaint against ${answers.opposing_party || 'Defendant'}.`,
    `${answers.party_name || 'Plaintiff'} alleges that they ${answers.protected_activity || 'engaged in protected activity'}.`,
    `After that protected activity, ${answers.party_name || 'Plaintiff'} experienced ${answers.adverse_action || 'adverse action'}.`,
    `The timeline shows that ${answers.timeline || 'the events occurred close in time'}.`,
    `As a result, ${answers.party_name || 'Plaintiff'} suffered ${answers.harm || 'compensable harm'}.`,
    `Requested relief includes: ${relief.join('; ')}.`,
    caseSynopsis ? `Working case synopsis: ${caseSynopsis}.` : '',
  ].join('\n\n');
  workspaceState.draft = {
    title: `${answers.party_name || 'Plaintiff'} v. ${answers.opposing_party || 'Defendant'} Retaliation Complaint`,
    requested_relief: relief,
    body,
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
        { name: 'complaint.get_workflow_capabilities', description: 'Summarize which complaint-workflow abilities are currently available for the session.', inputSchema: { type: 'object' } },
        { name: 'complaint.generate_complaint', description: 'Generate a complaint draft from intake and evidence.', inputSchema: { type: 'object' } },
        { name: 'complaint.update_draft', description: 'Persist edits to the complaint draft.', inputSchema: { type: 'object' } },
        { name: 'complaint.export_complaint_packet', description: 'Export the current lawsuit complaint packet with intake, evidence, review, and draft content.', inputSchema: { type: 'object' } },
        { name: 'complaint.update_case_synopsis', description: 'Persist a shared case synopsis that stays visible across workspace, CLI, and MCP flows.', inputSchema: { type: 'object' } },
        { name: 'complaint.reset_session', description: 'Clear the complaint workspace session.', inputSchema: { type: 'object' } },
        { name: 'complaint.review_ui', description: 'Review Playwright screenshot artifacts and produce a UI critique.', inputSchema: { type: 'object' } },
        { name: 'complaint.optimize_ui', description: 'Run the closed-loop screenshot, llm_router, optimizer, and revalidation workflow for the complaint dashboard UI.', inputSchema: { type: 'object' } },
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
            { name: 'complaint.get_workflow_capabilities', description: 'Summarize which complaint-workflow abilities are currently available for the session.', inputSchema: { type: 'object' } },
            { name: 'complaint.generate_complaint', description: 'Generate a complaint draft from intake and evidence.', inputSchema: { type: 'object' } },
            { name: 'complaint.update_draft', description: 'Persist edits to the complaint draft.', inputSchema: { type: 'object' } },
            { name: 'complaint.export_complaint_packet', description: 'Export the current lawsuit complaint packet with intake, evidence, review, and draft content.', inputSchema: { type: 'object' } },
            { name: 'complaint.update_case_synopsis', description: 'Persist a shared case synopsis that stays visible across workspace, CLI, and MCP flows.', inputSchema: { type: 'object' } },
            { name: 'complaint.reset_session', description: 'Clear the complaint workspace session.', inputSchema: { type: 'object' } },
            { name: 'complaint.review_ui', description: 'Review Playwright screenshot artifacts and produce a UI critique.', inputSchema: { type: 'object' } },
            { name: 'complaint.optimize_ui', description: 'Run the closed-loop screenshot, llm_router, optimizer, and revalidation workflow for the complaint dashboard UI.', inputSchema: { type: 'object' } },
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
      } else if (toolName === 'complaint.get_workflow_capabilities') {
        structuredContent = workflowCapabilitiesPayload(userId);
      } else if (toolName === 'complaint.generate_complaint') {
        generateWorkspaceDraft(workspaceState, args.requested_relief || []);
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
        structuredContent = exportComplaintPacketPayload(userId);
      } else if (toolName === 'complaint.reset_session') {
        workspaceSessions.set(userId, createWorkspaceState(userId));
        structuredContent = workspaceSessionPayload(userId);
      } else if (toolName === 'complaint.review_ui') {
        if ((Number(args.iterations || 0)) > 0) {
          structuredContent = {
            iterations: Number(args.iterations || 0),
            screenshot_dir: args.screenshot_dir || 'artifacts/ui-audit/screenshots',
            output_dir: args.output_path || 'artifacts/ui-audit/reviews',
            latest_review: '# Top Risks\n- Evidence capture guidance is still too easy to miss for first-time complainants.\n\n# High-Impact UX Fixes\n- Keep the intake, evidence, review, and draft journey visible above the fold.\n- Surface the MCP SDK contract directly inside the workspace so operators understand the shared workflow.\n\n# Stage Findings\n## Intake\nMarkdown fallback should not replace the structured intake guidance.\n\n## Evidence\nMarkdown fallback should not replace the structured evidence guidance.',
            stage_findings: {
              Intake: 'First-time complainants need clearer reassurance that incomplete dates and imperfect wording can still be saved.',
              Evidence: 'The evidence step should explain which documents help prove causation before users are asked to upload or summarize proof.',
              Review: 'Support-gap guidance should tell the operator what missing element to close next instead of only showing counts.',
              Draft: 'Draft generation should feel like the direct continuation of the case theory, not a separate document tool.',
              'Integration Discovery': 'The MCP SDK and optimizer path need to stay visible so operators do not miss the shared complaint-generator tooling.',
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
                review_excerpt: 'Evidence capture guidance is still too easy to miss for first-time complainants.',
                review_markdown_path: 'artifacts/ui-audit/reviews/iteration-01-review.md',
                review_json_path: 'artifacts/ui-audit/reviews/iteration-01-review.json',
              },
            ],
          };
        } else {
          structuredContent = {
            generated_at: '2026-03-23T00:00:00+00:00',
            backend: { strategy: 'playwright-stub' },
            screenshots: [],
            review: {
              summary: 'Stub UI review completed.',
              stage_findings: {
                Intake: 'The intake flow should make the first required story fields easier to understand before asking for detail.',
                Evidence: 'Users need clearer cues about what evidence strengthens the current complaint theory.',
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
      } else if (toolName === 'complaint.optimize_ui') {
        structuredContent = {
          workflow_type: 'ui_ux_closed_loop',
          max_rounds: Number(args.max_rounds || 2),
          rounds_executed: 1,
          stop_reason: 'validation_review_stable',
          latest_validation_review: '# Top Risks\n- Keep the intake flow calmer and more linear.\n\n# Stage Findings\n## Integration Discovery\nMarkdown fallback should not replace the structured integration-discovery guidance.',
          stage_findings: {
            Intake: 'The optimizer should reduce branching language and keep the first story steps calmer and more linear.',
            Evidence: 'The evidence panel still needs stronger claim-element guidance after optimization.',
            Review: 'The review panel should turn missing support counts into next-step instructions.',
            Draft: 'Draft readiness should remain visible after optimization so users know when a first draft is appropriate.',
            'Integration Discovery': 'The optimizer path itself should stay discoverable from the shared dashboard shortcuts and tool panels.',
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
                latest_review: '# Top Risks\n- Keep the intake flow calmer and more linear.',
              },
            },
          ],
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
    if (toolName === 'complaint.get_workflow_capabilities') {
      return sendJson(response, workflowCapabilitiesPayload(userId));
    }
    if (toolName === 'complaint.generate_complaint') {
      generateWorkspaceDraft(workspaceState, args.requested_relief || []);
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
      return sendJson(response, exportComplaintPacketPayload(userId));
    }
    if (toolName === 'complaint.reset_session') {
      workspaceSessions.set(userId, createWorkspaceState(userId));
      return sendJson(response, workspaceSessionPayload(userId));
    }
    if (toolName === 'complaint.review_ui') {
      if ((Number(args.iterations || 0)) > 0) {
        return sendJson(response, {
          iterations: Number(args.iterations || 0),
          screenshot_dir: args.screenshot_dir || 'artifacts/ui-audit/screenshots',
          output_dir: args.output_path || 'artifacts/ui-audit/reviews',
          latest_review: '# Top Risks\n- Evidence capture guidance is still too easy to miss for first-time complainants.\n\n# High-Impact UX Fixes\n- Keep the intake, evidence, review, and draft journey visible above the fold.\n- Surface the MCP SDK contract directly inside the workspace so operators understand the shared workflow.',
          stage_findings: {
            Intake: 'First-time complainants need clearer reassurance that incomplete dates and imperfect wording can still be saved.',
            Evidence: 'The evidence step should explain which documents help prove causation before users are asked to upload or summarize proof.',
            Review: 'Support-gap guidance should tell the operator what missing element to close next instead of only showing counts.',
            Draft: 'Draft generation should feel like the direct continuation of the case theory, not a separate document tool.',
            'Integration Discovery': 'The MCP SDK and optimizer path need to stay visible so operators do not miss the shared complaint-generator tooling.',
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
              review_excerpt: 'Evidence capture guidance is still too easy to miss for first-time complainants.',
              review_markdown_path: 'artifacts/ui-audit/reviews/iteration-01-review.md',
              review_json_path: 'artifacts/ui-audit/reviews/iteration-01-review.json',
            },
          ],
        });
      }
      return sendJson(response, {
        generated_at: '2026-03-23T00:00:00+00:00',
        backend: { strategy: 'playwright-stub' },
        screenshots: [],
        review: {
          summary: 'Stub UI review completed.',
          stage_findings: {
            Intake: 'The intake flow should make the first required story fields easier to understand before asking for detail.',
            Evidence: 'Users need clearer cues about what evidence strengthens the current complaint theory.',
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
      });
    }
    if (toolName === 'complaint.optimize_ui') {
      return sendJson(response, {
        workflow_type: 'ui_ux_closed_loop',
        max_rounds: Number(args.max_rounds || 2),
        rounds_executed: 1,
        stop_reason: 'validation_review_stable',
        latest_validation_review: '# Top Risks\n- Keep the intake flow calmer and more linear.',
        stage_findings: {
          Intake: 'The optimizer should reduce branching language and keep the first story steps calmer and more linear.',
          Evidence: 'The evidence panel still needs stronger claim-element guidance after optimization.',
          Review: 'The review panel should turn missing support counts into next-step instructions.',
          Draft: 'Draft readiness should remain visible after optimization so users know when a first draft is appropriate.',
          'Integration Discovery': 'The optimizer path itself should stay discoverable from the shared dashboard shortcuts and tool panels.',
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
              latest_review: '# Top Risks\n- Keep the intake flow calmer and more linear.',
            },
          },
        ],
      });
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
