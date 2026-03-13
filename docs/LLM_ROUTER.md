# Using LLM Router Backend

The complaint-generator now includes a backend that uses the `llm_router` from the `ipfs_datasets_py` submodule to route LLM requests. This provides a unified interface for working with multiple LLM providers.

## Features

- **Multiple Provider Support**: Route requests to OpenRouter, Hugging Face router/inference endpoints, local Hugging Face models, and more
- **Automatic Fallback**: Falls back to local models if remote providers are unavailable
- **Provider Caching**: Efficiently reuses provider instances
- **Configurable**: Supports custom configuration per backend

## Configuration

### Basic Usage

Add the LLM Router backend to your `config.llm_router.json`:

```json
{
    "BACKENDS": [
        {
            "id": "llm-router",
            "type": "llm_router",
            "provider": "copilot_cli",
            "model": "gpt-5-mini",
            "max_tokens": 128
        }
    ],
    "MEDIATOR": {
        "backends": ["llm-router"]
    }
}
```

### Using OpenRouter

To use OpenRouter (requires API key):

```json
{
    "BACKENDS": [
        {
            "id": "llm-router-openrouter",
            "type": "llm_router",
            "provider": "openrouter",
            "model": "anthropic/claude-2",
            "max_tokens": 256
        }
    ]
}
```

Set the environment variable:
```bash
export OPENROUTER_API_KEY="your-api-key"
```

### Using Hugging Face Router / Inference

To use the same OpenAI-compatible Hugging Face router endpoint documented for Chat UI `llm-router`:

```json
{
    "BACKENDS": [
        {
            "id": "hf-router",
            "type": "llm_router",
            "provider": "huggingface_router",
            "model": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            "base_url": "https://router.huggingface.co/v1",
            "max_tokens": 1024,
            "temperature": 0.2
        }
    ],
    "MEDIATOR": {
        "backends": ["hf-router"]
    }
}
```

Set one of these environment variables for authentication:

```bash
export HF_TOKEN="your-huggingface-token"
# or
export HUGGINGFACE_HUB_TOKEN="your-huggingface-token"
```

Notes:

- `provider="huggingface_router"` is normalized onto the existing OpenAI-compatible transport used by `ipfs_datasets_py.llm_router`.
- `provider="huggingface"` still means the local Transformers fallback unless you also set a Hugging Face router `base_url`.
- The same settings can be passed to the document optimizer through `optimization_provider`, `optimization_model_name`, and `optimization_llm_config`.

### Auto-detect Provider

Let the router automatically detect the best available provider:

```json
{
    "BACKENDS": [
        {
            "id": "llm-router-auto",
            "type": "llm_router",
            "max_tokens": 256
        }
    ]
}
```

The router will try providers in this order:
1. ipfs_accelerate_py (if available)
2. OpenRouter (if API key is set)
3. Other CLI providers
4. Local HuggingFace models

## Supported Providers

Note: In this repository's current `ipfs_datasets_py/llm_router.py` shim implementation, `codex_cli`, `copilot_cli`, `claude_code`, and `gemini_cli` are implemented as CLI providers. For `gemini_cli`, you must configure the correct CLI command/flags for the specific Gemini CLI you installed (there are multiple, with different argument conventions).

- `local_hf` / `huggingface` - Local Hugging Face Transformers fallback
- `huggingface_router` / `hf_router` / `huggingface_inference` / `hf_inference` - Hugging Face router/inference via `https://router.huggingface.co/v1`
- `openrouter` - OpenRouter API
- `codex_cli` - OpenAI Codex CLI
- `copilot_cli` - GitHub Copilot CLI
- `copilot_sdk` - GitHub Copilot Python SDK (controls Copilot CLI via JSON-RPC)
- `gemini_cli` - Google Gemini CLI
- `claude_code` - Claude Code CLI
- Auto-detect (no provider specified)

## Tracing and Session Artifacts

The CLI-based providers (`copilot_cli`, `codex_cli`) support optional tracing so you can keep session artifacts (transcripts/logs) inside this repo (for example under `statefiles/_runs/...`, which is typically git-ignored).

You can pass these keys through `config.llm_router.json` (they are forwarded as `**config` into `ipfs_datasets_py.llm_router.generate_text`).

