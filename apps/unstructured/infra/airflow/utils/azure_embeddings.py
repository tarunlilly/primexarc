"""
Azure OpenAI Embeddings Integration

Provides embeddings through Azure OpenAI API with fallback to local FastEmbed.
Supports production-grade authentication, caching, and error handling.
"""

import logging
import os
from typing import List, Optional, Dict, Any
from functools import lru_cache

logger = logging.getLogger(__name__)


class AzureEmbeddingsClient:
    """Azure OpenAI embeddings client with fallback support."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: str = "2024-02-15-preview",
        deployment_name: str = "text-embedding-3-large",
        embedding_dimensions: int = 3072,
    ):
        """
        Initialize Azure OpenAI embeddings client.

        Args:
            api_key: Azure OpenAI API key (env: AZURE_OPENAI_API_KEY)
            endpoint: Azure OpenAI endpoint URL (env: AZURE_OPENAI_ENDPOINT)
            api_version: OpenAI API version
            deployment_name: Embedding model deployment name
            embedding_dimensions: Output embedding dimensions (1536 or 3072)
        """
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_version = api_version or os.getenv(
            "AZURE_OPENAI_API_VERSION", "2024-02-15-preview"
        )
        self.deployment_name = deployment_name or os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"
        )
        self.embedding_dimensions = embedding_dimensions or int(
            os.getenv("AZURE_OPENAI_EMBEDDING_DIMENSIONS", "3072")
        )

        self.client = None
        self.fallback_client = None
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize Azure client with fallback to FastEmbed."""
        try:
            if self.api_key and self.endpoint:
                from azure.openai import AzureOpenAI

                self.client = AzureOpenAI(
                    api_key=self.api_key,
                    api_version=self.api_version,
                    azure_endpoint=self.endpoint,
                )
                logger.info(f"✓ Azure OpenAI client initialized: {self.deployment_name}")
            else:
                logger.warning(
                    "⚠️ Azure credentials not configured (AZURE_OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT missing)"
                )
                self._initialize_fallback()

        except Exception as e:
            logger.error(f"❌ Failed to initialize Azure client: {e}")
            self._initialize_fallback()

    def _initialize_fallback(self):
        """Initialize FastEmbed fallback client."""
        try:
            from fastembed import TextEmbedding

            self.fallback_client = TextEmbedding(
                model_name="BAAI/bge-large-en-v1.5", max_length=512
            )
            logger.info("✓ FastEmbed fallback client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize FastEmbed fallback: {e}")

    def embed_text(
        self,
        text: str,
        use_azure: bool = True,
    ) -> Optional[List[float]]:
        """
        Embed a single text string.

        Args:
            text: Text to embed
            use_azure: Try Azure first (True) or use fallback (False)

        Returns:
            List of floats representing the embedding, or None if failed
        """
        try:
            if use_azure and self.client:
                return self._embed_azure([text])[0]
            elif self.fallback_client:
                return self._embed_fastembed([text])[0]
            else:
                logger.error("❌ No embedding client available")
                return None
        except Exception as e:
            logger.error(f"❌ Error embedding text: {e}")
            return None

    def embed_texts(
        self,
        texts: List[str],
        use_azure: bool = True,
    ) -> Optional[List[List[float]]]:
        """
        Embed multiple texts.

        Args:
            texts: List of texts to embed
            use_azure: Try Azure first (True) or use fallback (False)

        Returns:
            List of embeddings, or None if failed
        """
        try:
            if use_azure and self.client:
                return self._embed_azure(texts)
            elif self.fallback_client:
                return self._embed_fastembed(texts)
            else:
                logger.error("❌ No embedding client available")
                return None
        except Exception as e:
            logger.error(f"❌ Error embedding texts: {e}")
            return None

    def _embed_azure(self, texts: List[str]) -> List[List[float]]:
        """
        Embed texts using Azure OpenAI API.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings
        """
        if not self.client:
            raise RuntimeError("Azure client not initialized")

        try:
            response = self.client.embeddings.create(
                input=texts,
                model=self.deployment_name,
                dimensions=self.embedding_dimensions,
            )

            embeddings = sorted(response.data, key=lambda x: x.index)
            result = [embedding.embedding for embedding in embeddings]

            logger.debug(
                f"✓ Azure embedded {len(texts)} texts → {len(result)} embeddings"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Azure embedding failed: {e}")
            if self.fallback_client:
                logger.info("↻ Falling back to FastEmbed...")
                return self._embed_fastembed(texts)
            raise

    def _embed_fastembed(self, texts: List[str]) -> List[List[float]]:
        """
        Embed texts using FastEmbed (local, CPU-based).

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings
        """
        if not self.fallback_client:
            raise RuntimeError("FastEmbed client not initialized")

        try:
            embeddings = list(self.fallback_client.embed(texts))
            logger.debug(
                f"✓ FastEmbed embedded {len(texts)} texts → {len(embeddings)} embeddings"
            )
            return embeddings

        except Exception as e:
            logger.error(f"❌ FastEmbed embedding failed: {e}")
            raise

    @property
    def is_azure_available(self) -> bool:
        """Check if Azure client is available."""
        return self.client is not None

    @property
    def is_fallback_available(self) -> bool:
        """Check if fallback client is available."""
        return self.fallback_client is not None

    def get_status(self) -> Dict[str, Any]:
        """Get client status information."""
        return {
            "azure_available": self.is_azure_available,
            "azure_deployment": self.deployment_name if self.is_azure_available else None,
            "azure_dimensions": self.embedding_dimensions,
            "fallback_available": self.is_fallback_available,
            "fallback_model": "BAAI/bge-large-en-v1.5" if self.is_fallback_available else None,
        }


@lru_cache(maxsize=1)
def get_embeddings_client() -> AzureEmbeddingsClient:
    """Get or create singleton embeddings client."""
    return AzureEmbeddingsClient()


def embed_text(text: str) -> Optional[List[float]]:
    """Convenience function to embed a single text."""
    client = get_embeddings_client()
    return client.embed_text(text)


def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    """Convenience function to embed multiple texts."""
    client = get_embeddings_client()
    return client.embed_texts(texts)
