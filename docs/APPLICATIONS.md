# Applications Guide

This document describes the user-facing applications in the Complaint Generator system, including the command-line interface (CLI) and web server.

The review operator surface also has dedicated app factories for non-legacy deployments:

- `applications.create_review_api_app(mediator)` mounts only the claim-support review and follow-up execution API routes.
- `applications.create_review_dashboard_app()` mounts only the `/claim-support-review` HTML dashboard.
- `applications.create_review_surface_app(mediator)` mounts both the dashboard UI and the review/follow-up API routes on one FastAPI app.

The repository also includes `config.review_surface.json` for launching the combined review surface through `run.py`.

## Overview

The Complaint Generator provides two primary application interfaces and dedicated review-surface variants:

1. **CLI Application** - Interactive command-line interface for legal complaint generation
2. **Web Server** - FastAPI-based web application with REST API and WebSocket support
3. **Review Surface Apps** - Focused FastAPI apps for the claim-support dashboard and review APIs

All application variants use the same underlying mediator and processing pipeline, providing consistent functionality across interfaces.

## CLI Application

### Features

The CLI application (`applications/cli.py`) provides an interactive terminal interface for:

- **User Authentication** - Username/password login with profile persistence
- **Interactive Dialogue** - Natural conversation for complaint intake
- **State Management** - Save and resume complaint sessions
- **Command Interface** - Special commands for workflow control

### Starting the CLI

```bash
python run.py --config config.llm_router.json
```

Ensure your configuration file has CLI enabled:

```json
{
  "APPLICATION": {
    "type": ["cli"]
  }
}
```

### Usage

When you start the CLI, you'll see:

```
*** JusticeDAO / Complaint Generator v1.0 ***

commands are:
!reset      wipe current state and start over
!resume     resumes from a statefile from disk
!save       saves current state to disk
!claim-review [claim_type] [key=value]
!execute-follow-up [claim_type] [key=value]

Username:
>
```

#### Authentication

1. Enter your username when prompted
2. Enter your password when prompted
3. The system loads your profile or creates a new one

#### Interactive Mode

After authentication, the system enters interactive mode where:

- The mediator asks questions to gather complaint information
- You provide answers in natural language
- Press Enter without typing to continue the conversation
- Use special commands (prefixed with `!`) for workflow control

#### Commands

| Command | Description |
|---------|-------------|
| `!reset` | Wipe current state and start over with a new complaint |
| `!save` | Save current conversation state to disk |
| `!resume` | Load a previously saved state from disk |
| `!claim-review` | Print the claim-support review payload in JSON for a claim type |
| `!execute-follow-up` | Execute follow-up retrieval tasks and print the execution payload in JSON |

Review command examples:

```text
!claim-review claim_type="employment retaliation"
!claim-review "civil rights" include_follow_up_plan=false
!execute-follow-up "civil rights" follow_up_support_kind=authority follow_up_max_tasks_per_claim=1
!execute-follow-up claim_type=retaliation follow_up_force=true include_post_execution_review=false
```

Supported `key=value` options:

- `claim_type`
- `user_id`
- `follow_up_cooldown_seconds`
- `follow_up_support_kind`
- `follow_up_max_tasks_per_claim`
- `include_support_summary`
- `include_overview`
- `include_follow_up_plan`
- `required_support_kinds` as a comma-separated list such as `required_support_kinds=evidence,authority`
- `include_post_execution_review`
- `execute_follow_up` on `!claim-review` for backward-compatible opt-in execution
- `follow_up_force` on `!execute-follow-up`

### Profile Storage

User profiles are stored with:
- Username and hashed password
- Complaint conversation history
- Answered questions
- Timestamps for session tracking

Profiles are persisted in the state management system (DuckDB) for future sessions.

## Web Server Application

### Features

The web server (`applications/server.py`) provides:

- **REST API Endpoints** - HTTP endpoints for complaint processing
- **WebSocket Support** - Real-time bidirectional communication
- **JWT Authentication** - Secure token-based authentication
- **HTML Templates** - Web UI for complaint generation
- **Cookie-Based Sessions** - Persistent user sessions