### Common tracing keys

- `trace`: boolean. Enables tracing (you can also enable tracing by setting `trace_dir` or `trace_jsonl_path`).
- `trace_dir`: directory path. When set, providers will write trace outputs into this directory.

### Copilot CLI (`copilot_cli`)

- Writes a markdown transcript via `copilot --share <path>` when tracing is enabled.
- If `trace_dir` is set, the transcript is written into that directory.
- If only `trace_jsonl_path` is set (and `trace_dir` is not), the transcript is written next to the JSONL path.
- When tracing is enabled and `copilot_log_dir` is not set, the shim sets `--log-dir` to `trace_dir` by default.

Optional keys:

- `copilot_config_dir`: pass through to `copilot --config-dir`.
- `copilot_log_dir`: pass through to `copilot --log-dir`.
- `resume_session_id`: pass through to `copilot --resume <sessionId>`.
- `continue_session`: boolean. If true and `resume_session_id` is not set, uses `copilot --continue`.
- `trace_jsonl_path`: append a small JSONL metadata record per call (the full transcript is in the markdown share file).

#### Cache-friendly multi-turn sessions (Copilot CLI)

Unlike the Codex CLI JSON traces, Copilot CLI does not currently expose a standardized `cached_input_tokens` counter. The practical way to be “prompt-caching-friendly” with Copilot CLI is to keep the prompt prefix stable across turns and to reuse the same Copilot CLI session.

In this repo, the adversarial/batch runners implement this by:

- Creating an isolated `copilot_config_dir` per logical conversation (and per role, e.g. mediator vs critic), so multiple sessions can run in parallel without sharing state.
- Setting `continue_session=true` so the Copilot CLI uses `--continue` and keeps a single session thread for that conversation.

This mode is exposed as a CLI flag on the example runners:

- `python examples/codex_multi_run_autopatch.py --session-cache-friendly ...`
- `python examples/batch_sgd_cycle.py --session-cache-friendly ...`
- `python examples/parallelism_backoff_sweep.py --session-cache-friendly ...`
- `python examples/adversarial_optimization_demo.py --session-cache-friendly ...`

Artifacts are written under each session directory (which is typically under `statefiles/_runs/...`), for example:

- `<session_dir>/_copilot/mediator/config/`
- `<session_dir>/_copilot/mediator/logs/`

Note: The Copilot CLI may error on `--continue` when no prior session exists in the config dir; the shim retries once without `--continue` so the first turn still succeeds.

### Codex CLI (`codex_cli`)

- When tracing is enabled, the shim adds `codex exec --json` and saves stdout JSONL into `trace_jsonl_path` or a generated file under `trace_dir`.

### Claude Code CLI (`claude_code`)

The shim supports Claude Code’s non-interactive mode via `claude --print`.

Defaults:

- Tools are disabled by default (`--tools ""`) to keep behavior LLM-like and avoid permission prompts.

Optional keys:

- `claude_output_format`: one of `text` (default), `json`, `stream-json`
- `claude_input_format`: `text` (default) or `stream-json`
- `claude_include_partial_messages`: boolean (only meaningful with `claude_output_format=stream-json`)
- `claude_no_session_persistence`: boolean
- `claude_permission_mode`: pass-through to `--permission-mode`
- `claude_system_prompt`, `claude_append_system_prompt`
- `claude_tools`: override tools setting (e.g. `default` or a comma-separated list)
- `claude_add_dir`: string or list of strings passed as repeated `--add-dir`
- `claude_allowed_tools`, `claude_disallowed_tools`
- `claude_session_id`: set a specific session UUID
- `resume_session_id`: resume a session id (shared key used by other providers)
- `continue_session`: resume most recent session (shared key used by other providers)
- `claude_fork_session`: boolean (use with `resume_session_id`)

Tracing:

- If `trace_dir` is set, the shim writes `claude_print_<timestamp>_<pid>.txt` containing stdout (and stderr, if any).
- If `trace_jsonl_path` is set, the shim appends a small JSONL metadata record per call.

### Gemini CLI (`gemini_cli`)

