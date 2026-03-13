# Configuration Guide

Complete reference for configuring the Complaint Generator system.

## Overview

The Complaint Generator uses a JSON configuration file (default: `config.llm_router.json`) to configure:

- **Backends** - LLM providers and models
- **Mediator** - Core orchestration settings
- **Applications** - CLI and web server settings
- **Logging** - Log levels and output

## Configuration File Location

By default, the system looks for `config.llm_router.json` in the repository root. You can specify a different location:

```bash
python run.py --config /path/to/your/config.json

# Or via environment variable
export COMPLAINT_GENERATOR_CONFIG=/path/to/config.json
python run.py
```

The repository also includes `config.review_surface.json` for the dedicated claim-support operator surface.

## Configuration Structure

```json
{
  "BACKENDS": [...],      // LLM provider configurations
  "MEDIATOR": {...},      // Mediator settings
  "APPLICATION": {...},   // Application settings
  "LOG": {...}            // Logging configuration
}
```

## BACKENDS Configuration

Define one or more LLM backends for the system to use.

### LLM Router Backend

Uses the `ipfs_datasets_py` LLM router for multi-provider support:

```json
{
  "id": "llm-router",
  "type": "llm_router",
  "provider": "copilot_cli",
  "model": "gpt-4",
  "max_tokens": 2048,
  "temperature": 0.7,
  "continue_session": true
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier for this backend |
| `type` | string | Yes | Must be `"llm_router"` |
| `provider` | string | Yes | LLM provider (see [Supported Providers](#supported-providers)) |
| `model` | string | Yes | Model name/identifier |
| `max_tokens` | integer | No | Maximum tokens to generate (default: 128) |
| `temperature` | float | No | Sampling temperature 0.0-2.0 (default: 0.7) |
| `top_p` | float | No | Nucleus sampling parameter (default: 1.0) |
| `continue_session` | boolean | No | Reuse session for Copilot CLI (default: false) |

#### Supported Providers

- `openrouter` - OpenRouter API (multiple models)
- `huggingface` - Local Hugging Face Transformers fallback via `ipfs_datasets_py.llm_router`
- `huggingface_router` - Hugging Face Inference via the OpenAI-compatible router endpoint used by Chat UI `llm-router`
- `copilot_cli` - GitHub Copilot CLI
- `codex_cli` - OpenAI Codex CLI
- `gemini_cli` - Google Gemini CLI
- `claude_code` - Anthropic Claude Code CLI
- `copilot_sdk` - GitHub Copilot Python SDK

See [docs/LLM_ROUTER.md](LLM_ROUTER.md) for detailed provider documentation.

#### Hugging Face Router / Chat UI Compatibility

To send requests through Hugging Face Inference using the same OpenAI-compatible router endpoint documented for Chat UI `llm-router`, configure a backend like this:

```json
{
  "id": "hf-router",
  "type": "llm_router",
  "provider": "huggingface_router",
  "model": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
  "base_url": "https://router.huggingface.co/v1",
  "max_tokens": 2048,
  "temperature": 0.2
}
```

Set one of these environment variables for authentication:

- `HF_TOKEN`
- `HUGGINGFACE_HUB_TOKEN`
- `HUGGINGFACE_API_KEY`

The formal complaint API and document pipeline also accept `optimization_llm_config` so the agentic optimizer can use the same Hugging Face router settings:

```json
{
  "enable_agentic_optimization": true,
  "optimization_provider": "huggingface_router",
  "optimization_model_name": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
  "optimization_llm_config": {
    "base_url": "https://router.huggingface.co/v1",
    "headers": {
      "X-Title": "Complaint Generator"
    }
  }
}
```

If you want automatic model selection before the optimization or drafting call, add an `arch_router` block. This runs `katanemo/Arch-Router-1.5B` as a pre-router and maps the returned route to one of your configured models:

```json
{
  "enable_agentic_optimization": true,
  "optimization_provider": "huggingface_router",
  "optimization_model_name": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
  "optimization_llm_config": {
    "base_url": "https://router.huggingface.co/v1",
    "headers": {
      "X-Title": "Complaint Generator"
    },
    "arch_router": {
      "enabled": true,
      "model": "katanemo/Arch-Router-1.5B",
      "context": "Complaint drafting, legal issue spotting, and filing packet generation.",
      "routes": {
        "legal_reasoning": "meta-llama/Llama-3.3-70B-Instruct",
        "drafting": "Qwen/Qwen3-Coder-480B-A35B-Instruct"
      }
    }
  }
}
```

The repository's sample [config.llm_router.json](../config.llm_router.json) now includes an `hf-router-auto-legal` backend profile with this pattern pre-configured.

### OpenAI Backend

Direct OpenAI API integration:

```json
{
  "id": "openai-gpt4",
  "type": "openai",
  "api_key": "${OPENAI_API_KEY}",
  "engine": "text-davinci-003",
  "temperature": 0.7,
  "top_p": 1.0,
  "max_tokens": 2048,
  "presence_penalty": 0.0,
  "frequency_penalty": 0.0,
  "best_of": 1
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier |
| `type` | string | Yes | Must be `"openai"` |
| `api_key` | string | Yes | OpenAI API key (use `${ENV_VAR}` for environment variables) |
| `engine` | string | Yes | OpenAI engine/model name |
| `temperature` | float | No | Sampling temperature 0.0-2.0 (default: 0.7) |
| `top_p` | float | No | Nucleus sampling (default: 1.0) |
| `max_tokens` | integer | No | Maximum tokens (default: 1952) |
| `presence_penalty` | float | No | Penalty for new topics -2.0 to 2.0 (default: 0.0) |
| `frequency_penalty` | float | No | Penalty for repetition -2.0 to 2.0 (default: 0.0) |
| `best_of` | integer | No | Generate N completions, return best (default: 1) |

**Environment Variable Substitution:**

Use `${VAR_NAME}` syntax to reference environment variables:
```json
"api_key": "${OPENAI_API_KEY}"
```

### Workstation Backend

Local model execution:

```json
{
  "id": "workstation-local",
  "type": "workstation",
  "model": "t5",
  "max_length": 512,
  "device": "cuda"
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier |
| `type` | string | Yes | Must be `"workstation"` |
| `model` | string | Yes | Model name: `"t5"`, `"gptj"`, `"bloom"`, etc. |
| `max_length` | integer | No | Maximum sequence length (default: 100) |
| `device` | string | No | Device: `"cpu"`, `"cuda"`, `"cuda:0"` (default: auto) |

**Supported Models:**
- `t5` - T5 (Text-to-Text Transfer Transformer)
- `gptj` - GPT-J-6B
- `bloom` - BLOOM models
- Custom HuggingFace models

## MEDIATOR Configuration

Configure the core mediator orchestration:

```json
{
  "MEDIATOR": {
    "backends": ["llm-router", "openai-gpt4"],
    "fallback": true,
    "timeout": 30,
    "max_retries": 3
  }
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `backends` | array[string] | Yes | List of backend IDs to use (in priority order) |
| `fallback` | boolean | No | Enable automatic fallback to next backend on failure (default: true) |
| `timeout` | integer | No | Request timeout in seconds (default: 30) |
| `max_retries` | integer | No | Maximum retry attempts per backend (default: 3) |

**Backend Priority:**

Backends are tried in the order specified. If the first backend fails and `fallback` is enabled, the system automatically tries the next backend.

Example:
```json
"backends": ["llm-router", "openai-gpt4", "workstation-local"]
```
1. Try `llm-router` first
2. If it fails, try `openai-gpt4`
3. If that fails, try `workstation-local`

## APPLICATION Configuration

Configure CLI and web server applications:

```json
{
  "APPLICATION": {
    "type": ["cli", "server"],
    "host": "0.0.0.0",
    "port": 8000,
    "workers": 4,
    "reload": false
  }
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | array[string] | Yes | Application types: `["cli"]`, `["server"]`, `["review-surface"]`, `["review-api"]`, `["review-dashboard"]`, or one web type combined with `"cli"` |
| `host` | string | No | Server bind address (default: `"0.0.0.0"`) |
| `port` | integer | No | Server port (default: 8000) |
| `workers` | integer | No | Number of Uvicorn workers (default: 1) |
| `reload` | boolean | No | Enable hot reload for development (default: false) |

**Application Types:**

- `"cli"` - Start command-line interface
- `"server"` - Start web server
- `"review-surface"` - Start the dedicated claim-support dashboard plus its review/follow-up API routes
- `"review-api"` - Start only the claim-support review/follow-up API routes
- `"review-dashboard"` - Start only the `/claim-support-review` HTML dashboard
- One web type can be combined with `"cli"`, for example `["cli", "review-surface"]`
- Multiple web types in one process are not supported because they share the same bind address and port

**Note:** The current configuration format has a legacy structure where `type` may be an object instead of an array. Both formats are supported:

```json
// Modern format (recommended)
"type": ["cli", "server"]

// Legacy format (still supported)
"type": {
  "cli": "cli",
  "server": "server"
}
```

## LOG Configuration

Configure logging behavior:

```json
{
  "LOG": {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": "logs/complaint-generator.log"
  }
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `level` | string | Yes | Log level: `"DEBUG"`, `"INFO"`, `"WARN"`, `"ERROR"`, `"CRITICAL"` |
| `format` | string | No | Log message format (Python logging format) |
| `file` | string | No | Log file path (if omitted, logs to stdout only) |

**Log Levels:**

- `DEBUG` - Detailed diagnostic information
- `INFO` - General informational messages
- `WARN` - Warning messages (default)
- `ERROR` - Error messages
- `CRITICAL` - Critical errors only

## Example Configurations

### Development Configuration

```json
{
  "BACKENDS": [
    {
      "id": "dev-backend",
      "type": "llm_router",
      "provider": "copilot_cli",
      "model": "gpt-4",
      "max_tokens": 2048
    }
  ],
  "MEDIATOR": {
    "backends": ["dev-backend"],
    "fallback": false
  },
  "APPLICATION": {
    "type": ["cli"],
    "reload": true
  },
  "LOG": {
    "level": "DEBUG"
  }
}
```

### Production Configuration

```json
{
  "BACKENDS": [
    {
      "id": "prod-primary",
      "type": "openai",
      "api_key": "${OPENAI_API_KEY}",
      "engine": "gpt-4",
      "max_tokens": 2048
    },
    {
      "id": "prod-fallback",
      "type": "llm_router",
      "provider": "openrouter",
      "model": "anthropic/claude-3-opus",
      "max_tokens": 2048
    }
  ],
  "MEDIATOR": {
    "backends": ["prod-primary", "prod-fallback"],
    "fallback": true,
    "timeout": 60,
    "max_retries": 5
  },
  "APPLICATION": {
    "type": ["server"],
    "host": "0.0.0.0",
    "port": 8000,
    "workers": 4
  },
  "LOG": {
    "level": "INFO",
    "file": "/var/log/complaint-generator/app.log"
  }
}
```

### Multi-Backend Configuration

```json
{
  "BACKENDS": [
    {
      "id": "copilot",
      "type": "llm_router",
      "provider": "copilot_cli",
      "model": "gpt-4",
      "max_tokens": 2048
    },
    {
      "id": "openai",
      "type": "openai",
      "api_key": "${OPENAI_API_KEY}",
      "engine": "gpt-4",
      "max_tokens": 2048
    },
    {
      "id": "local",
      "type": "workstation",
      "model": "gptj",
      "max_length": 512
    }
  ],
  "MEDIATOR": {
    "backends": ["copilot", "openai", "local"],
    "fallback": true
  },
  "APPLICATION": {
    "type": ["cli", "server"]
  },
  "LOG": {
    "level": "INFO"
  }
}
```

## Environment Variables

The configuration system supports environment variable substitution using `${VAR_NAME}` syntax.

### Setting Environment Variables

**Linux/Mac:**
```bash
export OPENAI_API_KEY="sk-..."
export BRAVE_SEARCH_API_KEY="..."
export COMPLAINT_GENERATOR_CONFIG="/path/to/config.json"
```

**Windows (PowerShell):**
```powershell
$env:OPENAI_API_KEY="sk-..."
$env:BRAVE_SEARCH_API_KEY="..."
$env:COMPLAINT_GENERATOR_CONFIG="C:\path\to\config.json"
```

### Recommended Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `OPENAI_API_KEY` | OpenAI API authentication | If using OpenAI backend |
| `BRAVE_SEARCH_API_KEY` | Brave Search API for web evidence | For web evidence discovery |
| `COMPLAINT_GENERATOR_CONFIG` | Custom config file path | No (defaults to config.llm_router.json) |
| `JWT_SECRET_KEY` | JWT signing key for server | Recommended for production |
| `SERVER_HOSTNAME` | Server hostname/URL | Recommended for production |

## Validation

The system validates configuration on startup and will exit with an error if:

- Required fields are missing
- Backend IDs referenced in MEDIATOR don't exist
- Invalid log levels specified
- Malformed JSON

Example validation error:
```
ERROR: missing backend configuration "invalid-backend-id" - cannot continue
```

## Configuration Best Practices

### Security

1. **Never commit API keys** - Use environment variables
2. **Use separate configs** - Different configs for dev/staging/prod
3. **Restrict file permissions** - `chmod 600 config.json` on production servers
4. **Rotate secrets regularly** - Change API keys and JWT secrets periodically

### Performance

1. **Order backends by speed** - Fastest providers first for better response times
2. **Enable fallback** - Ensures reliability when primary backend fails
3. **Adjust max_tokens** - Balance between quality and cost/speed
4. **Use workers** - Multiple workers for production server deployments

### Reliability

1. **Configure multiple backends** - Redundancy prevents single point of failure
2. **Set appropriate timeouts** - Balance between patience and responsiveness
3. **Enable retries** - Handles transient network issues
4. **Monitor logs** - Use INFO or WARN level in production

## Troubleshooting

### Backend Not Found

**Error:** `missing backend configuration "xxx" - cannot continue`

**Solution:** Ensure the backend ID in `MEDIATOR.backends` matches a backend `id` in `BACKENDS` array.

### API Key Issues

**Error:** `OpenAI API authentication failed`

**Solution:**
1. Verify environment variable is set: `echo $OPENAI_API_KEY`
2. Check variable substitution syntax: `"api_key": "${OPENAI_API_KEY}"`
3. Ensure no extra quotes or whitespace

### Application Won't Start

**Error:** `unknown application type: xxx`

**Solution:** Use valid application types: `"cli"`, `"server"`, `"review-surface"`, `"review-api"`, or `"review-dashboard"`.

**Error:** `multiple web application types are not supported in one process`

**Solution:** Choose a single web surface per process, optionally combined with `"cli"`.

### Port Already in Use

**Error:** `Address already in use`

**Solution:**
1. Change port in configuration: `"port": 8001`
2. Or kill process using the port: `lsof -ti:8000 | xargs kill -9`

## Related Documentation

- [LLM Router Guide](LLM_ROUTER.md) - Detailed LLM router documentation
- [Backends Guide](BACKENDS.md) - Backend configuration details
- [Applications Guide](APPLICATIONS.md) - CLI and server documentation
- [Deployment Guide](DEPLOYMENT.md) - Production deployment
- [Security Guide](SECURITY.md) - Security best practices

## Support

For configuration issues:
- Check logs for detailed error messages
- Verify JSON syntax with a JSON validator
- Review example configurations above
- Open an issue: https://github.com/endomorphosis/complaint-generator/issues
