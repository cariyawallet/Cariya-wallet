#!/usr/bin/env python3
"""
Test runner script for Cariya Wallet Backend tests.
"""
import sys
import os
import pytest
from pathlib import Path

# Add the parent directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    """Run all tests with proper configuration."""
    # Test configuration
    test_args = [
        "--verbose",
        "--tb=short",
        "--strict-markers",
        "--disable-warnings",
        "--color=yes",
        "--durations=10",
        "--maxfail=5",
        "--cov=utils",
        "--cov=main",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml"
    ]
    
    # Add test files
    test_files = [
        "tests/test_savings_functionality.py",
        "tests/test_api_endpoints.py"
    ]
    
    # Run tests
    print("🚀 Starting Cariya Wallet Backend Tests...")
    print("=" * 60)
    
    exit_code = pytest.main(test_args + test_files)
    
    if exit_code == 0:
        print("\n✅ All tests passed successfully!")
    else:
        print(f"\n❌ Tests failed with exit code: {exit_code}")
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