Because Gemini CLIs vary, the shim uses a configurable command and always sends the prompt on stdin.

If you installed Gemini via `npx @google/gemini-cli`, note that package currently requires Node `>=20` at runtime. The shim avoids a system Node upgrade by running it under a transient Node 20 binary via `npx -p node@20`.

Optional keys:

- `gemini_cli_path`: executable path/name (default: `gemini`)
- `gemini_cli_path`: can also be a shorthand `npx:@google/gemini-cli` to force using `npx -y @google/gemini-cli`
- `gemini_cmd`: full command override (string like `"mygemini --flag"` or a list like `["mygemini","--flag"]`). Takes precedence.
- `gemini_args`: extra args appended after the base command (string or list)
- `gemini_env`: dict of env vars to set for the subprocess

Tracing:

- If `trace_dir` is set, writes `gemini_exec_<timestamp>_<pid>.txt` containing stdout (and stderr, if any).
- If `trace_jsonl_path` is set, appends a JSONL metadata record per call.

### Copilot Python SDK (`copilot_sdk`)

The shim also supports using the Copilot Python SDK, which programmatically controls the Copilot CLI via JSON-RPC.

Notes:

- The SDK is an optional dependency; it is only imported when `provider="copilot_sdk"`.
- You still need the `copilot` CLI installed and authenticated.

Common keys:

- `trace_jsonl_path`: append a small JSONL metadata record per call (session id, workspace path, prompt/response sizes).

SDK-specific keys (all optional):

- `copilot_sdk_cli_path`: path to the `copilot` executable.
- `copilot_sdk_cli_url`: connect to an existing running server.
- `copilot_sdk_log_level`: SDK log level.
- `copilot_sdk_use_stdio`, `copilot_sdk_port`, `copilot_sdk_auto_start`, `copilot_sdk_auto_restart`, `copilot_sdk_cwd`
- `copilot_sdk_github_token`, `copilot_sdk_use_logged_in_user`
- `copilot_sdk_session_id`: custom session id.
- `copilot_sdk_streaming`: enable streaming events.
- `copilot_sdk_infinite_sessions`: dict config for infinite session compaction.


## Environment Variables

- `IPFS_DATASETS_PY_LLM_PROVIDER` - Force a specific provider
- `IPFS_DATASETS_PY_LLM_MODEL` - Default model name
- `OPENROUTER_API_KEY` - OpenRouter API key
- `HF_TOKEN` / `HUGGINGFACE_HUB_TOKEN` - Hugging Face router/inference token
- `IPFS_DATASETS_PY_ENABLE_IPFS_ACCELERATE` - Enable accelerate provider

## Example in run.py

Update your `run.py` to use the LLM Router backend:

```python
from backends import LLMRouterBackend

# ... existing code ...

for backend_id in config_mediator['backends']:
    backend_config = next((conf for conf in config_backends if conf['id'] == backend_id), None)
    
    if not backend_config:
        log.error('missing backend configuration "%s" - cannot continue' % backend_id)
        exit(-1)
    
    if backend_config['type'] == 'llm_router':
        backend = LLMRouterBackend(**backend_config)
    elif backend_config['type'] == 'openai':
        backend = OpenAIBackend(**backend_config)
    # ... other backend types ...
    
    backends.append(backend)
```

## Testing

Run the tests to verify the LLM Router backend:

```bash
pytest tests/test_llm_router_backend.py -v
```

## Benefits

1. **Unified Interface**: Single backend type for multiple LLM providers
2. **Flexible**: Easy to switch providers without changing code
3. **Reliable**: Automatic fallback to local models
4. **Modern**: Uses the well-maintained ipfs_datasets_py package
5. **Test-Friendly**: Easy to mock for testing

## Troubleshooting

### Submodule Not Initialized

If you see an error about missing `ipfs_datasets_py`:

```bash
git submodule update --init --recursive
```

### Missing Dependencies

For local HuggingFace models:
```bash
pip install transformers torch
```

For OpenRouter:
```bash
export OPENROUTER_API_KEY="your-api-key"
```

## Next Steps

- Add more backends using different providers
- Configure provider-specific options
- Integrate with ipfs_accelerate_py for distributed inference
- Add model-specific configurations
