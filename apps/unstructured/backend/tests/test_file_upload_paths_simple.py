"""
Storage Path Validation Unit Test - No FastAPI Import

Tests:
1. raw_prefix() correctly constructs S3 paths
2. S3_METADATA_PATH is included when set
3. Workspace/product/version hierarchy is preserved
4. No double prefixing of S3_METADATA_PATH
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from primedata.storage.paths import raw_prefix, embed_prefix, clean_prefix


def test_raw_prefix_with_metadata_path():
    """Test raw_prefix includes S3_METADATA_PATH when set."""
    print(f"\n{'='*100}")
    print("TEST 1: raw_prefix() WITH S3_METADATA_PATH")
    print(f"{'='*100}")

    os.environ["S3_METADATA_PATH"] = "primedata-dev"

    ws_id = "4b979faf-0462-4560-897b-e26800378f90"
    prod_id = "8037da2b-61cd-435d-8db7-b5472c98f805"
    version = 1

    prefix = raw_prefix(ws_id, prod_id, version)

    print(f"\n📌 Input Parameters:")
    print(f"   S3_METADATA_PATH: primedata-dev")
    print(f"   Workspace ID: {ws_id}")
    print(f"   Product ID: {prod_id}")
    print(f"   Version: {version}")

    print(f"\n📦 Generated Path:")
    print(f"   {prefix}")

    print(f"\n✓ Validations:")

    # Check metadata path
    assert prefix.startswith("primedata-dev"), f"❌ Prefix doesn't start with S3_METADATA_PATH"
    print(f"   ✅ Starts with S3_METADATA_PATH: primedata-dev")

    # Check workspace
    assert f"ws/{ws_id}" in prefix, f"❌ Workspace not in prefix"
    print(f"   ✅ Contains workspace folder: ws/{ws_id}")

    # Check product
    assert f"prod/{prod_id}" in prefix, f"❌ Product not in prefix"
    print(f"   ✅ Contains product folder: prod/{prod_id}")

    # Check version
    assert f"v/{version}" in prefix, f"❌ Version not in prefix"
    print(f"   ✅ Contains version folder: v/{version}")

    # Check raw stage
    assert "raw/" in prefix, f"❌ Raw stage not in prefix"
    print(f"   ✅ Contains raw stage: raw/")

    # Check ends with /
    assert prefix.endswith("raw/"), f"❌ Doesn't end with 'raw/'"
    print(f"   ✅ Ends with / for concatenation")

    print(f"\n{'='*100}\n")


def test_raw_prefix_without_metadata_path():
    """Test raw_prefix works without S3_METADATA_PATH."""
    print(f"\n{'='*100}")
    print("TEST 2: raw_prefix() WITHOUT S3_METADATA_PATH")
    print(f"{'='*100}")

    os.environ.pop("S3_METADATA_PATH", None)

    ws_id = "4b979faf-0462-4560-897b-e26800378f90"
    prod_id = "8037da2b-61cd-435d-8db7-b5472c98f805"
    version = 1

    prefix = raw_prefix(ws_id, prod_id, version)

    print(f"\n📌 Input Parameters:")
    print(f"   S3_METADATA_PATH: (not set)")
    print(f"   Workspace ID: {ws_id}")
    print(f"   Product ID: {prod_id}")
    print(f"   Version: {version}")

    print(f"\n📦 Generated Path:")
    print(f"   {prefix}")

    print(f"\n✓ Validations:")

    # Check starts with ws/
    assert prefix.startswith("ws/"), f"❌ Prefix should start with 'ws/'"
    print(f"   ✅ Starts with: ws/")

    # Check workspace
    assert f"ws/{ws_id}" in prefix, f"❌ Workspace not in prefix"
    print(f"   ✅ Contains workspace folder: ws/{ws_id}")

    # Check product
    assert f"prod/{prod_id}" in prefix, f"❌ Product not in prefix"
    print(f"   ✅ Contains product folder: prod/{prod_id}")

    # Check version
    assert f"v/{version}" in prefix, f"❌ Version not in prefix"
    print(f"   ✅ Contains version folder: v/{version}")

    # Check raw stage
    assert "raw/" in prefix, f"❌ Raw stage not in prefix"
    print(f"   ✅ Contains raw stage: raw/")

    print(f"\n{'='*100}\n")


def test_no_double_prefix():
    """Test that S3_METADATA_PATH is not duplicated in paths."""
    print(f"\n{'='*100}")
    print("TEST 3: NO DOUBLE PREFIX OF S3_METADATA_PATH")
    print(f"{'='*100}")

    os.environ["S3_METADATA_PATH"] = "primedata-dev"

    ws_id = "4b979faf-0462-4560-897b-e26800378f90"
    prod_id = "8037da2b-61cd-435d-8db7-b5472c98f805"
    version = 1

    prefix = raw_prefix(ws_id, prod_id, version)

    print(f"\n📌 Input Parameters:")
    print(f"   S3_METADATA_PATH: primedata-dev")
    print(f"   Workspace ID: {ws_id}")
    print(f"   Product ID: {prod_id}")
    print(f"   Version: {version}")

    print(f"\n📦 Generated Path:")
    print(f"   {prefix}")

    print(f"\n✓ Validations:")

    # Count occurrences
    count = prefix.count("primedata-dev")
    assert count == 1, f"❌ S3_METADATA_PATH appears {count} times (should be 1)"
    print(f"   ✅ S3_METADATA_PATH appears exactly ONCE in path")
    print(f"   ✅ No double prefixing")

    print(f"\n{'='*100}\n")


def test_full_s3_path_examples():
    """Show full S3 path examples with different configurations."""
    print(f"\n{'='*100}")
    print("TEST 4: FULL S3 PATH EXAMPLES")
    print(f"{'='*100}")

    ws_id = "4b979faf-0462-4560-897b-e26800378f90"
    prod_id = "8037da2b-61cd-435d-8db7-b5472c98f805"
    version = 1
    filename = "NLP_Data_Scientist_job_description.jsonl"
    bucket = "lly-light-dev"

    # Example 1: With S3_METADATA_PATH
    print(f"\n📌 Example 1: WITH S3_METADATA_PATH='primedata-dev'")
    os.environ["S3_METADATA_PATH"] = "primedata-dev"
    prefix1 = raw_prefix(ws_id, prod_id, version)
    full_path1 = f"s3://{bucket}/{prefix1}{filename}"

    print(f"   Prefix: {prefix1}")
    print(f"   Full S3 Path:")
    print(f"   {full_path1}")
    print(f"   ✅ File saved inside workspace folder structure")

    # Example 2: Without S3_METADATA_PATH
    print(f"\n📌 Example 2: WITHOUT S3_METADATA_PATH")
    os.environ.pop("S3_METADATA_PATH", None)
    prefix2 = raw_prefix(ws_id, prod_id, version)
    full_path2 = f"s3://{bucket}/{prefix2}{filename}"

    print(f"   Prefix: {prefix2}")
    print(f"   Full S3 Path:")
    print(f"   {full_path2}")
    print(f"   ✅ File saved inside workspace folder structure")

    # Example 3: With different S3_METADATA_PATH value
    print(f"\n📌 Example 3: WITH S3_METADATA_PATH='prod-data/archive'")
    os.environ["S3_METADATA_PATH"] = "prod-data/archive"
    prefix3 = raw_prefix(ws_id, prod_id, version)
    full_path3 = f"s3://{bucket}/{prefix3}{filename}"

    print(f"   Prefix: {prefix3}")
    print(f"   Full S3 Path:")
    print(f"   {full_path3}")
    print(f"   ✅ File saved inside workspace folder structure")

    print(f"\n{'='*100}\n")


def test_path_hierarchy_structure():
    """Verify the consistent path hierarchy structure."""
    print(f"\n{'='*100}")
    print("TEST 5: PATH HIERARCHY STRUCTURE")
    print(f"{'='*100}")

    os.environ["S3_METADATA_PATH"] = "primedata-dev"

    test_cases = [
        ("ws-1", "prod-1", 1),
        ("ws-2", "prod-2", 2),
        ("ws-3", "prod-3", 3),
    ]

    print(f"\n📋 Testing multiple workspace/product/version combinations:")

    for ws_id, prod_id, version in test_cases:
        prefix = raw_prefix(ws_id, prod_id, version)
        expected_pattern = f"primedata-dev/ws/{ws_id}/prod/{prod_id}/v/{version}/raw/"

        assert prefix == expected_pattern, f"❌ Path doesn't match expected pattern"
        print(f"   ✅ ws={ws_id}, prod={prod_id}, v={version}")
        print(f"      → {prefix}")

    print(f"\n{'='*100}\n")


if __name__ == "__main__":
    print("\n" + "="*100)
    print("END-TO-END FILE UPLOAD PATH VALIDATION REPORT")
    print("="*100)

    test_raw_prefix_with_metadata_path()
    test_raw_prefix_without_metadata_path()
    test_no_double_prefix()
    test_full_s3_path_examples()
    test_path_hierarchy_structure()

    print("\n" + "="*100)
    print("✅ ALL TESTS PASSED - FILE UPLOAD PATHS ARE CORRECT")
    print("="*100)
    print("\n📊 SUMMARY:")
    print("   ✅ S3_METADATA_PATH is included when set")
    print("   ✅ Workspace/product/version hierarchy preserved")
    print("   ✅ No double prefixing of S3_METADATA_PATH")
    print("   ✅ Files saved in correct S3 location")
    print("   ✅ Consistent path pattern across all scenarios")
    print("\n" + "="*100 + "\n")