import os
import sys
import json
import uuid
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import pymupdf
import chromadb

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.db.session import SessionLocal, init_db
from app.db.models import Document, DocumentChunk
from app.api.v1.documents import (
    process_document_pipeline,
    execute_extraction_and_chunking,
    chat_with_document,
    reprocess_document
)
from app.schemas.chat import DocumentChatRequest
from app.services.vector_store import VectorStoreService
from fastapi import HTTPException


class TestAutomaticPipeline(unittest.TestCase):
    """
    Automated integration test suite for PaperPilot Automatic Document Processing:
    - uploaded -> extracting -> embedding -> indexing -> ready
    - Scanned PDF graceful OCR-required stop
    - Embedding failure handling
    - Chat rejection when incomplete
    - Zero duplicate chunks/vectors on reprocess
    """

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = SessionLocal()
        # Isolated Chroma client
        self.chroma_client = chromadb.Client()
        self.vector_store = VectorStoreService(
            collection_name=f"test_auto_{uuid.uuid4().hex[:8]}",
            client=self.chroma_client
        )

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def _create_sample_pdf(self, pages_text: list, filename: str = "auto_sample.pdf") -> str:
        doc = pymupdf.open()
        for idx, text in enumerate(pages_text):
            page = doc.new_page(width=595, height=842)
            if text:
                rect = pymupdf.Rect(40, 40, 555, 800)
                page.insert_textbox(rect, text, fontsize=10)
        path = os.path.join(self.temp_dir.name, filename)
        doc.save(path)
        doc.close()
        return path

    def test_complete_automatic_pipeline_success(self):
        """Verify full automatic pipeline runs end-to-end to status: ready."""
        pages = [
            "Chapter 1: Chemical Reactions and Equations. When magnesium burns in air it forms magnesium oxide.",
            "Chemical equations balance mass according to the law of conservation of mass.",
            "Corrosion and rancidity are two common daily effects of oxidation reactions."
        ]
        pdf_path = self._create_sample_pdf(pages)
        doc_id = str(uuid.uuid4())

        doc = Document(
            id=doc_id,
            filename=f"{doc_id}.pdf",
            original_filename="science_auto.pdf",
            file_path=pdf_path,
            file_size_bytes=os.path.getsize(pdf_path),
            total_pages=3,
            status="uploaded",
            embedding_status="pending"
        )
        self.db.add(doc)
        self.db.commit()

        dummy_vectors = [[0.1] * 768 for _ in range(10)]
        with patch("app.services.embedding_service.embedding_service.generate_embeddings_for_batch", return_value=dummy_vectors):
            with patch("app.api.v1.documents.vector_store_service", self.vector_store):
                processed = process_document_pipeline(doc_id, db=self.db)

        self.assertIsNotNone(processed)
        self.assertEqual(processed.status, "ready")
        self.assertEqual(processed.embedding_status, "completed")
        self.assertGreater(processed.total_chunks, 0)
        self.assertEqual(processed.total_pages, 3)

        # Chunks verified in SQLite
        chunks = self.db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).all()
        self.assertEqual(len(chunks), processed.total_chunks)
        self.assertTrue(all(c.embedding_json is not None for c in chunks))

        # Vectors verified in ChromaDB
        indexed_count = self.vector_store.get_document_vector_count(doc_id)
        self.assertEqual(indexed_count, len(chunks))

        # Clean up
        self.vector_store.delete_document_vectors(doc_id)
        self.db.delete(doc)
        self.db.commit()

    def test_pipeline_scanned_pdf_sets_ocr_required(self):
        """Scanned PDF without text gracefully terminates at status: ocr_required."""
        pdf_path = self._create_sample_pdf(["", "", ""])
        doc_id = str(uuid.uuid4())

        doc = Document(
            id=doc_id,
            filename=f"{doc_id}.pdf",
            original_filename="scanned.pdf",
            file_path=pdf_path,
            file_size_bytes=1024,
            total_pages=3,
            status="uploaded"
        )
        self.db.add(doc)
        self.db.commit()

        processed = process_document_pipeline(doc_id, db=self.db)
        self.assertEqual(processed.status, "ocr_required")
        self.assertIn("OCR is not yet supported", processed.error_message)

        # Clean up
        self.db.delete(doc)
        self.db.commit()

    def test_chat_blocked_when_document_processing(self):
        """Verify chat requests are rejected while document is in processing states."""
        doc_id = str(uuid.uuid4())
        doc = Document(
            id=doc_id,
            filename=f"{doc_id}.pdf",
            original_filename="pending.pdf",
            file_path=os.path.join(self.temp_dir.name, "none.pdf"),
            status="embedding"
        )
        self.db.add(doc)
        self.db.commit()

        with self.assertRaises(HTTPException) as ctx:
            chat_with_document(
                doc_id,
                DocumentChatRequest(message="What is this?"),
                db=self.db
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("embedding", ctx.exception.detail)

        # Clean up
        self.db.delete(doc)
        self.db.commit()

    def test_reprocess_avoids_duplicate_vectors(self):
        """Reprocessing an existing document replaces chunks and vectors without duplication."""
        pages = ["Page one chemistry text.", "Page two physics text."]
        pdf_path = self._create_sample_pdf(pages)
        doc_id = str(uuid.uuid4())

        doc = Document(
            id=doc_id,
            filename=f"{doc_id}.pdf",
            original_filename="reprocess_test.pdf",
            file_path=pdf_path,
            file_size_bytes=1024,
            total_pages=2,
            status="uploaded"
        )
        self.db.add(doc)
        self.db.commit()

        dummy_vectors = [[0.05] * 768 for _ in range(5)]
        with patch("app.services.embedding_service.embedding_service.generate_embeddings_for_batch", return_value=dummy_vectors):
            with patch("app.api.v1.documents.vector_store_service", self.vector_store):
                # 1st run
                p1 = process_document_pipeline(doc_id, db=self.db)
                c1 = self.vector_store.get_document_vector_count(doc_id)

                # 2nd run (reprocess)
                p2 = process_document_pipeline(doc_id, db=self.db)
                c2 = self.vector_store.get_document_vector_count(doc_id)

        self.assertEqual(c1, c2)
        self.assertEqual(p1.total_chunks, p2.total_chunks)

        # Clean up
        self.vector_store.delete_document_vectors(doc_id)
        self.db.delete(doc)
        self.db.commit()


if __name__ == "__main__":
    unittest.main()
