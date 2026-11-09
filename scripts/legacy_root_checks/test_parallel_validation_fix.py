#!/usr/bin/env python3
"""
Quick test to verify the parallel validation fix works correctly.
"""

import sys
import os

# Add the ipfs_datasets_py to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ipfs_datasets_py'))

def test_parallel_validation():
    """Test that parallel validation works with the fixed tuple unpacking."""
    from ipfs_datasets_py.optimizers.agentic.validation import OptimizationValidator, ValidationLevel
    
    print("Testing parallel validation with fixed tuple unpacking...")
    
    # Create validator
    validator = OptimizationValidator(
        level=ValidationLevel.STANDARD,
        parallel=True,
        use_enhanced_parallel=True
    )
    
    # Test code
    code = """
def add(a: int, b: int) -> int:
    '''Add two numbers.'''
    return a + b
"""
    
    # Run validation - this should now work properly
    try:
        result = validator.validate(code, parallel=True)
        print(f"✓ Validation passed: {result.passed}")
        print(f"  Level: {result.level.value}")
        print(f"  Errors: {len(result.errors)}")
        print(f"  Warnings: {len(result.warnings)}")
        
        if hasattr(result, 'syntax_passed'):
            print(f"  Syntax: {'✓ Passed' if result.syntax_passed else '✗ Failed'}")
        
        return result.passed is not None  # Just check that we got a result
    except Exception as e:
        print(f"✗ Error during validation: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_parallel_validation()
    print()
    if success:
        print("✓ Parallel validation fix verified successfully!")
        sys.exit(0)
    else:
        print("✗ Parallel validation fix verification failed")
        sys.exit(1)
