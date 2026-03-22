const fs = require('fs');
const http = require('http');
const path = require('path');
const { URL } = require('url');

const root = path.resolve(__dirname, '..');
const templatesDir = path.join(root, 'templates');
const staticDir = path.join(root, 'static');
const port = 19000;

const sampleProfile = {
  complaint_summary: {
    claim_type: 'retaliation',
    claim_summary: 'Retaliation after reporting discrimination.',
  },
  chat_history: {
    '2026-03-21T10:00:00Z': {
      sender: 'System:',
      message: 'Please describe the retaliation you experienced.',
      explanation: {
        summary: 'The complaint generator uses this to draft the factual allegations.',
      },
    },
    '2026-03-21T10:01:00Z': {
      sender: 'demo-user',
      message: 'I reported discrimination and was fired two days later.',
    },
  },
  data: {
    claim_type: 'retaliation',
    facts: [
      'Jane Doe reported discrimination to HR.',
      'Acme terminated Jane Doe shortly afterward.',
    ],
  },
};

const cookiePayload = {
  hashed_username: 'demo-user',
  hashed_password: 'demo-password',
  token: 'demo-token',
};

function send(res, status, contentType, body) {
  res.writeHead(status, { 'Content-Type': contentType });
  res.end(body);
}

function sendJson(res, status, payload) {
  send(res, status, 'application/json', JSON.stringify(payload));
}

function sendHtmlFile(res, fileName) {
  const fullPath = path.join(templatesDir, fileName);
  send(res, 200, 'text/html; charset=utf-8', fs.readFileSync(fullPath, 'utf8'));
}

function sendStaticFile(res, pathname) {
  const fullPath = path.join(root, pathname);
  if (!fullPath.startsWith(staticDir) || !fs.existsSync(fullPath)) {
    send(res, 404, 'text/plain; charset=utf-8', 'Not Found');
    return;
  }

  const extension = path.extname(fullPath).toLowerCase();
  const contentTypes = {
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml',
  };
  send(res, 200, contentTypes[extension] || 'application/octet-stream', fs.readFileSync(fullPath));
}

function collectBody(req) {
  return new Promise((resolve) => {
    let data = '';
    req.on('data', (chunk) => {
      data += chunk;
    });
    req.on('end', () => {
      resolve(data);
    });
  });
}

const server = http.createServer(async (req, res) => {
  const parsed = new URL(req.url, `http://localhost:${port}`);
  const { pathname } = parsed;

  if (req.method === 'GET' && pathname === '/health') {
    return sendJson(res, 200, { status: 'ok' });
  }

  if (req.method === 'GET' && pathname === '/') {
    return sendHtmlFile(res, 'index.html');
  }

  if (req.method === 'GET' && pathname === '/home') {
    return sendHtmlFile(res, 'home.html');
  }

  if (req.method === 'GET' && pathname === '/chat') {
    return sendHtmlFile(res, 'chat.html');
  }

  if (req.method === 'GET' && pathname === '/profile') {
    return sendHtmlFile(res, 'profile.html');
  }

  if (req.method === 'GET' && pathname === '/results') {
    return sendHtmlFile(res, 'results.html');
  }

  if (req.method === 'GET' && pathname === '/document') {
    return sendHtmlFile(res, 'document.html');
  }

  if (req.method === 'GET' && pathname === '/document/optimization-trace') {
    return sendHtmlFile(res, 'optimization_trace.html');
  }

  if (req.method === 'GET' && pathname === '/claim-support-review') {
    return sendHtmlFile(res, 'claim_support_review.html');
  }

  if (req.method === 'GET' && pathname.startsWith('/static/')) {
    return sendStaticFile(res, pathname.slice(1));
  }

  if (req.method === 'GET' && pathname === '/cookies') {
    return send(res, 200, 'text/plain; charset=utf-8', JSON.stringify(cookiePayload));
  }

  if (req.method === 'POST' && pathname === '/load_profile') {
    await collectBody(req);
    return sendJson(res, 200, {
      results: {
        ...cookiePayload,
        data: JSON.stringify(sampleProfile),
      },
      data: JSON.stringify(sampleProfile),
    });
  }

  if (req.method === 'POST' && pathname === '/create_profile') {
    const rawBody = await collectBody(req);
    let parsedBody = {};
    try {
      parsedBody = JSON.parse(rawBody || '{}');
    } catch (error) {
      parsedBody = {};
    }
    const requestBody = parsedBody.request || {};
    return sendJson(res, 200, {
      hashed_username: requestBody.username || cookiePayload.hashed_username,
      hashed_password: cookiePayload.hashed_password,
    });
  }

  send(res, 404, 'text/plain; charset=utf-8', 'Not Found');
});

server.listen(port, '127.0.0.1', () => {
  process.stdout.write(`Playwright test server listening on http://localhost:${port}\n`);
});