### Starting the Server

```bash
python run.py --config config.llm_router.json
```

Ensure your configuration file has server enabled:

```json
{
  "APPLICATION": {
    "type": ["server"]
  }
}
```

The server starts on the configured host and port (typically `http://localhost:8000` or as configured).

## Review Surface Application

The dedicated review surface can be started without the broader legacy web app:

```bash
python run.py --config config.review_surface.json
```

This mode serves:

- `/claim-support-review` for the operator dashboard
- `/api/claim-support/review` for read-only review payloads
- `/api/claim-support/execute-follow-up` for explicit follow-up execution
- `/health` for lightweight liveness and readiness checks on the dedicated review app

### API Endpoints

#### GET Endpoints

| Endpoint | Description | Returns |
|----------|-------------|---------|
| `/` | Main landing page | HTML template (index.html) |
| `/home` | Home page after login | HTML template (home.html) |
| `/chat` | Chat interface | HTML template (chat.html) |
| `/claim-support-review` | Operator review dashboard for claim support and follow-up execution | HTML template (claim_support_review.html) |
| `/profile` | User profile page | HTML template (profile.html) |
| `/results` | Results/complaint display | HTML template (results.html) |
| `/document` | Document viewer | HTML template (document.html) |
| `/cookies` | Debug cookie information | JSON cookie data |
| `/test` | Test authentication | Profile data or error |

#### POST Endpoints

| Endpoint | Description | Returns |
|----------|-------------|---------|
| `/api/claim-support/review` | Claim-element review packet for operator or UI workflows | JSON payload with `claim_coverage_matrix`, `claim_coverage_summary`, and optional `support_summary`, `claim_overview`, or `follow_up_plan`; `follow_up_execution` remains compatibility-only |
| `/api/claim-support/execute-follow-up` | Explicit side-effecting follow-up execution endpoint | JSON payload with `follow_up_execution`, `follow_up_execution_summary`, and optional `post_execution_review` |

##### `/api/claim-support/review` - Claim Support Review

POST a small JSON request to retrieve the current claim-support review state without running the full automatic research workflow.

Example request:

```json
{
  "claim_type": "retaliation",
  "required_support_kinds": ["evidence", "authority"],
  "follow_up_cooldown_seconds": 3600,
  "include_support_summary": true,
  "include_overview": true,
  "include_follow_up_plan": true,
  "execute_follow_up": false,
  "follow_up_support_kind": null,
  "follow_up_max_tasks_per_claim": 3
}
```

Example response fields:

- `claim_coverage_matrix`: detailed per-claim and per-element grouped support links.
- `claim_coverage_summary`: compact status counts plus missing and partially supported element labels.
- `support_summary`: persisted support-link summary keyed by claim type.
- `claim_overview`: covered, partially supported, and missing element buckets keyed by claim type.
- `follow_up_plan`: actionable retrieval tasks keyed by claim type.
- `follow_up_plan_summary`: compact task, suppression, and graph-support counts keyed by claim type.
- `follow_up_execution`: compatibility-only opt-in execution results keyed by claim type when `execute_follow_up=true`.
- `follow_up_execution_summary`: compatibility-only compact execution, suppression, cooldown-skip, and graph-support counts keyed by claim type.
- `compatibility_notice`: route-level deprecation metadata returned only when `execute_follow_up=true`.

If `user_id` is omitted, the endpoint resolves it from the mediator state and falls back to `anonymous`.
If `execute_follow_up` is omitted or `false`, the endpoint remains read-only and does not trigger retrieval side effects.
New clients should prefer `/api/claim-support/execute-follow-up` when they want side effects, and treat `execute_follow_up` on the review endpoint as a backward-compatible bridge.
When the compatibility path is used, the response also includes `Deprecation`, `Sunset`, `Link`, and `Warning` headers pointing callers at `/api/claim-support/execute-follow-up`.

