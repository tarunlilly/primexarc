"""
PrimeData Storage Package

This package contains storage-related components for S3 and GCS backends.
"""

from .storage_client import StorageClient, storage_client

__all__ = ["StorageClient", "storage_client"]

