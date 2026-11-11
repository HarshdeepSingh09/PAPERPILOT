import os
import sys
import unittest
import tempfile
import pymupdf

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.utils.text_cleaner import TextCleaner
from app.services.chunking_service import IntelligentChunker, default_chunker
from app.services.pdf_service import (
    pdf_service,
    PasswordProtectedPDFError,
    CorruptedPDFError
)
from app.db.session import SessionLocal, init_db
from app.db.models import Document, DocumentChunk, LEGACY_OWNER_USER_ID
from app.api.v1.documents import execute_extraction_and_chunking


class TestPDFExtractionAndChunking(unittest.TestCase):
    """
    Automated test suite for PaperPilot Phase 2.1:
    - Text extraction
    - Text cleaning and normalization
    - Configurable chunking and sentence boundary preservation
    - Page number preservation across multi-page chunks
    - Empty pages, short docs, long docs, scanned docs
    - Password protected and corrupted file handling
    - Database persistence and idempotency
    """

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def _create_sample_pdf(self, pages_text: list, filename: str = "sample.pdf") -> str:
        """Helper to create a PDF with the given list of text strings per page using insert_textbox."""
        doc = pymupdf.open()
        for idx, text in enumerate(pages_text):
            page = doc.new_page(width=595, height=842)  # Standard A4
            if text:
                rect = pymupdf.Rect(40, 40, 555, 800)
                page.insert_textbox(rect, text, fontsize=10)
        path = os.path.join(self.temp_dir.name, filename)
        doc.save(path)
        doc.close()
        return path

    # 1. Text Cleaner Tests
    def test_text_cleaning_normalization(self):
        # Line break de-hyphenation
        raw = "This is a demon-\nstration of de-hyphen-\nation in action."
        cleaned = TextCleaner.clean(raw)
        self.assertIn("demonstration", cleaned)
        self.assertIn("de-hyphenation", cleaned)

        # Control characters and form-feed normalization
        raw_control = "Text with null\x00 byte and form\x0cfeed and soft\xadhyphen."
        cleaned_control = TextCleaner.clean(raw_control)
        self.assertEqual(cleaned_control, "Text with null byte and form feed and softhyphen.")

        # Excessive blank lines collapsing
        raw_newlines = "Paragraph 1\n\n\n\n\nParagraph 2\n\n\n\nParagraph 3"
        cleaned_newlines = TextCleaner.clean(raw_newlines)
        self.assertEqual(cleaned_newlines, "Paragraph 1\n\nParagraph 2\n\nParagraph 3")

        # Mathematical and punctuation preservation
        math_text = "E = mc^2; ∫ f(x)dx = F(x) + C. α + β = γ. Cost is $100.00 (50%)."
        cleaned_math = TextCleaner.clean(math_text)
        self.assertEqual(cleaned_math, math_text)

    # 2. Normal Multi-page PDF
    def test_normal_multi_page_pdf(self):
        pages = [
            "Introduction to PaperPilot. PaperPilot is an intelligent document processing engine.",
            "Chapter 2 focuses on chemistry. Chemical reactions involve rearrangement of atoms and bonds.",
            "Chapter 3 covers physics and energy conservation. Energy can neither be created nor destroyed.",
            "Chapter 4 provides experimental methods and laboratory safety procedures.",
            "Conclusion and future outlook. All research questions were thoroughly addressed."
        ]
        pdf_path = self._create_sample_pdf(pages, "multi_page.pdf")

        result = pdf_service.inspect_and_extract(pdf_path)
        self.assertEqual(result["total_pages"], 5)
        self.assertEqual(result["extracted_pages"], 5)
        self.assertFalse(result["is_scanned"])
        self.assertGreater(result["total_characters"], 200)

        # Verify page numbers in extracted pages
        for idx, page_info in enumerate(result["pages"]):
            self.assertEqual(page_info["page"], idx + 1)
            self.assertFalse(page_info["is_empty"])

        # Run chunking
        chunks = default_chunker.chunk_document("doc-normal", result["pages"])
        self.assertGreater(len(chunks), 0)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].page_start, 1)

    # 3. Empty Pages Handling
    def test_empty_pages_handling(self):
        pages = [
            "Page 1 contains valid content that explains the foundational principles.",
            "",  # Page 2 is completely empty
            "Page 3 contains continuation content after an empty separator page."
        ]
        pdf_path = self._create_sample_pdf(pages, "empty_pages.pdf")

        result = pdf_service.inspect_and_extract(pdf_path)
        self.assertEqual(result["total_pages"], 3)
        self.assertEqual(result["extracted_pages"], 2)
        self.assertFalse(result["is_scanned"])

        # Page 2 should be marked empty
        self.assertFalse(result["pages"][0]["is_empty"])
        self.assertTrue(result["pages"][1]["is_empty"])
        self.assertFalse(result["pages"][2]["is_empty"])

        chunks = default_chunker.chunk_document("doc-empty-pages", result["pages"])
        pages_in_chunks = set()
        for c in chunks:
            pages_in_chunks.update(c.pages)
        self.assertIn(1, pages_in_chunks)
        self.assertIn(3, pages_in_chunks)

    # 4. Very Short Document
    def test_very_short_document(self):
        short_text = ["This is a tiny document with just one sentence."]
        pdf_path = self._create_sample_pdf(short_text, "short.pdf")

        result = pdf_service.inspect_and_extract(pdf_path)
        self.assertEqual(result["total_pages"], 1)
        self.assertEqual(result["extracted_pages"], 1)

        chunks = default_chunker.chunk_document("doc-short", result["pages"])
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_index, 0)
        self.assertEqual(chunks[0].page_start, 1)
        self.assertEqual(chunks[0].page_end, 1)
        self.assertEqual(chunks[0].pages, [1])
        self.assertEqual(chunks[0].content, short_text[0])

    # 5. Long Document
    def test_long_document_processing(self):
        # 10 pages with dense text (~1,000 characters per page)
        long_paragraph = (
            "Photosynthesis is a biological process used by plants and other organisms to convert light energy into chemical energy. "
            "Light energy is absorbed by proteins called reaction centers that contain green chlorophyll pigments. "
            "In plants, these proteins are held inside organelles called chloroplasts, which are most abundant in leaf cells. "
            "In these light-dependent reactions, some energy is used to strip electrons from suitable substances, such as water, producing oxygen gas. "
            "The hydrogen freed by the splitting of water is used in the creation of two further compounds that serve as short-term stores of energy. "
        )
        long_pages = [f"Page {i + 1} Heading.\n\n" + long_paragraph for i in range(10)]
        pdf_path = self._create_sample_pdf(long_pages, "long_doc.pdf")

        result = pdf_service.inspect_and_extract(pdf_path)
        self.assertEqual(result["total_pages"], 10)
        self.assertEqual(result["extracted_pages"], 10)
        self.assertGreater(result["total_characters"], 5000)

        chunks = default_chunker.chunk_document("doc-long", result["pages"])
        self.assertGreater(len(chunks), 5)

        # Verify chunk order and sizes
        for idx, chunk in enumerate(chunks):
            self.assertEqual(chunk.chunk_index, idx)
            self.assertGreater(chunk.char_count, 100)
            self.assertLessEqual(chunk.char_count, int(default_chunker.chunk_size * 1.3))

    # 6. Scanned / Image-only / No Extractable Text Detection
    def test_scanned_pdf_detection(self):
        doc = pymupdf.open()
        for _ in range(3):
            page = doc.new_page()
            # Draw a shape to simulate a scanned image page without extractable text
            page.draw_rect(pymupdf.Rect(50, 50, 200, 200), color=(0, 0, 0), fill=(0.8, 0.8, 0.8))
        path = os.path.join(self.temp_dir.name, "scanned_doc.pdf")
        doc.save(path)
        doc.close()

        result = pdf_service.inspect_and_extract(path)
        self.assertEqual(result["total_pages"], 3)
        self.assertEqual(result["total_characters"], 0)
        self.assertTrue(result["is_scanned"])

        # Test execute_extraction_and_chunking sets ocr_required status
        db_doc = Document(
            id="doc-scanned-test",
            user_id=LEGACY_OWNER_USER_ID,
            filename="scanned_doc.pdf",
            original_filename="Scanned Paper.pdf",
            file_path=path,
            total_pages=3,
            status="processing"
        )
        self.db.add(db_doc)
        self.db.commit()

        processed = execute_extraction_and_chunking(db_doc, self.db)
        self.assertEqual(processed.status, "ocr_required")
        self.assertIn("OCR is not yet supported", processed.error_message)
        self.assertEqual(processed.total_chunks, 0)

        # Cleanup db_doc
        self.db.delete(db_doc)
        self.db.commit()

    # 7. Chunk Overlap and Multi-Page Range Tracking
    def test_chunk_overlap_and_multi_page_ranges(self):
        # Configure chunker with chunk_size=250 and overlap=80
        chunker = IntelligentChunker(chunk_size=250, chunk_overlap=80)

        pages = [
            {
                "page": 1,
                "text": (
                    "First sentence on page one sets the historical context. "
                    "Second sentence on page one provides foundational definitions. "
                    "Third sentence on page one completes the preliminary section."
                )
            },
            {
                "page": 2,
                "text": (
                    "Fourth sentence begins page two detailing analytical models. "
                    "Fifth sentence on page two reviews experimental parameters. "
                    "Sixth sentence on page two compares theoretical and actual results."
                )
            },
            {
                "page": 3,
                "text": (
                    "Seventh sentence on page three presents practical implications. "
                    "Eighth sentence on page three highlights limitations of this study. "
                    "Ninth sentence on page three wraps up the complete document analysis."
                )
            }
        ]

        chunks = chunker.chunk_document("doc-ranges", pages)
        self.assertGreater(len(chunks), 2)

        # Verify multi-page tracking
        has_multi_page = any(len(c.pages) > 1 for c in chunks)
        self.assertTrue(has_multi_page, "At least one chunk should span across page boundary")

        for c in chunks:
            self.assertEqual(c.page_start, min(c.pages))
            self.assertEqual(c.page_end, max(c.pages))
            if len(c.pages) > 1:
                self.assertLess(c.page_start, c.page_end)

        # Verify overlap: consecutive chunks share sentence words
        for i in range(len(chunks) - 1):
            chunk_a = chunks[i].content
            chunk_b = chunks[i + 1].content
            words_a = set(chunk_a.split()[-10:])
            words_b = set(chunk_b.split()[:10])
            common_words = words_a.intersection(words_b)
            self.assertGreater(len(common_words), 0, f"Chunk {i} and {i+1} must overlap in content")

    # 8. Password Protected PDF Handling
    def test_password_protected_pdf(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 72), "Confidential encrypted document.", fontsize=12)
        encrypted_path = os.path.join(self.temp_dir.name, "encrypted.pdf")
        doc.save(
            encrypted_path,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw="securepass123",
            owner_pw="adminpass123"
        )
        doc.close()

        with self.assertRaises(PasswordProtectedPDFError) as ctx:
            pdf_service.inspect_and_extract(encrypted_path)
        self.assertIn("password", str(ctx.exception).lower())

    # 9. Corrupted PDF Handling
    def test_corrupted_pdf_handling(self):
        corrupt_path = os.path.join(self.temp_dir.name, "corrupt.pdf")
        with open(corrupt_path, "wb") as f:
            f.write(b"%PDF-1.4\nSome random garbage that is not valid PDF data\x00\xff")

        with self.assertRaises(CorruptedPDFError):
            pdf_service.inspect_and_extract(corrupt_path)

    # 10. Database Persistence & Reprocessing Idempotency
    def test_database_persistence_and_idempotency(self):
        pages = [
            "Section 1 outlines the initial hypotheses and questions.",
            "Section 2 presents numerical findings and observations."
        ]
        pdf_path = self._create_sample_pdf(pages, "persist_test.pdf")

        doc_record = Document(
            id="doc-persist-test",
            user_id=LEGACY_OWNER_USER_ID,
            filename="persist_test.pdf",
            original_filename="Persist Test.pdf",
            file_path=pdf_path,
            total_pages=2,
            status="processing"
        )
        self.db.add(doc_record)
        self.db.commit()

        # Run extraction & chunking
        processed = execute_extraction_and_chunking(doc_record, self.db)
        self.assertEqual(processed.status, "ready")
        self.assertGreater(processed.total_chunks, 0)

        initial_chunk_count = self.db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_record.id).count()
        self.assertEqual(initial_chunk_count, processed.total_chunks)

        # Reprocess the same document (simulating re-triggering extraction)
        reprocessed = execute_extraction_and_chunking(doc_record, self.db)
        reprocessed_chunk_count = self.db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_record.id).count()

        # Chunk count MUST be identical (no duplicates!)
        self.assertEqual(reprocessed_chunk_count, initial_chunk_count)

        # Cleanup
        self.db.delete(doc_record)
        self.db.commit()


if __name__ == "__main__":
    unittest.main()
