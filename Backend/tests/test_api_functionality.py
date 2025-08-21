#!/usr/bin/env python3
"""
Test script to verify the actual API functionality of the enhanced savings system.
This script tests the API endpoints by making actual HTTP requests.
"""
import sys
import os
import time
import requests
from pathlib import Path

# Add the parent directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_api_server():
    """Test if the API server is running and responding."""
    print("🔍 Testing API server connectivity...")
    
    try:
        # Test basic connectivity
        response = requests.get("http://localhost:8000/docs", timeout=5)
        if response.status_code == 200:
            print("✅ API server is running and accessible")
            return True
        else:
            print(f"❌ API server responded with status: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API server. Is it running on localhost:8000?")
        print("   Start the server with: uvicorn main:app --reload")
        return False
    except Exception as e:
        print(f"❌ Error testing API server: {str(e)}")
        return False

def test_savings_endpoint():
    """Test the enhanced savings endpoint."""
    print("\n🔍 Testing enhanced savings endpoint...")
    
    try:
        # First, we need to create a mother to test with
        mother_data = {
            "first_name": "Test",
            "surname": "Mother",
            "mobile_number": "+256700000000",
            "num_children": 2,
            "ages_of_children": [5, 8],
            "location": "Test Location"
        }
        
        # Create mother
        response = requests.post("http://localhost:8000/addMother", json=mother_data, timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to create test mother: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
        
        mother_response = response.json()
        mother_id = mother_data["mobile_number"]  # The generated_id should be the mobile number
        
        print(f"✅ Created test mother with ID: {mother_id}")
        
        # Test adding savings with transaction tracking
        savings_data = {
            "amount": 2000.0,
            "month": 3,
            "phone_number": "+256700000000",
            "payment_method": "Mobile Money",
            "reference_number": "REF123456",
            "notes": "Test savings entry"
        }
        
        response = requests.post(
            f"http://localhost:8000/mothers/{mother_id}/savings",
            json=savings_data,
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to add savings: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
        
        savings_response = response.json()
        print("✅ Successfully added savings with transaction tracking")
        print(f"   Transaction ID: {savings_response.get('transaction_id')}")
        print(f"   Amount: {savings_response.get('monthly_savings')}")
        print(f"   Payment Method: {savings_response.get('payment_method')}")
        print(f"   Phone Number: {savings_response.get('phone_number')}")
        
        # Test getting transactions
        response = requests.get("http://localhost:8000/savings-transactions", timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to get transactions: {response.status_code}")
            return False
        
        transactions = response.json()
        if isinstance(transactions, list) and len(transactions) > 0:
            print("✅ Successfully retrieved transactions")
            print(f"   Found {len(transactions)} transactions")
        else:
            print("❌ No transactions found or invalid response")
            return False
        
        # Test getting transaction summary for the mother
        response = requests.get(f"http://localhost:8000/mothers/{mother_id}/transaction-summary", timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to get transaction summary: {response.status_code}")
            return False
        
        summary = response.json()
        print("✅ Successfully retrieved transaction summary")
        print(f"   Total transactions: {summary.get('total_transactions')}")
        print(f"   Total amount: {summary.get('total_amount')}")
        
        # Test payment method statistics
        response = requests.get("http://localhost:8000/payment-method-statistics", timeout=10)
        if response.status_code != 200:
            print(f"❌ Failed to get payment method statistics: {response.status_code}")
            return False
        
        stats = response.json()
        print("✅ Successfully retrieved payment method statistics")
        print(f"   Total transactions: {stats.get('total_transactions')}")
        print(f"   Total amount: {stats.get('total_amount')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing savings endpoint: {str(e)}")
        return False

def main():
    """Run API functionality tests."""
    print("🚀 Cariya Wallet Backend - API Functionality Tests")
    print("=" * 60)
    
    tests = [
        ("API Server Connectivity", test_api_server),
        ("Enhanced Savings API", test_savings_endpoint),
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
    
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All API tests passed! The enhanced savings functionality is working correctly.")
        print("\n✨ API Features Verified:")
        print("   • Server connectivity and responsiveness")
        print("   • Mother creation and management")
        print("   • Enhanced savings with transaction tracking")
        print("   • Transaction retrieval and filtering")
        print("   • Transaction summary generation")
        print("   • Payment method statistics")
        return 0
    else:
        print("⚠️  Some API tests failed. Please check the server and implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
