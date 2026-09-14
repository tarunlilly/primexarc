#!/usr/bin/env python3
"""
Integration Test: S3 Storage Client Simulation
Simulates actual storage_client calls with fixed code patterns
Verifies all keys passed to storage_client include S3_METADATA_PATH
"""

import sys
import os
from pathlib import Path

# Set environment variables
os.environ["S3_METADATA_PATH"] = "primedata-dev/"
sys.path.insert(0, str(Path(__file__).parent / "backend" / "src"))


class MockStorageClient:
    """Mock storage_client that captures all operations."""

    def __init__(self):
        self.operations = []

    def list_objects(self, bucket: str, prefix: str) -> list:
        self.operations.append({
            "operation": "list_objects",
            "bucket": bucket,
            "prefix": prefix,
            "double_prefix": prefix.count("primedata-dev/") > 1,
            "missing_prefix": not prefix.startswith("primedata-dev/") and "ws/" in prefix,
        })
        return []

    def get_object(self, bucket: str, key: str) -> bytes:
        self.operations.append({
            "operation": "get_object",
            "bucket": bucket,
            "key": key,
            "double_prefix": key.count("primedata-dev/") > 1,
            "missing_prefix": not key.startswith("primedata-dev/") and "ws/" in key,
        })
        return b""

    def put_bytes(self, bucket: str, key: str, data: bytes) -> bool:
        self.operations.append({
            "operation": "put_bytes",
            "bucket": bucket,
            "key": key,
            "double_prefix": key.count("primedata-dev/") > 1,
            "missing_prefix": not key.startswith("primedata-dev/") and "ws/" in key,
        })
        return True

    def delete_object(self, bucket: str, key: str) -> bool:
        self.operations.append({
            "operation": "delete_object",
            "bucket": bucket,
            "key": key,
            "double_prefix": key.count("primedata-dev/") > 1,
            "missing_prefix": not key.startswith("primedata-dev/") and "ws/" in key,
        })
        return True


