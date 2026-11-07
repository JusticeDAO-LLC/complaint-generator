# Applications package

The `applications` package is the HTTP, case-route, and process-launch surface recorded by the repository module map at [`docs/architecture/repository_module_map.json`](../docs/architecture/repository_module_map.json). The package directory is `applications`, and its initializer is [`applications/__init__.py`](__init__.py).

## Interface

Public entry for new code is [`applications.interface`](interface.py).

| Field | Value |
| --- | --- |
| Schema | `complaint-generator/module-interface@1` |
| Interface version | `1.0.0` |
| Module | `applications.interface` |

`INTERFACE_VERSION` is `1.0.0`. Importing `applications.interface` records owner modules and symbol names. That import does not import the owner modules, start a server, or read a private workspace path.

New code imports `applications.interface` rather than `complaint_workspace`. `applications.complaint_workspace` is not an owner of this interface and is not imported by the facade. The module map lists [`applications/complaint_workspace.py`](complaint_workspace.py) as the largest Python module in the repository and [`applications/dashboard_ui.py`](dashboard_ui.py) among the largest modules. Those files stay implementation modules behind the facade.

## Owner modules

The interface names these owner modules and no others:

| Owner module | Source | Public symbols |
| --- | --- | --- |
| `applications.server` | [`applications/server.py`](server.py) | `SERVER` |
| `applications.case_routes` | [`applications/case_routes.py`](case_routes.py) | `CASE_ROUTE_KINDS`, `compose_case_routes` |
| `applications.launcher` | [`applications/launcher.py`](launcher.py) | `launch_application`, `start_configured_applications`, `create_uvicorn_app_for_type` |

`SERVER` is the public route symbol on `applications.server`. `CASE_ROUTE_KINDS` and `compose_case_routes` are the public route symbols on `applications.case_routes`. Workspace entry symbols are `launch_application`, `start_configured_applications`, and `create_uvicorn_app_for_type` on `applications.launcher`.

This document names only those routes. It does not add a route the interface does not name.

## Module map notes

The same module map records two duplicate-owner concerns that include modules under this package:

- CLI: [`applications/cli.py`](cli.py) is the legacy interactive CLI, and [`applications/complaint_cli.py`](complaint_cli.py) is the workspace Typer CLI. `complaint_generator/cli.py` is a package facade that re-exports `applications.complaint_cli`.
- MCP: [`applications/complaint_mcp_protocol.py`](complaint_mcp_protocol.py) is the MCP JSON-RPC protocol implementation, and [`applications/complaint_mcp_server.py`](complaint_mcp_server.py) is the MCP server process entrypoint. `complaint_generator` holds thin facades for both.

Those CLI and MCP modules are duplicate-owner records in the module map. They are not owner modules of `applications.interface` and they are not public route symbols of interface version `1.0.0`.
