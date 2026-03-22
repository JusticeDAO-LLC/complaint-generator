const http = require('http');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

const root = path.resolve(__dirname, '..');
const templatesDir = path.join(root, 'templates');
const staticDir = path.join(root, 'static');
const sdkPreviewPath = path.join(root, 'ipfs_datasets_py', 'ipfs_accelerate_py', 'SDK_PLAYGROUND_PREVIEW.html');
const port = 19000;

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

  if (request.method === 'GET' && url.pathname.startsWith('/static/')) {
    return sendFile(response, path.join(staticDir, url.pathname.replace('/static/', '')));
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