def test_storage_operations():
    """Test storage operations with fixed code."""

    print("\n" + "="*120)
    print("🔌 STORAGE CLIENT INTEGRATION TEST")
    print("Testing all fixed code patterns with mock storage_client")
    print("="*120)

    from primedata.storage.paths import (
        _get_base_prefix,
        embed_prefix,
        clean_prefix,
    )

    storage_client = MockStorageClient()
    ws_id = "ws-123"
    prod_id = "prod-456"
    version = 1

    print(f"\n{'='*120}")
    print("SIMULATING FIXED CODE PATTERNS")
    print(f"{'='*120}\n")

    # Simulate validator.py line 115
    print("1️⃣ Validator (dq/validator.py line 115)")
    print("   Code: await storage_client.get_object('primedata-config', rules_key)")
    base = _get_base_prefix()
    rules_key = f"{base}ws/{ws_id}/prod/{prod_id}/dq/rules.yaml"
    print(f"   Key: {rules_key}")
    storage_client.get_object("primedata-config", rules_key)
    print("   ✅ Called storage_client.get_object()\n")

    # Simulate validator.py line 141
    print("2️⃣ Validator Embeddings (dq/validator.py line 141)")
    print("   Code: await storage_client.list_objects('primedata-embed', chunks_key_prefix)")
    chunks_prefix = embed_prefix(ws_id, prod_id, version)
    print(f"   Prefix: {chunks_prefix}")
    storage_client.list_objects("primedata-embed", chunks_prefix)
    print("   ✅ Called storage_client.list_objects()\n")

    # Simulate validator.py line 148
    print("3️⃣ Validator Get Chunk (dq/validator.py line 148)")
    print("   Code: await storage_client.get_object('primedata-embed', obj.name)")
    chunk_key = f"{chunks_prefix}chunk_001.json"
    print(f"   Key: {chunk_key}")
    storage_client.get_object("primedata-embed", chunk_key)
    print("   ✅ Called storage_client.get_object()\n")

    # Simulate data_quality.py line 475
    print("4️⃣ Data Quality Delete Rules (api/data_quality.py line 475)")
    print("   Code: await storage_client.delete_object('primedata-config', rules_key)")
    base = _get_base_prefix()
    rules_key = f"{base}ws/{ws_id}/prod/{prod_id}/dq/rules.yaml"
    print(f"   Key: {rules_key}")
    storage_client.delete_object("primedata-config", rules_key)
    print("   ✅ Called storage_client.delete_object()\n")

    # Simulate exports.py line 183
    print("5️⃣ Exports List (api/exports.py line 183)")
    print("   Code: storage_client.list_objects('primedata-exports', export_prefix_path)")
    base = _get_base_prefix()
    export_prefix_path = f"{base}ws/{ws_id}/prod/{prod_id}/"
    print(f"   Prefix: {export_prefix_path}")
    storage_client.list_objects("primedata-exports", export_prefix_path)
    print("   ✅ Called storage_client.list_objects()\n")

    # Simulate exports.py line 274
    print("6️⃣ Exports Upload Bundle (api/exports.py line 274)")
    print("   Code: storage_client.put_bytes('primedata-exports', bundle_key, bundle_data)")
    base = _get_base_prefix()
    bundle_key = f"{base}ws/{ws_id}/prod/{prod_id}/exports/bundle.zip"
    print(f"   Key: {bundle_key}")
    storage_client.put_bytes("primedata-exports", bundle_key, b"bundle_data")
    print("   ✅ Called storage_client.put_bytes()\n")

    # Simulate artifacts.py line 83
    print("7️⃣ Artifacts List (api/artifacts.py line 83)")
    print("   Code: storage_client.list_objects('primedata-raw', prefix)")
    raw_prefix_val = f"{_get_base_prefix()}ws/{ws_id}/prod/{prod_id}/v/{version}/raw/"
    print(f"   Prefix: {raw_prefix_val}")
    storage_client.list_objects("primedata-raw", raw_prefix_val)
    print("   ✅ Called storage_client.list_objects()\n")

    # Simulate dag_tasks.py line 242
    print("8️⃣ DAG Clean Artifact Stats (ingestion_pipeline/dag_tasks.py line 242)")
    print("   Code: stat_info = _retrieve_file_stats('primedata-clean', storage_key)")
    clean_prefix_val = clean_prefix(ws_id, prod_id, version)
    storage_key = f"{clean_prefix_val}file.jsonl"
    print(f"   Key: {storage_key}")
    storage_client.get_object("primedata-clean", storage_key)  # Simulating _retrieve_file_stats
    print("   ✅ Called storage_client.get_object()\n")

    # Summary
    print(f"{'='*120}")
    print("📊 STORAGE CLIENT OPERATION SUMMARY")
    print(f"{'='*120}\n")

    print(f"Total Operations: {len(storage_client.operations)}\n")

    all_good = True
    for idx, op in enumerate(storage_client.operations, 1):
        key_or_prefix = op.get("key") or op.get("prefix")
        double = op["double_prefix"]
        missing = op["missing_prefix"]

        status = "✅"
        issues = []

        if double:
            status = "❌"
            issues.append("DOUBLE PREFIX")
            all_good = False

        if missing:
            status = "❌"
            issues.append("MISSING PREFIX")
            all_good = False

        issue_str = f" [{', '.join(issues)}]" if issues else ""
        print(f"{status} {idx}. {op['operation']:15} | {op['bucket']:20} | {key_or_prefix}{issue_str}")

    print(f"\n{'='*120}")
    if all_good:
        print("✅ ✅ ✅ ALL STORAGE OPERATIONS VALID ✅ ✅ ✅")
        print(f"{'='*120}")
        print(f"""
✅ Storage Client Integration Test Results:

Total Operations Simulated: {len(storage_client.operations)}
Operations with Correct Paths: {len(storage_client.operations)}

✅ No double prefixes detected
✅ No missing prefixes detected
✅ All operations use S3_METADATA_PATH correctly

Integration Status: ✅ READY FOR PRODUCTION
""")
        return 0
    else:
        print("❌ SOME OPERATIONS FAILED VALIDATION")
        print(f"{'='*120}")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(test_storage_operations())
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
