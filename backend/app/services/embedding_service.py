import os
import json
import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Document, DocumentChunk

logger = logging.getLogger(__name__)


class EmbeddingServiceError(Exception):
    """Base exception for embedding service failures."""
    pass


class MissingAPIKeyError(EmbeddingServiceError):
    """Raised when the Gemini API key is missing or is the default placeholder."""
    pass


class InvalidAPIKeyError(EmbeddingServiceError):
    """Raised when the Gemini API key is rejected as unauthorized or invalid."""
    pass


class RateLimitExceededError(EmbeddingServiceError):
    """Raised when API rate limits / quotas are exceeded and retries are exhausted."""
    pass


class EmbeddingAPIError(EmbeddingServiceError):
    """Raised when an unrecoverable Gemini API error occurs."""
    pass


@dataclass
class EmbeddedChunk:
    """Represents a chunk with its semantic embedding vector and preserved metadata."""
    chunk_id: str
    document_id: str
    chunk_index: int
    page_start: int
    page_end: int
    pages: List[int]
    content: str
    embedding: List[float]
    dimension: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "pages": self.pages,
            "content": self.content,
            "dimension": self.dimension,
            "embedding": self.embedding,
        }


@dataclass
class EmbeddingBatchResult:
    """Result of embedding generation for an entire document."""
    document_id: str
    total_chunks: int
    embedded_chunks: int
    dimension: int
    status: str  # "completed", "failed", "pending"
    model: str
    error_message: Optional[str] = None
    chunks: List[EmbeddedChunk] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "total_chunks": self.total_chunks,
            "embedded_chunks": self.embedded_chunks,
            "dimension": self.dimension,
            "status": self.status,
            "model": self.model,
            "error_message": self.error_message,
            "chunks_count": len(self.chunks),
        }


