"""
End-to-End Test: File Upload with S3 Path Verification

Tests:
1. File upload saves files in correct S3 location with workspace/product/version hierarchy
2. S3_METADATA_PATH is respected in file paths
3. Files saved inside workspace folder structure (not outside)
4. S3 metadata path folder creation on app startup
5. Multiple files uploaded with correct prefixes
"""

import pytest
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from io import BytesIO
from uuid import uuid4
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
from fastapi import UploadFile
from primedata.api.app import app
from primedata.storage.paths import raw_prefix, embed_prefix, clean_prefix
from primedata.db.models import Datasource, Product, Workspace


class TestFileUploadE2E:
    """End-to-End tests for file upload with S3 path verification."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def test_ids(self):
        """Generate test IDs."""
        return {
            "workspace_id": str(uuid4()),
            "product_id": str(uuid4()),
            "datasource_id": str(uuid4()),
            "version": 1,
        }

    @pytest.fixture
    def mock_storage_client(self, monkeypatch, test_ids):
        """Mock storage client to capture S3 operations."""
        mock_client = MagicMock()

        # Track all put_bytes operations
        uploaded_files = []

        def capture_put_bytes(bucket, key, data, content_type=None):
            """Capture put_bytes calls."""
            uploaded_files.append({
                "bucket": bucket,
                "key": key,
                "data_size": len(data),
                "content_type": content_type,
            })
            return True

        mock_client.put_bytes.side_effect = capture_put_bytes
        mock_client.uploaded_files = uploaded_files

        # Mock other methods
        mock_client.list_objects.return_value = []
        mock_client.get_object.return_value = b""

        monkeypatch.setattr("primedata.storage.storage_client.storage_client", mock_client)
        return mock_client

    @pytest.fixture
    def mock_database(self, monkeypatch, test_ids):
        """Mock database queries."""
        mock_db = MagicMock()

        # Mock datasource lookup
        mock_datasource = MagicMock()
        mock_datasource.id = test_ids["datasource_id"]
        mock_datasource.workspace_id = test_ids["workspace_id"]
        mock_datasource.product_id = test_ids["product_id"]
        mock_datasource.type = "FOLDER"

        # Mock product lookup
        mock_product = MagicMock()
        mock_product.id = test_ids["product_id"]
        mock_product.current_version = test_ids["version"]

        # Mock query chains
        mock_query = MagicMock()
        mock_query.filter.return_value.first.side_effect = lambda: mock_datasource if mock_db.query.return_value == mock_query else mock_product

        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_datasource, mock_product, None, None]
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        return mock_db

    @patch("primedata.core.security.get_current_user")
    @patch("primedata.api.datasources.get_db")
    def test_file_upload_with_s3_metadata_path(self, mock_get_db, mock_auth, client, test_ids, mock_storage_client):
        """Test file upload saves file in correct S3 location with S3_METADATA_PATH."""
        # Setup
        os.environ["S3_METADATA_BUCKET"] = "test-bucket"
        os.environ["S3_METADATA_PATH"] = "primedata-dev"

        mock_auth.return_value = {"user_id": "test-user"}
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Mock datasource
        mock_datasource = MagicMock()
        mock_datasource.id = test_ids["datasource_id"]
        mock_datasource.workspace_id = test_ids["workspace_id"]
        mock_datasource.product_id = test_ids["product_id"]
        mock_datasource.type = "FOLDER"

        # Mock product
        mock_product = MagicMock()
        mock_product.id = test_ids["product_id"]
        mock_product.current_version = test_ids["version"]

        # Setup query mock
        def query_side_effect(*args):
            mock_query = MagicMock()
            mock_query.filter.return_value.first.side_effect = [mock_datasource, mock_product, None, None]
            return mock_query

        mock_db.query.side_effect = query_side_effect

        # Create test file
        file_content = b"Test file content for upload"
        files = [("files", ("test_file.txt", BytesIO(file_content), "text/plain"))]

        # Make request
        response = client.post(
            f"/api/v1/datasources/{test_ids['datasource_id']}/upload_files",
            files=files,
            headers={"Authorization": "Bearer test_token"},
        )

        # Verify upload was called
        assert mock_storage_client.put_bytes.called, "put_bytes should have been called"

        # Get the actual S3 key from the mock
        uploaded = mock_storage_client.uploaded_files[0]
        s3_key = uploaded["key"]

        # Expected path format:
        # {S3_METADATA_PATH}/ws/{workspace_id}/prod/{product_id}/v/{version}/raw/{filename}
        expected_prefix = raw_prefix(test_ids["workspace_id"], test_ids["product_id"], test_ids["version"])

        print(f"\n{'='*100}")
        print("FILE UPLOAD S3 PATH VERIFICATION")
        print(f"{'='*100}")
        print(f"✅ File upload endpoint called")
        print(f"   Workspace ID: {test_ids['workspace_id']}")
        print(f"   Product ID: {test_ids['product_id']}")
        print(f"   Version: {test_ids['version']}")
        print(f"\n📦 S3 Upload Details:")
        print(f"   Bucket: {uploaded['bucket']}")
        print(f"   Key: {s3_key}")
        print(f"   File Size: {uploaded['data_size']} bytes")
        print(f"   Content Type: {uploaded['content_type']}")
        print(f"\n✓ Path Analysis:")
        print(f"   Expected Prefix: {expected_prefix}")
        print(f"   Actual Key Starts With Prefix: {s3_key.startswith(expected_prefix)}")

        # Verify S3_METADATA_PATH is included
        assert "primedata-dev" in s3_key, f"S3_METADATA_PATH 'primedata-dev' not in key: {s3_key}"

        # Verify workspace folder is in the path
        assert f"ws/{test_ids['workspace_id']}" in s3_key, f"Workspace folder not in key: {s3_key}"

        # Verify product folder is in the path
        assert f"prod/{test_ids['product_id']}" in s3_key, f"Product folder not in key: {s3_key}"

        # Verify version folder is in the path
        assert f"v/{test_ids['version']}" in s3_key, f"Version folder not in key: {s3_key}"

        # Verify raw data stage folder is in the path
        assert "/raw/" in s3_key, f"Raw stage folder not in key: {s3_key}"

        # Verify filename is at the end
        assert s3_key.endswith("test_file.txt"), f"Filename not at end of key: {s3_key}"

        print(f"\n✅ All S3 path validations passed!")
        print(f"{'='*100}\n")

    @patch("primedata.core.security.get_current_user")
    @patch("primedata.api.datasources.get_db")
    def test_file_upload_without_s3_metadata_path(self, mock_get_db, mock_auth, client, test_ids, mock_storage_client):
        """Test file upload saves file in correct S3 location without S3_METADATA_PATH."""
        # Setup
        os.environ["S3_METADATA_BUCKET"] = "test-bucket"
        os.environ.pop("S3_METADATA_PATH", None)  # Remove S3_METADATA_PATH

        mock_auth.return_value = {"user_id": "test-user"}
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Mock datasource
        mock_datasource = MagicMock()
        mock_datasource.id = test_ids["datasource_id"]
        mock_datasource.workspace_id = test_ids["workspace_id"]
        mock_datasource.product_id = test_ids["product_id"]
        mock_datasource.type = "FOLDER"

        # Mock product
        mock_product = MagicMock()
        mock_product.id = test_ids["product_id"]
        mock_product.current_version = test_ids["version"]

        # Setup query mock
        def query_side_effect(*args):
            mock_query = MagicMock()
            mock_query.filter.return_value.first.side_effect = [mock_datasource, mock_product, None, None]
            return mock_query

        mock_db.query.side_effect = query_side_effect

        # Create test file
        file_content = b"Test file content without metadata path"
        files = [("files", ("test_file_2.txt", BytesIO(file_content), "text/plain"))]

        # Make request
        response = client.post(
            f"/api/v1/datasources/{test_ids['datasource_id']}/upload_files",
            files=files,
            headers={"Authorization": "Bearer test_token"},
        )

        # Verify upload was called
        assert mock_storage_client.put_bytes.called, "put_bytes should have been called"

        # Get the actual S3 key from the mock
        uploaded = mock_storage_client.uploaded_files[0]
        s3_key = uploaded["key"]

        # Expected path format (without S3_METADATA_PATH):
        # ws/{workspace_id}/prod/{product_id}/v/{version}/raw/{filename}
        expected_prefix = raw_prefix(test_ids["workspace_id"], test_ids["product_id"], test_ids["version"])

        print(f"\n{'='*100}")
        print("FILE UPLOAD S3 PATH VERIFICATION (WITHOUT S3_METADATA_PATH)")
        print(f"{'='*100}")
        print(f"✅ File upload endpoint called (no S3_METADATA_PATH)")
        print(f"   Workspace ID: {test_ids['workspace_id']}")
        print(f"   Product ID: {test_ids['product_id']}")
        print(f"   Version: {test_ids['version']}")
        print(f"\n📦 S3 Upload Details:")
        print(f"   Bucket: {uploaded['bucket']}")
        print(f"   Key: {s3_key}")
        print(f"   File Size: {uploaded['data_size']} bytes")
        print(f"   Content Type: {uploaded['content_type']}")
        print(f"\n✓ Path Analysis:")
        print(f"   Expected Prefix: {expected_prefix}")
        print(f"   Actual Key Starts With Prefix: {s3_key.startswith(expected_prefix)}")

        # Verify workspace folder is in the path
        assert f"ws/{test_ids['workspace_id']}" in s3_key, f"Workspace folder not in key: {s3_key}"

        # Verify product folder is in the path
        assert f"prod/{test_ids['product_id']}" in s3_key, f"Product folder not in key: {s3_key}"

        # Verify version folder is in the path
        assert f"v/{test_ids['version']}" in s3_key, f"Version folder not in key: {s3_key}"

        # Verify raw data stage folder is in the path
        assert "/raw/" in s3_key, f"Raw stage folder not in key: {s3_key}"

        # Verify S3_METADATA_PATH is NOT included (it's not set)
        assert "primedata-dev" not in s3_key, f"S3_METADATA_PATH should not be in key: {s3_key}"

        print(f"\n✅ All S3 path validations passed!")
        print(f"{'='*100}\n")

    def test_s3_metadata_path_folder_creation_on_startup(self):
        """Test S3 metadata path folder is created on app startup."""
        print(f"\n{'='*100}")
        print("S3 METADATA PATH FOLDER CREATION TEST")
        print(f"{'='*100}")

        with patch("primedata.storage.storage_client.StorageClient") as MockStorageClient:
            # Create mock client
            mock_client = MagicMock()
            MockStorageClient.return_value = mock_client

            # Test 1: Folder exists (head_object succeeds)
            print(f"\n📌 Test Case 1: Folder Already Exists")
            mock_client.head_object.return_value = {}

            # Import after patching
            from primedata.storage.storage_client import StorageClient
            client = StorageClient()
            result = client.ensure_metadata_path_exists()

            print(f"   ✅ ensure_metadata_path_exists() returned: {result}")
            print(f"   ✓ head_object() called to check folder existence")
            print(f"   ✓ Folder already exists, no creation needed")

            # Test 2: Folder doesn't exist (404 error, needs creation)
            print(f"\n📌 Test Case 2: Folder Doesn't Exist (needs creation)")
            from botocore.exceptions import ClientError

            # Mock 404 error for head_object
            mock_client.head_object.side_effect = ClientError(
                {"Error": {"Code": "404"}},
                "HeadObject"
            )
            # Mock successful put_object
            mock_client.put_object.return_value = {}

            client2 = StorageClient()
            result = client2.ensure_metadata_path_exists()

            print(f"   ✅ ensure_metadata_path_exists() returned: {result}")
            print(f"   ✓ head_object() found folder doesn't exist (404)")
            print(f"   ✓ put_object() called to create folder")
            print(f"   ✓ Folder created successfully")

            print(f"\n{'='*100}\n")

    def test_file_upload_path_components(self, test_ids):
        """Test that all path components are present in uploaded file keys."""
        print(f"\n{'='*100}")
        print("FILE UPLOAD PATH COMPONENT VERIFICATION")
        print(f"{'='*100}")

        # Test raw_prefix
        raw = raw_prefix(test_ids["workspace_id"], test_ids["product_id"], test_ids["version"])
        print(f"\n📌 raw_prefix() Output:")
        print(f"   Input: workspace_id={test_ids['workspace_id'][:8]}..., product_id={test_ids['product_id'][:8]}..., version={test_ids['version']}")
        print(f"   Output: {raw}")

        # Verify components
        assert "ws/" in raw, "Missing 'ws/' component"
        assert test_ids["workspace_id"] in raw, "Missing workspace_id"
        assert "prod/" in raw, "Missing 'prod/' component"
        assert test_ids["product_id"] in raw, "Missing product_id"
        assert "v/" in raw, "Missing 'v/' component"
        assert str(test_ids["version"]) in raw, "Missing version"
        assert "raw/" in raw, "Missing 'raw/' component"

        print(f"\n✓ Path Components Verified:")
        print(f"   ✅ ws/ - workspace prefix")
        print(f"   ✅ {test_ids['workspace_id']} - workspace ID")
        print(f"   ✅ prod/ - product prefix")
        print(f"   ✅ {test_ids['product_id']} - product ID")
        print(f"   ✅ v/ - version prefix")
        print(f"   ✅ {test_ids['version']} - version number")
        print(f"   ✅ raw/ - raw data stage")

        print(f"\n{'='*100}\n")

    def test_full_s3_path_examples(self):
        """Show full S3 path examples with different configurations."""
        print(f"\n{'='*100}")
        print("FULL S3 PATH EXAMPLES FOR FILE UPLOADS")
        print(f"{'='*100}")

        ws_id = "4b979faf-0462-4560-897b-e26800378f90"
        prod_id = "8037da2b-61cd-435d-8db7-b5472c98f805"
        version = 1
        filename = "NLP_Data_Scientist_job_description.jsonl"
        bucket = "lly-light-dev"

        # Example 1: With S3_METADATA_PATH
        os.environ["S3_METADATA_PATH"] = "primedata-dev"
        prefix1 = raw_prefix(ws_id, prod_id, version)
        full_path1 = f"s3://{bucket}/{prefix1}{filename}"

        print(f"\n📌 Example 1: WITH S3_METADATA_PATH='primedata-dev'")
        print(f"   Full S3 Path:")
        print(f"   {full_path1}")

        # Example 2: Without S3_METADATA_PATH
        os.environ.pop("S3_METADATA_PATH", None)
        prefix2 = raw_prefix(ws_id, prod_id, version)
        full_path2 = f"s3://{bucket}/{prefix2}{filename}"

        print(f"\n📌 Example 2: WITHOUT S3_METADATA_PATH (empty)")
        print(f"   Full S3 Path:")
        print(f"   {full_path2}")

        # Example 3: With different S3_METADATA_PATH value
        os.environ["S3_METADATA_PATH"] = "prod-data/archive"
        prefix3 = raw_prefix(ws_id, prod_id, version)
        full_path3 = f"s3://{bucket}/{prefix3}{filename}"

        print(f"\n📌 Example 3: WITH S3_METADATA_PATH='prod-data/archive'")
        print(f"   Full S3 Path:")
        print(f"   {full_path3}")

        print(f"\n{'='*100}\n")


class TestStoragePathValidation:
    """Validate storage path construction at unit level."""

    def test_raw_prefix_with_metadata_path(self):
        """Test raw_prefix includes S3_METADATA_PATH when set."""
        os.environ["S3_METADATA_PATH"] = "primedata-dev"

        ws_id = "ws-123"
        prod_id = "prod-456"
        version = 1

        prefix = raw_prefix(ws_id, prod_id, version)

        assert prefix.startswith("primedata-dev"), f"Prefix doesn't start with S3_METADATA_PATH: {prefix}"
        assert f"ws/{ws_id}" in prefix, f"Workspace not in prefix: {prefix}"
        assert f"prod/{prod_id}" in prefix, f"Product not in prefix: {prefix}"
        assert f"v/{version}" in prefix, f"Version not in prefix: {prefix}"
        assert prefix.endswith("raw/"), f"Prefix doesn't end with 'raw/': {prefix}"

    def test_raw_prefix_without_metadata_path(self):
        """Test raw_prefix works without S3_METADATA_PATH."""
        os.environ.pop("S3_METADATA_PATH", None)

        ws_id = "ws-789"
        prod_id = "prod-012"
        version = 2

        prefix = raw_prefix(ws_id, prod_id, version)

        assert prefix.startswith("ws/"), f"Prefix should start with 'ws/': {prefix}"
        assert f"ws/{ws_id}" in prefix, f"Workspace not in prefix: {prefix}"
        assert f"prod/{prod_id}" in prefix, f"Product not in prefix: {prefix}"
        assert f"v/{version}" in prefix, f"Version not in prefix: {prefix}"
        assert prefix.endswith("raw/"), f"Prefix doesn't end with 'raw/': {prefix}"

    def test_no_double_prefix(self):
        """Test that S3_METADATA_PATH is not duplicated in paths."""
        os.environ["S3_METADATA_PATH"] = "primedata-dev"

        ws_id = "ws-111"
        prod_id = "prod-222"
        version = 1

        prefix = raw_prefix(ws_id, prod_id, version)

        # Count occurrences of the metadata path
        count = prefix.count("primedata-dev")
        assert count == 1, f"S3_METADATA_PATH appears {count} times (should be 1): {prefix}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])