#!/usr/bin/env python3
"""
Basic functionality test script for Cariya Wallet Backend.
This script can be run independently to verify core functionality.
"""
import sys
import os
from pathlib import Path

# Add the parent directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_transaction_id_generation():
    """Test transaction ID generation functionality."""
    try:
        from main import generate_transaction_id
        
        # Generate multiple transaction IDs
        ids = [generate_transaction_id() for _ in range(5)]
        
        # Verify uniqueness
        unique_ids = set(ids)
        if len(ids) == len(unique_ids):
            print("✅ Transaction ID generation: PASSED")
            print(f"   Generated IDs: {ids[:3]}...")
        else:
            print("❌ Transaction ID generation: FAILED - Duplicate IDs found")
            return False
            
        # Verify format (should start with SAV and be reasonably long)
        for tid in ids:
            if not tid.startswith("SAV") or len(tid) < 20:
                print("❌ Transaction ID generation: FAILED - Invalid format")
                return False
                
        return True
        
    except Exception as e:
        print(f"❌ Transaction ID generation: FAILED - {str(e)}")
        return False

def test_savings_entry_model():
    """Test the enhanced SavingsEntry model."""
    try:
        from main import SavingsEntry
        from pydantic import ValidationError
        
        # Test valid data
        valid_data = {
            "amount": 2000.0,
            "month": 3,
            "phone_number": "+256700000000",
            "payment_method": "Mobile Money",
            "reference_number": "REF123456",
            "notes": "Test entry"
        }
        
        entry = SavingsEntry(**valid_data)
        print("✅ SavingsEntry model validation: PASSED")
        print(f"   Amount: {entry.amount}")
        print(f"   Phone: {entry.phone_number}")
        print(f"   Payment Method: {entry.payment_method}")
        
        # Test invalid payment method
        try:
            invalid_data = valid_data.copy()
            invalid_data["payment_method"] = "Invalid Method"
            SavingsEntry(**invalid_data)
            print("❌ SavingsEntry validation: FAILED - Should reject invalid payment method")
            return False
        except ValidationError:
            print("✅ SavingsEntry validation: PASSED - Rejects invalid payment method")
            
        return True
        
    except Exception as e:
        print(f"❌ SavingsEntry model test: FAILED - {str(e)}")
        return False

def test_imports():
    """Test that all required modules can be imported."""
    try:
        # Test core imports
        from utils.models import SavingsTransaction, MonthlySavings
        from utils.helpers import get_mother_transaction_summary, get_payment_method_statistics
        print("✅ Core module imports: PASSED")
        
        # Test main app imports
        from main import app
        print("✅ Main app import: PASSED")
        
        return True
        
    except Exception as e:
        print(f"❌ Import test: FAILED - {str(e)}")
        return False

def test_database_schema():
    """Test database schema validation."""
    try:
        from utils.models import SavingsTransaction
        
        # Check model attributes
        required_fields = [
            'transaction_id', 'mother_id', 'month_key', 'amount',
            'phone_number', 'payment_method', 'transaction_status'
        ]
        
        model_fields = [attr for attr in dir(SavingsTransaction) if not attr.startswith('_')]
        
        for field in required_fields:
            if hasattr(SavingsTransaction, field):
                print(f"✅ Field '{field}': Found")
            else:
                print(f"❌ Field '{field}': Missing")
                return False
                
        print("✅ Database schema validation: PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Database schema test: FAILED - {str(e)}")
        return False

def main():
    """Run all basic functionality tests."""
    print("🚀 Cariya Wallet Backend - Basic Functionality Tests")
    print("=" * 60)
    
    tests = [
        ("Import Test", test_imports),
        ("Database Schema Test", test_database_schema),
        ("SavingsEntry Model Test", test_savings_entry_model),
        ("Transaction ID Generation Test", test_transaction_id_generation),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running: {test_name}")
        print("-" * 40)
        
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} failed")
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {str(e)}")
    
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The enhanced savings functionality is ready.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
