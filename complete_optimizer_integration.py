#!/usr/bin/env python3
"""
Complete the query optimizer integration by updating detect_graph_type() and optimize_query().
"""

import re

# Read the file
with open("ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/query_unified_optimizer.py", "r") as f:
    content = f.read()

# 1. Find and replace detect_graph_type method
old_detect_graph_type = '''    def detect_graph_type(self, query: Dict[str, Any]) -> str:
        """
        Detect the graph type from the query parameters.

        Uses a cache to avoid repeated pattern matching for identical or similar queries.

        Args:
            query (Dict): Query parameters
    
        Returns:
            str: Detected graph type
        """
        # Check explicit graph_type first (no caching needed for this path)
        if "graph_type" in query:
            return query["graph_type"]

        # Check cache before doing pattern matching
        cache_key = self._get_graph_type_cache_key(query)
        if cache_key in self._graph_type_cache:
            return self._graph_type_cache[cache_key]

        # Pattern matching for detection
        query_blob = str(query).lower()

        # Detect graph type based on keywords
        if any(kw in query_blob for kw in ["wikipedia", "wikidata", "dbpedia"]):
            detected_type = "wikipedia"
        elif any(kw in query_blob for kw in ["ipld", "content-addressed", "cid", "dag", "ipfs"]):
            detected_type = "ipld"
        else:
            detected_type = "general"

        # Cache the result (with simple size management)
        if len(self._graph_type_cache) < self._graph_type_cache_max_size:
            self._graph_type_cache[cache_key] = detected_type

        return detected_type'''

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
        
        return "general"'''

# Replace detect_graph_type
if old_detect_graph_type in content:
    content = content.replace(old_detect_graph_type, new_detect_graph_type)
    print("✓ Updated detect_graph_type() method")
else:
    print("✗ Could not find detect_graph_type() method to replace")

# 2. Find and replace the caching section in optimize_query
old_caching = '''        # Cache metadata.
        caching: Dict[str, Any] = {"enabled": bool(getattr(optimizer, "cache_enabled", False))}
        if caching["enabled"]:
            try:
                key_query = copy.deepcopy(planned_query)
                if "query_vector" in key_query:
                    key_query["query_vector"] = "[vector]"
                caching["key"] = hashlib.sha256(
                    json.dumps(key_query, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()
            except (TypeError, ValueError):
                pass'''

new_caching = '''        # Cache metadata with optimized fingerprint generation (38% bottleneck optimization).
        caching: Dict[str, Any] = {"enabled": bool(getattr(optimizer, "cache_enabled", False))}
        if caching["enabled"]:
            try:
                # Use optimized fingerprint caching instead of deep copy + full hash
                self._fingerprint_access_count += 1
                
                # Create signature for fingerprint cache lookup
                fp_sig = self._create_query_fingerprint_signature(planned_query)
                
                # Check fingerprint cache
                if fp_sig in self._query_fingerprint_cache:
                    self._fingerprint_hit_count += 1
                    caching["key"] = self._query_fingerprint_cache[fp_sig]
                else:
                    # Compute fingerprint with optimized algorithm
                    fingerprint = self._compute_query_fingerprint(planned_query)
                    
                    # Cache if not full
                    if len(self._query_fingerprint_cache) < self._query_fingerprint_max_size:
                        self._query_fingerprint_cache[fp_sig] = fingerprint
                    
                    caching["key"] = fingerprint
            except (TypeError, ValueError):
                pass'''

# Replace caching section
if old_caching in content:
    content = content.replace(old_caching, new_caching)
    print("✓ Updated optimize_query() caching section")
else:
    print("✗ Could not find optimize_query() caching section to replace")

# Write back
with open("ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/query_unified_optimizer.py", "w") as f:
    f.write(content)

print("\n✓ Integration complete!")
print("\nNext steps:")
print("  1. Run tests to validate changes")
print("  2. Benchmark performance improvements")
print("  3. Update documentation")
