# IPFS Datasets Py Compatibility Matrix

This matrix defines how complaint-generator Phase 0 integration capabilities map to `ipfs_datasets_py` modules and feature flags.

## Capability Mapping

| Capability | Primary Module(s) | Fallback Module(s) | Feature Flag | Status Contract |
|---|---|---|---|---|
| Legal datasets | `ipfs_datasets_py.legal_scrapers` | `ipfs_datasets_py.legal_research` | `IPFS_DATASETS_ENHANCED_LEGAL` | `available`, `enabled`, `active`, `details` |
| Search tools | `ipfs_datasets_py.web_archiving` | `ipfs_datasets_py.search` | `IPFS_DATASETS_ENHANCED_SEARCH` | `available`, `enabled`, `active`, `details` |
| Graph tools | `ipfs_datasets_py.graphrag` | `ipfs_datasets_py.graphrag_integration` | `IPFS_DATASETS_ENHANCED_GRAPH` | `available`, `enabled`, `active`, `details` |
| Vector tools | `ipfs_datasets_py.search.search_embeddings` | `ipfs_datasets_py.embeddings_router` | `IPFS_DATASETS_ENHANCED_VECTOR` | `available`, `enabled`, `active`, `details` |
| Optimizer tools | `ipfs_datasets_py.optimizers` | `ipfs_datasets_py.graphrag.query_optimizer` | `IPFS_DATASETS_ENHANCED_OPTIMIZER` | `available`, `enabled`, `active`, `details` |
| MCP tools | `ipfs_datasets_py.mcp_server` | `ipfs_datasets_py.mcp` | Always-on detection | `available`, `enabled`, `active`, `details` |

## Runtime Contract

The adapter exposes a registry per capability:

```json
{
  "legal_datasets": {
    "available": true,
    "enabled": false,
    "active": false,
    "details": null
  }
}
```

Definitions:

- `available`: a compatible module import succeeded
- `enabled`: feature flag is enabled in env/config
- `active`: both `available` and `enabled` are true
- `details`: first import error summary when unavailable

## Notes

- Phase 0 does not change mediator runtime behavior by default.
- New integration code lives in `mediator/integrations/` and is designed for incremental adoption by existing hooks.
- If `ipfs_datasets_py` APIs change, update module mappings in `mediator/integrations/adapter.py` and this matrix together.