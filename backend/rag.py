"""RAG retrieval over the FAISS vector store built by ingest.py."""
import json
import os

import faiss
import numpy as np

from config import EMBEDDING_MODEL, VECTORSTORE_DIR

_model = None
_index = None
_chunks = None


def _load_model():
    global _model
    if _model is None:
        import torch

        torch.set_num_threads(2)
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    return _model


def load_store():
    """Load FAISS index + chunks.json (cached). Returns (index, chunks)."""
    global _index, _chunks
    if _index is None or _chunks is None:
        index_path = os.path.join(VECTORSTORE_DIR, "index.faiss")
        chunks_path = os.path.join(VECTORSTORE_DIR, "chunks.json")
        if not os.path.exists(index_path) or not os.path.exists(chunks_path):
            raise FileNotFoundError(
                "Vector store not found. Run backend/ingest.py first."
            )
        _index = faiss.read_index(index_path)
        with open(chunks_path, encoding="utf-8") as f:
            _chunks = json.load(f)
    return _index, _chunks


def chunk_count():
    _, chunks = load_store()
    return len(chunks)


def retrieve(query: str, allowed_sources, top_k=3, overfetch=20):
    """Top-k chunks for one query, restricted to allowed_sources (book titles)."""
    index, chunks = load_store()
    model = _load_model()
    emb = model.encode([query], normalize_embeddings=True)
    emb = np.asarray(emb, dtype=np.float32)
    n = min(overfetch, len(chunks))
    scores, idxs = index.search(emb, n)
    results, seen = [], set()
    for score, i in zip(scores[0], idxs[0]):
        if i < 0:
            continue
        chunk = chunks[i]
        if chunk["source"] not in allowed_sources:
            continue
        key = chunk["text"][:200]
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "source": chunk["source"],
                "page": chunk.get("page"),
                "text": chunk["text"],
                "score": float(score),
            }
        )
        if len(results) >= top_k:
            break
    return results


def retrieve_multi(queries, allowed_sources, top_k=3):
    """Retrieve per query and dedupe across queries (by text prefix)."""
    merged, seen = [], set()
    for q in queries:
        for chunk in retrieve(q, allowed_sources, top_k=top_k):
            key = chunk["text"][:200]
            if key in seen:
                continue
            seen.add(key)
            merged.append(chunk)
    return merged
