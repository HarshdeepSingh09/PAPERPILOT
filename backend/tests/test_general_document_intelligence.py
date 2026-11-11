import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
import zipfile
from unittest.mock import patch

import chromadb
import pymupdf
from fastapi import HTTPException

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, init_db
from app.db.models import Document, DocumentChunk, ChatMessage, DocumentInsight, User
from app.api.v1.documents import (
    upload_document,
    get_document_content,
    update_document_category,
    chat_with_document,
)
from app.api.v1.insights import get_document_insights, generate_document_insights
from app.schemas.chat import DocumentChatRequest
from app.schemas.insights import CategoryUpdateRequest, AdaptiveInsightsResponse, InsightsGenerateRequest
from app.services.document_extractor import (
    document_extractor,
    UnsupportedFileFormatError,
    EmptyDocumentError,
    PasswordProtectedDocumentError,
    CorruptedDocumentError,
    FileSizeLimitError,
)
from app.services.classification_service import (
    classification_service,
    DOCUMENT_CATEGORIES,
)
from app.services.adaptive_insights_service import (
    adaptive_insights_service,
    LEGAL_DISCLAIMER,
)
from app.services.vector_store import VectorStoreService
from app.services.rag_service import RAGService


class _FakeUploadFile:
    """Minimal async UploadFile-compatible wrapper that reads without an anyio threadpool portal."""

    def __init__(self, filename: str, data: bytes, content_type: str):
        self.filename = filename
        self.content_type = content_type
        self._buf = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)


def _run_coro_sync(coro):
    """Drive a coroutine whose awaits resolve immediately without opening a socket self-pipe."""
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value
    raise RuntimeError("Unexpected pending await inside synchronous test runner")


def build_pdf_bytes(pages_text: list[str], encrypt_password: str | None = None) -> bytes:
    doc = pymupdf.open()
    for page_text in pages_text:
        page = doc.new_page()
        page.insert_text((72, 72), page_text, fontsize=11)
    if encrypt_password:
        buf = doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=encrypt_password,
            owner_pw=encrypt_password,
        )
    else:
        buf = doc.tobytes()
    doc.close()
    return buf


def build_docx_bytes(blocks: list[tuple[str, str]], tables: list[list[list[str]]] | None = None, title: str = "") -> bytes:
    """
    Creates a real valid OOXML .docx ZIP archive with heading styles, paragraphs, tables, and core.xml metadata.
    blocks: list of (style_id, text) e.g. ('Heading1', 'Meeting Summary'), ('Normal', 'Body paragraph.')
    """
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '</Relationships>'
    )
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:title>{title}</dc:title>'
        '<dc:creator>PaperPilot Test Author</dc:creator>'
        '</cp:coreProperties>'
    )

    body_xml_parts = []
    for style_id, text in blocks:
        safe_txt = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        p_pr = f'<w:pPr><w:pStyle w:val="{style_id}"/></w:pPr>' if style_id and style_id != "Normal" else ""
        body_xml_parts.append(f"<w:p>{p_pr}<w:r><w:t>{safe_txt}</w:t></w:r></w:p>")

    if tables:
        for tbl in tables:
            tr_parts = []
            for row in tbl:
                tc_parts = []
                for cell in row:
                    safe_cell = cell.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    tc_parts.append(f"<w:tc><w:p><w:r><w:t>{safe_cell}</w:t></w:r></w:p></w:tc>")
                tr_parts.append(f"<w:tr>{''.join(tc_parts)}</w:tr>")
            body_xml_parts.append(f"<w:tbl>{''.join(tr_parts)}</w:tbl>")

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{"".join(body_xml_parts)}<w:sectPr/></w:body>'
        '</w:document>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("docProps/core.xml", core_xml)
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


