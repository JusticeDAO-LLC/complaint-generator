#!/usr/bin/env python3
"""
Insert optimization methods into UnifiedGraphRAGQueryOptimizer.

Adds get_optimization_stats and helper methods for query fingerprinting and
fast graph type detection.
"""

import sys

# Read the file
with open("ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/query_unified_optimizer.py", "r") as f:
    lines = f.readlines()

# Find the line with "def get_execution_plan"
insert_line = None
for i, line in enumerate(lines):
    if "def get_execution_plan(self, query: Dict[str, Any], priority: str = " in line:
        insert_line = i
        break

if insert_line is None:
    print("ERROR: Could not find get_execution_plan method")
    sys.exit(1)

print(f"Found get_execution_plan at line {insert_line + 1}")

# Create the methods to insert
new_methods = '''    def _create_query_fingerprint_signature(self, query: Dict[str, Any]) -> str:
        """
        Create lightweight signature for query fingerprint cache lookup.
        
        Much faster than full hash - used for dict key lookup.
        Optimizes the 38% cache key generation bottleneck.
        """
        parts = []
        
        # Vector query signature (ignore actual vector data)
        if "query_vector" in query:
            vector_len = len(query.get("query_vector", []))
            parts.append(f "vec_{vector_len}")
            parts.append(f"vr_{query.get('max_vector_results', 5)}")
        
        # Text query signature
        query_text = query.get("query", query.get("query_text", ""))
        if query_text:
            text_hash = hash(str(query_text)[:50]) % (2**31)
            parts.append(f"txt_{text_hash}")
        
        # Traversal parameters
        traversal = query.get("traversal", {})
        if isinstance(traversal, dict):
            parts.append(f"td_{traversal.get('max_depth', 2)}")
            edge_types = traversal.get("edge_types", [])
            if edge_types:
                parts.append(f"et_{len(edge_types)}")
        
        # Priority
        priority = query.get("priority", "normal")
        parts.append(f"p_{priority}")
        
        return "|".join(parts)
    
    def _compute_query_fingerprint(self, query: Dict[str, Any]) -> str:
        """
        Compute query fingerprint with minimal processing.
        
        Optimizations:
        - Replace vectors with placeholder early (avoid hashing large arrays)
        - Use incremental string building instead of deepcopy
        - Minimal normalization
        """
        # Normalize query for hashing
        normalized = {}
        for key, value in query.items():
            if key == "query_vector" and isinstance(value, (list, tuple)):
                # Replace vector with size hint
                normalized[key] = f"[vector_{len(value)}]"
            elif isinstance(value, dict):
                # Recursively normalize dicts (one level only for speed)
                normalized[key] = {k: v if not isinstance(v, (list, tuple)) or len(v) < 10 else f"[list_{len(v)}]" 
                                  for k, v in value.items()}
            elif isinstance(value, (list, tuple)) and len(value) > 10:
                # Replace large lists with size hint
                normalized[key] = f"[list_{len(value)}]"
            else:
                normalized[key] = value
        
        # Hash the normalized query
        try:
            import json
            json_str = json.dumps(normalized, sort_keys=True, default=str)
            return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        except (TypeError, ValueError):
            # Fallback for non-serializable objects
            return hashlib.sha256(str(normalized).encode("utf-8")).hexdigest()
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """
        Get optimization statistics for monitoring performance improvements.
        
        Returns:
            Dict with cache hit rates and counts
        """
        fp_hit_rate = (self._fingerprint_hit_count / self._fingerprint_access_count * 100) if self._fingerprint_access_count > 0 else 0
        type_hit_rate = (self._type_detection_hit_count / self._type_detection_access_count * 100) if self._type_detection_access_count > 0 else 0
        
        return {
            "query_fingerprint_cache": {
                "size": len(self._query_fingerprint_cache),
                "max_size": self._query_fingerprint_max_size,
                "accesses": self._fingerprint_access_count,
                "hits": self._fingerprint_hit_count,
                "hit_rate_percent": fp_hit_rate,
            },
            "graph_type_detection_cache": {
                "size": len(self._graph_type_detection_cache),
                "max_size": self._graph_type_detection_max_size,
                "accesses": self._type_detection_access_count,
                "hits": self._type_detection_hit_count,
                "hit_rate_percent": type_hit_rate,
            }
        }

'''

# Insert the methods
lines.insert(insert_line, new_methods)

# Write back
with open("ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/query_unified_optimizer.py", "w") as f:
    f.writelines(lines)

print(f"Successfully inserted optimization methods at line {insert_line}")
print("Methods added:")
print("  - _create_query_fingerprint_signature")
print("  - _compute_query_fingerprint")
print("  - get_optimization_stats")
