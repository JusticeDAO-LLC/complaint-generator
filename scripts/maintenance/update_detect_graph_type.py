#!/usr/bin/env python3
"""
Update detect_graph_type to use optimized caching and add helper methods.
"""

# Read the file
with open("ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/query_unified_optimizer.py", "r") as f:
    lines = f.readlines()

# Find detect_graph_type method
start_line = None
end_line = None
for i, line in enumerate(lines):
    if "def detect_graph_type(self, query: Dict[str, Any]) -> str:" in line:
        start_line = i
    if start_line is not None and i > start_line and line.strip().startswith("def ") and "self" in line:
        end_line = i
        break

if start_line is None:
    print("ERROR: Could not find detect_graph_type method")
    import sys
    sys.exit(1)

print(f"Found detect_graph_type at line {start_line + 1}")
if end_line:
    print(f"Method ends at line {end_line}")
else:
    print("Method continues to end of class")
    # Find next method after detect_graph_type
    for i in range(start_line + 1, len(lines)):
        if lines[i].strip().startswith("def ") and "self" in lines[i]:
            end_line = i
            break
    if not end_line:
        end_line = len(lines)

print(f"Replacing lines {start_line + 1} to {end_line}")

# New implementation
new_detect_graph_type = '''    def detect_graph_type(self, query: Dict[str, Any]) -> str:
        """
        Detect the graph type from the query parameters.

        Uses fast heuristic-based detection with caching to avoid repeated pattern matching.
        Optimized to reduce 32% bottleneck from graph type detection.

        Args:
            query (Dict): Query parameters
    
        Returns:
            str: Detected graph type
        """
        self._type_detection_access_count += 1
        
        # Check explicit graph_type first (no caching needed for this path)
        if "graph_type" in query:
            return query["graph_type"]
        
        # Create fast detection signature
        detection_sig = self._create_fast_detection_signature(query)
        
        # Check detection cache
        if detection_sig in self._graph_type_detection_cache:
            self._type_detection_hit_count += 1
            return self._graph_type_detection_cache[detection_sig]

        # Fast heuristic detection (O(1) checks instead of exhaustive string search)
        detected_type = self._detect_by_heuristics(query)
        
        # Cache the result (with simple size management)
        if len(self._graph_type_detection_cache) < self._graph_type_detection_max_size:
            self._graph_type_detection_cache[detection_sig] = detected_type
        
        return detected_type
    
    def _create_fast_detection_signature(self, query: Dict[str, Any]) -> str:
        """Create lightweight signature for fast graph type detection cache."""
        parts = []
        
        # Check explicit markers first (highest priority)
        if "entity_source" in query:
            parts.append(f"src:{query['entity_source']}")
        
        # Check query text for keywords (first 30 chars for speed)
        query_text = query.get("query", query.get("query_text", ""))
        if query_text:
            text_prefix = str(query_text)[:30].lower()
            if "wikipedia" in text_prefix or "wikidata" in text_prefix:
                parts.append("wiki_text")
            elif "ipld" in text_prefix or "cid" in text_prefix:
                parts.append("ipld_text")
        
        # Check entity sources list
        entity_sources = query.get("entity_sources", [])
        if isinstance(entity_sources, list) and len(entity_sources) > 1:
            parts.append("multi_source")
        
        return "|".join(parts) if parts else "default"
    
    def _detect_by_heuristics(self, query: Dict[str, Any]) -> str:
        """
        Fast heuristic-based graph type detection.
        
        Uses O(1) property checks instead of exhaustive string searches.
        Optimizes the 32% graph type detection bottleneck.
        """
        # Check entity_source field (fastest check)
        entity_source = query.get("entity_source", "").lower()
        if entity_source == "wikipedia":
            return "wikipedia"
        elif entity_source == "ipld":
            return "ipld"
        
        # Check entity_sources list for mixed graphs
        entity_sources = query.get("entity_sources", [])
        if isinstance(entity_sources, list) and len(entity_sources) > 1:
            return "mixed"
        
        # Check query text for type keywords (limited substring search)
        query_text = str(query.get("query", query.get("query_text", ""))).lower()
        if query_text:
            # Check for Wikipedia markers
            if any(kw in query_text for kw in ["wikipedia", "wikidata", "dbpedia"]):
                return "wikipedia"
            # Check for IPLD markers
            elif any(kw in query_text for kw in ["ipld", "content-addressed", "cid", "dag", "ipfs"]):
                return "ipld"
        
        # Fallback: check entity_ids format
        entity_ids = query.get("entity_ids", [])
        if entity_ids and isinstance(entity_ids, list):
            # IPLD entities often start with 'Qm' or 'bafy' (CID prefixes)
            first_id = str(entity_ids[0]) if entity_ids else ""
            if first_id.startswith(("Qm", "bafy", "zdpu", "zb2r")):
                return "ipld"
        
        return "general"

'''

# Replace the method
new_lines = lines[:start_line] + [new_detect_graph_type] + lines[end_line:]

# Write back
with open("ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/query_unified_optimizer.py", "w") as f:
    f.writelines(new_lines)

print(f"✓ Replaced detect_graph_type and added helper methods")
print(f"  - Updated detect_graph_type() with caching")
print(f"  - Added _create_fast_detection_signature()")
print(f"  - Added _detect_by_heuristics()")
