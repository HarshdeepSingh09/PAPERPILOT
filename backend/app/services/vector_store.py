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

    @staticmethod
    def _build_where_filter(document_id: Optional[str] = None, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if document_id and user_id:
            return {"$and": [{"document_id": document_id}, {"user_id": user_id}]}
        if document_id:
            return {"document_id": document_id}
        if user_id:
            return {"user_id": user_id}
        return None

    def get_document_vector_count(self, document_id: str, user_id: Optional[str] = None) -> int:
        """
        Counts how many vectors are indexed in ChromaDB for a specific document_id
        (and optional user_id for ownership enforcement).
        """
        collection = self.get_or_create_collection()
        try:
            where_filter = self._build_where_filter(document_id=document_id, user_id=user_id)
            results = collection.get(where=where_filter)
            ids = results.get("ids", [])
            return len(ids)
        except Exception as e:
            logger.warning(f"Error checking vector count for document '{document_id}': {e}")
            return 0

    def get_indexing_status(self, document_id: str, db: Optional[Session] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns vector indexing status comparing ChromaDB vector count against SQLite chunk count.
        """
        effective_uid = user_id
        if db is not None:
            q = db.query(Document).filter(Document.id == document_id)
            if user_id is not None:
                q = q.filter(Document.user_id == user_id)
            doc = q.first()
            if not doc:
                raise DocumentNotFoundError(f"Document with ID '{document_id}' not found.")
            effective_uid = doc.user_id
            total_chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).count()
        indexed_count = self.get_document_vector_count(document_id, user_id=effective_uid)
        if db is None:
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
        batch_size: int = MAX_BATCH_SIZE,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ingests existing embeddings from SQLite for the given document into ChromaDB.
        Tags every vector with user_id metadata, avoids regenerating embeddings, and guarantees zero duplicate vectors.
        """
        q = db.query(Document).filter(Document.id == document_id)
        if user_id is not None:
            q = q.filter(Document.user_id == user_id)
        doc = q.first()
        if not doc:
            raise DocumentNotFoundError(f"Document with ID '{document_id}' not found.")

        owner_uid = doc.user_id

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

        existing_count = self.get_document_vector_count(document_id, user_id=owner_uid)
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
        if self.get_document_vector_count(document_id) > 0:
            self.delete_document_vectors(document_id)

        collection = self.get_or_create_collection()

        # Ingest in batches to avoid SQLite/memory limits
        for i in range(0, total_chunks, batch_size):
            batch = chunks[i : i + batch_size]
            ids = [c.id for c in batch]
            embeddings = [c.embedding for c in batch]
            documents = [c.content for c in batch]
            metadatas = []
            for c in batch:
                meta = {
                    "document_id": c.document_id,
                    "user_id": str(owner_uid),
                    "chunk_id": c.id,
                    "chunk_index": c.chunk_index,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "pages": c.pages_json,
                }
                if getattr(c, "section_title", None):
                    meta["section_title"] = str(c.section_title)[:200]
                if getattr(c, "paragraph_range", None):
                    meta["paragraph_range"] = str(c.paragraph_range)
                metadatas.append(meta)

            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )

        new_count = self.get_document_vector_count(document_id, user_id=owner_uid)
        logger.info(f"Indexed {new_count} chunks for document '{document_id}' (user '{owner_uid}') into ChromaDB.")

        return {
            "document_id": document_id,
            "collection_name": self.collection_name,
            "indexed_vectors": new_count,
            "total_chunks": total_chunks,
            "status": "completed",
            "message": f"Successfully indexed {new_count} vectors into ChromaDB collection '{self.collection_name}'.",
        }

    def delete_document_vectors(self, document_id: str, user_id: Optional[str] = None) -> int:
        """
        Deletes all vector embeddings associated with a document_id (and optional user_id) from ChromaDB.
        """
        collection = self.get_or_create_collection()
        try:
            where_filter = self._build_where_filter(document_id=document_id, user_id=user_id)
            res = collection.get(where=where_filter)
            ids = res.get("ids", [])
            count = len(ids)
            if count > 0:
                collection.delete(where=where_filter)
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
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Performs ownership-verified semantic similarity search on a document's chunks in ChromaDB.
        Enforces SQLite ownership and ChromaDB user_id metadata filtering so another user's chunks can never be retrieved.
        """
        clean_query = (query or "").strip()
        if not clean_query:
            raise ValueError("Search query cannot be empty.")

        effective_uid = user_id
        # Verify document exists (and belongs to user_id when provided) in SQLite
        if db is not None:
            q = db.query(Document).filter(Document.id == document_id)
            if user_id is not None:
                q = q.filter(Document.user_id == user_id)
            doc = q.first()
            if not doc:
                raise DocumentNotFoundError(f"Document with ID '{document_id}' not found.")
            effective_uid = doc.user_id

        # Verify document has vectors indexed under this user's isolation scope
        indexed_count = self.get_document_vector_count(document_id, user_id=effective_uid)
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
        where_filter = self._build_where_filter(document_id=document_id, user_id=effective_uid)

        raw_results = collection.query(
            query_embeddings=[query_vector],
            where=where_filter,
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

            # Defense-in-depth post-filter check against metadata leakage
            if effective_uid is not None and meta.get("user_id") != str(effective_uid):
                continue

            pages = parse_pages_metadata(meta.get("pages", ""))

            dist_val = float(dist)
            similarity = round(max(0.0, min(1.0, 1.0 - dist_val)), 6)

            results.append({
                "chunk_id": str(meta.get("chunk_id", id_)),
                "chunk_index": int(meta.get("chunk_index", 0)),
                "content": content,
                "page_start": int(meta.get("page_start", 1)),
                "page_end": int(meta.get("page_end", 1)),
                "pages": pages,
                "section_title": meta.get("section_title"),
                "paragraph_range": meta.get("paragraph_range"),
                "distance": round(dist_val, 6),
                "similarity_score": similarity,
            })

        # Sort by similarity score descending (closest first)
        results.sort(key=lambda r: r["similarity_score"], reverse=True)
        return results

    def search_user_documents(
        self,
        user_id: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        document_id: Optional[str] = None,
        query_embedding: Optional[List[float]] = None,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """
        Workspace-wide or document-scoped semantic search strictly restricted to a single user_id.
        """
        if not user_id:
            raise ValueError("user_id is required for isolated workspace vector search.")
        if document_id:
            return self.search_document(
                document_id=document_id,
                query=query,
                top_k=top_k,
                query_embedding=query_embedding,
                db=db,
                user_id=user_id,
            )

        clean_query = (query or "").strip()
        if not clean_query:
            raise ValueError("Search query cannot be empty.")

        collection = self.get_or_create_collection()
        user_vecs = collection.get(where={"user_id": user_id})
        total_user_vecs = len(user_vecs.get("ids") or [])
        if total_user_vecs == 0:
            return []

        if query_embedding is not None:
            query_vector = query_embedding
        else:
            vectors = embedding_service.generate_embeddings_for_batch([clean_query])
            if not vectors or not vectors[0]:
                raise VectorStoreError("Failed to generate query embedding vector.")
            query_vector = vectors[0]

        n_results = max(1, min(top_k, total_user_vecs, 50))
        raw_results = collection.query(
            query_embeddings=[query_vector],
            where={"user_id": user_id},
            n_results=n_results,
        )

        ids = raw_results.get("ids", [[]])[0]
        docs = raw_results.get("documents", [[]])[0]
        metas = raw_results.get("metadatas", [[]])[0]
        dists = raw_results.get("distances", [[]])[0]

        results: List[Dict[str, Any]] = []
        for i in range(len(ids)):
            meta = metas[i] if i < len(metas) else {}
            if meta.get("user_id") != str(user_id):
                continue
            dist_val = float(dists[i] if i < len(dists) else 0.0)
            results.append({
                "document_id": str(meta.get("document_id", "")),
                "chunk_id": str(meta.get("chunk_id", ids[i])),
                "chunk_index": int(meta.get("chunk_index", 0)),
                "content": docs[i] if i < len(docs) else "",
                "page_start": int(meta.get("page_start", 1)),
                "page_end": int(meta.get("page_end", 1)),
                "pages": parse_pages_metadata(meta.get("pages", "")),
                "section_title": meta.get("section_title"),
                "paragraph_range": meta.get("paragraph_range"),
                "distance": round(dist_val, 6),
                "similarity_score": round(max(0.0, min(1.0, 1.0 - dist_val)), 6),
            })

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
