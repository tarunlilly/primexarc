"""
Web connector for scraping HTML content from URLs.
"""

import time
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import requests

from primedata.utils.log_utils import get_logger
from ..storage.storage_client import storage_client
from ..storage.paths import safe_filename
from .base import BaseConnector

logger = get_logger(__name__)


class WebConnector(BaseConnector):
    """Connector for web scraping and HTML content extraction."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize web connector.

        Expected config:
        {
            'urls': List[str],           # URLs to scrape
            'obey_robots': bool,         # Whether to respect robots.txt (default: True)
            'rate_limit_rps': float,     # Rate limit in requests per second (default: 1.0)
            'max_pages': int,            # Maximum pages to scrape (default: 50)
            'timeout': int,              # Request timeout in seconds (default: 30)
            'headers': Dict[str, str]    # Custom headers (optional)
        }
        """
        logger.info(f"🌐 WebConnector.__init__ | config keys: {list(config.keys())}")
        try:
            super().__init__(config)
            self.urls = config.get("urls", [])
            self.obey_robots = config.get("obey_robots", True)
            self.rate_limit_rps = config.get("rate_limit_rps", 1.0)
            self.max_pages = config.get("max_pages", 50)
            self.timeout = config.get("timeout", 30)
            self.headers = config.get("headers", {})

            logger.debug(f"📋 WebConnector init checkpoint: urls={len(self.urls)}, rate_limit_rps={self.rate_limit_rps}, max_pages={self.max_pages}, timeout={self.timeout}s")

            # Default headers
            default_headers = {"User-Agent": "PrimeData-WebConnector/1.0"}
            self.headers = {**default_headers, **self.headers}

            logger.info(f"✅ WebConnector.__init__ complete | {len(self.urls)} URLs configured")
        except Exception as e:
            logger.error(f"❌ WebConnector.__init__ failed: {e}", exc_info=True)
            raise

    def validate_config(self) -> Tuple[bool, str]:
        """Validate web connector configuration."""
        logger.info(f"🌐 WebConnector.validate_config | checking config validity")
        try:
            if not self.urls:
                logger.debug(f"📋 validate_config checkpoint: validating URLs list")
                logger.error(f"❌ validate_config failed: No URLs provided")
                return False, "No URLs provided"

            if not isinstance(self.urls, list):
                logger.error(f"❌ validate_config failed: URLs not a list, type={type(self.urls)}")
                return False, "URLs must be a list"

            # Validate URLs
            logger.debug(f"📋 validate_config checkpoint: validating {len(self.urls)} URLs")
            for url in self.urls:
                try:
                    parsed = urlparse(url)
                    if not parsed.scheme or not parsed.netloc:
                        logger.error(f"❌ validate_config failed: Invalid URL format: {url}")
                        return False, f"Invalid URL: {url}"
                except Exception as e:
                    logger.error(f"❌ validate_config failed: URL parse error for {url}: {e}")
                    return False, f"Invalid URL: {url}"

            if self.rate_limit_rps <= 0:
                logger.error(f"❌ validate_config failed: Invalid rate_limit_rps={self.rate_limit_rps}")
                return False, "Rate limit must be positive"

            if self.max_pages <= 0:
                logger.error(f"❌ validate_config failed: Invalid max_pages={self.max_pages}")
                return False, "Max pages must be positive"

            logger.info(f"✅ validate_config complete | config valid for {len(self.urls)} URLs")
            return True, "Configuration is valid"
        except Exception as e:
            logger.error(f"❌ validate_config error: {e}", exc_info=True)
            return False, str(e)

    def test_connection(self) -> Tuple[bool, str]:
        """Test connection by making a request to the first URL."""
        logger.info(f"🌐 WebConnector.test_connection | testing first URL in list")
        if not self.urls:
            logger.error(f"❌ test_connection failed: No URLs configured")
            return False, "No URLs configured"

        try:
            url = self.urls[0]
            logger.debug(f"📋 test_connection checkpoint: attempting request to {url} with timeout={self.timeout}s")
            response = requests.get(url, headers=self.headers, timeout=self.timeout, allow_redirects=True)

            if response.status_code == 200:
                logger.info(f"✅ test_connection complete | successfully connected to {url} (status: {response.status_code})")
                return True, f"Successfully connected to {url} (status: {response.status_code})"
            else:
                logger.warning(f"❌ test_connection failed: HTTP {response.status_code} from {url}")
                return False, f"HTTP {response.status_code} from {url}"

        except requests.exceptions.Timeout:
            logger.error(f"❌ test_connection failed: Timeout connecting to {url}")
            return False, f"Timeout connecting to {url}"
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ test_connection failed: Connection error to {url}")
            return False, f"Connection error to {url}"
        except Exception as e:
            logger.error(f"❌ test_connection failed: {type(e).__name__}: {e}", exc_info=True)
            return False, f"Error connecting to {url}: {str(e)}"

    def sync_full(self, output_bucket: str, output_prefix: str) -> Dict[str, Any]:
        """Scrape all configured URLs and store HTML content."""
        logger.info(f"🌐 WebConnector.sync_full | bucket={output_bucket}, prefix={output_prefix}, urls_count={len(self.urls)}")
        start_time = time.time()
        files_processed = 0
        bytes_transferred = 0
        errors = 0
        details = {"urls_processed": [], "urls_failed": [], "total_requests": 0}

        try:
            # Limit URLs to max_pages
            urls_to_process = self.urls[: self.max_pages]
            logger.debug(f"📋 sync_full checkpoint: processing {len(urls_to_process)} URLs (max_pages={self.max_pages})")

            for i, url in enumerate(urls_to_process):
                try:
                    # Rate limiting
                    if i > 0:
                        logger.debug(f"📋 sync_full checkpoint: rate limiting {i+1}/{len(urls_to_process)}")
                        time.sleep(1.0 / self.rate_limit_rps)

                    # Make request
                    logger.debug(f"📋 sync_full checkpoint: fetching URL {i+1}/{len(urls_to_process)}: {url}")
                    response = requests.get(url, headers=self.headers, timeout=self.timeout, allow_redirects=True)
                    details["total_requests"] += 1

                    if response.status_code == 200:
                        # Generate safe filename
                        parsed_url = urlparse(url)
                        filename = f"{parsed_url.netloc}_{safe_filename(parsed_url.path)}"
                        if not filename.endswith(".html"):
                            filename += ".html"

                        # Store content
                        key = f"{output_prefix}{filename}"
                        content = response.content

                        logger.debug(f"📋 sync_full checkpoint: storing {filename} ({len(content)} bytes) to S3")
                        success = storage_client.put_bytes(output_bucket, key, content, "text/html")

                        if success:
                            files_processed += 1
                            bytes_transferred += len(content)
                            details["urls_processed"].append(
                                {"url": url, "filename": filename, "size": len(content), "status_code": response.status_code}
                            )
                            logger.info(f"✅ sync_full | stored {url} as {filename} ({len(content)} bytes)")
                        else:
                            errors += 1
                            details["urls_failed"].append({"url": url, "error": "Failed to store in storage"})
                            logger.error(f"❌ sync_full failed: could not store {url} to S3")
                    else:
                        errors += 1
                        details["urls_failed"].append({"url": url, "error": f"HTTP {response.status_code}"})
                        logger.warning(f"❌ sync_full warning: HTTP {response.status_code} for {url}")

                except requests.exceptions.Timeout:
                    errors += 1
                    details["urls_failed"].append({"url": url, "error": "Timeout"})
                    logger.error(f"❌ sync_full failed: timeout for {url}")
                except Exception as e:
                    errors += 1
                    details["urls_failed"].append({"url": url, "error": str(e)})
                    logger.error(f"❌ sync_full failed: {type(e).__name__} processing {url}: {e}", exc_info=True)

            duration = time.time() - start_time

            result = {
                "files": files_processed,
                "bytes": bytes_transferred,
                "errors": errors,
                "duration": duration,
                "details": details,
            }

            logger.info(f"✅ sync_full complete | files={files_processed}, bytes={bytes_transferred}, errors={errors}, duration={duration:.2f}s")
            return result
        except Exception as e:
            logger.error(f"❌ sync_full error: {type(e).__name__}: {e}", exc_info=True)
            raise

    def _get_config_schema(self) -> Dict[str, Any]:
        """Get JSON schema for web connector configuration."""
        logger.info(f"🌐 WebConnector._get_config_schema | generating config schema")
        try:
            logger.debug(f"📋 _get_config_schema checkpoint: building schema properties")
            schema = {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string", "format": "uri"},
                        "description": "List of URLs to scrape",
                    },
                    "obey_robots": {"type": "boolean", "default": True, "description": "Whether to respect robots.txt"},
                    "rate_limit_rps": {
                        "type": "number",
                        "minimum": 0.1,
                        "maximum": 10.0,
                        "default": 1.0,
                        "description": "Rate limit in requests per second",
                    },
                    "max_pages": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 1000,
                        "default": 50,
                        "description": "Maximum number of pages to scrape",
                    },
                    "timeout": {
                        "type": "integer",
                        "minimum": 5,
                        "maximum": 300,
                        "default": 30,
                        "description": "Request timeout in seconds",
                    },
                    "headers": {"type": "object", "description": "Custom HTTP headers"},
                },
                "required": ["urls"],
            }
            logger.info(f"✅ _get_config_schema complete | schema generated")
            return schema
        except Exception as e:
            logger.error(f"❌ _get_config_schema error: {type(e).__name__}: {e}", exc_info=True)
            raise
