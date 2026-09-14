"""
Embedding generation module for PrimeData.

This module provides functionality to generate embeddings for text chunks
using various embedding models, with MiniLM as the default.

Key runtime goals (Airflow-friendly):
- Avoid importing heavy torch/sentence-transformers at DAG import time.
- Prefer fastembed (onnxruntime-based) to avoid torch/transformers ABI issues.
- Provide deterministic hash fallback when model deps are unavailable.
"""

import hashlib
from typing import Any, Dict, List, Optional
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from ..core.embedding_config import get_embedding_model_config, AZURE_OPENAI_DEPLOYMENT_NAMES
from ..core.settings import get_settings
from ..utils.log_utils import get_logger

logger = get_logger(__name__)


class EmbeddingGenerator:
    """Generate embeddings for text using various models."""

    def __init__(
        self,
        model_name: str,
        dimension: Optional[int] = None,
        workspace_id: Optional[UUID] = None,
        db: Optional[Session] = None,
        deployment_name: Optional[str] = None,
    ) -> None:
        """
        Initialize embedding generator.

        Args:
            model_name: Name of the embedding model to use
            dimension: Expected embedding dimension (auto-detected if None)
            workspace_id: Optional workspace ID to check for API keys in workspace settings
            db: Optional database session to query workspace settings
            deployment_name: Optional Azure OpenAI deployment name (overrides env var if provided)
        """
        self.model_name = model_name
        self.deployment_name = deployment_name

        model_config = get_embedding_model_config(model_name)
        self.model_config = model_config

        if model_config:
            self.dimension = int(dimension or model_config.dimension or 384)
            logger.info(f"Initializing {model_config.name} with expected dimension {self.dimension}")
        else:
            self.dimension = int(dimension or 384)
            logger.warning(f"Unknown model {model_name}, using fallback dimension {self.dimension}")

        # Runtime handles
        self.model = None  # may be fastembed embedder or other backend
        self.openai_client = None
        self.workspace_id = workspace_id
        self.db = db

        # Runtime stats (used for vector/embedding health metrics)
        # NOTE: These are best-effort counters (no guarantees in multithreaded use).
        self.stats: Dict[str, float] = {
            "texts_total": 0.0,
            "api_requests": 0.0,  # OpenAI calls (single or batch)
            "api_errors": 0.0,
            "embed_calls": 0.0,  # fastembed calls (single or batch)
            "embed_errors": 0.0,
            "fallback_vectors": 0.0,  # number of vectors produced via hash fallback
            "dim_mismatch_vectors": 0.0,  # vectors whose original dim != expected (coerced)
        }

        # Initialize the model
        self._load_model()

    # -------------------------
    # Model loading
    # -------------------------
    def _load_model(self) -> None:
        """Load the embedding model using centralized configuration."""
        logger.debug(f"🧠 Loading embedding model: {self.model_name}")
        model_config = self.model_config

        try:
            # Check if model_name is in AZURE_OPENAI_DEPLOYMENT_NAMES
            if self.model_name in AZURE_OPENAI_DEPLOYMENT_NAMES:
                s = get_settings()
                # Use deployment_name from init param or env var
                deployment_name = self.deployment_name or s.AZURE_OPENAI_DEPLOYMENT_NAME

                logger.info(f"📋 Recognized Azure OpenAI model: {self.model_name}")
                logger.info(f"   ├─ Model Name: {self.model_name}")
                logger.info(f"   ├─ Deployment Name: {deployment_name}")
                logger.debug(f"📏 Dimension from environment: {self.dimension}")

                # Create a temporary model config for Azure OpenAI
                from dataclasses import dataclass
                from primedata.core.embedding_config import EmbeddingModelType

                # Create synthetic model config for Azure OpenAI
                @dataclass
                class AzureModelConfig:
                    id: str = self.model_name
                    name: str = f"Azure OpenAI ({self.model_name})"
                    description: str = f"Azure OpenAI deployment: {deployment_name}"
                    model_type: EmbeddingModelType = EmbeddingModelType.AZURE_OPENAI
                    dimension: int = self.dimension
                    model_path: str = deployment_name  # ← Use deployment name for connection
                    is_available: bool = True
                    requires_api_key: bool = False
                    metadata: dict = None

                self.model_config = AzureModelConfig()
                self._load_azure_openai_model()
                return

            if not model_config:
                logger.warning(f"⚠️ Unknown model {self.model_name}, falling back to hash-based embeddings")
                self.model = None
                return

            if not getattr(model_config, "is_available", True):
                logger.warning(f"⚠️ Model {self.model_name} is not available, falling back to hash-based embeddings")
                self.model = None
                return

            model_type = getattr(model_config.model_type, "value", str(model_config.model_type))
            logger.debug(f"📋 Model type: {model_type}")

            # --- Prefer fastembed for local sentence-transformer class models ---
            if model_type == "sentence_transformers":
                logger.debug("📋 Attempting to load fastembed")
                # IMPORTANT:
                # We intentionally prefer fastembed to avoid torch/transformers issues in containers.
                # fastembed supports several popular ST models via ONNX runtime.
                self.model = self._try_load_fastembed(model_config.model_path)
                if self.model is not None:
                    logger.info(f"✅ Loaded fastembed model for {model_config.name}: {model_config.model_path}")
                    return

                # If fastembed fails (SSL errors, network issues), fall back to native sentence-transformers
                logger.warning(
                    "⚠️ fastembed not available or failed to load. "
                    "Attempting fallback to native sentence-transformers..."
                )
                self.model = self._try_load_sentence_transformers(model_config.model_path)
                if self.model is not None:
                    logger.info(f"✅ Loaded sentence-transformers model for {model_config.name}: {model_config.model_path}")
                    return

                # If both fail, fall back to hash-based embeddings
                logger.error(
                    "❌ Both fastembed and sentence-transformers failed. "
                    "Falling back to hash-based embeddings (search will not work semantically)."
                )
                self.model = None
                return

            # --- OpenAI embeddings ---
            if model_type == "openai":
                logger.debug("📋 Attempting to load OpenAI embeddings")
                api_key = self._get_openai_api_key()
                if not api_key:
                    logger.warning(
                        f"⚠️ OpenAI API key not configured for {model_config.name}. "
                        "Set workspace setting openai_api_key or OPENAI_API_KEY env var. "
                        "Falling back to hash-based embeddings."
                    )
                    self.model = None
                    self.openai_client = None
                    return

                try:
                    import openai  # type: ignore

                    self.openai_client = openai.OpenAI(api_key=api_key)
                    self.model = "openai"
                    logger.info(f"✅ OpenAI model {model_config.name} configured")
                    return
                except ImportError:
                    logger.error("❌ openai package not installed. Install with: pip install openai")
                    self.model = None
                    self.openai_client = None
                    return

            # --- Azure OpenAI embeddings (Service Principal via Graph API) ---
            if model_type == "azure_openai":
                logger.debug("📋 Attempting to load Azure OpenAI embeddings")
                self._load_azure_openai_model()
                return

            logger.warning(f"⚠️ Unsupported model type {model_config.model_type} for {self.model_name}")
            self.model = None

        except Exception as e:
            logger.error(f"❌ Failed to load model {self.model_name}: {e}", exc_info=True)
            logger.warning("⚠️ Falling back to hash-based embeddings")
            self.model = None
            self.openai_client = None

    def _try_load_fastembed(self, model_path: str) -> Optional[Any]:
        """
        Try to load a fastembed TextEmbedding model.
        Returns the embedder instance or None.
        """
        try:
            from fastembed import TextEmbedding  # type: ignore
        except Exception as e:
            logger.warning(f"fastembed not importable: {e}")
            return None

        try:
            # fastembed expects model names it supports, e.g.
            # "sentence-transformers/all-MiniLM-L6-v2"
            # Your config should set model_path accordingly.
            embedder = TextEmbedding(model_name=model_path)
            return embedder
        except Exception as e:
            logger.warning(f"fastembed failed to initialize for model '{model_path}': {e}")
            return None

    def _try_load_sentence_transformers(self, model_path: str) -> Optional[Any]:
        """
        Try to load native sentence-transformers model as fallback.
        Returns the model instance or None.
        """
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as e:
            logger.warning(f"sentence-transformers not importable: {e}")
            return None

        try:
            model = SentenceTransformer(model_path)
            logger.info(f"Loaded sentence-transformers model: {model_path}")
            return model
        except Exception as e:
            logger.warning(f"sentence-transformers failed to initialize for model '{model_path}': {e}")
            return None

    def _get_openai_api_key(self) -> Optional[str]:
        """Get OpenAI API key: workspace settings first, then environment."""
        api_key = None

        if self.workspace_id and self.db:
            try:
                from primedata.db.models import Workspace  # local import to avoid heavy imports

                ws = self.db.query(Workspace).filter(Workspace.id == self.workspace_id).first()
                if ws and getattr(ws, "settings", None):
                    api_key = ws.settings.get("openai_api_key")
            except Exception as e:
                logger.warning(f"Failed to load workspace settings for OpenAI key: {e}")

        if not api_key:
            settings = get_settings()
            api_key = getattr(settings, "OPENAI_API_KEY", None)

        return api_key

    def _load_azure_openai_model(self) -> None:
        """Load Azure OpenAI client with Service Principal authentication."""
        try:
            from primedata.core.settings import get_settings
            from primedata.indexing.azure_openai_auth import AzureOpenAITokenProvider
            import openai  # type: ignore

            s = get_settings()

            # Validate required Azure credentials
            if not all([s.AZURE_CLIENT_ID, s.AZURE_CLIENT_SECRET, s.AZURE_TENANT_ID, s.AZURE_OPENAI_ENDPOINT]):
                logger.error(
                    "❌ Azure OpenAI credentials not fully configured. "
                    "Set: AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID, AZURE_OPENAI_ENDPOINT"
                )
                self.model = None
                self.openai_client = None
                return

            # Create token provider for Graph API authentication
            logger.debug("🔐 Initializing Azure token provider")
            self._azure_token_provider = AzureOpenAITokenProvider(
                tenant_id=s.AZURE_TENANT_ID,
                client_id=s.AZURE_CLIENT_ID,
                client_secret=s.AZURE_CLIENT_SECRET,
                scope=s.AZURE_OPENAI_SCOPE,
            )

            # Initialize Azure OpenAI client with token provider
            logger.debug(f"📋 Creating Azure OpenAI client for {s.AZURE_OPENAI_ENDPOINT}")
            self.openai_client = openai.AzureOpenAI(
                azure_endpoint=s.AZURE_OPENAI_ENDPOINT,
                azure_ad_token_provider=self._azure_token_provider.get_token,
                api_version=s.AZURE_OPENAI_API_VERSION,
            )
            self.model = "azure_openai"
            logger.info(
                f"✅ Azure OpenAI model configured: {s.AZURE_OPENAI_MODEL_NAME or s.AZURE_OPENAI_DEPLOYMENT_NAME} "
                f"(dim={s.AZURE_OPENAI_DIMENSIONS})"
            )

        except ImportError as e:
            logger.error(f"❌ openai package not installed: {e}. Install with: pip install openai")
            self.model = None
            self.openai_client = None
        except Exception as e:
            logger.error(f"❌ Failed to initialize Azure OpenAI: {e}", exc_info=True)
            self.model = None
            self.openai_client = None

    # -------------------------
    # Embedding generation
    # -------------------------
    def embed(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        logger.debug(f"🧠 Generating embedding for text (len={len(text)})")
        self.stats["texts_total"] += 1.0
        if not text:
            logger.debug("✓ Empty text, returning zero vector")
            return self._coerce_dim(np.zeros(self.dimension, dtype=np.float32))

        # OpenAI
        if self.model == "openai" and self.openai_client and self.model_config:
            logger.debug("📋 Using OpenAI embeddings")
            self.stats["api_requests"] += 1.0
            try:
                resp = self.openai_client.embeddings.create(model=self.model_config.model_path, input=text)
                vec = np.array(resp.data[0].embedding, dtype=np.float32)
                logger.debug(f"✅ Generated OpenAI embedding (dim={len(vec)})")
                return self._coerce_dim(vec)
            except Exception as e:
                logger.error(f"❌ Error generating OpenAI embedding: {e}", exc_info=True)
                self.stats["api_errors"] += 1.0
                self.stats["fallback_vectors"] += 1.0
                logger.debug("📋 Falling back to hash embedding")
                return self._hash_embedding(text)

        # Azure OpenAI (AzureOpenAI client is API-compatible with OpenAI)
        if self.model == "azure_openai" and self.openai_client and self.model_config:
            logger.debug("📋 Using Azure OpenAI embeddings")
            self.stats["api_requests"] += 1.0
            try:
                resp = self.openai_client.embeddings.create(model=self.model_config.model_path, input=text)
                vec = np.array(resp.data[0].embedding, dtype=np.float32)
                logger.debug(f"✅ Generated Azure OpenAI embedding (dim={len(vec)})")
                return self._coerce_dim(vec)
            except Exception as e:
                logger.error(f"❌ Error generating Azure OpenAI embedding: {e}", exc_info=True)
                self.stats["api_errors"] += 1.0
                self.stats["fallback_vectors"] += 1.0
                logger.debug("📋 Falling back to hash embedding")
                return self._hash_embedding(text)

        # fastembed (TextEmbedding) or sentence-transformers (SentenceTransformer)
        if self.model is not None and self.model not in ("openai", "azure_openai"):
            logger.debug("📋 Using local embedding model")
            self.stats["embed_calls"] += 1.0
            try:
                # Check if it's a SentenceTransformer model (has .encode method)
                if hasattr(self.model, 'encode'):
                    # sentence-transformers model
                    logger.debug("📋 Using sentence-transformers")
                    vec = self.model.encode(text, convert_to_numpy=True, show_progress_bar=False)
                    vec = np.asarray(vec, dtype=np.float32)
                    logger.debug(f"✅ Generated embedding (dim={len(vec)})")
                    return self._coerce_dim(vec)
                else:
                    # fastembed model (returns iterator)
                    logger.debug("📋 Using fastembed")
                    vec = next(iter(self.model.embed([text])))
                    vec = np.asarray(vec, dtype=np.float32)
                    logger.debug(f"✅ Generated embedding (dim={len(vec)})")
                    return self._coerce_dim(vec)
            except Exception as e:
                logger.error(f"❌ Error generating embedding: {e}", exc_info=True)
                self.stats["embed_errors"] += 1.0
                self.stats["fallback_vectors"] += 1.0
                logger.debug("📋 Falling back to hash embedding")
                return self._hash_embedding(text)

        # hash fallback
        logger.debug("📋 Using hash-based fallback embedding")
        self.stats["fallback_vectors"] += 1.0
        return self._hash_embedding(text)

    def embed_batch(self, texts: List[str], batch_size: Optional[int] = None) -> List[np.ndarray]:
        """Generate embeddings for a batch of texts."""
        logger.debug(f"🧠 Generating batch embeddings for {len(texts)} texts")
        if not texts:
            logger.debug("✓ Empty texts list")
            return []
        self.stats["texts_total"] += float(len(texts))

        # OpenAI
        if self.model == "openai" and self.openai_client and self.model_config:
            logger.debug("📋 Using OpenAI batch embeddings")
            self.stats["api_requests"] += 1.0
            try:
                resp = self.openai_client.embeddings.create(model=self.model_config.model_path, input=texts)
                out = [self._coerce_dim(np.array(item.embedding, dtype=np.float32)) for item in resp.data]
                logger.debug(f"✅ Generated {len(out)} OpenAI embeddings")
                return out
            except Exception as e:
                logger.error(f"❌ Error generating OpenAI batch embeddings: {e}", exc_info=True)
                self.stats["api_errors"] += 1.0
                self.stats["fallback_vectors"] += float(len(texts))
                logger.debug("📋 Falling back to hash embeddings")
                return [self._hash_embedding(t) for t in texts]

        # Azure OpenAI (AzureOpenAI client is API-compatible with OpenAI)
        if self.model == "azure_openai" and self.openai_client and self.model_config:
            logger.debug("📋 Using Azure OpenAI batch embeddings")
            self.stats["api_requests"] += 1.0
            try:
                resp = self.openai_client.embeddings.create(model=self.model_config.model_path, input=texts)
                out = [self._coerce_dim(np.array(item.embedding, dtype=np.float32)) for item in resp.data]
                logger.debug(f"✅ Generated {len(out)} Azure OpenAI embeddings")
                return out
            except Exception as e:
                logger.error(f"❌ Error generating Azure OpenAI batch embeddings: {e}", exc_info=True)
                self.stats["api_errors"] += 1.0
                self.stats["fallback_vectors"] += float(len(texts))
                logger.debug("📋 Falling back to hash embeddings")
                return [self._hash_embedding(t) for t in texts]

        # fastembed or sentence-transformers
        if self.model is not None and self.model not in ("openai", "azure_openai"):
            logger.debug("📋 Using local batch embeddings")
            self.stats["embed_calls"] += 1.0
            try:
                # Check if it's a SentenceTransformer model (has .encode method)
                if hasattr(self.model, 'encode'):
                    # sentence-transformers model
                    logger.debug("📋 Using sentence-transformers batch")
                    vectors = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False, batch_size=batch_size or 32)
                    out = [self._coerce_dim(np.asarray(v, dtype=np.float32)) for v in vectors]
                    logger.debug(f"✅ Generated {len(out)} embeddings from sentence-transformers")
                    return out
                else:
                    # fastembed model (does its own batching internally)
                    logger.debug("📋 Using fastembed batch")
                    vectors = list(self.model.embed(texts))
                    out = [self._coerce_dim(np.asarray(v, dtype=np.float32)) for v in vectors]
                    logger.debug(f"✅ Generated {len(out)} embeddings from fastembed")
                    return out
            except Exception as e:
                logger.error(f"❌ Error generating batch embeddings: {e}", exc_info=True)
                self.stats["embed_errors"] += 1.0
                self.stats["fallback_vectors"] += float(len(texts))
                logger.debug("📋 Falling back to hash embeddings")
                return [self._hash_embedding(t) for t in texts]

        # hash fallback
        logger.debug(f"📋 Using hash-based fallback for {len(texts)} texts")
        self.stats["fallback_vectors"] += float(len(texts))
        return [self._hash_embedding(t) for t in texts]

    # -------------------------
    # Helpers
    # -------------------------
    def _coerce_dim(self, vec: np.ndarray) -> np.ndarray:
        """
        Ensure vector has exactly self.dimension.
        Pads or truncates deterministically if needed.
        """
        vec = np.asarray(vec, dtype=np.float32).reshape(-1)
        if vec.shape[0] != self.dimension:
            self.stats["dim_mismatch_vectors"] += 1.0
        if vec.shape[0] == self.dimension:
            return vec

        if vec.shape[0] > self.dimension:
            return vec[: self.dimension]

        # pad with zeros
        out = np.zeros(self.dimension, dtype=np.float32)
        out[: vec.shape[0]] = vec
        return out

    def _hash_embedding(self, text: str) -> np.ndarray:
        """Generate a deterministic hash-based embedding as fallback."""
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        out = np.zeros(self.dimension, dtype=np.float32)
        hb = bytes.fromhex(text_hash)

        for i in range(self.dimension):
            b = hb[i % len(hb)]
            out[i] = (float(b) - 128.0) / 128.0

        # embed length signal
        out[0] = min(len(text) / 1000.0, 1.0)
        return out

    def get_dimension(self) -> int:
        """Get embedding dimension."""
        if self.model == "openai" and self.model_config:
            return int(self.model_config.dimension)
        return int(self.dimension)

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model."""
        is_openai = self.model == "openai" and self.openai_client is not None
        is_fastembed = self.model is not None and self.model != "openai"
        model_loaded = is_openai or is_fastembed

        model_type = None
        if is_openai:
            model_type = "openai"
        elif is_fastembed:
            model_type = "fastembed"

        return {
            "model_name": self.model_name,
            "dimension": self.get_dimension(),
            "model_loaded": model_loaded,
            "model_type": model_type,
            "fallback_mode": not model_loaded,
        }


def create_embedding_generator(
    model_name: str,
    dimension: Optional[int] = None,
    workspace_id: Optional[UUID] = None,
    db: Optional[Session] = None,
    deployment_name: Optional[str] = None,
) -> EmbeddingGenerator:
    """Factory function to create an embedding generator. Model name must be explicitly specified."""
    return EmbeddingGenerator(model_name, dimension, workspace_id, db, deployment_name)



def get_default_embedder() -> EmbeddingGenerator:
    """
    Raises an error - no default embedder available.
    MiniLM has been removed. Explicitly specify a model_name when creating EmbeddingGenerator.

    Example:
        embedder = EmbeddingGenerator("text-embedding-3-large", 3072)
        embedder = EmbeddingGenerator("e5-large", 1024)
    """
    raise RuntimeError(
        "No default embedder available. You must explicitly specify a model_name. "
        "Example: EmbeddingGenerator('text-embedding-3-large', 3072) or "
        "EmbeddingGenerator('e5-large', 1024)"
    )
