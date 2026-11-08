#!/usr/bin/env python3
"""
Add optimization cache variables to __init__ method.
"""

# Read the file
with open("ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/query_unified_optimizer.py", "r") as f:
    lines = f.readlines()

# Find the line with _entity_importance_cache initialization
insert_line = None
for i, line in enumerate(lines):
    if "self._entity_importance_cache: Dict[str, float] = {}" in line:
        insert_line = i + 1  # Insert after this line
        break

if insert_line is None:
    print("ERROR: Could not find _entity_importance_cache initialization")
    import sys
    sys.exit(1)

print(f"Found _entity_importance_cache at line {insert_line}")

# Create the variables to insert
new_vars = '''        
        # Query fingerprint cache for optimize_query (38% bottleneck optimization)
        self._query_fingerprint_cache: Dict[str, str] = {}
        self._query_fingerprint_max_size = 1000
        self._fingerprint_hit_count = 0
        self._fingerprint_access_count = 0
        
        # Fast graph type detection cache (32% bottleneck optimization)
        self._graph_type_detection_cache: Dict[str, str] = {}
        self._graph_type_detection_max_size = 500
        self._type_detection_hit_count = 0
        self._type_detection_access_count = 0
'''

# Insert the variables
lines.insert(insert_line, new_vars)

# Write back
with open("ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/query_unified_optimizer.py", "w") as f:
    f.writelines(lines)

print(f"Successfully inserted optimization cache variables at line {insert_line + 1}")
print("Variables added:")
print("  - _query_fingerprint_cache")
print("  - _query_fingerprint_max_size")
print("  - _fingerprint_hit_count")
print("  - _fingerprint_access_count")
print("  - _graph_type_detection_cache")
print("  - _graph_type_detection_max_size")
print("  - _type_detection_hit_count")
print("  - _type_detection_access_count")
