#!/usr/bin/env python
"""
Generate decision tree JSON files for all complaint types.
"""

from complaint_analysis.decision_trees import DecisionTreeGenerator

def main():
    """Generate all decision trees."""
    output_dir = 'complaint_analysis/decision_trees'
    print(f"Generating decision trees to: {output_dir}")
    
    generator = DecisionTreeGenerator(output_dir=output_dir)
    generator.generate_all_trees()
    
    print(f"\nGenerated {len(generator.trees)} decision trees:")
    for complaint_type in sorted(generator.trees.keys()):
        tree = generator.trees[complaint_type]
        print(f"  - {complaint_type}: {len(tree.questions)} questions, {len(tree.required_fields)} required fields")
    
    print(f"\nDecision tree JSON files saved to: {output_dir}/")

if __name__ == '__main__':
    main()
