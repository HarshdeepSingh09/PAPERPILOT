import os
import sys
import json
import uuid
import shutil
import tempfile
import unittest
from unittest.mock import patch
import chromadb

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi import HTTPException
from app.db.session import SessionLocal, init_db
from app.db.models import Document, DocumentChunk, User, LEGACY_OWNER_USER_ID
from app.schemas.document import SearchRequest
from app.api.v1.documents import (
    index_document_vectors,
    get_document_index_status,
    search_document_chunks,
    delete_document
)
from app.services.vector_store import (
    VectorStoreService,
    VectorStoreError,
    DocumentNotFoundError,
    DocumentNotIndexedError,
    UnembeddedChunksError,
    parse_pages_metadata,
    vector_store_service
)


class TestChromaVectorStoreService(unittest.TestCase):
    """
    Automated test suite for PaperPilot Phase 2.2B:
    ChromaDB Vector Database Service Integration.
    """

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.db = SessionLocal()
        # Use isolated in-memory client for fast, leak-free test isolation
        self.chroma_client = chromadb.Client()
        self.service = VectorStoreService(
            collection_name=f"test_coll_{uuid.uuid4().hex[:8]}",
            client=self.chroma_client
        )

    def tearDown(self):
        self.db.close()

    def _create_mock_document(self, num_chunks=3, with_embeddings=True):
        doc_id = str(uuid.uuid4())
        doc = Document(
            id=doc_id,
            user_id=LEGACY_OWNER_USER_ID,
            filename=f"{doc_id}.pdf",
            original_filename="test_science.pdf",
            file_path=os.path.join(tempfile.gettempdir(), f"{doc_id}.pdf"),
            file_size_bytes=1024,
            total_pages=5,
            extracted_pages=5,
            total_characters=3000,
            total_chunks=num_chunks,
            status="ready",
            embedding_status="completed" if with_embeddings else "pending"
        )
        self.db.add(doc)

        dummy_vectors = [
            [0.1 if j % 2 == 0 else -0.1 for j in range(768)],
            [0.2 if j % 3 == 0 else -0.05 for j in range(768)],
            [0.5 if j % 4 == 0 else 0.01 for j in range(768)],
        ]

        for i in range(num_chunks):
            emb = dummy_vectors[i % len(dummy_vectors)] if with_embeddings else None
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=doc_id,
                chunk_index=i,
                content=f"Sample text content for chunk {i} about chemical reactions and properties.",
                char_count=65,
                page_start=i + 1,
                page_end=i + 1,
                pages_json=json.dumps([i + 1]),
                embedding_json=json.dumps(emb) if emb else None,
                embedding_dimension=768 if emb else None
            )
            self.db.add(chunk)

        self.db.commit()
        return doc

    # 1. Page Metadata Parsing
    def test_parse_pages_metadata_variations(self):
        self.assertEqual(parse_pages_metadata("[1, 2, 3]"), [1, 2, 3])
        self.assertEqual(parse_pages_metadata("1, 2"), [1, 2])
        self.assertEqual(parse_pages_metadata([4, 5]), [4, 5])
        self.assertEqual(parse_pages_metadata(7), [7])
        self.assertEqual(parse_pages_metadata(""), [])
        self.assertEqual(parse_pages_metadata(None), [])

    # 2. Ingest Document Chunks into ChromaDB
    def test_index_document_chunks_success(self):
        doc = self._create_mock_document(num_chunks=3, with_embeddings=True)
        res = self.service.index_document_chunks(doc.id, self.db)

        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["indexed_vectors"], 3)
        self.assertEqual(res["total_chunks"], 3)
        self.assertEqual(res["document_id"], doc.id)

        count = self.service.get_document_vector_count(doc.id)
        self.assertEqual(count, 3)

    # 3. Re-indexing without Force Prevents Duplication
    def test_reindex_without_force_skips_duplicates(self):
        doc = self._create_mock_document(num_chunks=3, with_embeddings=True)
        self.service.index_document_chunks(doc.id, self.db)

        res_second = self.service.index_document_chunks(doc.id, self.db, force=False)
        self.assertEqual(res_second["status"], "already_indexed")
        self.assertEqual(res_second["indexed_vectors"], 3)

        count = self.service.get_document_vector_count(doc.id)
        self.assertEqual(count, 3)

    # 4. Re-indexing with Force Replaces Cleanly
    def test_reindex_with_force_replaces_cleanly(self):
        doc = self._create_mock_document(num_chunks=3, with_embeddings=True)
        self.service.index_document_chunks(doc.id, self.db)

        res_force = self.service.index_document_chunks(doc.id, self.db, force=True)
        self.assertEqual(res_force["status"], "completed")
        self.assertEqual(res_force["indexed_vectors"], 3)

        count = self.service.get_document_vector_count(doc.id)
        self.assertEqual(count, 3)

    # 5. Unembedded Chunks Validation
    def test_index_unembedded_chunks_raises_error(self):
        doc = self._create_mock_document(num_chunks=2, with_embeddings=False)
        with self.assertRaises(UnembeddedChunksError):
            self.service.index_document_chunks(doc.id, self.db)

    # 6. Non-existent Document Validation
    def test_index_nonexistent_document_raises_error(self):
        with self.assertRaises(DocumentNotFoundError):
            self.service.index_document_chunks("nonexistent-doc-id", self.db)

    # 7. Indexing Status Inspection
    def test_get_indexing_status(self):
        doc = self._create_mock_document(num_chunks=3, with_embeddings=True)

        # Before indexing
        status_before = self.service.get_indexing_status(doc.id, self.db)
        self.assertFalse(status_before["is_indexed"])
        self.assertEqual(status_before["status"], "not_indexed")
        self.assertEqual(status_before["indexed_vectors"], 0)
        self.assertEqual(status_before["total_chunks"], 3)

        # After indexing
        self.service.index_document_chunks(doc.id, self.db)
        status_after = self.service.get_indexing_status(doc.id, self.db)
        self.assertTrue(status_after["is_indexed"])
        self.assertEqual(status_after["status"], "indexed")
        self.assertEqual(status_after["indexed_vectors"], 3)

    # 8. Deleting Document Vectors
    def test_delete_document_vectors(self):
        doc = self._create_mock_document(num_chunks=3, with_embeddings=True)
        self.service.index_document_chunks(doc.id, self.db)
        self.assertEqual(self.service.get_document_vector_count(doc.id), 3)

        deleted = self.service.delete_document_vectors(doc.id)
        self.assertEqual(deleted, 3)
        self.assertEqual(self.service.get_document_vector_count(doc.id), 0)

    # 9. Document-Specific Filtering in Vector Search
    def test_document_specific_filtering(self):
        doc1 = self._create_mock_document(num_chunks=2, with_embeddings=True)
        doc2 = self._create_mock_document(num_chunks=2, with_embeddings=True)

        self.service.index_document_chunks(doc1.id, self.db)
        self.service.index_document_chunks(doc2.id, self.db)

        # Query using a vector similar to chunk 0
        query_vec = [0.1 if j % 2 == 0 else -0.1 for j in range(768)]

        results_doc1 = self.service.search_document(
            doc1.id,
            query="chemical reactions",
            top_k=4,
            query_embedding=query_vec,
            db=self.db
        )
        self.assertTrue(len(results_doc1) > 0)
        for r in results_doc1:
            chunk_rec = self.db.query(DocumentChunk).filter(DocumentChunk.id == r["chunk_id"]).first()
            self.assertEqual(chunk_rec.document_id, doc1.id)

    # 10. Semantic Search Metadata and Distance Preservation
    def test_search_preserves_metadata_and_citations(self):
        doc = self._create_mock_document(num_chunks=3, with_embeddings=True)
        self.service.index_document_chunks(doc.id, self.db)

        query_vec = [0.1 if j % 2 == 0 else -0.1 for j in range(768)]
        results = self.service.search_document(
            doc.id,
            query="test query",
            top_k=2,
            query_embedding=query_vec,
            db=self.db
        )

        self.assertEqual(len(results), 2)
        top = results[0]
        self.assertIn("chunk_id", top)
        self.assertIn("chunk_index", top)
        self.assertIn("content", top)
        self.assertIn("page_start", top)
        self.assertIn("page_end", top)
        self.assertIn("pages", top)
        self.assertIsInstance(top["pages"], list)
        self.assertIn("distance", top)
        self.assertIn("similarity_score", top)
        self.assertGreaterEqual(top["similarity_score"], 0.0)
        self.assertLessEqual(top["similarity_score"], 1.0)

    # 11. Search Unindexed Document Raises Error
    def test_search_unindexed_document_raises_error(self):
        doc = self._create_mock_document(num_chunks=2, with_embeddings=True)
        with self.assertRaises(DocumentNotIndexedError):
            self.service.search_document(
                doc.id,
                query="test",
                query_embedding=[0.1] * 768,
                db=self.db
            )

    # 12. Search Empty Query Raises ValueError
    def test_search_empty_query_raises_error(self):
        doc = self._create_mock_document(num_chunks=2, with_embeddings=True)
        self.service.index_document_chunks(doc.id, self.db)
        with self.assertRaises(ValueError):
            self.service.search_document(
                doc.id,
                query="   ",
                query_embedding=[0.1] * 768,
                db=self.db
            )

    # 13. Persistent ChromaDB across Re-initialization
    def test_persistence_across_service_reinit(self):
        temp_dir = tempfile.mkdtemp()
        try:
            doc = self._create_mock_document(num_chunks=2, with_embeddings=True)
            persistent_service = VectorStoreService(
                persist_directory=temp_dir,
                collection_name="test_persist_coll"
            )
            persistent_service.index_document_chunks(doc.id, self.db)

            # Re-initialize service pointing to the identical persistent directory
            reloaded_service = VectorStoreService(
                persist_directory=temp_dir,
                collection_name="test_persist_coll"
            )
            count = reloaded_service.get_document_vector_count(doc.id)
            self.assertEqual(count, 2)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestChromaVectorStoreEndpoints(unittest.TestCase):
    """
    Automated integration tests for PaperPilot ChromaDB API endpoints.
    """

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.original_client = vector_store_service._client
        # Use isolated in-memory Chroma client for instantaneous endpoint test execution
        vector_store_service._client = chromadb.Client()
        vector_store_service._collection = None

    @classmethod
    def tearDownClass(cls):
        vector_store_service._client = cls.original_client
        vector_store_service._collection = None

    def setUp(self):
        self.db = SessionLocal()
        self.owner = self.db.query(User).filter(User.id == LEGACY_OWNER_USER_ID).first()
        self.doc_id = str(uuid.uuid4())
        self.doc = Document(
            id=self.doc_id,
            user_id=self.owner.id,
            filename=f"{self.doc_id}.pdf",
            original_filename="api_test_doc.pdf",
            file_path=os.path.join(tempfile.gettempdir(), f"{self.doc_id}.pdf"),
            file_size_bytes=2048,
            total_pages=3,
            extracted_pages=3,
            total_characters=1500,
            total_chunks=2,
            status="ready",
            embedding_status="completed"
        )
        self.db.add(self.doc)

        # Add 2 chunks with 768-dim embeddings
        for i in range(2):
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=self.doc_id,
                chunk_index=i,
                content=f"API chunk {i} discussing chemical reactions and catalysts.",
                char_count=60,
                page_start=i + 1,
                page_end=i + 1,
                pages_json=json.dumps([i + 1]),
                embedding_json=json.dumps([0.05 if j % 2 == 0 else -0.05 for j in range(768)]),
                embedding_dimension=768
            )
            self.db.add(chunk)

        self.db.commit()

    def tearDown(self):
        try:
            vector_store_service.delete_document_vectors(self.doc_id)
        except Exception:
            pass
        self.db.query(DocumentChunk).filter(DocumentChunk.document_id == self.doc_id).delete()
        self.db.query(Document).filter(Document.id == self.doc_id).delete()
        self.db.commit()
        self.db.close()

    # 14. API: GET /index-status
    def test_api_get_index_status(self):
        resp = get_document_index_status(self.doc_id, current_user=self.owner, db=self.db)
        self.assertEqual(resp.document_id, self.doc_id)
        self.assertEqual(resp.total_chunks, 2)
        self.assertEqual(resp.indexed_vectors, 0)
        self.assertFalse(resp.is_indexed)
        self.assertEqual(resp.status, "not_indexed")

    # 15. API: POST /index
    def test_api_post_index(self):
        resp = index_document_vectors(self.doc_id, force=False, current_user=self.owner, db=self.db)
        self.assertEqual(resp.document_id, self.doc_id)
        self.assertEqual(resp.indexed_vectors, 2)
        self.assertEqual(resp.total_chunks, 2)
        self.assertEqual(resp.status, "completed")

        # Calling again without force returns already_indexed
        resp2 = index_document_vectors(self.doc_id, force=False, current_user=self.owner, db=self.db)
        self.assertEqual(resp2.status, "already_indexed")
        self.assertEqual(resp2.indexed_vectors, 2)

    # 16. API: POST /search
    def test_api_post_search(self):
        # Index chunks first
        index_document_vectors(self.doc_id, force=False, current_user=self.owner, db=self.db)

        # Mock embedding_service.generate_embeddings_for_batch to run offline in sandbox
        dummy_query_vector = [[0.05 if j % 2 == 0 else -0.05 for j in range(768)]]
        with patch("app.services.vector_store.embedding_service.generate_embeddings_for_batch", return_value=dummy_query_vector):
            resp = search_document_chunks(
                self.doc_id,
                SearchRequest(query="chemical reactions", top_k=2),
                current_user=self.owner,
                db=self.db
            )

        self.assertEqual(resp.document_id, self.doc_id)
        self.assertEqual(resp.query, "chemical reactions")
        self.assertEqual(resp.total_results, 2)
        self.assertEqual(len(resp.results), 2)
        top = resp.results[0]
        self.assertTrue(top.chunk_id)
        self.assertGreaterEqual(top.similarity_score, 0.0)
        self.assertLessEqual(top.similarity_score, 1.0)
        self.assertIsInstance(top.pages, list)

    # 17. API: Search Unindexed Document returns 400
    def test_api_search_unindexed_document_returns_400(self):
        dummy_query_vector = [[0.05 if j % 2 == 0 else -0.05 for j in range(768)]]
        with patch("app.services.vector_store.embedding_service.generate_embeddings_for_batch", return_value=dummy_query_vector):
            with self.assertRaises(HTTPException) as ctx:
                search_document_chunks(
                    self.doc_id,
                    SearchRequest(query="test query", top_k=2),
                    current_user=self.owner,
                    db=self.db
                )
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("not been indexed", ctx.exception.detail)

    # 18. API: Delete Document Purges Chroma Vectors
    def test_api_delete_document_cleans_chroma_vectors(self):
        # Index document
        index_document_vectors(self.doc_id, force=False, current_user=self.owner, db=self.db)
        self.assertEqual(vector_store_service.get_document_vector_count(self.doc_id), 2)

        # Delete document via API route
        delete_document(self.doc_id, current_user=self.owner, db=self.db)

        # Chroma vector count must now be 0
        self.assertEqual(vector_store_service.get_document_vector_count(self.doc_id), 0)



if __name__ == "__main__":
    unittest.main()
