#!/usr/bin/env python3
"""
Test script to verify probate complaint type integration.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from complaint_analysis import (
    SeedGenerator,
    DecisionTreeGenerator,
    get_registered_types
)
from complaint_analysis.keywords import _global_registry as registry

def test_probate_registration():
    """Test that probate is registered as a complaint type."""
    print("Testing probate registration...")
    
    types = get_registered_types()
    print(f"✓ Found {len(types)} registered complaint types")
    
    if 'probate' in types:
        print("✓ Probate is registered")
    else:
        print("✗ Probate is NOT registered")
        return False
    
    return True


def test_probate_keywords():
    """Test that probate has keywords registered."""
    print("\nTesting probate keywords...")
    
    keywords = registry.get_keywords('complaint', complaint_type='probate')
    print(f"✓ Found {len(keywords)} probate keywords")
    
    # Check for some expected keywords
    expected = ['probate', 'executor', 'will', 'trust', 'estate', 'decedent']
    found = [kw for kw in expected if kw in keywords]
    
    if len(found) == len(expected):
        print(f"✓ All expected keywords found: {found}")
    else:
        print(f"✗ Missing keywords. Found: {found}, Expected: {expected}")
        return False
    
    return True


def test_probate_seed_generation():
    """Test that probate seeds can be generated."""
    print("\nTesting probate seed generation...")
    
    generator = SeedGenerator()
    templates = generator.templates  # This is a Dict[str, SeedComplaintTemplate]
    
    # Check if probate template exists
    probate_template_ids = [tid for tid in templates.keys() if 'probate' in tid]
    
    if probate_template_ids:
        print(f"✓ Generated {len(probate_template_ids)} probate seed template(s)")
        template_id = probate_template_ids[0]
        template = templates[template_id]
        print(f"  Template ID: {template.id}")
        print(f"  Template type: {template.type}")
        print(f"  Required fields: {len(template.required_fields)}")
        print(f"  Keywords: {len(template.keywords)}")
    else:
        print("✗ No probate templates generated")
        print(f"  Available templates: {list(templates.keys())}")
        return False
    
    return True


def test_probate_decision_tree():
    """Test that probate decision tree exists."""
    print("\nTesting probate decision tree...")
    
    tree_generator = DecisionTreeGenerator()
    
    # Load the probate tree
    import json
    tree_path = os.path.join(
        os.path.dirname(__file__),
        'complaint_analysis',
        'decision_trees',
        'probate_tree.json'
    )
    
    if os.path.exists(tree_path):
        with open(tree_path, 'r') as f:
            tree_data = json.load(f)
        
        print(f"✓ Probate decision tree exists")
        print(f"  Complaint type: {tree_data.get('complaint_type')}")
        print(f"  Questions: {len(tree_data.get('questions', {}))}")
        print(f"  Required fields: {len(tree_data.get('required_fields', []))}")
        
        # Check for expected questions
        questions = tree_data.get('questions', {})
        if any('decedent' in q.get('question', '').lower() for q in questions.values()):
            print("  ✓ Contains decedent-related questions")
        
        return True
    else:
        print(f"✗ Probate decision tree not found at {tree_path}")
        return False


def test_probate_legal_patterns():
    """Test that probate legal patterns are registered."""
    print("\nTesting probate legal patterns...")
    
    from complaint_analysis.legal_patterns import get_legal_terms
    
    patterns = get_legal_terms('probate')
    
    if patterns:
        print(f"✓ Found {len(patterns)} probate legal patterns")
        # Show a few examples
        print(f"  Examples: {patterns[:3]}")
    else:
        print("✗ No probate legal patterns found")
        return False
    
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("PROBATE COMPLAINT TYPE INTEGRATION TEST")
    print("=" * 60)
    
    tests = [
        test_probate_registration,
        test_probate_keywords,
        test_probate_seed_generation,
        test_probate_decision_tree,
        test_probate_legal_patterns,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    if all(results):
        print("\n✓ All tests PASSED!")
        return 0
    else:
        print("\n✗ Some tests FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())
