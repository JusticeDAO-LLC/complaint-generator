"""
Shared Knowledge Graph Export Logic — lib shim.

When the ipfs_datasets_py submodule is present, we re-export its Neo4jExporter,
ExportConfig, ExportResult, and MigrationError so cross-repo consumers can
import from a single stable path (lib.knowledge_graph_export).

If the submodule is not installed, a standalone implementation is provided so
the lib module is always importable.
"""

from integrations.ipfs_datasets.loader import import_module_optional

try:
    _exporter, _exporter_error = import_module_optional("ipfs_datasets_py.knowledge_graphs.migration.neo4j_exporter")
    if _exporter is None:
        raise ImportError(str(_exporter_error or "graph migration exporter unavailable"))
    Neo4jExporter = _exporter.Neo4jExporter
    ExportConfig = _exporter.ExportConfig
    ExportResult = _exporter.ExportResult
    try:
        _exceptions, _exceptions_error = import_module_optional("ipfs_datasets_py.knowledge_graphs.exceptions")
        if _exceptions is None:
            raise ImportError(str(_exceptions_error or "graph exceptions unavailable"))
        MigrationError = _exceptions.MigrationError
    except (ImportError, AttributeError):
        class MigrationError(Exception):  # type: ignore[no-redef]
            def __init__(self, message, details=None):
                super().__init__(message)
                self.details = details

