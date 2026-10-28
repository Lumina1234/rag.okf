"""
Embeddings service.
Singleton wrapper around sentence-transformers (BAAI/bge-m3).
Supports local cached model path for fully offline use.
"""
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import List

from core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Thin wrapper around HuggingFaceEmbeddings.
    Uses a local path if the model has been pre-downloaded; otherwise
    downloads from HuggingFace on first run.
    """

    def __init__(self):
        self._embeddings = None
        self._model_name: str = settings.EMBEDDING_MODEL
        self._local_path: Path = settings.MODELS_DIR / "bge-m3"

    def _load(self):
        """Lazy-load the embedding model (only once)."""
        if self._embeddings is not None:
            return

        from langchain_huggingface import HuggingFaceEmbeddings
        import torch
        try:
            torch.set_num_threads(1)
        except Exception:
            pass

        # Prefer local pre-downloaded copy
        model_path = (
            str(self._local_path)
            if self._local_path.exists()
            else self._model_name
        )

        logger.info(f"Loading embedding model from: {model_path}")
        self._embeddings = HuggingFaceEmbeddings(
            model_name=model_path,
            model_kwargs={"device": settings.EMBEDDING_DEVICE},
            encode_kwargs={
                "normalize_embeddings": settings.EMBEDDING_NORMALIZE,
                "batch_size": settings.EMBEDDING_BATCH_SIZE,
            },
        )
        logger.info("Embedding model ready.")

    @property
    def model(self):
        self._load()
        return self._embeddings

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of document strings."""
        self._load()
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string."""
        self._load()
        return self._embeddings.embed_query(text)

    def download_model(self) -> bool:
        """
        Pre-download BGE-M3 to local disk for offline use.
        Call this once from a setup script.
        """
        try:
            from huggingface_hub import snapshot_download
            logger.info(f"Downloading {self._model_name} to {self._local_path} ...")
            snapshot_download(
                repo_id=self._model_name,
                local_dir=str(self._local_path),
                ignore_patterns=["*.msgpack", "*.h5", "flax_model*", "tf_model*"],
            )
            logger.info("Model downloaded successfully.")
            return True
        except Exception as e:
            logger.error(f"Model download failed: {e}")
            return False


# Singleton instance
embedding_service = EmbeddingService()