##### `/api/claim-support/execute-follow-up` - Follow-Up Execution

POST to this endpoint when the caller wants an explicit execution surface rather than using the compatibility `execute_follow_up` flag on the review endpoint.

Example request:

```json
{
  "claim_type": "retaliation",
  "required_support_kinds": ["evidence", "authority"],
  "follow_up_cooldown_seconds": 3600,
  "follow_up_support_kind": "evidence",
  "follow_up_max_tasks_per_claim": 1,
  "follow_up_force": false,
  "include_post_execution_review": true,
  "include_support_summary": true,
  "include_overview": true,
  "include_follow_up_plan": true
}
```

Example response fields:

- `follow_up_execution`: raw execution results keyed by claim type.
- `follow_up_execution_summary`: compact execution, suppression, cooldown-skip, and graph-support counts keyed by claim type.
- `post_execution_review`: refreshed review payload after execution, including updated coverage and optional follow-up planning.

Use this endpoint for new clients that want execution to be unambiguously side-effecting. The review endpoint remains available for read-only review and backward-compatible opt-in execution.

#### WebSocket Endpoints

##### `/api/chat` - Real-time Chat

WebSocket endpoint for real-time complaint processing:

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8000/api/chat');
```

**Authentication:**
- Requires `Authorization` cookie with JWT token
- Also accepts `hashed_username` and `hashed_password` cookies

**Message Format:**
```javascript
// Send
ws.send(JSON.stringify({
  type: "message",
  content: "Your complaint text here"
}));

// Receive
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

**Broadcast Messages:**
The server broadcasts messages to all connected clients when:
- A user connects: `{"hashed_username": "...", "message": "got connected"}`
- A user disconnects: `{"hashed_username": "...", "message": "left"}`
- A user sends a message: `{...message data...}`

### Authentication

The server uses **JWT (JSON Web Tokens)** for authentication:

#### Token Generation

```python
def create_access_token(data: dict, expires_delta: timedelta = None):
    # Returns a JWT token valid for 30 minutes (default)
    # or specified expiration time
```

**Token Payload:**
- User data (username, permissions, etc.)
- Expiration timestamp
- Issued at timestamp

**Algorithm:** HS256 (HMAC with SHA-256)

#### Cookie-Based Authentication

The server expects authentication cookies:
- `Authorization` - JWT token
- `hashed_username` - Hashed username
- `hashed_password` - Hashed password

**⚠️ Security Note:** The current implementation has a hardcoded JWT secret key in the source code. This should be moved to environment variables or a secure configuration system for production use.

### HTML Templates

The server uses Jinja2 templates located in the `templates/` directory:

| Template | Purpose |
|----------|---------|
| `index.html` | Landing page with login |
| `home.html` | Main dashboard after authentication |
| `chat.html` | Interactive chat interface for complaints |
| `claim_support_review.html` | Operator dashboard for claim review and follow-up execution |
| `profile.html` | User profile management |
| `results.html` | Display generated complaint results |
| `document.html` | Document viewer/editor (WYSIWYG) |
| `login.html` | Login form |
| `register.html` | User registration |
| `unauthorized.html` | 403 error page |

### WebSocket Connection Manager

The server includes a `SocketManager` class for managing WebSocket connections:

```python
class SocketManager:
    def __init__(self):
        self.active_connections: list[(WebSocket, str)] = []
    
    async def connect(websocket: WebSocket, user: str)
    def disconnect(websocket: WebSocket, user: str)
    async def broadcast(data: dict)  # Broadcast to all connected clients
```

## Running Both Applications

You can run the CLI together with one web surface:

```json
{
  "APPLICATION": {
    "type": ["cli", "review-surface"]
  }
}
```

This starts the selected web surface in the background and then enters the CLI.

## Application Entry Points

### main.py

The primary entry point (`main.py`) provides:
- Configuration loading from `config.llm_router.json`
- Backend initialization (OpenAI, LLM Router, Workstation)
- Mediator setup with configured backends
- Application instantiation (CLI and/or Server)

