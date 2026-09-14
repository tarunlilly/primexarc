"""
Test DataSource API endpoints including type normalization.
Tests lowercase/mixed-case datasource type inputs are normalized to uppercase.
"""

import pytest
from uuid import uuid4
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.orm import Session

from primedata.api.datasources import DataSourceCreateRequest, TestConfigRequest
from primedata.db.models import DataSourceType


class TestDataSourceTypeNormalization:
    """Test that DataSourceType inputs are normalized to uppercase."""

    def test_lowercase_web_normalized_to_uppercase(self):
        """Test lowercase 'web' is normalized to uppercase 'WEB'."""
        # Create request with lowercase type
        request = DataSourceCreateRequest(
            workspace_id=uuid4(),
            product_id=uuid4(),
            name="Test Web Source",
            type="web",  # lowercase
            config={"urls": ["https://example.com"]}
        )

        # Should be converted to uppercase WEB
        assert request.type == DataSourceType.WEB
        assert request.type.value == "WEB"
        print("✅ Lowercase 'web' normalized to 'WEB'")

    def test_lowercase_aws_s3_normalized_to_uppercase(self):
        """Test lowercase 'aws_s3' is normalized to uppercase 'AWS_S3'."""
        # Create request with lowercase type
        request = DataSourceCreateRequest(
            workspace_id=uuid4(),
            product_id=uuid4(),
            name="Test AWS S3 Source",
            type="aws_s3",  # lowercase
            config={
                "s3_bucket_name": "primedata-dev",
                "s3_region": "us-east-2",
                "s3_prefix": "test2/sample_test/",
                "inclusion_patterns": ".pdf,.docx"
            }
        )

        # Should be converted to uppercase AWS_S3
        assert request.type == DataSourceType.AWS_S3
        assert request.type.value == "AWS_S3"
        print("✅ Lowercase 'aws_s3' normalized to 'AWS_S3'")

    def test_lowercase_folder_normalized_to_uppercase(self):
        """Test lowercase 'folder' is normalized to uppercase 'FOLDER'."""
        request = DataSourceCreateRequest(
            workspace_id=uuid4(),
            product_id=uuid4(),
            name="Test Folder Source",
            type="folder",  # lowercase
            config={"root_path": "/data/files"}
        )

        assert request.type == DataSourceType.FOLDER
        assert request.type.value == "FOLDER"
        print("✅ Lowercase 'folder' normalized to 'FOLDER'")

    def test_lowercase_azure_blob_normalized_to_uppercase(self):
        """Test lowercase 'azure_blob' is normalized to uppercase 'AZURE_BLOB'."""
        request = DataSourceCreateRequest(
            workspace_id=uuid4(),
            product_id=uuid4(),
            name="Test Azure Source",
            type="azure_blob",  # lowercase
            config={"container_name": "data", "connection_string": "..."}
        )

        assert request.type == DataSourceType.AZURE_BLOB
        assert request.type.value == "AZURE_BLOB"
        print("✅ Lowercase 'azure_blob' normalized to 'AZURE_BLOB'")

    def test_mixed_case_normalized_to_uppercase(self):
        """Test mixed case like 'Aws_S3' is normalized to uppercase 'AWS_S3'."""
        request = DataSourceCreateRequest(
            workspace_id=uuid4(),
            product_id=uuid4(),
            name="Test Mixed Case",
            type="Aws_S3",  # mixed case
            config={"s3_bucket_name": "test"}
        )

        assert request.type == DataSourceType.AWS_S3
        assert request.type.value == "AWS_S3"
        print("✅ Mixed case 'Aws_S3' normalized to 'AWS_S3'")

    def test_uppercase_unchanged(self):
        """Test uppercase 'WEB' remains unchanged."""
        request = DataSourceCreateRequest(
            workspace_id=uuid4(),
            product_id=uuid4(),
            name="Test Uppercase",
            type="WEB",  # already uppercase
            config={"urls": ["https://example.com"]}
        )

        assert request.type == DataSourceType.WEB
        assert request.type.value == "WEB"
        print("✅ Uppercase 'WEB' unchanged")

    def test_test_config_request_normalizes_type(self):
        """Test TestConfigRequest also normalizes incoming types."""
        request = TestConfigRequest(
            type="aws_s3",  # lowercase
            config={
                "s3_bucket_name": "primedata-dev",
                "s3_region": "us-east-2"
            }
        )

        assert request.type == DataSourceType.AWS_S3
        assert request.type.value == "AWS_S3"
        print("✅ TestConfigRequest normalizes 'aws_s3' to 'AWS_S3'")

    def test_enum_constant_comparison(self):
        """Test that enum comparisons work correctly with normalized types."""
        request = DataSourceCreateRequest(
            workspace_id=uuid4(),
            product_id=uuid4(),
            name="Test Enum Comparison",
            type="web",  # lowercase input
            config={"urls": ["https://example.com"]}
        )

        # Direct enum comparison (as used in the code)
        if request.type == DataSourceType.WEB:
            result = "matched_web"
        elif request.type == DataSourceType.FOLDER:
            result = "matched_folder"
        else:
            result = "no_match"

        assert result == "matched_web"
        print("✅ Enum comparison works with normalized types")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
