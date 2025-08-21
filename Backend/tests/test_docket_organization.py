#!/usr/bin/env python3
"""
Test to verify the API docket organization is working correctly.
"""
import sys
import os
from pathlib import Path

# Add the parent directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_docket_organization():
    """Test that all endpoints are properly organized into dockets."""
    print("🔍 Testing API docket organization...")
    
    try:
        from main import app
        
        # Get all routes with their tags
        routes_with_tags = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'tags'):
                routes_with_tags.append({
                    'path': route.path,
                    'tags': route.tags,
                    'methods': [method.lower() for method in route.methods] if hasattr(route, 'methods') else []
                })
        
        # Define expected dockets
        expected_dockets = [
            "Partner Management",
            "Activity Management", 
            "Donor Management",
            "Mother Management",
            "Savings & Analytics",
            "Donor View",
            "Admin & System"
        ]
        
        # Check that all expected dockets exist
        found_dockets = set()
        for route in routes_with_tags:
            if route['tags']:
                found_dockets.update(route['tags'])
        
        missing_dockets = set(expected_dockets) - found_dockets
        if missing_dockets:
            print(f"❌ Missing dockets: {missing_dockets}")
            return False
        
        print(f"✅ All expected dockets found: {list(found_dockets)}")
        
        # Count endpoints per docket
        docket_counts = {}
        for route in routes_with_tags:
            if route['tags']:
                for tag in route['tags']:
                    docket_counts[tag] = docket_counts.get(tag, 0) + 1
        
        print("\n📊 Endpoints per docket:")
        for docket, count in docket_counts.items():
            print(f"   • {docket}: {count} endpoints")
        
        # Check that no endpoints are untagged
        untagged_routes = [route for route in routes_with_tags if not route['tags']]
        if untagged_routes:
            print(f"\n⚠️  Untagged routes found: {len(untagged_routes)}")
            for route in untagged_routes:
                print(f"   - {route['path']}")
        
        # Verify specific dockets have expected endpoint counts
        expected_counts = {
            "Partner Management": 11,
            "Activity Management": 2,  # addActivity and get all activities
            "Donor Management": 7,
            "Mother Management": 7,
            "Savings & Analytics": 12,
            "Donor View": 1,
            "Admin & System": 4
        }
        
        print("\n🔍 Verifying endpoint counts:")
        all_correct = True
        for docket, expected_count in expected_counts.items():
            actual_count = docket_counts.get(docket, 0)
            if actual_count == expected_count:
                print(f"   ✅ {docket}: {actual_count}/{expected_count}")
            else:
                print(f"   ❌ {docket}: {actual_count}/{expected_count} (expected {expected_count})")
                all_correct = False
        
        return all_correct
        
    except Exception as e:
        print(f"❌ Docket organization test failed: {str(e)}")
        return False

def test_swagger_compatibility():
    """Test that the docket organization is compatible with Swagger UI."""
    print("\n🔍 Testing Swagger UI compatibility...")
    
    try:
        from main import app
        
        # Check if the app has the required attributes for Swagger
        if hasattr(app, 'openapi'):
            print("✅ FastAPI app has openapi method")
        else:
            print("❌ FastAPI app missing openapi method")
            return False
        
        # Check if routes have proper HTTP methods
        routes_with_methods = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                routes_with_methods.append(route)
        
        print(f"✅ Found {len(routes_with_methods)} routes with HTTP methods")
        
        # Verify that all tagged routes have proper HTTP methods
        tagged_routes_with_methods = [r for r in routes_with_methods if hasattr(r, 'tags') and r.tags]
        print(f"✅ Found {len(tagged_routes_with_methods)} tagged routes with HTTP methods")
        
        return True
        
    except Exception as e:
        print(f"❌ Swagger compatibility test failed: {str(e)}")
        return False

def test_docket_naming():
    """Test that docket names are consistent and professional."""
    print("\n🔍 Testing docket naming conventions...")
    
    try:
        from main import app
        
        # Get all docket names
        docket_names = set()
        for route in app.routes:
            if hasattr(route, 'tags') and route.tags:
                docket_names.update(route.tags)
        
        # Check naming conventions
        issues = []
        for name in docket_names:
            # Check capitalization
            if not name[0].isupper():
                issues.append(f"'{name}' should start with capital letter")
            
            # Check for proper spacing
            if '  ' in name:
                issues.append(f"'{name}' has double spaces")
            
            # Check length
            if len(name) > 50:
                issues.append(f"'{name}' is too long ({len(name)} chars)")
        
        if issues:
            print("⚠️  Docket naming issues found:")
            for issue in issues:
                print(f"   - {issue}")
            return False
        
        print("✅ All docket names follow conventions")
        return True
        
    except Exception as e:
        print(f"❌ Docket naming test failed: {str(e)}")
        return False

def main():
    """Run all docket organization tests."""
    print("🚀 Cariya Wallet Backend - API Docket Organization Tests")
    print("=" * 70)
    
    tests = [
        ("Docket Organization", test_docket_organization),
        ("Swagger Compatibility", test_swagger_compatibility),
        ("Docket Naming", test_docket_naming),
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
        print("🎉 All docket organization tests passed!")
        print("\n✨ API Organization Benefits:")
        print("   • Clean, professional Swagger UI")
        print("   • Logical endpoint grouping")
        print("   • Easy navigation for developers")
        print("   • Enterprise-ready API structure")
        print("   • Maintainable codebase")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the docket organization.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
