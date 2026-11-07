# Complaint generator package

The `complaint_generator` package is the versioned facade for workspace services, the package CLI entry, and the MCP tool surface. The package directory is `complaint_generator`, and its initializer is [`complaint_generator/__init__.py`](__init__.py). The repository module map records this package at [`docs/architecture/repository_module_map.json`](../docs/architecture/repository_module_map.json).

Running the package as a module uses [`complaint_generator/__main__.py`](__main__.py), which calls `main` from the CLI owner below.

## Interface

Public entry for this package is [`complaint_generator.interface`](interface.py).

| Field | Value |
| --- | --- |
| Schema | `complaint-generator/module-interface@1` |
| Interface version | `1.0.0` |
| Module | `complaint_generator.interface` |

The interface version is `1.0.0`. `INTERFACE_VERSION` is `1.0.0`. Importing `complaint_generator.interface` records the owner modules and their public symbol names. That import does not import those owners, start a server, or read a private workspace path.

## Owner modules

The interface names these owner modules and no others. The CLI module the interface lists is `complaint_generator.entrypoints`. The MCP module the interface lists is `complaint_generator.mcp`.

| Owner module | Source | Public symbols |
| --- | --- | --- |
| `complaint_generator.entrypoints` | [`complaint_generator/entrypoints.py`](entrypoints.py) | `main`, `run_main` |
| `complaint_generator.workspace` | [`complaint_generator/workspace.py`](workspace.py) | `ComplaintWorkspaceService`, `create_identity`, `start_session`, `generate_complaint` |
| `complaint_generator.mcp` | [`complaint_generator/mcp.py`](mcp.py) | `handle_jsonrpc_message`, `tool_list_payload` |

`main` and `run_main` are the public CLI symbols on `complaint_generator.entrypoints`. Workspace symbols are `ComplaintWorkspaceService`, `create_identity`, `start_session`, and `generate_complaint` on `complaint_generator.workspace`. MCP symbols are `handle_jsonrpc_message` and `tool_list_payload` on `complaint_generator.mcp`.

This document names only those public symbols for interface version `1.0.0`. It does not add a symbol the interface does not name.

## Modules beside the interface

These modules already exist in the package. They are not owner modules of `complaint_generator.interface` and they are not the CLI or MCP modules that interface version `1.0.0` lists.

| Module | Source | Relationship to the interface |
| --- | --- | --- |
| Package CLI facade | [`cli.py`](cli.py) | `complaint_generator.cli` re-exports the workspace Typer application. It is not the CLI module listed by the interface. |
| MCP server process | [`mcp_server.py`](mcp_server.py) | `complaint_generator.mcp_server` is the process entry that can start a server. It is not the MCP module listed by the interface. |

New code that needs the recorded public surface imports `complaint_generator.interface`. It does not treat `complaint_generator.cli` or `complaint_generator.mcp_server` as owners of interface version `1.0.0`.
