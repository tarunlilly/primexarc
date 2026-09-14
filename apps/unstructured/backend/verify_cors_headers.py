#!/usr/bin/env python3
"""
Verify that the backend is returning CORS headers correctly.

This script tests the backend CORS configuration by making requests
and checking for the required CORS headers in responses.

Usage:
    python3 verify_cors_headers.py [backend_url]

Examples:
    python3 verify_cors_headers.py
    python3 verify_cors_headers.py https://localhost:8000
    python3 verify_cors_headers.py https://primedata-internal.apps-internal.lrl.lilly.com
"""

import sys
import requests
from urllib.parse import urljoin

# Default backend URL
DEFAULT_URL = "http://localhost:8000"

# Test origins that should be allowed
TEST_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://primedata-frontend.apps-internal.lrl.lilly.com",
    "https://primedata-internal.apps-internal.lrl.lilly.com",
]

# Test origin that should be blocked
BLOCKED_ORIGIN = "https://evil.com"


def test_cors_get(base_url, origin):
    """Test GET request with CORS origin header."""
    url = urljoin(base_url, "/test/cors-headers")
    headers = {"Origin": origin}

    print(f"\n📤 Testing GET from origin: {origin}")
    print(f"   URL: {url}")

    try:
        response = requests.get(url, headers=headers, timeout=5, verify=False)
        print(f"   Status: {response.status_code}")

        # Check for CORS headers
        cors_origin = response.headers.get("access-control-allow-origin")
        cors_methods = response.headers.get("access-control-allow-methods")
        cors_headers = response.headers.get("access-control-allow-headers")
        cors_creds = response.headers.get("access-control-allow-credentials")

        print(f"\n   📋 Response Headers:")
        print(f"      Access-Control-Allow-Origin: {cors_origin or '❌ MISSING'}")
        print(f"      Access-Control-Allow-Methods: {cors_methods or '❌ MISSING'}")
        print(f"      Access-Control-Allow-Headers: {cors_headers or '❌ MISSING'}")
        print(f"      Access-Control-Allow-Credentials: {cors_creds or '❌ MISSING'}")

        if cors_origin == origin:
            print(f"\n   ✅ CORS headers present and correct!")
            return True
        else:
            print(f"\n   ❌ CORS headers missing or incorrect")
            return False

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_cors_options(base_url, origin):
    """Test OPTIONS preflight request with CORS headers."""
    url = urljoin(base_url, "/test/cors-headers")
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "content-type",
    }

    print(f"\n📤 Testing OPTIONS (preflight) from origin: {origin}")
    print(f"   URL: {url}")

    try:
        response = requests.options(url, headers=headers, timeout=5, verify=False)
        print(f"   Status: {response.status_code}")

        # Check for CORS headers
        cors_origin = response.headers.get("access-control-allow-origin")
        cors_methods = response.headers.get("access-control-allow-methods")
        cors_headers = response.headers.get("access-control-allow-headers")
        cors_creds = response.headers.get("access-control-allow-credentials")
        max_age = response.headers.get("access-control-max-age")

        print(f"\n   📋 Response Headers:")
        print(f"      Access-Control-Allow-Origin: {cors_origin or '❌ MISSING'}")
        print(f"      Access-Control-Allow-Methods: {cors_methods or '❌ MISSING'}")
        print(f"      Access-Control-Allow-Headers: {cors_headers or '❌ MISSING'}")
        print(f"      Access-Control-Allow-Credentials: {cors_creds or '❌ MISSING'}")
        print(f"      Access-Control-Max-Age: {max_age or '❌ MISSING'}")

        if cors_origin == origin:
            print(f"\n   ✅ Preflight CORS headers present and correct!")
            return True
        else:
            print(f"\n   ❌ Preflight CORS headers missing or incorrect")
            return False

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_blocked_origin(base_url):
    """Test that blocked origins don't get CORS headers."""
    url = urljoin(base_url, "/test/cors-headers")
    headers = {"Origin": BLOCKED_ORIGIN}

    print(f"\n🚫 Testing blocked origin: {BLOCKED_ORIGIN}")
    print(f"   URL: {url}")

    try:
        response = requests.get(url, headers=headers, timeout=5, verify=False)
        print(f"   Status: {response.status_code}")

        cors_origin = response.headers.get("access-control-allow-origin")

        if cors_origin is None:
            print(f"   ✅ Blocked origin correctly has NO CORS header")
            return True
        else:
            print(f"   ❌ ERROR: Blocked origin got CORS header: {cors_origin}")
            return False

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_health_endpoint(base_url):
    """Test that health endpoint returns CORS headers."""
    url = urljoin(base_url, "/health/simple")
    origin = "https://primedata-frontend.apps-internal.lrl.lilly.com"
    headers = {"Origin": origin}

    print(f"\n📤 Testing /health/simple from origin: {origin}")
    print(f"   URL: {url}")

    try:
        response = requests.get(url, headers=headers, timeout=5, verify=False)
        print(f"   Status: {response.status_code}")

        cors_origin = response.headers.get("access-control-allow-origin")

        print(f"\n   📋 Response Headers:")
        print(f"      Access-Control-Allow-Origin: {cors_origin or '❌ MISSING'}")

        if cors_origin == origin:
            print(f"   ✅ Health endpoint has CORS headers!")
            return True
        else:
            print(f"   ❌ Health endpoint missing CORS headers")
            return False

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def main():
    """Run all CORS verification tests."""
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    print("=" * 80)
    print("🔍 CORS Headers Verification Script")
    print("=" * 80)
    print(f"\nBackend URL: {base_url}")
    print(f"Testing endpoints: /test/cors-headers, /health/simple")

    # Disable SSL warnings for self-signed certificates
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    results = {
        "allowed_origins_get": [],
        "allowed_origins_options": [],
        "blocked_origin": False,
        "health_endpoint": False,
    }

    # Test allowed origins with GET
    print("\n" + "=" * 80)
    print("TEST 1: GET requests with allowed origins")
    print("=" * 80)
    for origin in TEST_ORIGINS:
        success = test_cors_get(base_url, origin)
        results["allowed_origins_get"].append((origin, success))

    # Test allowed origins with OPTIONS
    print("\n" + "=" * 80)
    print("TEST 2: OPTIONS (preflight) requests with allowed origins")
    print("=" * 80)
    for origin in TEST_ORIGINS:
        success = test_cors_options(base_url, origin)
        results["allowed_origins_options"].append((origin, success))

    # Test blocked origin
    print("\n" + "=" * 80)
    print("TEST 3: Blocked origin verification")
    print("=" * 80)
    results["blocked_origin"] = test_blocked_origin(base_url)

    # Test health endpoint
    print("\n" + "=" * 80)
    print("TEST 4: Health endpoint")
    print("=" * 80)
    results["health_endpoint"] = test_health_endpoint(base_url)

    # Print summary
    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)

    get_passed = sum(1 for _, success in results["allowed_origins_get"] if success)
    options_passed = sum(
        1 for _, success in results["allowed_origins_options"] if success
    )

    print(f"\n✅ GET requests: {get_passed}/{len(TEST_ORIGINS)} passed")
    for origin, success in results["allowed_origins_get"]:
        status = "✅" if success else "❌"
        print(f"   {status} {origin}")

    print(f"\n✅ OPTIONS requests: {options_passed}/{len(TEST_ORIGINS)} passed")
    for origin, success in results["allowed_origins_options"]:
        status = "✅" if success else "❌"
        print(f"   {status} {origin}")

    print(f"\n{'✅' if results['blocked_origin'] else '❌'} Blocked origin test")
    print(f"{'✅' if results['health_endpoint'] else '❌'} Health endpoint test")

    # Overall result
    all_passed = (
        all(success for _, success in results["allowed_origins_get"])
        and all(success for _, success in results["allowed_origins_options"])
        and results["blocked_origin"]
        and results["health_endpoint"]
    )

    print("\n" + "=" * 80)
    if all_passed:
        print("✅ ALL TESTS PASSED - CORS IS WORKING CORRECTLY!")
    else:
        print("❌ SOME TESTS FAILED - CORS CONFIGURATION NEEDS FIXING")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
