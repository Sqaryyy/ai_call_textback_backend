"""
Calendar API Endpoint Testing Script

Run this script to test all calendar endpoints.
Make sure your server is running on http://localhost:8000
"""

import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api/v1/calendar"

# Test data - update these with your actual values
BUSINESS_ID = "1950e475-f499-427b-bb1a-31f487e6554c"
INTEGRATION_ID = "cb30636d-6431-4828-919b-265f83b500e1"
CALENDAR_ID = "lukapilip@gmail.com"  # or "primary"


def print_test(name, response):
    """Helper to print test results"""
    print(f"\n{'=' * 60}")
    print(f"TEST: {name}")
    print(f"Status: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response: {response.text}")
    print(f"{'=' * 60}")


def test_google_auth():
    """Test 1: Initiate Google OAuth"""
    print("\n🔐 Testing Google OAuth Initiation...")
    response = requests.post(f"{BASE_URL}/google/authorize/{BUSINESS_ID}")
    print_test("Google Authorization URL", response)
    return response.status_code == 200


def test_list_integrations():
    """Test 2: List all calendar integrations"""
    print("\n📋 Testing List Integrations...")
    response = requests.get(f"{BASE_URL}/{BUSINESS_ID}/integrations")
    print_test("List Integrations", response)
    return response.status_code == 200


def test_select_calendar():
    """Test 3: Select a specific Google calendar"""
    print("\n📅 Testing Select Calendar...")
    response = requests.patch(
        f"{BASE_URL}/google/{INTEGRATION_ID}/select-calendar",
        params={"calendar_id": CALENDAR_ID}
    )
    print_test("Select Google Calendar", response)
    return response.status_code == 200


def test_set_primary():
    """Test 4: Set integration as primary"""
    print("\n⭐ Testing Set Primary Calendar...")
    response = requests.patch(f"{BASE_URL}/{INTEGRATION_ID}/set-primary")
    print_test("Set Primary Calendar", response)
    return response.status_code == 200


def test_get_availability():
    """Test 5: Get available time slots"""
    print("\n🕒 Testing Get Availability...")

    start = datetime.now()
    end = start + timedelta(days=7)

    params = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "duration_minutes": 30,
        "limit": 10
    }

    response = requests.get(
        f"{BASE_URL}/{BUSINESS_ID}/availability",
        params=params
    )
    print_test("Get Availability", response)
    return response.status_code == 200


def test_next_available():
    """Test 6: Get next available slot"""
    print("\n⏭️ Testing Next Available Slot...")

    params = {
        "duration_minutes": 30,
        "days_ahead": 14
    }

    response = requests.get(
        f"{BASE_URL}/{BUSINESS_ID}/availability/next-available",
        params=params
    )
    print_test("Next Available Slot", response)
    return response.status_code == 200


def test_availability_summary():
    """Test 7: Get availability summary for a date"""
    print("\n📊 Testing Availability Summary...")

    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    response = requests.get(
        f"{BASE_URL}/{BUSINESS_ID}/availability/summary",
        params={"date": tomorrow}
    )
    print_test("Availability Summary", response)
    return response.status_code == 200


def test_outlook_auth():
    """Test 8: Initiate Outlook OAuth (optional)"""
    print("\n🔐 Testing Outlook OAuth Initiation...")
    response = requests.post(f"{BASE_URL}/outlook/authorize/{BUSINESS_ID}")
    print_test("Outlook Authorization URL", response)
    return response.status_code == 200


def test_remove_integration():
    """Test 9: Remove calendar integration (be careful!)"""
    print("\n⚠️  Testing Remove Integration (SKIPPED - would delete your integration)")
    print("To test this, uncomment the code below:")
    print(f"# response = requests.delete(f'{BASE_URL}/{INTEGRATION_ID}')")
    return True

    # Uncomment to actually test deletion:
    # response = requests.delete(f"{BASE_URL}/{INTEGRATION_ID}")
    # print_test("Remove Integration", response)
    # return response.status_code == 200


def run_all_tests():
    """Run all tests and report results"""
    print("\n" + "=" * 60)
    print("🚀 STARTING CALENDAR API TESTS")
    print("=" * 60)

    tests = [
        ("Google OAuth", test_google_auth),
        ("List Integrations", test_list_integrations),
        ("Select Calendar", test_select_calendar),
        ("Set Primary", test_set_primary),
        ("Get Availability", test_get_availability),
        ("Next Available", test_next_available),
        ("Availability Summary", test_availability_summary),
        ("Outlook OAuth", test_outlook_auth),
        ("Remove Integration", test_remove_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ Error in {name}: {str(e)}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    print(f"\n🎯 Results: {passed}/{total} tests passed")
    print("=" * 60)


if __name__ == "__main__":
    # Update these values before running
    print(f"Using:")
    print(f"  Business ID: {BUSINESS_ID}")
    print(f"  Integration ID: {INTEGRATION_ID}")
    print(f"  Calendar ID: {CALENDAR_ID}")
    print(f"  Base URL: {BASE_URL}")

    input("\nPress Enter to start tests (Ctrl+C to cancel)...")

    run_all_tests()