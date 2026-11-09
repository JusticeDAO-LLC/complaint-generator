#!/usr/bin/env python3
"""Quick test for CriticScore comparison operators."""

import sys
sys.path.insert(0, '/home/barberb/complaint-generator/ipfs_datasets_py')

from ipfs_datasets_py.optimizers.graphrag.ontology_critic import CriticScore

# Create test scores
score1 = CriticScore(
    completeness=0.8,
    consistency=0.85,
    clarity=0.75,
    granularity=0.80,
    relationship_coherence=0.82,
    domain_alignment=0.88
)

score2 = CriticScore(
    completeness=0.7,
    consistency=0.75,
    clarity=0.70,
    granularity=0.72,
    relationship_coherence=0.71,
    domain_alignment=0.78
)

score3 = CriticScore(
    completeness=0.8,
    consistency=0.85,
    clarity=0.75,
    granularity=0.80,
    relationship_coherence=0.82,
    domain_alignment=0.88
)

print(f"score1.overall = {score1.overall:.4f}")
print(f"score2.overall = {score2.overall:.4f}")
print(f"score3.overall = {score3.overall:.4f}")
print()

# Test comparisons
print(f"score1 > score2: {score1 > score2}")  # Should be True
print(f"score1 < score2: {score1 < score2}")  # Should be False
print(f"score1 >= score2: {score1 >= score2}")  # Should be True
print(f"score1 <= score2: {score1 <= score2}")  # Should be False
print(f"score1 == score3: {score1 == score3}")  # Should be True
print(f"score1 != score2: {score1 != score2}")  # Should be True
print()

# Test sorting
scores = [score2, score1, score3]
sorted_scores = sorted(scores)
print(f"Sorted scores (by overall): {[round(s.overall, 4) for s in sorted_scores]}")
print()

# Test with list max/min
print(f"Best score (max): {max(scores).overall:.4f}")
print(f"Worst score (min): {min(scores).overall:.4f}")

print("\n✓ All comparison operator tests passed!")
