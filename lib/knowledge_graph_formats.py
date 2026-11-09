"""
Shared Knowledge Graph Data Formats — lib shim.

When the ipfs_datasets_py submodule is present, we expose all its migration
format types (GraphData, NodeData, RelationshipData, SchemaData, MigrationFormat,
register_format, registered_formats) through this module so cross-repo consumers
can import from a single stable path (lib.knowledge_graph_formats).

If the submodule is not installed, a lightweight pure-Python fallback is provided
so the lib module is always importable.
"""

from integrations.ipfs_datasets.loader import import_module_optional

try:
    _formats, _formats_error = import_module_optional("ipfs_datasets_py.knowledge_graphs.migration.formats")
    if _formats is None:
        raise ImportError(str(_formats_error or "graph migration formats unavailable"))
    MigrationFormat = _formats.MigrationFormat
    NodeData = _formats.NodeData
    RelationshipData = _formats.RelationshipData
    SchemaData = _formats.SchemaData
    GraphData = _formats.GraphData
    register_format = _formats.register_format
    registered_formats = _formats.registered_formats
except (ImportError, AttributeError):
    # --- Lightweight fallback (no external dependencies) ---
    import json
    from dataclasses import dataclass, field
    from typing import Callable, Dict, Iterator, List, Any, Optional
    from enum import Enum

    class MigrationFormat(Enum):
        DAG_JSON = "dag-json"
        JSON_LINES = "jsonlines"
        CAR = "car"
        GRAPHML = "graphml"
        GEXF = "gexf"
        PAJEK = "pajek"

    @dataclass
    class NodeData:
        id: str
        labels: List[str] = field(default_factory=list)
        properties: Dict[str, Any] = field(default_factory=dict)
        def to_dict(self): return {'id': self.id, 'labels': self.labels, 'properties': self.properties}
        @classmethod
        def from_dict(cls, d): return cls(id=d['id'], labels=d.get('labels', []), properties=d.get('properties', {}))
        def to_json(self): return json.dumps(self.to_dict())

    @dataclass
    class RelationshipData:
        id: str
        type: str
        start_node: str
        end_node: str
        properties: Dict[str, Any] = field(default_factory=dict)
        def to_dict(self): return {'id': self.id, 'type': self.type, 'start_node': self.start_node, 'end_node': self.end_node, 'properties': self.properties}
        @classmethod
        def from_dict(cls, d): return cls(id=d['id'], type=d['type'], start_node=d['start_node'], end_node=d['end_node'], properties=d.get('properties', {}))
        def to_json(self): return json.dumps(self.to_dict())

    @dataclass
    class SchemaData:
        indexes: List[Dict[str, Any]] = field(default_factory=list)
        constraints: List[Dict[str, Any]] = field(default_factory=list)
        node_labels: List[str] = field(default_factory=list)
        relationship_types: List[str] = field(default_factory=list)
        def to_dict(self): return {'indexes': self.indexes, 'constraints': self.constraints, 'node_labels': self.node_labels, 'relationship_types': self.relationship_types}
        @classmethod
        def from_dict(cls, d): return cls(indexes=d.get('indexes', []), constraints=d.get('constraints', []), node_labels=d.get('node_labels', []), relationship_types=d.get('relationship_types', []))

    _SaveHandler = Callable[["GraphData", str], None]
    _LoadHandler = Callable[[str], "GraphData"]

    class _FormatRegistry:
        def __init__(self):
            self._save: Dict = {}
            self._load: Dict = {}
        def register(self, fmt, save, load):
            self._save[fmt] = save
            self._load[fmt] = load
        @staticmethod
        def _unsupported_format(operation, fmt, handlers):
            requested = getattr(fmt, "value", fmt)
            available = sorted(
                str(getattr(registered, "value", registered))
                for registered in handlers
            )
            available_text = ", ".join(available) if available else "none"
            return ValueError(
                f"Unsupported {operation} format {requested!r}: no handler is "
                f"registered. Available {operation} formats: {available_text}. "
                "Call register_format() to add a handler."
            )
        def save(self, graph, filepath, fmt):
            h = self._save.get(fmt)
            if h is None:
                raise self._unsupported_format("save", fmt, self._save)
            h(graph, filepath)
        def load(self, filepath, fmt):
            h = self._load.get(fmt)
            if h is None:
                raise self._unsupported_format("load", fmt, self._load)
            return h(filepath)
        def registered_formats(self): return [f for f in self._save if f in self._load]

    _registry = _FormatRegistry()

    def register_format(fmt, save, load): _registry.register(fmt, save, load)
    def registered_formats(): return _registry.registered_formats()

    @dataclass
    class GraphData:
        nodes: List[NodeData] = field(default_factory=list)
        relationships: List[RelationshipData] = field(default_factory=list)
        schema: Optional[SchemaData] = None
        metadata: Dict[str, Any] = field(default_factory=dict)
        def to_dict(self):
            return {'nodes': [n.to_dict() for n in self.nodes], 'relationships': [r.to_dict() for r in self.relationships], 'schema': self.schema.to_dict() if self.schema else None, 'metadata': self.metadata}
        @classmethod
        def from_dict(cls, d):
            return cls(nodes=[NodeData.from_dict(n) for n in d.get('nodes', [])], relationships=[RelationshipData.from_dict(r) for r in d.get('relationships', [])], schema=SchemaData.from_dict(d['schema']) if d.get('schema') else None, metadata=d.get('metadata', {}))
        def to_json(self, indent=None): return json.dumps(self.to_dict(), indent=indent)
        @classmethod
        def from_json(cls, s): return cls.from_dict(json.loads(s))
        def save_to_file(self, filepath, format=MigrationFormat.DAG_JSON): _registry.save(self, filepath, format)
        @classmethod
        def load_from_file(cls, filepath, format=MigrationFormat.DAG_JSON): return _registry.load(filepath, format)
        def iter_nodes_chunked(self, chunk_size=500):
            for i in range(0, len(self.nodes), chunk_size): yield self.nodes[i:i+chunk_size]
        def iter_relationships_chunked(self, chunk_size=500):
            for i in range(0, len(self.relationships), chunk_size): yield self.relationships[i:i+chunk_size]

    def _builtin_save_dag_json(graph, filepath):
        with open(filepath, 'w') as f: f.write(graph.to_json(indent=2))
    def _builtin_load_dag_json(filepath):
        with open(filepath) as f: return GraphData.from_json(f.read())
    def _builtin_save_json_lines(graph, filepath):
        with open(filepath, 'w') as f:
            for n in graph.nodes: f.write(json.dumps({'type': 'node', 'data': n.to_dict()}) + '\n')
            for r in graph.relationships: f.write(json.dumps({'type': 'relationship', 'data': r.to_dict()}) + '\n')
    def _builtin_load_json_lines(filepath):
        nodes, rels, schema = [], [], None
        with open(filepath) as f:
            for line in f:
                if not line.strip(): continue
                obj = json.loads(line)
                if obj['type'] == 'node': nodes.append(NodeData.from_dict(obj['data']))
                elif obj['type'] == 'relationship': rels.append(RelationshipData.from_dict(obj['data']))
                elif obj['type'] == 'schema': schema = SchemaData.from_dict(obj['data'])
        return GraphData(nodes=nodes, relationships=rels, schema=schema)

    register_format(MigrationFormat.DAG_JSON, _builtin_save_dag_json, _builtin_load_dag_json)
    register_format(MigrationFormat.JSON_LINES, _builtin_save_json_lines, _builtin_load_json_lines)

__all__ = [
    "MigrationFormat",
    "NodeData",
    "RelationshipData",
    "SchemaData",
    "GraphData",
    "register_format",
    "registered_formats",
]
