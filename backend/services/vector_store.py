"""
FAISS vector store service.
Manages one FAISS index per workspace, persisted to disk.
Provides add, search, and delete-by-doc operations.
"""
import json
import logging
import pickle
from pathlib import Path
from typing import Any, Optional

import numpy as np
from langchain_core.documents import Document as LCDocument

from core.config import settings
from services.embeddings import embedding_service

logger = logging.getLogger(__name__)

# In-memory cache of loaded indexes: workspace_id -> FAISS vectorstore
_index_cache: dict[int, Any] = {}


def _workspace_dir(workspace_id: int) -> Path:
    path = settings.VECTOR_DB_DIR / str(workspace_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _meta_path(workspace_id: int) -> Path:
    return _workspace_dir(workspace_id) / "metadata.json"


def _load_metadata(workspace_id: int) -> dict:
    """Load chunk->doc metadata from JSON sidecar."""
    p = _meta_path(workspace_id)
    if p.exists():
        return json.loads(p.read_text())
    return {}


def _save_metadata(workspace_id: int, meta: dict) -> None:
    _meta_path(workspace_id).write_text(json.dumps(meta, indent=2))


def _get_store(workspace_id: int):
    """Load (or return cached) FAISS store for a workspace."""
    if workspace_id in _index_cache:
        return _index_cache[workspace_id]

    from langchain_community.vectorstores import FAISS

    index_path = _workspace_dir(workspace_id) / "faiss_index"
    if index_path.exists():
        try:
            store = FAISS.load_local(
                str(index_path),
                embedding_service.model,
                allow_dangerous_deserialization=True,
            )
            _index_cache[workspace_id] = store
            logger.info(f"Loaded FAISS index for workspace {workspace_id}")
            return store
        except Exception as e:
            logger.warning(f"Failed to load FAISS index: {e}. Will rebuild.")

    return None


def add_documents(workspace_id: int, documents: list[LCDocument]) -> int:
    """
    Embed and index a list of LangChain Documents into the workspace FAISS store.
    Returns the number of chunks added.
    """
    from langchain_community.vectorstores import FAISS

    if not documents:
        return 0

    index_path = str(_workspace_dir(workspace_id) / "faiss_index")
    existing = _get_store(workspace_id)

    if existing is None:
        store = FAISS.from_documents(documents, embedding_service.model)
    else:
        store = existing
        store.add_documents(documents)

    store.save_local(index_path)
    _index_cache[workspace_id] = store

    # Update metadata sidecar
    meta = _load_metadata(workspace_id)
    for doc in documents:
        doc_id = str(doc.metadata.get("doc_id"))
        meta.setdefault(doc_id, {"filename": doc.metadata.get("filename"), "chunks": 0})
        meta[doc_id]["chunks"] += 1
    _save_metadata(workspace_id, meta)

    logger.info(f"Added {len(documents)} chunks to workspace {workspace_id}")
    return len(documents)


def search(
    workspace_id: int | list[int],
    query: str,
    top_k: int = 5,
) -> list[tuple[LCDocument, float]]:
    """
    Similarity search in the workspace FAISS index(es).
    Returns list of (document, score) tuples, sorted by relevance.
    """
    w_ids = [workspace_id] if isinstance(workspace_id, int) else workspace_id
    
    all_results = []
    for w_id in set(w_ids):
        store = _get_store(w_id)
        if store is not None:
            try:
                results = store.similarity_search_with_score(query, k=top_k)
                all_results.extend(results)
            except Exception as e:
                logger.error(f"FAISS search error for workspace {w_id}: {e}")
                
    all_results.sort(key=lambda x: x[1])
    return all_results[:top_k]


def delete_document(workspace_id: int, doc_id: int) -> bool:
    """
    Remove all chunks belonging to a document.
    FAISS doesn't support in-place deletion; we rebuild the index
    from remaining documents.
    """
    from langchain_community.vectorstores import FAISS

    store = _get_store(workspace_id)
    if store is None:
        return True  # nothing to do

    index_path = str(_workspace_dir(workspace_id) / "faiss_index")

    try:
        # Collect all docs that are NOT from the deleted document
        # Access internal docstore
        docstore = store.docstore._dict
        all_remaining: list[LCDocument] = [
            v for v in docstore.values()
            if v.metadata.get("doc_id") != doc_id
        ]

        # Rebuild
        if all_remaining:
            new_store = FAISS.from_documents(all_remaining, embedding_service.model)
            new_store.save_local(index_path)
            _index_cache[workspace_id] = new_store
        else:
            # Remove index files entirely
            import shutil
            idx_dir = _workspace_dir(workspace_id) / "faiss_index"
            if idx_dir.exists():
                shutil.rmtree(idx_dir)
            _index_cache.pop(workspace_id, None)

        # Update metadata
        meta = _load_metadata(workspace_id)
        meta.pop(str(doc_id), None)
        _save_metadata(workspace_id, meta)

        logger.info(f"Deleted doc {doc_id} from workspace {workspace_id} index")
        return True
    except Exception as e:
        logger.error(f"Error deleting doc from FAISS: {e}")
        return False


def workspace_doc_count(workspace_id: int) -> int:
    """Return number of unique documents indexed for a workspace."""
    return len(_load_metadata(workspace_id))


def invalidate_cache(workspace_id: int) -> None:
    """Evict a workspace from the in-memory cache (forces reload from disk)."""
    _index_cache.pop(workspace_id, None)
