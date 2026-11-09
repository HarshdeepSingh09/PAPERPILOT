import os
import json
import logging
from typing import List, Dict, Any, Optional
import chromadb
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Document, DocumentChunk
from app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    """Base exception for ChromaDB vector store operations."""
    pass


class DocumentNotFoundError(VectorStoreError):
    """Raised when a document cannot be found in the database."""
    pass


class DocumentNotIndexedError(VectorStoreError):
    """Raised when similarity search is attempted on an unindexed document."""
    pass


class UnembeddedChunksError(VectorStoreError):
    """Raised when attempting to index chunks that do not yet have embeddings."""
    pass


def parse_pages_metadata(val: Any) -> List[int]:
    """
    Safely parses page numbers from various metadata formats (JSON string, comma-separated, list, int).
    """
    if isinstance(val, list):
        return [int(x) for x in val]
    if isinstance(val, int):
        return [val]
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return []
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [int(x) for x in parsed]
        except Exception:
            pass
        parts = [p.strip() for p in val.replace("[", "").replace("]", "").split(",") if p.strip()]
        return [int(p) for p in parts if p.isdigit()]
    return []


class VectorStoreService:
    """
    Dedicated vector store service powered by ChromaDB.
    Persists document chunk vectors with metadata, supports document filtering,
    re-indexing with zero duplication, and semantic similarity search.
    """

    DEFAULT_COLLECTION_NAME = "paperpilot_documents"
    DEFAULT_TOP_K = 4
    MAX_BATCH_SIZE = 100

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        client: Optional[Any] = None,
    ):
        self.persist_directory = persist_directory or settings.CHROMA_PERSIST_DIR
        self.collection_name = collection_name
        self._client = client
        self._collection = None

    def get_client(self) -> chromadb.ClientAPI:
        """
        Lazily initializes and returns the ChromaDB client.
        """
        if self._client is None:
            os.makedirs(self.persist_directory, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self.persist_directory)
        return self._client

    def get_or_create_collection(self, name: Optional[str] = None):
        """
        Retrieves or initializes the designated ChromaDB collection with cosine distance metric.
        """
        coll_name = name or self.collection_name
        client = self.get_client()
        return client.get_or_create_collection(
            name=coll_name,
            metadata={"hnsw:space": "cosine"}
        )

    def get_document_vector_count(self, document_id: str) -> int:
        """
        Counts how many vectors are indexed in ChromaDB for a specific document_id.
        """
        collection = self.get_or_create_collection()
        try:
            results = collection.get(where={"document_id": document_id})
            ids = results.get("ids", [])
            return len(ids)
        except Exception as e:
            logger.warning(f"Error checking vector count for document '{document_id}': {e}")
            return 0

    def get_indexing_status(self, document_id: str, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Returns vector indexing status comparing ChromaDB vector count against SQLite chunk count.
        """
        indexed_count = self.get_document_vector_count(document_id)
        total_chunks = 0

        if db is not None:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if not doc:
                raise DocumentNotFoundError(f"Document with ID '{document_id}' not found.")
            total_chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).count()
        else:
            total_chunks = indexed_count

        is_indexed = total_chunks > 0 and indexed_count >= total_chunks
        if is_indexed:
            status_str = "indexed"
        elif indexed_count > 0:
            status_str = "partial"
        else:
            status_str = "not_indexed"

        return {
            "document_id": document_id,
            "collection_name": self.collection_name,
            "indexed_vectors": indexed_count,
            "total_chunks": total_chunks,
            "is_indexed": is_indexed,
            "status": status_str,
        }

    def index_document_chunks(
        self,
        document_id: str,
        db: Session,
        force: bool = False,
        batch_size: int = MAX_BATCH_SIZE
    ) -> Dict[str, Any]:
        """
        Ingests existing embeddings from SQLite for the given document into ChromaDB.
        Avoids regenerating embeddings and guarantees zero duplicate vectors.
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError(f"Document with ID '{document_id}' not found.")

        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )

        if not chunks:
            raise VectorStoreError(f"Document '{document_id}' has no chunks to index.")

        # Check for un-embedded chunks
        unembedded = [c for c in chunks if not c.embedding_json]
        if unembedded:
            raise UnembeddedChunksError(
                f"Document '{document_id}' has {len(unembedded)} chunk(s) without embeddings. "
                "Please generate embeddings via /embed first."
            )

        existing_count = self.get_document_vector_count(document_id)
        total_chunks = len(chunks)

        # If already indexed and not force, return early
        if existing_count >= total_chunks and not force:
            return {
                "document_id": document_id,
                "collection_name": self.collection_name,
                "indexed_vectors": existing_count,
                "total_chunks": total_chunks,
                "status": "already_indexed",
                "message": (
                    f"Document '{document_id}' is already fully indexed with {existing_count} vectors. "
                    "Use force=True to re-index."
                ),
            }

        # Clean existing vectors for this document to prevent duplicate or orphaned vectors
        if existing_count > 0:
            self.delete_document_vectors(document_id)

        collection = self.get_or_create_collection()

        # Ingest in batches to avoid SQLite/memory limits
        for i in range(0, total_chunks, batch_size):
            batch = chunks[i : i + batch_size]
            ids = [c.id for c in batch]
            embeddings = [c.embedding for c in batch]
            documents = [c.content for c in batch]
            metadatas = [
                {
                    "document_id": c.document_id,
                    "chunk_id": c.id,
                    "chunk_index": c.chunk_index,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "pages": c.pages_json,
                }
                for c in batch
            ]

            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )

        new_count = self.get_document_vector_count(document_id)
        logger.info(f"Indexed {new_count} chunks for document '{document_id}' into ChromaDB.")

        return {
            "document_id": document_id,
            "collection_name": self.collection_name,
            "indexed_vectors": new_count,
            "total_chunks": total_chunks,
            "status": "completed",
            "message": f"Successfully indexed {new_count} vectors into ChromaDB collection '{self.collection_name}'.",
        }

    def delete_document_vectors(self, document_id: str) -> int:
        """
        Deletes all vector embeddings associated with a document_id from ChromaDB.
        """
        collection = self.get_or_create_collection()
        try:
            res = collection.get(where={"document_id": document_id})
            ids = res.get("ids", [])
            count = len(ids)
            if count > 0:
                collection.delete(where={"document_id": document_id})
                logger.info(f"Deleted {count} ChromaDB vectors for document '{document_id}'.")
            return count
        except Exception as e:
            logger.error(f"Error deleting vectors for document '{document_id}': {e}")
            raise VectorStoreError(f"Failed to delete vectors for document '{document_id}': {str(e)}") from e

    def search_document(
        self,
        document_id: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        query_embedding: Optional[List[float]] = None,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """
        Performs semantic similarity search on a document's chunks in ChromaDB.
        Returns top matching chunks with similarity score, distance, and page citations.
        """
        clean_query = (query or "").strip()
        if not clean_query:
            raise ValueError("Search query cannot be empty.")

        # Verify document exists in SQLite if db is provided
        if db is not None:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if not doc:
                raise DocumentNotFoundError(f"Document with ID '{document_id}' not found.")

        # Verify document has vectors indexed
        indexed_count = self.get_document_vector_count(document_id)
        if indexed_count == 0:
            raise DocumentNotIndexedError(
                f"Document '{document_id}' has not been indexed in ChromaDB yet. "
                "Please call POST /api/v1/documents/{id}/index before searching."
            )

        # Generate query embedding if not provided directly
        if query_embedding is not None:
            query_vector = query_embedding
        else:
            vectors = embedding_service.generate_embeddings_for_batch([clean_query])
            if not vectors or not vectors[0]:
                raise VectorStoreError("Failed to generate query embedding vector.")
            query_vector = vectors[0]

        collection = self.get_or_create_collection()
        n_results = max(1, min(top_k, indexed_count, 50))

        raw_results = collection.query(
            query_embeddings=[query_vector],
            where={"document_id": document_id},
            n_results=n_results,
        )

        ids = raw_results.get("ids", [[]])[0]
        docs = raw_results.get("documents", [[]])[0]
        metas = raw_results.get("metadatas", [[]])[0]
        dists = raw_results.get("distances", [[]])[0]

        results: List[Dict[str, Any]] = []
        for i in range(len(ids)):
            id_ = ids[i]
            content = docs[i] if i < len(docs) else ""
            meta = metas[i] if i < len(metas) else {}
            dist = dists[i] if i < len(dists) else 0.0

            pages = parse_pages_metadata(meta.get("pages", ""))

            # Cosine distance to similarity score: similarity = 1 - distance
            # Clamped between 0.0 and 1.0
            dist_val = float(dist)
            similarity = round(max(0.0, min(1.0, 1.0 - dist_val)), 6)

            results.append({
                "chunk_id": str(meta.get("chunk_id", id_)),
                "chunk_index": int(meta.get("chunk_index", 0)),
                "content": content,
                "page_start": int(meta.get("page_start", 1)),
                "page_end": int(meta.get("page_end", 1)),
                "pages": pages,
                "distance": round(dist_val, 6),
                "similarity_score": similarity,
            })

        # Sort by similarity score descending (closest first)
        results.sort(key=lambda r: r["similarity_score"], reverse=True)
        return results

    def reset_collection(self) -> None:
        """
        Deletes and recreates the collection. Useful for tests or cleanups.
        """
        client = self.get_client()
        try:
            client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = None


vector_store_service = VectorStoreService()
