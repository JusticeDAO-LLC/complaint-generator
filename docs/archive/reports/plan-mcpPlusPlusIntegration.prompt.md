## Plan: Integrate MCP++ P2P innovations into mcp_server

Bring the proven libp2p TaskQueue + shared-cache + remote-tool-exec capabilities from mcplusplus/p2p_tasks into ipfs_datasets_py’s MCP server, while keeping the current stdio MCP transport as the primary interface. Run the P2P service in-process using the existing thread-based Trio runtime wrapper, and adapt the P2P “call_tool” operation to the existing hierarchical tool dispatch.

**Steps**
1. Discovery + baseline (one-time)
   - Confirm ipfs_accelerate_py is importable from ipfs_datasets_py runtime (so we can start with “import then migrate” without copying code immediately).
   - Identify existing task queue / cache / background-task tools in mcp_server and map them to the P2P-backed implementations.

2. Define integration boundaries (interfaces) (depends on 1)
   - Introduce a small “ToolDispatcher” abstraction in mcp_server that wraps HierarchicalToolManager/tools_dispatch and produces a normalized response envelope.
   - Introduce a small “AuthContext” abstraction (user/session/roles/scopes) that can be created from either JWT/session credentials (mcp_server) or P2P message credentials.

3. Add P2P configuration (parallel with 2)
   - Extend mcp_server configuration to include: enable/disable P2P, listen port, queue storage path, rendezvous namespace, discovery toggles (mdns/dht/relay/holepunch), and auth mode.
   - Preserve compatibility with existing env var names in p2p_tasks/service.py for easier rollout.

4. Run P2P service in-process (depends on 2,3)
   - Add a P2P service manager inside mcp_server that starts/stops the Trio-based service via the thread runner.
   - Wire startup into the MCP server lifecycle: start the P2P service before starting stdio; ensure stop is called on shutdown/KeyboardInterrupt.

5. Remote tool execution over P2P (depends on 2,4)
   - Adapt the P2P TaskQueue service handler for ops in {tool, call_tool, tool.call} to invoke the new ToolDispatcher adapter.
   - Ensure request/response envelopes are consistent with newline-delimited JSON framing; include request ids and structured errors.

6. TaskQueue integration (depends on 4; parallel with 5)
   - Adopt DuckDB-backed TaskQueue as the durable backend for background tasks.
   - Map existing background task tools to enqueue/monitor/claim tasks using the TaskQueue API (local fast-path), while keeping the P2P RPC ops for distributed workers.

7. Shared cache integration (depends on 4; parallel with 5,6)
   - Adopt DiskTTLCache RPC ops (cache.get/has/set/delete) in mcp_server tool surface.
   - Add a small adapter to let mcp_server tools use the cache locally when the service is in-process.

8. Peer discovery + connectivity “innovations” (depends on 4)
   - Expose service state + peer observation as tools (service status, list_known_peers, last_seen).
   - Optionally migrate SimplePeerBootstrap / UniversalConnectivity patterns from mcplusplus_module for more reliable dialing and multiaddr management.

9. Auth unification (depends on 2; parallel with 5-8)
   - Extend P2P message auth to accept JWT/session-derived tokens, validated by the shared AuthContext/validator module.
   - Keep the existing shared-token auth as an optional compatibility mode for bootstrap/testing.

10. Observability + metrics (parallel with 5-9)
   - Emit EnhancedMetricsCollector events for P2P ops: request latency, tool execution latency, queue operations, cache ops, error rates.
   - Add structured logs that correlate MCP request ids with P2P request ids.

11. Tests + verification (depends on 5-7)
   - Unit tests: protocol/auth helpers, ToolDispatcher adapter mapping, queue persistence behavior, cache TTL behavior.
   - Optional integration tests (skippable): start TaskQueueP2PServiceRuntime on a random port and use p2p_tasks/client.py to call cache ops and call_tool against a trivial safe MCP tool.

**Relevant files**
- ipfs_datasets_py/ipfs_datasets_py/mcp_server/server.py — lifecycle hooks (start_stdio/start) for starting/stopping P2P runtime
- ipfs_datasets_py/ipfs_datasets_py/mcp_server/hierarchical_tool_manager.py — target dispatcher for remote tool execution
- ipfs_datasets_py/ipfs_datasets_py/mcp_server/monitoring.py — metrics integration
- ipfs_datasets_py/ipfs_datasets_py/mcp_server/configs.py — add P2P configuration surface
- ipfs_datasets_py/ipfs_datasets_py/mcp_server/tool_registry.py — register new P2P tools and/or wire existing tools to TaskQueue/cache
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/p2p_tasks/runtime.py — thread-based Trio runner (good fit for anyio)
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/p2p_tasks/service.py — ops: call_tool/tool.call, cache ops, peer state
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/p2p_tasks/client.py — P2P client for integration tests
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/p2p_tasks/task_queue.py — DuckDB durable queue
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/p2p_tasks/cache_store.py — DiskTTLCache implementation
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/mcplusplus_module/trio/bridge.py — runtime-bridging pattern (if needed beyond thread runner)

**Verification**
1. Run existing MCP server tests: pytest -q ipfs_datasets_py/ipfs_datasets_py/mcp_server/_test_mcp_server.py
2. Add and run new unit tests for dispatcher/auth/cache/taskqueue.
3. Run an optional P2P integration test suite (skippable in CI when libp2p deps aren’t available).

**Decisions**
- Runtime: use anyio for the main MCP server; run the Trio/libp2p P2P service via the existing background-thread runner.
- Topology: single-process deployment (stdio MCP server plus in-process P2P service).
- Auth: unify with mcp_server auth/session model; keep shared-token mode as optional compatibility.
- Scope: implement remote tool execution, task queue, and shared cache together, using a shared ToolDispatcher/AuthContext foundation.

**Further Considerations**
1. Code migration strategy: start by importing p2p_tasks from ipfs_accelerate_py; once stabilized, vendor/move the minimal subset into ipfs_datasets_py/mcp_server/p2p to reduce cross-submodule coupling.
2. Security: decide whether P2P payload encryption remains optional or should become required when JWT auth is enabled.
3. Operational defaults: choose conservative defaults for mdns/dht/relay/holepunch in production vs dev environments.