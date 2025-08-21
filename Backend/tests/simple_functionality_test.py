#!/usr/bin/env python3
"""
Simple functionality test for the enhanced savings functionality.
This script tests the core functionality without pytest dependencies.
"""
import sys
import os
from pathlib import Path

# Add the parent directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_savings_entry_validation():
    """Test the enhanced SavingsEntry validation."""
    print("🔍 Testing SavingsEntry validation...")
    
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
        print("✅ Valid data accepted")
        
        # Test invalid amount
        try:
            invalid_amount_data = valid_data.copy()
            invalid_amount_data["amount"] = -100.0
            SavingsEntry(**invalid_amount_data)
            print("❌ Invalid amount should have been rejected")
            return False
        except ValidationError as e:
            print("✅ Invalid amount correctly rejected")
        
        # Test invalid month
        try:
            invalid_month_data = valid_data.copy()
            invalid_month_data["month"] = 15
            SavingsEntry(**invalid_month_data)
            print("❌ Invalid month should have been rejected")
            return False
        except ValidationError as e:
            print("✅ Invalid month correctly rejected")
        
        # Test invalid phone number
        try:
            invalid_phone_data = valid_data.copy()
            invalid_phone_data["phone_number"] = "1234567890"
            SavingsEntry(**invalid_phone_data)
            print("❌ Invalid phone number should have been rejected")
            return False
        except ValidationError as e:
            print("✅ Invalid phone number correctly rejected")
        
        # Test invalid payment method
        try:
            invalid_payment_data = valid_data.copy()
            invalid_payment_data["payment_method"] = "Invalid Method"
            SavingsEntry(**invalid_payment_data)
            print("❌ Invalid payment method should have been rejected")
            return False
        except ValidationError as e:
            print("✅ Invalid payment method correctly rejected")
        
        print("✅ All validation tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Validation test failed: {str(e)}")
        return False

def test_transaction_id_generation():
    """Test transaction ID generation."""
    print("\n🔍 Testing transaction ID generation...")
    
    try:
        from main import generate_transaction_id
        
        # Generate multiple IDs
        ids = [generate_transaction_id() for _ in range(5)]
        
        # Check uniqueness
        unique_ids = set(ids)
        if len(ids) == len(unique_ids):
            print("✅ Generated unique transaction IDs")
        else:
            print("❌ Duplicate transaction IDs generated")
            return False
        
        # Check format
        for tid in ids:
            if not tid.startswith("SAV") or len(tid) < 20:
                print(f"❌ Invalid transaction ID format: {tid}")
                return False
        
        print("✅ All transaction IDs have correct format")
        print(f"   Sample IDs: {ids[:3]}")
        return True
        
    except Exception as e:
        print(f"❌ Transaction ID generation test failed: {str(e)}")
        return False

def test_models_import():
    """Test that all required models can be imported."""
    print("\n🔍 Testing model imports...")
    
    try:
        from utils.models import SavingsTransaction, MonthlySavings, Mother
        print("✅ All required models imported successfully")
        return True
    except Exception as e:
        print(f"❌ Model import failed: {str(e)}")
        return False

def test_helper_functions():
    """Test that helper functions can be imported."""
    print("\n🔍 Testing helper function imports...")
    
    try:
        from utils.helpers import (
            calculate_expected_savings, 
            get_mother_transaction_summary, 
            get_payment_method_statistics
        )
        print("✅ All helper functions imported successfully")
        return True
    except Exception as e:
        print(f"❌ Helper function import failed: {str(e)}")
        return False

def test_expected_savings_calculation():
    """Test the expected savings calculation."""
    print("\n🔍 Testing expected savings calculation...")
    
    try:
        from utils.helpers import calculate_expected_savings
        
        # Test calculations
        assert calculate_expected_savings(1) == 1000.0
        assert calculate_expected_savings(2) == 2000.0
        assert calculate_expected_savings(3) == 3000.0
        assert calculate_expected_savings(5) == 5000.0
        
        print("✅ Expected savings calculation working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Expected savings calculation test failed: {str(e)}")
        return False

def test_api_endpoints():
    """Test that the API endpoints are properly defined."""
    print("\n🔍 Testing API endpoint definitions...")
    
    try:
        from main import app
        
        # Check if the app has the expected endpoints
        routes = [route.path for route in app.routes if hasattr(route, 'path')]
        
        expected_endpoints = [
            "/mothers/{mother_id}/savings",
            "/savings-transactions",
            "/savings-transactions/{transaction_id}",
            "/mothers/{mother_id}/transaction-summary",
            "/payment-method-statistics"
        ]
        
        missing_endpoints = []
        for endpoint in expected_endpoints:
            # Check if any route contains the endpoint pattern
            found = False
            for route in routes:
                # Remove path parameters for comparison
                route_clean = route.replace("/{", "/").replace("}", "")
                endpoint_clean = endpoint.replace("/{", "/").replace("}", "")
                if route_clean == endpoint_clean:
                    found = True
                    break
            if not found:
                missing_endpoints.append(endpoint)
        
        if missing_endpoints:
            print(f"❌ Missing endpoints: {missing_endpoints}")
            print(f"Available routes: {routes}")
            return False
        
        print("✅ All expected API endpoints are defined")
        return True
        
    except Exception as e:
        print(f"❌ API endpoint test failed: {str(e)}")
        return False

def main():
    """Run all functionality tests."""
    print("🚀 Cariya Wallet Backend - Enhanced Savings Functionality Tests")
    print("=" * 70)
    
    tests = [
        ("Model Imports", test_models_import),
        ("Helper Functions", test_helper_functions),
        ("SavingsEntry Validation", test_savings_entry_validation),
        ("Transaction ID Generation", test_transaction_id_generation),
        ("Expected Savings Calculation", test_expected_savings_calculation),
        ("API Endpoints", test_api_endpoints),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: FAILED with exception: {str(e)}")
    
    print("\n" + "=" * 70)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The enhanced savings functionality is working correctly.")
        print("\n✨ Key Features Verified:")
        print("   • Transaction tracking with unique IDs")
        print("   • Payment method validation")
        print("   • Phone number validation")
        print("   • Amount and month validation")
        print("   • Expected savings calculation")
        print("   • API endpoint definitions")
        print("   • Model and helper function imports")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