except (ImportError, AttributeError):
    # ---------- Standalone fallback (no submodule required) ----------
    import logging
    from dataclasses import dataclass, field
    from typing import Dict, List, Any, Optional, Callable
    from datetime import datetime
    import time

    from lib.knowledge_graph_formats import (
        GraphData, NodeData, RelationshipData, SchemaData, MigrationFormat
    )

    class MigrationError(Exception):
        def __init__(self, message, details=None):
            super().__init__(message)
            self.details = details

    @dataclass
    class ExportConfig:
        uri: str = "bolt://localhost:7687"
        username: str = "neo4j"
        password: str = "password"
        database: str = "neo4j"
        batch_size: int = 1000
        include_schema: bool = True
        include_indexes: bool = True
        include_constraints: bool = True
        output_file: Optional[str] = None
        output_format: MigrationFormat = MigrationFormat.DAG_JSON
        progress_callback: Optional[Callable[[int, int, str], None]] = None
        node_labels: Optional[List[str]] = None
        relationship_types: Optional[List[str]] = None

    @dataclass
    class ExportResult:
        success: bool
        node_count: int = 0
        relationship_count: int = 0
        duration_seconds: float = 0.0
        output_file: Optional[str] = None
        errors: List[str] = field(default_factory=list)
        warnings: List[str] = field(default_factory=list)

        def to_dict(self) -> Dict[str, Any]:
            return {
                'success': self.success,
                'node_count': self.node_count,
                'relationship_count': self.relationship_count,
                'duration_seconds': self.duration_seconds,
                'output_file': self.output_file,
                'errors': self.errors,
                'warnings': self.warnings,
            }

    class Neo4jExporter:
        def __init__(self, config: ExportConfig):
            self.config = config
            self._driver = None
            self._neo4j_available = False
            try:
                from neo4j import GraphDatabase  # type: ignore[import]
                self._GraphDatabase = GraphDatabase
                self._neo4j_available = True
            except ImportError:
                logging.warning(
                    "neo4j package not available. Install with: pip install neo4j"
                )
                self._GraphDatabase = None

        def _connect(self) -> bool:
            if not self._neo4j_available:
                raise MigrationError(
                    "neo4j package not installed. Install with: pip install neo4j"
                )
            try:
                self._driver = self._GraphDatabase.driver(
                    self.config.uri,
                    auth=(self.config.username, self.config.password),
                )
                self._driver.verify_connectivity()
                return True
            except MigrationError:
                raise
            except Exception as e:
                raise MigrationError(
                    "Failed to connect to Neo4j",
                    details={"uri": self.config.uri, "database": self.config.database},
                ) from e

        def _close(self) -> None:
            if self._driver:
                try:
                    self._driver.close()
                except Exception as e:
                    logging.warning("Failed to close Neo4j driver cleanly: %s", e)

        def _export_nodes(self, graph_data: GraphData) -> int:
            count = 0
            batch_num = 0
            query = (
                "MATCH (n) "
                "RETURN id(n) as id, labels(n) as labels, properties(n) as properties"
            )
            if self.config.node_labels:
                cond = " OR ".join(f"n:{lbl}" for lbl in self.config.node_labels)
                query = (
                    f"MATCH (n) WHERE {cond} "
                    "RETURN id(n) as id, labels(n) as labels, properties(n) as properties"
                )
            with self._driver.session(database=self.config.database) as session:
                batch = []
                for record in session.run(query):
                    batch.append(NodeData(
                        id=str(record['id']),
                        labels=record['labels'],
                        properties=dict(record['properties']),
                    ))
                    count += 1
                    if len(batch) >= self.config.batch_size:
                        graph_data.nodes.extend(batch)
                        batch_num += 1
                        batch = []
                        if self.config.progress_callback:
                            self.config.progress_callback(count, -1, f"Exported {count} nodes")
                if batch:
                    graph_data.nodes.extend(batch)
            return count

        def _export_relationships(self, graph_data: GraphData) -> int:
            count = 0
            batch_num = 0
            query = (
                "MATCH (a)-[r]->(b) "
                "RETURN id(r) as id, type(r) as type, "
                "id(a) as start, id(b) as end, properties(r) as properties"
            )
            if self.config.relationship_types:
                cond = " OR ".join(
                    f"type(r) = '{t}'" for t in self.config.relationship_types
                )
                query = (
                    f"MATCH (a)-[r]->(b) WHERE {cond} "
                    "RETURN id(r) as id, type(r) as type, "
                    "id(a) as start, id(b) as end, properties(r) as properties"
                )
            with self._driver.session(database=self.config.database) as session:
                batch = []
                for record in session.run(query):
                    batch.append(RelationshipData(
                        id=str(record['id']),
                        type=record['type'],
                        start_node=str(record['start']),
                        end_node=str(record['end']),
                        properties=dict(record['properties']),
                    ))
                    count += 1
                    if len(batch) >= self.config.batch_size:
                        graph_data.relationships.extend(batch)
                        batch_num += 1
                        batch = []
                        if self.config.progress_callback:
                            self.config.progress_callback(-1, count, f"Exported {count} relationships")
                if batch:
                    graph_data.relationships.extend(batch)
            return count

        def _export_schema(self, graph_data: GraphData) -> None:
            if not self.config.include_schema:
                return
            schema = SchemaData()
            with self._driver.session(database=self.config.database) as session:
                if self.config.include_indexes:
                    try:
                        for record in session.run("SHOW INDEXES"):
                            schema.indexes.append({
                                'name': record.get('name'),
                                'type': record.get('type'),
                                'labels': record.get('labelsOrTypes', []),
                                'properties': record.get('properties', []),
                            })
                    except Exception as e:
                        logging.warning("Could not export indexes: %s", e)
                if self.config.include_constraints:
                    try:
                        for record in session.run("SHOW CONSTRAINTS"):
                            schema.constraints.append({
                                'name': record.get('name'),
                                'type': record.get('type'),
                                'labels': record.get('labelsOrTypes', []),
                                'properties': record.get('properties', []),
                            })
                    except Exception as e:
                        logging.warning("Could not export constraints: %s", e)
                schema.node_labels = [
                    r['label'] for r in session.run("CALL db.labels()")
                ]
                schema.relationship_types = [
                    r['relationshipType']
                    for r in session.run("CALL db.relationshipTypes()")
                ]
            graph_data.schema = schema

        def export(self) -> ExportResult:
            start_time = time.time()
            result = ExportResult(success=False)
            try:
                self._connect()
                graph_data = GraphData(metadata={
                    'export_time': datetime.now().isoformat(),
                    'source_uri': self.config.uri,
                    'source_database': self.config.database,
                })
                result.node_count = self._export_nodes(graph_data)
                result.relationship_count = self._export_relationships(graph_data)
                if self.config.include_schema:
                    self._export_schema(graph_data)
                if self.config.output_file:
                    graph_data.save_to_file(self.config.output_file, self.config.output_format)
                    result.output_file = self.config.output_file
                result.duration_seconds = time.time() - start_time
                result.success = True
                return result
            except MigrationError as e:
                result.errors.append(str(e))
                result.duration_seconds = time.time() - start_time
                return result
            except Exception as e:
                result.errors.append(str(e))
                result.duration_seconds = time.time() - start_time
                return result
            finally:
                self._close()

        def export_to_graph_data(self) -> Optional[GraphData]:
            original_output = self.config.output_file
            self.config.output_file = None
            try:
                self._connect()
                graph_data = GraphData(metadata={
                    'export_time': datetime.now().isoformat(),
                    'source_uri': self.config.uri,
                    'source_database': self.config.database,
                })
                self._export_nodes(graph_data)
                self._export_relationships(graph_data)
                if self.config.include_schema:
                    self._export_schema(graph_data)
                return graph_data
            except MigrationError:
                return None
            finally:
                self._close()
                self.config.output_file = original_output


__all__ = ["Neo4jExporter", "ExportConfig", "ExportResult", "MigrationError"]
