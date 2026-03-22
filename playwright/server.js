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
  ['/mlwysiwyg', template('MLWYSIWYG.html')],
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

  if (request.method === 'GET' && url.pathname === '/api/documents/optimization-trace') {
    return sendJson(response, { cid: url.searchParams.get('cid') || '', changes: [] });
  }

  if (request.method === 'GET' && url.pathname === '/ipfs-datasets/sdk-playground') {
    return sendFile(response, sdkPreviewPath);
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
