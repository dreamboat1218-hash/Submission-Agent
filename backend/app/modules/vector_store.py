"""可选 ChromaDB 向量索引。

默认使用 SQLite 关键词检索；启用 ``USE_VECTOR_SEARCH=true`` 后，
文档会同步写入 ChromaDB，并采用确定性的中文二元组哈希嵌入，保证本地零模型依赖。
"""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Any

from ..config import get_settings

logger = logging.getLogger(__name__)

_VECTOR_DIM = 256


class HashEmbeddingFunction:
    def __init__(self, dim: int = _VECTOR_DIM) -> None:
        self.dim = dim

    def __call__(self, input: list[str]) -> list[list[float]]:
        vectors = []
        for text in input:
            vector = [0.0] * self.dim
            chars = text.replace(" ", "").replace("\n", "")
            tokens = list(chars)
            tokens += [chars[i : i + 2] for i in range(len(chars) - 1)]
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dim
                vector[index] += 1.0
            norm = math.sqrt(sum(v * v for v in vector))
            if norm > 0:
                vector = [v / norm for v in vector]
            vectors.append(vector)
        return vectors


class VectorIndex:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any | None = None
        self._collection: Any | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.use_vector_search)

    def _connect(self):
        if not self.enabled:
            return None
        if self._collection is None:
            try:
                import chromadb
            except ImportError as exc:
                logger.warning("未安装 chromadb，向量检索不可用：%s", exc)
                return None
            self._client = chromadb.PersistentClient(path=str(self.settings.chroma_persist_dir))
            self._collection = self._client.get_or_create_collection(
                name="bid_knowledge",
                embedding_function=HashEmbeddingFunction(),
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def upsert(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        collection = self._connect()
        if collection is None:
            return
        try:
            collection.upsert(ids=[doc_id], documents=[text], metadatas=[metadata or {"doc_type": ""}])
        except Exception as exc:
            logger.warning("向量索引写入失败：%s", exc)

    def query(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        collection = self._connect()
        if collection is None:
            return []
        try:
            result = collection.query(query_texts=[text], n_results=top_k)
            ids = (result.get("ids") or [[]])[0]
            distances = (result.get("distances") or [[]])[0]
            return [(str(doc_id), 1.0 - float(distance)) for doc_id, distance in zip(ids, distances)]
        except Exception as exc:
            logger.warning("向量检索失败：%s", exc)
            return []

    def delete(self, doc_id: str) -> None:
        collection = self._connect()
        if collection is None:
            return
        try:
            collection.delete(ids=[doc_id])
        except Exception:
            pass
