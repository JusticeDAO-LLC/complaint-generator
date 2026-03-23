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

function generateWorkspaceDraft(workspaceState, requestedRelief) {
  const answers = workspaceState.intake_answers;
  const relief = requestedRelief && requestedRelief.length ? requestedRelief : ['Back pay', 'Injunctive relief'];
  const body = [
    `${answers.party_name || 'Plaintiff'} brings this retaliation complaint against ${answers.opposing_party || 'Defendant'}.`,
    `${answers.party_name || 'Plaintiff'} alleges that they ${answers.protected_activity || 'engaged in protected activity'}.`,
    `After that protected activity, ${answers.party_name || 'Plaintiff'} experienced ${answers.adverse_action || 'adverse action'}.`,
    `The timeline shows that ${answers.timeline || 'the events occurred close in time'}.`,
    `As a result, ${answers.party_name || 'Plaintiff'} suffered ${answers.harm || 'compensable harm'}.`,
    `Requested relief includes: ${relief.join('; ')}.`,
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
        { name: 'complaint.start_session', description: 'Load or initialize a complaint workspace session.', inputSchema: { type: 'object' } },
        { name: 'complaint.submit_intake', description: 'Save complaint intake answers.', inputSchema: { type: 'object' } },
        { name: 'complaint.save_evidence', description: 'Save testimony or document evidence to the workspace.', inputSchema: { type: 'object' } },
        { name: 'complaint.review_case', description: 'Return the support matrix and evidence review.', inputSchema: { type: 'object' } },
        { name: 'complaint.generate_complaint', description: 'Generate a complaint draft from intake and evidence.', inputSchema: { type: 'object' } },
        { name: 'complaint.update_draft', description: 'Persist edits to the complaint draft.', inputSchema: { type: 'object' } },
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
            { name: 'complaint.start_session', description: 'Load or initialize a complaint workspace session.', inputSchema: { type: 'object' } },
            { name: 'complaint.submit_intake', description: 'Save complaint intake answers.', inputSchema: { type: 'object' } },
            { name: 'complaint.save_evidence', description: 'Save testimony or document evidence to the workspace.', inputSchema: { type: 'object' } },
            { name: 'complaint.review_case', description: 'Return the support matrix and evidence review.', inputSchema: { type: 'object' } },
            { name: 'complaint.generate_complaint', description: 'Generate a complaint draft from intake and evidence.', inputSchema: { type: 'object' } },
            { name: 'complaint.update_draft', description: 'Persist edits to the complaint draft.', inputSchema: { type: 'object' } },
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
        });
        structuredContent = workspaceSessionPayload(userId);
      } else if (toolName === 'complaint.review_case' || toolName === 'complaint.start_session') {
        structuredContent = workspaceSessionPayload(userId);
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
      });
      return sendJson(response, workspaceSessionPayload(userId));
    }
    if (toolName === 'complaint.review_case' || toolName === 'complaint.start_session') {
      return sendJson(response, workspaceSessionPayload(userId));
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
