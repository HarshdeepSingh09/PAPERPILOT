import os
import sys
import json
import unittest
from unittest.mock import MagicMock, patch
import tempfile

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings
from app.db.session import SessionLocal, init_db
from app.db.models import Document, DocumentChunk, LEGACY_OWNER_USER_ID
from app.services.embedding_service import (
    GeminiEmbeddingService,
    MissingAPIKeyError,
    InvalidAPIKeyError,
    RateLimitExceededError,
    EmbeddingAPIError,
    EmbeddedChunk,
    EmbeddingBatchResult
)


class TestGeminiEmbeddingIntegration(unittest.TestCase):
    """
    Automated test suite for PaperPilot Phase 2.2A:
    - Gemini embeddings integration (text-embedding-004)
    - Reading chunks from SQLite
    - 768-dimensional vector generation
    - Metadata preservation (document_id, chunk_id, chunk_index, page_start, page_end, pages)
    - API failure, rate limit retry, and missing/invalid API key handling
    - Empty chunk handling
    - Idempotency & avoiding unnecessary regeneration
    """

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.db = SessionLocal()
        # Initialize service with small batch size and instant backoff for fast tests
        self.service = GeminiEmbeddingService(
            model_name="gemini-embedding-001",
            batch_size=10,
            max_retries=3,
            initial_backoff=0.01
        )

    def tearDown(self):
        self.db.close()

    # 1. Missing API Key Validation
    def test_missing_api_key_handling(self):
        with patch.object(settings, "GEMINI_API_KEY", ""):
            with self.assertRaises(MissingAPIKeyError) as ctx:
                self.service.get_validated_api_key()
            self.assertIn("not configured", str(ctx.exception))

        with patch.object(settings, "GEMINI_API_KEY", "your_gemini_api_key_here"):
            with self.assertRaises(MissingAPIKeyError) as ctx:
                self.service.get_validated_api_key()
            self.assertIn("not configured", str(ctx.exception))

    # 2. Invalid API Key / Authentication Failure Handling
    def test_invalid_api_key_handling(self):
        with patch.object(self.service, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.models.embed_content.side_effect = Exception("401 Unauthorized: API_KEY_INVALID")
            mock_get_client.return_value = mock_client

            with self.assertRaises(InvalidAPIKeyError) as ctx:
                self.service.generate_embeddings_for_batch(["Test text"], api_key="INVALID_KEY_XYZ")
            self.assertIn("invalid or unauthorized", str(ctx.exception).lower())

    # 3. Rate Limit / Transient Retry with Exponential Backoff
    def test_rate_limit_and_retry_backoff(self):
        with patch.object(self.service, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            # Fail twice with 429 Resource Exhausted, then succeed on 3rd attempt
            mock_embedding = MagicMock()
            mock_embedding.values = [0.1] * 768
            mock_resp = MagicMock()
            mock_resp.embeddings = [mock_embedding]

            mock_client.models.embed_content.side_effect = [
                Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded"),
                Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded"),
                mock_resp
            ]
            mock_get_client.return_value = mock_client

            vectors = self.service.generate_embeddings_for_batch(["Retry test"], api_key="VALID_TEST_KEY")
            self.assertEqual(len(vectors), 1)
            self.assertEqual(len(vectors[0]), 768)
            self.assertEqual(mock_client.models.embed_content.call_count, 3)

    # 4. Rate Limit Exhaustion
    def test_rate_limit_exhaustion_raises(self):
        with patch.object(self.service, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.models.embed_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")
            mock_get_client.return_value = mock_client

            with self.assertRaises(RateLimitExceededError):
                self.service.generate_embeddings_for_batch(["Quota test"], api_key="VALID_TEST_KEY")

    # 5. Empty Chunk Handling
    def test_empty_chunk_handling(self):
        # Create a document with 1 normal chunk and 1 empty chunk
        doc = Document(
            id="doc-empty-chunk-test",
            user_id=LEGACY_OWNER_USER_ID,
            filename="empty_chunk_test.pdf",
            original_filename="Empty Chunk Test.pdf",
            file_path="dummy.pdf",
            total_pages=1,
            total_chunks=2,
            status="ready",
            embedding_status="pending"
        )
        self.db.add(doc)
        c1 = DocumentChunk(
            id="chunk-non-empty",
            document_id=doc.id,
            chunk_index=0,
            content="Valid chunk text for embedding.",
            char_count=31,
            page_start=1,
            page_end=1,
            pages_json="[1]"
        )
        c2 = DocumentChunk(
            id="chunk-empty",
            document_id=doc.id,
            chunk_index=1,
            content="   ",  # Whitespace only
            char_count=3,
            page_start=1,
            page_end=1,
            pages_json="[1]"
        )
        self.db.add_all([c1, c2])
        self.db.commit()

        with patch.object(self.service, "generate_embeddings_for_batch") as mock_batch:
            mock_batch.return_value = [[0.05] * 768]

            result = self.service.embed_document_chunks(doc.id, self.db, api_key="DUMMY_KEY")

            # Only 1 text should be sent to the API
            self.assertEqual(mock_batch.call_count, 1)
            sent_texts = mock_batch.call_args[0][0]
            self.assertEqual(len(sent_texts), 1)
            self.assertEqual(sent_texts[0], "Valid chunk text for embedding.")

            # Chunk 1 has embedding, chunk 2 does not
            self.db.refresh(c1)
            self.db.refresh(c2)
            self.assertIsNotNone(c1.embedding_json)
            self.assertEqual(c1.embedding_dimension, 768)
            self.assertIsNone(c2.embedding_json)

        # Cleanup
        self.db.delete(doc)
        self.db.commit()

    # 6. Real Extracted Document Embedding Generation & 768 Dimensions
    def test_embedding_generation_on_document_chunks(self):
        # Create a test document with 5 chunks across 3 pages
        doc = Document(
            id="doc-embedding-test",
            user_id=LEGACY_OWNER_USER_ID,
            filename="test_embed.pdf",
            original_filename="Test Embed Document.pdf",
            file_path="dummy_path.pdf",
            total_pages=3,
            total_chunks=5,
            status="ready",
            embedding_status="pending"
        )
        self.db.add(doc)

        created_chunks = []
        for i in range(5):
            page_start = 1 if i < 2 else (2 if i < 4 else 3)
            page_end = page_start if i % 2 == 0 else min(page_start + 1, 3)
            pages = sorted(list(set([page_start, page_end])))
            c = DocumentChunk(
                id=f"chunk-embed-{i}",
                document_id=doc.id,
                chunk_index=i,
                content=f"This is chunk index {i} discussing chemical reaction principles on pages {pages}.",
                char_count=80,
                page_start=page_start,
                page_end=page_end,
                pages_json=json.dumps(pages)
            )
            created_chunks.append(c)
        self.db.add_all(created_chunks)
        self.db.commit()

        # Mock embedding generator returning standard text-embedding-004 vectors (768 float dimensions)
        sample_vector = [0.0123 * (i % 10) for i in range(768)]
        with patch.object(self.service, "generate_embeddings_for_batch") as mock_batch:
            mock_batch.return_value = [sample_vector] * 5

            result = self.service.embed_document_chunks(doc.id, self.db, api_key="VALID_KEY")

            # Verify batch result
            self.assertEqual(result.document_id, doc.id)
            self.assertEqual(result.total_chunks, 5)
            self.assertEqual(result.embedded_chunks, 5)
            self.assertEqual(result.dimension, 768)
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.model, "gemini-embedding-001")

            # Verify metadata preservation for all chunks
            for idx, ec in enumerate(result.chunks):
                self.assertEqual(ec.chunk_index, idx)
                self.assertEqual(ec.dimension, 768)
                self.assertEqual(len(ec.embedding), 768)
                self.assertEqual(ec.document_id, doc.id)
                self.assertGreater(len(ec.pages), 0)
                self.assertEqual(ec.page_start, min(ec.pages))
                self.assertEqual(ec.page_end, max(ec.pages))

            # Verify SQLite persistence
            self.db.refresh(doc)
            self.assertEqual(doc.embedding_status, "completed")
            self.assertEqual(doc.embedding_model, "gemini-embedding-001")

            db_chunks = self.db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).all()
            for c in db_chunks:
                self.assertIsNotNone(c.embedding_json)
                self.assertEqual(c.embedding_dimension, 768)
                self.assertEqual(len(c.embedding), 768)

        # Cleanup
        self.db.delete(doc)
        self.db.commit()

    # 7. Avoid Unnecessary Regeneration When Completed
    def test_avoid_unnecessary_regeneration(self):
        doc = Document(
            id="doc-cached-test",
            user_id=LEGACY_OWNER_USER_ID,
            filename="cached.pdf",
            original_filename="Cached.pdf",
            file_path="dummy.pdf",
            total_pages=1,
            total_chunks=1,
            status="ready",
            embedding_status="completed",
            embedding_model="gemini-embedding-001"
        )
        self.db.add(doc)
        c = DocumentChunk(
            id="chunk-cached-1",
            document_id=doc.id,
            chunk_index=0,
            content="Already embedded content.",
            char_count=25,
            page_start=1,
            page_end=1,
            pages_json="[1]",
            embedding_json=json.dumps([0.5] * 768),
            embedding_dimension=768
        )
        self.db.add(c)
        self.db.commit()

        # Calling without force must NOT call the API
        with patch.object(self.service, "generate_embeddings_for_batch") as mock_batch:
            res = self.service.embed_document_chunks(doc.id, self.db, force=False)
            self.assertEqual(mock_batch.call_count, 0)
            self.assertEqual(res.status, "completed")
            self.assertEqual(res.dimension, 768)

        # Calling with force=True MUST call the API
        with patch.object(self.service, "generate_embeddings_for_batch") as mock_batch:
            mock_batch.return_value = [[0.9] * 768]
            res_forced = self.service.embed_document_chunks(doc.id, self.db, force=True, api_key="KEY")
            self.assertEqual(mock_batch.call_count, 1)
            self.assertEqual(res_forced.status, "completed")

        # Cleanup
        self.db.delete(doc)
        self.db.commit()


if __name__ == "__main__":
    unittest.main()