### run.py

Alternative entry point (`run.py`) with simplified interface:
- Loads configuration
- Initializes backends and mediator
- Starts configured applications

## Configuration

Applications are configured in `config.llm_router.json`:

```json
{
  "APPLICATION": {
    "type": ["review-surface"],
    "host": "0.0.0.0",
    "port": 8000
  },
  "BACKENDS": [...],
  "MEDIATOR": {...},
  "LOG": {
    "level": "INFO"
  }
}
```

The repository root also includes `config.review_surface.json` as a ready-to-run focused operator profile.

See [docs/CONFIGURATION.md](CONFIGURATION.md) for complete configuration reference.

## Security Considerations

### Current Implementation

⚠️ **Important Security Notes:**

1. **Hardcoded Secrets** - The server has a hardcoded JWT secret key that should be moved to environment variables
2. **Hostname** - Hardcoded hostname `http://10.10.0.10:1792` should be configurable
3. **Password Hashing** - The CLI uses "hashed" passwords, but the hashing mechanism is not clearly defined
4. **HTTPS** - The server runs on HTTP by default; HTTPS should be configured for production

### Recommended Improvements

For production deployment:

1. **Use Environment Variables:**
```python
SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
HOSTNAME = os.environ.get('SERVER_HOSTNAME', 'http://localhost:8000')
```

2. **Proper Password Hashing:**
```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
```

3. **HTTPS Configuration:**
```python
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8443,
    ssl_keyfile="/path/to/key.pem",
    ssl_certfile="/path/to/cert.pem"
)
```

4. **Rate Limiting** - Add rate limiting for API endpoints
5. **CORS Configuration** - Configure CORS for cross-origin requests
6. **Input Validation** - Validate and sanitize all user inputs

See [docs/SECURITY.md](SECURITY.md) for comprehensive security guidelines.

## Development

### Adding New Endpoints

To add a new REST endpoint:

```python
@app.get("/your-endpoint")
async def your_handler(request: Request):
    # Your logic here
    return {"result": "data"}
```

### Adding WebSocket Handlers

To add a new WebSocket endpoint:

```python
@app.websocket("/api/your-socket")
async def your_socket(websocket: WebSocket):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            # Process data
            await manager.broadcast(response)
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
```

### Adding New Templates

1. Create HTML template in `templates/`
2. Add route handler to serve the template
3. Use Jinja2 templating for dynamic content

## Troubleshooting

### CLI Issues

**Problem:** "Username/Password not accepted"
- Check that your credentials are correct
- Verify profile storage is working (DuckDB accessible)

**Problem:** "Commands not working"
- Ensure commands start with `!`
- Check command spelling (`!reset`, `!save`, `!resume`)

### Server Issues

**Problem:** "Port already in use"
```bash
# Find and kill process using the port
lsof -ti:8000 | xargs kill -9
```

**Problem:** "WebSocket connection failed"
- Verify JWT token is valid and not expired
- Check authentication cookies are set correctly
- Ensure WebSocket URL matches server configuration

**Problem:** "Template not found"
- Verify `templates/` directory exists
- Check template file names match route handlers
- Ensure working directory is repository root

### Authentication Issues

**Problem:** "JWT token expired"
- Tokens expire after 30 minutes by default
- Request a new token by re-authenticating

**Problem:** "Invalid token signature"
- Ensure SECRET_KEY matches between token creation and validation
- Do not modify JWT token contents

## Related Documentation

- [Configuration Guide](CONFIGURATION.md) - Application configuration
- [Architecture Overview](ARCHITECTURE.md) - System architecture
- [Security Guide](SECURITY.md) - Security best practices
- [Deployment Guide](DEPLOYMENT.md) - Production deployment
- [API Reference](API_REFERENCE.md) - Complete API documentation

## Support

For issues or questions:
- GitHub Issues: https://github.com/endomorphosis/complaint-generator/issues
- GitHub Discussions: https://github.com/endomorphosis/complaint-generator/discussions