class TestGeneralDocumentIntelligence(unittest.TestCase):
    """
    Phase 4 comprehensive automated verification suite:
    - Multi-format validation & extraction (.pdf, .docx, .txt)
    - Corrupt / empty / oversized / password-protected rejection
    - 8-category intelligent classification (never filename-only, low-confidence fallback)
    - Manual category override & persistence
    - Adaptive intelligence for Research, Business, Meeting Notes, Legal, Financial, Manual, General
    - Universal RAG chat, document isolation, and page/section citations
    """

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.db = SessionLocal()
        self.tmp_dir = tempfile.mkdtemp(prefix="pp_phase4_")
        self.created_doc_ids: list[str] = []
        self.test_user_id = str(uuid.uuid4())
        self.test_user = User(
            id=self.test_user_id,
            name="Phase 4 Test User",
            email=f"phase4_{self.test_user_id[:8]}@example.com",
            password_hash=hash_password("Phase4StrongPass!"),
            role="user",
            is_active=True,
        )
        self.db.add(self.test_user)
        self.db.commit()
        self.db.refresh(self.test_user)
        self.chroma_client = chromadb.Client()
        self.vector_store = VectorStoreService(
            collection_name=f"test_phase4_{uuid.uuid4().hex[:8]}",
            client=self.chroma_client,
        )
        self.rag = RAGService(
            model_name="gemini-3.5-flash",
            vector_store=self.vector_store,
            max_retries=1,
            initial_backoff=0.01,
        )

    def tearDown(self):
        for doc_id in self.created_doc_ids:
            try:
                doc = self.db.query(Document).filter(Document.id == doc_id).first()
                if doc and doc.file_path and os.path.exists(doc.file_path):
                    try:
                        os.remove(doc.file_path)
                    except OSError:
                        pass
                self.db.query(DocumentInsight).filter(DocumentInsight.document_id == doc_id).delete()
                self.db.query(ChatMessage).filter(ChatMessage.document_id == doc_id).delete()
                self.db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
                self.db.query(Document).filter(Document.id == doc_id).delete()
                self.db.commit()
            except Exception:
                self.db.rollback()
        try:
            self.db.query(User).filter(User.id == self.test_user_id).delete()
            self.db.commit()
        except Exception:
            self.db.rollback()
        user_upload_dir = os.path.join(settings.UPLOAD_DIR, self.test_user_id)
        shutil.rmtree(user_upload_dir, ignore_errors=True)
        self.db.close()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # --- 1. Multi-format Validation & Invalid Files ---

    def test_validation_rejects_invalid_corrupt_empty_encrypted_and_oversized(self):
        # Unsupported extension
        with self.assertRaises(UnsupportedFileFormatError):
            document_extractor.validate_extension_and_mime("malware.exe", "application/octet-stream")

        # Invalid MIME for .pdf
        with self.assertRaises(UnsupportedFileFormatError):
            document_extractor.validate_extension_and_mime("doc.pdf", "image/png")

        # Empty 0-byte file
        empty_path = os.path.join(self.tmp_dir, "empty.txt")
        with open(empty_path, "wb") as f:
            pass
        with self.assertRaises(EmptyDocumentError):
            document_extractor.validate_saved_file(empty_path, "txt", 0)

        # Oversized file check
        big_path = os.path.join(self.tmp_dir, "big.txt")
        with open(big_path, "wb") as f:
            f.write(b"hello")
        with self.assertRaises(FileSizeLimitError):
            document_extractor.validate_saved_file(big_path, "txt", 50 * 1024 * 1024, max_size_bytes=1024)

        # Binary disguised as .txt
        bin_txt = os.path.join(self.tmp_dir, "binary.txt")
        with open(bin_txt, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        with self.assertRaises(CorruptedDocumentError):
            document_extractor.validate_saved_file(bin_txt, "txt", 16)

        # Corrupted DOCX
        bad_docx = os.path.join(self.tmp_dir, "bad.docx")
        with open(bad_docx, "wb") as f:
            f.write(b"not a zip archive")
        with self.assertRaises(CorruptedDocumentError):
            document_extractor.validate_saved_file(bad_docx, "docx", 18)

        # Password-protected / encrypted DOCX (OLE2 header)
        enc_docx = os.path.join(self.tmp_dir, "locked.docx")
        with open(enc_docx, "wb") as f:
            f.write(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)
        with self.assertRaises(PasswordProtectedDocumentError):
            document_extractor.validate_saved_file(enc_docx, "docx", 72)

        # Password-protected PDF
        enc_pdf = os.path.join(self.tmp_dir, "locked.pdf")
        with open(enc_pdf, "wb") as f:
            f.write(build_pdf_bytes(["Secret protected text"], encrypt_password="pass123"))
        with self.assertRaises(PasswordProtectedDocumentError):
            document_extractor.validate_saved_file(enc_pdf, "pdf", os.path.getsize(enc_pdf))

    # --- 2. Real Extraction Across PDF, DOCX, TXT ---

    def test_docx_and_txt_extraction_preserves_sections_headings_and_paragraphs(self):
        docx_bytes = build_docx_bytes(
            title="Weekly Engineering Sync",
            blocks=[
                ("Heading1", "Minutes of Meeting"),
                ("Normal", "Attendees: Alice Chen, Bob Patel, Priya Nair. Call to order at 10:00 AM."),
                ("Heading1", "Important Decisions"),
                ("Normal", "Decision: Approved migration to v2 embeddings by November 20, 2026."),
                ("Heading1", "Action Items"),
                ("Normal", "Assigned to: Alice Chen - Finalize database migration script by Nov 15, 2026."),
                ("Normal", "Bob Patel will prepare rollout checklist before Nov 18, 2026."),
            ],
            tables=[
                [["Owner", "Task", "Due Date"], ["Alice Chen", "DB Migration", "Nov 15, 2026"]],
            ],
        )
        docx_path = os.path.join(self.tmp_dir, "sync.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        ext_docx = document_extractor.inspect_and_extract(docx_path, "docx")
        self.assertEqual(ext_docx["file_format"], "docx")
        self.assertEqual(ext_docx["citation_unit"], "section")
        self.assertFalse(ext_docx["is_scanned"])
        self.assertGreaterEqual(len(ext_docx["headings"]), 3)
        self.assertGreaterEqual(ext_docx["total_pages"], 1)
        self.assertIn("Minutes of Meeting", ext_docx["headings"][0]["text"])
        self.assertIn("Alice Chen | DB Migration | Nov 15, 2026", ext_docx["pages"][-1]["text"])

        txt_content = (
            "# Project Field Notes\n\n"
            "This document records general observations collected during the autumn survey.\n\n"
            "## Weather Conditions\n\n"
            "Skies remained mostly clear throughout the week with mild afternoon breezes."
        )
        txt_path = os.path.join(self.tmp_dir, "notes.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt_content)

        ext_txt = document_extractor.inspect_and_extract(txt_path, "txt")
        self.assertEqual(ext_txt["file_format"], "txt")
        self.assertEqual(ext_txt["citation_unit"], "section")
        self.assertGreaterEqual(ext_txt["total_pages"], 1)
        self.assertGreater(ext_txt["total_characters"], 80)

    # --- 3. Intelligent Classification (Never Filename-Only, Low Confidence Fallback) ---

    def test_classification_all_categories_content_based_not_filename(self):
        # Deliberately pass no filename (classifier never takes filename!) and test content/structure
        samples = [
            (
                "Educational Material",
                "Chapter 2: Acids, Bases and Salts. Activity 2.1: Test the solutions in the laboratory. "
                "Learning Objectives: Understand pH scale. In-text Questions and Exercises at the end of chapter. Class 10 Science NCERT.",
                {"chapter_name": "Acids, Bases and Salts", "chapter_number": "Chapter 2", "subject": "Science"},
            ),
            (
                "Research Paper",
                "Abstract\nWe propose a novel transformer retrieval architecture evaluated on three benchmarks. "
                "Methodology\nOur experimental setup uses 5-fold cross validation with p < 0.01 statistical significance. "
                "Results and Discussion\nAs shown by Smith et al. (arXiv:2401.1234), limitations of our study remain.\nReferences",
                {},
            ),
            (
                "Business Report",
                "Executive Summary\nQuarterly Business Review covering market share, competitive landscape, and SWOT analysis. "
                "Key Performance Indicators (KPI) and customer acquisition ROI improved. Strategic Recommendations include expanding partner pipeline.",
                {},
            ),
            (
                "Meeting Notes",
                "Minutes of Meeting\nAttendees: Sarah, Raj, Elena\nAgenda Items: Q4 Launch\n"
                "Decisions Made: Approved UI freeze.\nAction Items: Assigned to: Raj - Complete QA by Friday.\nNext Meeting: Nov 25.",
                {},
            ),
            (
                "Legal Document",
                "MASTER SERVICES AGREEMENT\nWHEREAS the Licensor and Licensee agree as follows, hereinafter referred to as the Parties. "
                "Each Party shall indemnify the other. Governing Law and Jurisdiction: State of Delaware. Arbitration and Termination Clause.",
                {},
            ),
            (
                "Financial Report",
                "Consolidated Income Statement and Balance Sheet for Fiscal Year FY2025.\n"
                "Total Revenue reached $48.2 million with Gross Margin of 62.4% and EBITDA of $11.5 million. "
                "Operating Expenses were $18.1 million. Shareholders' Equity and Cash Flow Statement were audited.",
                {},
            ),
            (
                "User Manual / Technical Documentation",
                "Installation Guide & Quick Start\nPrerequisites: Python 3.11+.\nStep 1: Run the CLI install command.\n"
                "Configuration & API Reference.\nWarning: Do not disconnect power during firmware update.\nTroubleshooting: Error code 404 fix.",
                {},
            ),
            (
                "General Document",
                "Yesterday afternoon the community garden hosted a small autumn gathering near the park fountain where neighbors shared homemade soup.",
                {},
            ),
        ]

        with patch.object(classification_service, "get_client", return_value=None):
            for expected_cat, text, meta in samples:
                res = classification_service.classify_document(
                    text_sample=text,
                    doc_metadata=meta,
                    use_ai=False,
                )
                self.assertEqual(
                    res["category"],
                    expected_cat,
                    f"Expected '{expected_cat}', got '{res['category']}' (reason: {res['reason']})",
                )
                self.assertGreaterEqual(res["confidence"], 0.0)
                self.assertLessEqual(res["confidence"], 1.0)

    # --- 4. Adaptive Insights Across All Non-Educational Categories ---

    def test_adaptive_insights_all_categories_and_caching(self):
        cat_texts = {
            "Research Paper": "Abstract: We study neural retrieval. Methodology: 10-fold evaluation on MS MARCO. Results show 14% gain. Limitations include English-only corpus.",
            "Business Report": "Executive Summary: SaaS expansion drove $4.2 million ARR growth (+22%). Action: Expand enterprise sales. Recommendation: Prioritize onboarding automation.",
            "Meeting Notes": "Minutes of Meeting. Attendees: Mia, Leo. Decision: Agreed to ship beta. Action: Assigned to: Mia - Update API docs by Dec 1, 2026. Unresolved: Pricing tier TBD.",
            "Legal Document": 'Agreement between "Acme Corp." and "Beta LLC". Party shall maintain confidentiality for 24 months. Termination requires 30 days written notice under Delaware Governing Law.',
            "Financial Report": "FY2025 Balance Sheet & Income Statement. Total Revenue: $12.5 million. Operating Expenses: $7.2 million. Gross Margin: 58.0%. Net profit increased YoY.",
            "User Manual / Technical Documentation": "Setup Guide. Step 1: Configure API keys in .env. Warning: Never commit secrets to git. Troubleshooting: Restart service if connection fails.",
            "General Document": "Local library announced extended weekend hours starting next month along with new study rooms on the second floor.",
        }

        for cat, content in cat_texts.items():
            doc_id = str(uuid.uuid4())
            self.created_doc_ids.append(doc_id)
            doc = Document(
                id=doc_id,
                user_id=self.test_user_id,
                filename=f"{doc_id}.txt",
                original_filename=f"sample_{cat[:6]}.txt",
                file_path=os.path.join(self.tmp_dir, f"{doc_id}.txt"),
                file_size_bytes=len(content),
                total_pages=1,
                extracted_pages=1,
                total_characters=len(content),
                total_chunks=1,
                status="ready",
                file_format="txt",
                document_category=cat,
                classification_confidence=0.9,
            )
            self.db.add(doc)
            self.db.add(DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=doc_id,
                chunk_index=0,
                content=content,
                char_count=len(content),
                page_start=1,
                page_end=1,
                pages_json="[1]",
                section_title="Overview",
                paragraph_range="1-2",
            ))
            self.db.commit()

            with patch.object(adaptive_insights_service, "get_client", return_value=None):
                res = adaptive_insights_service.get_or_generate_insights(doc_id, self.db, force_regenerate=True)

            self.assertEqual(res["category"], cat)
            self.assertEqual(res["generation_source"], "extractive")
            ins = res["insights"]
            if cat == "Legal Document":
                self.assertEqual(ins.get("disclaimer"), LEGAL_DISCLAIMER)
            if cat == "Meeting Notes":
                self.assertTrue(len(ins.get("assigned_responsibilities", [])) >= 1)
                self.assertTrue(len(ins.get("deadlines_mentioned", [])) >= 1)
            if cat == "Financial Report":
                self.assertTrue(len(ins.get("important_figures", [])) >= 1)

            # Verify SQLite cache hit via FastAPI insights endpoint handler
            cached = get_document_insights(
                document_id=doc_id,
                category=None,
                current_user=self.test_user,
                db=self.db,
            )
            validated = AdaptiveInsightsResponse.model_validate(cached)
            self.assertEqual(validated.category, cat)
            self.assertEqual(validated.document_id, doc_id)

            # Verify POST /generate endpoint returns cached result cleanly
            re_res = generate_document_insights(
                payload=InsightsGenerateRequest(document_id=doc_id, category=cat, force_regenerate=False),
                current_user=self.test_user,
                db=self.db,
            )
            self.assertEqual(AdaptiveInsightsResponse.model_validate(re_res).category, cat)

    # --- 5. Upload Pipeline, Manual Override, Universal Chat Citations & Isolation ---

    def test_upload_override_isolation_and_universal_chat_endpoints(self):
        # Verify Phase 4 FastAPI routes are mounted in the OpenAPI schema / router tree
        registered_paths = set(app.openapi()["paths"].keys())
        self.assertIn("/api/v1/documents/upload", registered_paths)
        self.assertIn("/api/v1/documents/{document_id}/category", registered_paths)
        self.assertIn("/api/v1/documents/{document_id}/content", registered_paths)
        self.assertIn("/api/v1/insights/{document_id}", registered_paths)
        self.assertIn("/api/v1/insights/generate", registered_paths)

        # 1. Upload Meeting Notes DOCX with a misleading generic filename ('upload_a.docx')
        docx_bytes = build_docx_bytes(
            title="Q4 Product Sync",
            blocks=[
                ("Heading1", "Minutes of Meeting"),
                ("Normal", "Attendees: Jordan Lee, Samira Khan. Agenda: Release readiness."),
                ("Heading1", "Action Items"),
                ("Normal", "Decision: Agreed to freeze schema on Nov 14, 2026."),
                ("Normal", "Assigned to: Jordan Lee - Verify regression tests by Nov 16, 2026."),
            ],
        )

        # 2. Upload Research Paper PDF with misleading filename ('upload_b.pdf')
        pdf_bytes = build_pdf_bytes([
            "Abstract\nWe evaluate hybrid retrieval on long legal and technical corpora.\nMethodology\nWe use 768-dimensional cosine vectors and cross-validation.\nReferences\nSmith et al. (2025)."
        ])

        dummy_vec = [0.05] * 768

        def fake_embed_batch(texts, api_key=None):
            return [dummy_vec for _ in texts]

        with patch("app.services.embedding_service.embedding_service.generate_embeddings_for_batch", side_effect=fake_embed_batch), \
             patch("app.api.v1.documents.vector_store_service", self.vector_store), \
             patch("app.api.v1.documents.rag_service", self.rag), \
             patch.object(classification_service, "get_client", return_value=None):
            d_docx = _run_coro_sync(
                upload_document(
                    file=_FakeUploadFile(
                        "upload_a.docx",
                        docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                    background=False,
                    background_tasks=None,
                    current_user=self.test_user,
                    db=self.db,
                )
            )
            self.created_doc_ids.append(d_docx.id)
            self.assertEqual(d_docx.status, "ready")
            self.assertEqual(d_docx.user_id, self.test_user_id)
            self.assertEqual(d_docx.file_format, "docx")
            self.assertEqual(d_docx.citation_unit, "section")
            self.assertEqual(d_docx.document_category, "Meeting Notes")

            d_pdf = _run_coro_sync(
                upload_document(
                    file=_FakeUploadFile("upload_b.pdf", pdf_bytes, "application/pdf"),
                    background=False,
                    background_tasks=None,
                    current_user=self.test_user,
                    db=self.db,
                )
            )
            self.created_doc_ids.append(d_pdf.id)
            self.assertEqual(d_pdf.status, "ready")
            self.assertEqual(d_pdf.user_id, self.test_user_id)
            self.assertEqual(d_pdf.file_format, "pdf")
            self.assertEqual(d_pdf.citation_unit, "page")
            self.assertEqual(d_pdf.document_category, "Research Paper")

            # Verify /content endpoint for DOCX reader
            c_res = get_document_content(document_id=d_docx.id, current_user=self.test_user, db=self.db)
            self.assertEqual(c_res.citation_unit, "section")
            self.assertGreaterEqual(len(c_res.sections), 1)

            # Verify manual category override endpoint
            patched = update_document_category(
                document_id=d_docx.id,
                payload=CategoryUpdateRequest(category="Business Report"),
                current_user=self.test_user,
                db=self.db,
            )
            self.assertEqual(patched.document_category, "Business Report")
            self.assertEqual(patched.classification_source, "manual")
            self.assertEqual(patched.classification_confidence, 1.0)

            # Verify document isolation & universal RAG chat citations (section vs page)
            with patch.object(
                self.rag,
                "generate_answer",
                return_value="Jordan Lee will verify regression tests by Nov 16, 2026 (Section 2).",
            ):
                ans_docx = chat_with_document(
                    document_id=d_docx.id,
                    request=DocumentChatRequest(message="Who is responsible for verifying regression tests?"),
                    current_user=self.test_user,
                    db=self.db,
                )
            self.assertTrue(len(ans_docx.citations) > 0)
            self.assertEqual(ans_docx.citations[0].source_type, "section")
            self.assertTrue(ans_docx.citations[0].label.startswith("Section"))

            # Verify PDF chat returns page citations and never retrieves DOCX chunks
            with patch.object(
                self.rag,
                "generate_answer",
                return_value="Hybrid retrieval uses 768-dimensional cosine vectors (Page 1).",
            ):
                ans_pdf = chat_with_document(
                    document_id=d_pdf.id,
                    request=DocumentChatRequest(message="What vectors are used in methodology?"),
                    current_user=self.test_user,
                    db=self.db,
                )
            self.assertEqual(ans_pdf.citations[0].source_type, "page")
            self.assertEqual(ans_pdf.citations[0].label, "Page 1")
            for cit in ans_pdf.citations:
                self.assertNotIn("Jordan Lee", cit.snippet or "")

        # Verify invalid upload via endpoint raises HTTP 400 cleanly
        with self.assertRaises(HTTPException) as ctx:
            _run_coro_sync(
                upload_document(
                    file=_FakeUploadFile("script.exe", b"MZ...", "application/octet-stream"),
                    background=False,
                    background_tasks=None,
                    current_user=self.test_user,
                    db=self.db,
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
