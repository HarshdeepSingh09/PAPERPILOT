import os
import re
from typing import List, Dict, Any, Optional
import pymupdf
from app.utils.text_cleaner import TextCleaner


class PDFExtractionError(Exception):
    """Base exception for PDF extraction issues."""
    pass


class PasswordProtectedPDFError(PDFExtractionError):
    """Raised when a PDF requires a password to decrypt/read."""
    pass


class CorruptedPDFError(PDFExtractionError):
    """Raised when a PDF file is corrupt or unreadable."""
    pass


class PDFService:
    """
    Handles PDF loading, text extraction, page metadata preservation,
    cleaning, and scanned/image-only document detection.
    """

    @classmethod
    def inspect_and_extract(cls, file_path: str) -> Dict[str, Any]:
        """
        Extracts, normalizes, and analyzes text from every page of a PDF document.

        Returns a dictionary with:
        - total_pages: int
        - extracted_pages: int
        - total_characters: int
        - is_scanned: bool
        - pages: List[Dict[str, Any]] (each with page, text, char_count, is_empty, has_images)
        - metadata: Dict[str, Any]
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found at: {file_path}")

        try:
            doc = pymupdf.open(file_path)
        except pymupdf.FileDataError as e:
            raise CorruptedPDFError(f"The PDF file is corrupted or invalid: {str(e)}")
        except Exception as e:
            raise CorruptedPDFError(f"Failed to open PDF document: {str(e)}")

        try:
            # Check for encryption / password requirement
            if doc.is_encrypted or doc.needs_pass:
                raise PasswordProtectedPDFError(
                    "The uploaded PDF is password protected. Please provide an unencrypted document."
                )

            total_pages = len(doc)
            if total_pages == 0:
                raise CorruptedPDFError("The PDF document contains 0 pages.")

            pages_data: List[Dict[str, Any]] = []
            total_chars = 0
            has_any_images = False

            for page_idx in range(total_pages):
                page_num = page_idx + 1  # 1-indexed page number
                page = doc[page_idx]

                # Extract raw text and clean it
                raw_text = page.get_text("text") or ""
                cleaned_text = TextCleaner.clean(raw_text)
                char_count = len(cleaned_text)
                total_chars += char_count

                # Check if page has images
                page_images = page.get_images()
                page_has_images = len(page_images) > 0
                if page_has_images:
                    has_any_images = True

                pages_data.append({
                    "page": page_num,
                    "text": cleaned_text,
                    "char_count": char_count,
                    "is_empty": (char_count == 0),
                    "has_images": page_has_images
                })

            metadata = doc.metadata or {}
            extracted_pages_count = sum(1 for p in pages_data if not p["is_empty"])

            # Scanned / Image-only detection:
            # If the PDF has pages, but total extracted visible characters across all pages is 0
            # (or below 20 characters total while containing embedded images):
            is_scanned = (total_chars == 0) or (total_chars < 20 and has_any_images)

            doc_structure = cls._extract_metadata_from_doc(doc, metadata, pages_data)

            return {
                "total_pages": total_pages,
                "extracted_pages": extracted_pages_count,
                "total_characters": total_chars,
                "is_scanned": is_scanned,
                "pages": pages_data,
                "metadata": {
                    "title": doc_structure.get("title") or metadata.get("title", ""),
                    "author": doc_structure.get("author") or metadata.get("author", ""),
                    "producer": metadata.get("producer", "")
                },
                "document_metadata": doc_structure
            }

        finally:
            doc.close()

    @classmethod
    def _extract_metadata_from_doc(
        cls,
        doc: pymupdf.Document,
        raw_metadata: Dict[str, Any],
        pages_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Examines typography, headings, and chapter markers in the opening pages
        to extract title, chapter name, chapter number, and subject.
        """
        total_pages = len(doc)
        result = {
            "title": None,
            "chapter_name": None,
            "chapter_number": None,
            "subject": None,
            "author": None,
            "opening_snippet": None
        }

        if total_pages == 0:
            return result

        first_page_text = pages_data[0]["text"] if pages_data else ""
        result["opening_snippet"] = first_page_text[:400].strip() if first_page_text else None

        # Clean author if present in raw metadata
        raw_author = (raw_metadata.get("author") or "").strip()
        if raw_author and not raw_author.lower().startswith("dtp") and not raw_author.lower().startswith("user"):
            result["author"] = raw_author

        # Clean raw title
        raw_title = (raw_metadata.get("title") or "").strip()
        cleaned_raw_title = re.sub(r'(?i)\.(pmd|pdf|docx?|txt)$', '', raw_title).strip()
        if cleaned_raw_title and not re.match(r'(?i)^chap\s*\d+$', cleaned_raw_title):
            result["title"] = cleaned_raw_title

        # Inspect typography on first page
        p1 = doc[0]
        blocks = p1.get_text("dict").get("blocks", [])
        text_blocks = []

        for b in blocks:
            if "lines" in b and b["lines"]:
                spans = [s["text"].strip() for l in b["lines"] for s in l.get("spans", []) if s.get("text", "").strip()]
                if spans:
                    font_size = b["lines"][0]["spans"][0].get("size", 10.0)
                    text = " ".join(spans).strip()
                    if text:
                        text_blocks.append({"text": text, "size": font_size})

        # 1. Search for Chapter number patterns
        for b in text_blocks[:10]:
            t = b["text"]
            ch_match = re.search(
                r'(?i)\b(?:chapter|unit|lesson)\s*[:\-–]?\s*(\d+|[IVXLCDM]+)\b|\b(\d+|[IVXLCDM]+)\s*(?:chapter|unit|lesson)\b',
                t
            )
            if ch_match:
                num = ch_match.group(1) or ch_match.group(2)
                result["chapter_number"] = f"Chapter {num}"
                break

        # 2. Search for prominent Title / Chapter Name in large heading blocks
        large_blocks = [b for b in text_blocks if b["size"] >= 16.0]
        for b in large_blocks:
            t = b["text"].strip()
            # Skip if block is just "1 CHAPTER" or "Chapter 1"
            if re.search(r'(?i)^\d+\s*chapter\b|^\s*chapter\s*\d+\s*$', t):
                continue
            if len(t) > 3:
                result["chapter_name"] = t
                result["title"] = t
                break

        # If not found in large blocks, check top text blocks
        if not result["chapter_name"] and text_blocks:
            for b in text_blocks[:5]:
                t = b["text"].strip()
                if re.search(r'(?i)^\d+\s*chapter\b|^\s*chapter\s*\d+\s*$', t):
                    continue
                if len(t) > 5 and not t.lower().startswith("activity") and not t.lower().startswith("figure"):
                    result["chapter_name"] = t
                    if not result["title"]:
                        result["title"] = t
                    break

        # 3. Search for Subject (e.g. Science, Mathematics, Physics, Chemistry)
        subject_keywords = ["science", "mathematics", "physics", "chemistry", "biology", "history", "geography"]
        for b in text_blocks[:10]:
            if b["text"].strip().lower() in subject_keywords:
                result["subject"] = b["text"].strip().capitalize()
                break

        # Check running headers on page 2 or 3 if subject not found on page 1
        if not result["subject"] and total_pages > 1:
            for p_idx in [1, 2]:
                if p_idx < total_pages:
                    page_b = doc[p_idx].get_text("dict").get("blocks", [])[:5]
                    for b in page_b:
                        if "lines" in b and b["lines"]:
                            spans = [s["text"].strip() for l in b["lines"] for s in l.get("spans", []) if s.get("text", "").strip()]
                            txt = " ".join(spans).strip()
                            if txt.lower() in subject_keywords:
                                result["subject"] = txt.capitalize()
                                break
                    if result["subject"]:
                        break

        return result

    @classmethod
    def get_pdf_metadata(cls, file_path: str) -> Dict[str, Any]:
        """
        Quick metadata inspection helper.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found at {file_path}")

        try:
            doc = pymupdf.open(file_path)
        except Exception as e:
            raise CorruptedPDFError(f"Could not read PDF metadata: {str(e)}")

        try:
            if doc.is_encrypted or doc.needs_pass:
                raise PasswordProtectedPDFError("The PDF is password protected.")
            total_pages = len(doc)
            metadata = doc.metadata or {}
        finally:
            doc.close()

        return {
            "total_pages": total_pages,
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
        }


pdf_service = PDFService()