class GeminiEmbeddingService:
    """
    Dedicated service for generating text embeddings using Google's Gemini API.
    Reads chunks directly from SQLite, processes in batches, preserves chunk metadata,
    and applies exponential backoff for transient failures.
    """

    DEFAULT_MODEL = "gemini-embedding-001"
    DEFAULT_BATCH_SIZE = 50
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_BACKOFF = 1.0
    DEFAULT_OUTPUT_DIM = 768

    def __init__(
        self,
        model_name: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
        output_dim: Optional[int] = DEFAULT_OUTPUT_DIM,
    ):
        raw_model = model_name or settings.GEMINI_EMBEDDING_MODEL or self.DEFAULT_MODEL
        # Normalize model string (strip leading "models/" if present)
        self.model_name = raw_model.replace("models/", "")
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.output_dim = output_dim

    def get_validated_api_key(self) -> str:
        """
        Validates that a non-empty, non-placeholder Gemini API key is configured.
        """
        key = (settings.GEMINI_API_KEY or "").strip()
        if not key or key == "your_gemini_api_key_here":
            raise MissingAPIKeyError(
                "Gemini API key is not configured. Please set GEMINI_API_KEY in backend/.env "
                "with a valid key from Google AI Studio."
            )
        return key

    def _get_client(self, api_key: str):
        """
        Initializes the official google.genai Client.
        """
        from google import genai
        return genai.Client(api_key=api_key)

    def generate_embeddings_for_batch(self, texts: List[str], api_key: Optional[str] = None) -> List[List[float]]:
        """
        Generates embedding vectors for a batch of strings with retry logic.
        """
        if not texts:
            return []

        active_key = api_key or self.get_validated_api_key()
        client = self._get_client(active_key)

        backoff = self.initial_backoff
        last_exception = None

        config = None
        if self.output_dim:
            from google.genai import types
            config = types.EmbedContentConfig(output_dimensionality=self.output_dim)

        for attempt in range(1, self.max_retries + 1):
            try:
                if config:
                    response = client.models.embed_content(
                        model=self.model_name,
                        contents=texts,
                        config=config,
                    )
                else:
                    response = client.models.embed_content(
                        model=self.model_name,
                        contents=texts,
                    )

                if not response.embeddings:
                    raise EmbeddingAPIError("Gemini API returned an empty embeddings list.")

                vectors: List[List[float]] = []
                for emb in response.embeddings:
                    vectors.append(list(emb.values))

                return vectors

            except Exception as e:
                err_str = str(e).lower()
                last_exception = e

                # Check for invalid / unauthorized API key
                if "api_key_invalid" in err_str or "unauthorized" in err_str or "401" in err_str or "api key not valid" in err_str:
                    raise InvalidAPIKeyError(
                        f"The configured Gemini API key is invalid or unauthorized: {str(e)}"
                    ) from e

                # Check for rate limiting / quota exhaustion
                is_rate_limit = (
                    "429" in err_str or
                    "resource_exhausted" in err_str or
                    "quota" in err_str or
                    "rate limit" in err_str
                )

                # Check for transient server errors
                is_transient = "503" in err_str or "unavailable" in err_str or "timeout" in err_str

                if (is_rate_limit or is_transient) and attempt < self.max_retries:
                    logger.warning(
                        f"Gemini API attempt {attempt}/{self.max_retries} failed with {type(e).__name__}: {e}. "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue

                if is_rate_limit:
                    raise RateLimitExceededError(
                        f"Gemini API rate limit or quota exceeded after {attempt} attempts: {str(e)}"
                    ) from e

                # Other unrecoverable errors
                raise EmbeddingAPIError(f"Gemini embedding API call failed: {str(e)}") from e

        raise EmbeddingAPIError(f"Embedding generation failed after {self.max_retries} attempts: {last_exception}")

    def embed_document_chunks(
        self,
        document_id: str,
        db: Session,
        force: bool = False,
        api_key: Optional[str] = None
    ) -> EmbeddingBatchResult:
        """
        Reads chunks from SQLite for the given document, generates semantic embeddings,
        persists vector data into SQLite, and tracks embedding status.

        Avoids re-generating embeddings if they already exist unless force=True.
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document with ID '{document_id}' not found.")

        # Read chunks from SQLite
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )

        if not chunks:
            doc.embedding_status = "completed"
            doc.embedding_model = self.model_name
            db.commit()
            return EmbeddingBatchResult(
                document_id=document_id,
                total_chunks=0,
                embedded_chunks=0,
                dimension=0,
                status="completed",
                model=self.model_name,
            )

        # Check if already completed and all chunks have valid embeddings
        if not force and doc.embedding_status == "completed":
            all_embedded = all(c.embedding_json is not None for c in chunks)
            if all_embedded:
                logger.info(f"Document '{document_id}' already has completed embeddings. Skipping regeneration.")
                embedded_list = [
                    EmbeddedChunk(
                        chunk_id=c.id,
                        document_id=c.document_id,
                        chunk_index=c.chunk_index,
                        page_start=c.page_start,
                        page_end=c.page_end,
                        pages=c.pages,
                        content=c.content,
                        embedding=c.embedding or [],
                        dimension=c.embedding_dimension or 0,
                    )
                    for c in chunks
                ]
                sample_dim = chunks[0].embedding_dimension or 0
                return EmbeddingBatchResult(
                    document_id=document_id,
                    total_chunks=len(chunks),
                    embedded_chunks=len(chunks),
                    dimension=sample_dim,
                    status="completed",
                    model=doc.embedding_model or self.model_name,
                    chunks=embedded_list,
                )

        # Mark document status as processing
        doc.embedding_status = "processing"
        doc.embedding_model = self.model_name
        db.commit()

        try:
            # Filter eligible chunks (non-empty)
            eligible_chunks: List[DocumentChunk] = []
            texts_to_embed: List[str] = []

            for chunk in chunks:
                cleaned_text = (chunk.content or "").strip()
                if cleaned_text:
                    eligible_chunks.append(chunk)
                    texts_to_embed.append(cleaned_text)
                else:
                    # Empty chunk handling
                    chunk.embedding_json = None
                    chunk.embedding_dimension = 0

            # Batch generation
            all_vectors: List[List[float]] = []
            for i in range(0, len(texts_to_embed), self.batch_size):
                batch = texts_to_embed[i : i + self.batch_size]
                vectors = self.generate_embeddings_for_batch(batch, api_key=api_key)
                all_vectors.extend(vectors)

            # Assign embeddings and verify dimensions
            embedded_chunks: List[EmbeddedChunk] = []
            detected_dim = len(all_vectors[0]) if all_vectors else 0

            for chunk, vector in zip(eligible_chunks, all_vectors):
                chunk.embedding_json = json.dumps(vector)
                chunk.embedding_dimension = len(vector)

                embedded_chunks.append(
                    EmbeddedChunk(
                        chunk_id=chunk.id,
                        document_id=chunk.document_id,
                        chunk_index=chunk.chunk_index,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        pages=chunk.pages,
                        content=chunk.content,
                        embedding=vector,
                        dimension=len(vector),
                    )
                )

            # Persist and finalize document status
            doc.embedding_status = "completed"
            doc.embedding_model = self.model_name
            db.commit()
            db.refresh(doc)

            return EmbeddingBatchResult(
                document_id=document_id,
                total_chunks=len(chunks),
                embedded_chunks=len(embedded_chunks),
                dimension=detected_dim,
                status="completed",
                model=self.model_name,
                chunks=embedded_chunks,
            )

        except Exception as e:
            db.rollback()
            doc.embedding_status = "failed"
            doc.error_message = f"Embedding generation failed: {str(e)}"
            db.commit()
            logger.error(f"Failed to generate embeddings for document '{document_id}': {e}")
            raise


# Default singleton instance
embedding_service = GeminiEmbeddingService()
