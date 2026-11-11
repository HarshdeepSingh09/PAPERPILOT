import os
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Tuple
import pymupdf

from app.core.config import settings
from app.services.pdf_service import (
    pdf_service,
    PDFExtractionError,
    PasswordProtectedPDFError,
    CorruptedPDFError,
)
from app.utils.text_cleaner import TextCleaner


class DocumentValidationError(Exception):
    """Base error for unsupported, empty, oversized, corrupted, or encrypted files."""
    status_code: int = 400


class UnsupportedFileFormatError(DocumentValidationError):
    status_code = 400


class FileSizeLimitError(DocumentValidationError):
    status_code = 413


class EmptyDocumentError(DocumentValidationError):
    status_code = 422


class PasswordProtectedDocumentError(DocumentValidationError):
    status_code = 400


class CorruptedDocumentError(DocumentValidationError):
    status_code = 422


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

ALLOWED_MIME_TYPES = {
    "pdf": {
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
        "",
    },
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
        "",
    },
    "txt": {
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/octet-stream",
        "",
    },
}

OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"


class DocumentExtractorService:
    """
    Unified multi-format document validator and text/structure extractor for:
    - PDF (.pdf) -> delegates to PDFService
    - Word (.docx) -> parses OOXML paragraphs, headings, tables, and core properties
    - Plain Text (.txt) -> decodes text, detects headings/sections and paragraph ranges
    """

    @staticmethod
    def get_file_format(filename: str) -> str:
        ext = os.path.splitext((filename or "").strip())[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise UnsupportedFileFormatError(
                "Unsupported file format. Allowed formats: PDF (.pdf), Word (.docx), Text (.txt)."
            )
        return ext.lstrip(".")

    @classmethod
    def validate_extension_and_mime(cls, filename: str, content_type: Optional[str]) -> str:
        file_format = cls.get_file_format(filename)
        mime = (content_type or "").split(";")[0].strip().lower()
        allowed = ALLOWED_MIME_TYPES.get(file_format, set())
        if mime and mime not in allowed:
            raise UnsupportedFileFormatError(
                f"Invalid MIME type '{mime}' for .{file_format} file."
            )
        return file_format

    @classmethod
    def validate_saved_file(
        cls,
        file_path: str,
        file_format: str,
        file_size: int,
        max_size_bytes: Optional[int] = None,
    ) -> None:
        max_bytes = max_size_bytes or (settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024)
        if file_size <= 0:
            raise EmptyDocumentError("The uploaded file is empty (0 bytes).")
        if file_size > max_bytes:
            raise FileSizeLimitError(
                f"File exceeds the maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB."
            )

        if file_format == "pdf":
            try:
                doc = pymupdf.open(file_path)
            except Exception as e:
                raise CorruptedDocumentError(f"The uploaded file is corrupted or not a valid PDF: {e}") from e
            try:
                if doc.is_encrypted or doc.needs_pass:
                    raise PasswordProtectedDocumentError(
                        "The PDF document is password-protected. Please upload an unprotected PDF."
                    )
                if len(doc) == 0:
                    raise CorruptedDocumentError("The PDF document contains 0 pages.")
            finally:
                doc.close()

        elif file_format == "docx":
            with open(file_path, "rb") as f:
                header = f.read(16)
            if header.startswith(OLE2_MAGIC):
                raise PasswordProtectedDocumentError(
                    "The Word document appears to be password-protected/encrypted or in legacy .doc format. "
                    "Please upload an unencrypted .docx file."
                )
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    names = set(zf.namelist())
                    if "EncryptionInfo" in names or "EncryptedPackage" in names:
                        raise PasswordProtectedDocumentError(
                            "The Word document is password-protected. Please upload an unencrypted .docx file."
                        )
                    if "word/document.xml" not in names:
                        raise CorruptedDocumentError("The .docx archive is missing word/document.xml.")
                    # Verify XML parses cleanly
                    ET.fromstring(zf.read("word/document.xml"))
            except PasswordProtectedDocumentError:
                raise
            except zipfile.BadZipFile as e:
                raise CorruptedDocumentError(f"The uploaded file is corrupted or not a valid .docx archive: {e}") from e
            except ET.ParseError as e:
                raise CorruptedDocumentError(f"The uploaded .docx XML is malformed: {e}") from e

        elif file_format == "txt":
            with open(file_path, "rb") as f:
                raw = f.read()
            has_utf16_bom = raw.startswith((b"\xff\xfe", b"\xfe\xff"))
            if not has_utf16_bom and b"\x00" in raw[:8192]:
                raise CorruptedDocumentError(
                    "The uploaded .txt file appears to contain binary data rather than plain text."
                )
            decoded = cls._decode_text_bytes(raw)
            if not TextCleaner.is_meaningful_text(TextCleaner.clean(decoded), min_chars=1):
                raise EmptyDocumentError("The uploaded .txt file is empty or contains no readable text.")

    @staticmethod
    def _decode_text_bytes(raw: bytes) -> str:
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16", errors="replace")
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    @classmethod
    def inspect_and_extract(cls, file_path: str, file_format: Optional[str] = None) -> Dict[str, Any]:
        fmt = (file_format or os.path.splitext(file_path)[1].lstrip(".") or "pdf").lower()
        if fmt == "pdf":
            res = pdf_service.inspect_and_extract(file_path)
            res["file_format"] = "pdf"
            res["citation_unit"] = "page"
            return res
        elif fmt == "docx":
            return cls._extract_docx(file_path)
        elif fmt == "txt":
            return cls._extract_txt(file_path)
        else:
            raise UnsupportedFileFormatError(f"Unsupported file format: {fmt}")

    @classmethod
    def _extract_docx(cls, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"DOCX file not found at: {file_path}")

        with open(file_path, "rb") as f:
            header = f.read(16)
        if header.startswith(OLE2_MAGIC):
            raise PasswordProtectedDocumentError(
                "The Word document is password-protected or encrypted."
            )

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                names = set(zf.namelist())
                if "EncryptionInfo" in names or "EncryptedPackage" in names:
                    raise PasswordProtectedDocumentError("The Word document is password-protected.")
                if "word/document.xml" not in names:
                    raise CorruptedDocumentError("Invalid DOCX: missing word/document.xml.")

                doc_xml = zf.read("word/document.xml")
                core_xml = zf.read("docProps/core.xml") if "docProps/core.xml" in names else None
        except (PasswordProtectedDocumentError, CorruptedDocumentError):
            raise
        except zipfile.BadZipFile as e:
            raise CorruptedDocumentError(f"Corrupted DOCX file: {e}") from e

        # Extract core metadata (title, creator, subject)
        core_title = None
        core_author = None
        core_subject = None
        if core_xml:
            try:
                core_root = ET.fromstring(core_xml)
                t_el = core_root.find(f".//{DC_NS}title")
                c_el = core_root.find(f".//{DC_NS}creator")
                s_el = core_root.find(f".//{DC_NS}subject")
                if t_el is not None and t_el.text and t_el.text.strip():
                    core_title = t_el.text.strip()
                if c_el is not None and c_el.text and c_el.text.strip():
                    core_author = c_el.text.strip()
                if s_el is not None and s_el.text and s_el.text.strip():
                    core_subject = s_el.text.strip()
            except Exception:
                pass

        try:
            root = ET.fromstring(doc_xml)
        except ET.ParseError as e:
            raise CorruptedDocumentError(f"Malformed DOCX XML: {e}") from e

        body = root.find(f"{W_NS}body")
        if body is None:
            raise CorruptedDocumentError("Invalid DOCX: missing document body.")

        paragraphs: List[Dict[str, Any]] = []
        para_idx = 0

        for child in body:
            tag = child.tag
            if tag == f"{W_NS}p":
                text, heading_level = cls._parse_docx_paragraph(child)
                if text:
                    para_idx += 1
                    paragraphs.append({
                        "paragraph_index": para_idx,
                        "text": text,
                        "heading_level": heading_level,
                        "is_heading": heading_level is not None,
                    })
            elif tag == f"{W_NS}tbl":
                table_lines = cls._parse_docx_table(child)
                for row_text in table_lines:
                    para_idx += 1
                    paragraphs.append({
                        "paragraph_index": para_idx,
                        "text": row_text,
                        "heading_level": None,
                        "is_heading": False,
                    })

        return cls._build_sectioned_extraction(
            paragraphs=paragraphs,
            file_format="docx",
            raw_title=core_title,
            raw_author=core_author,
            raw_subject=core_subject,
        )

    @classmethod
    def _parse_docx_paragraph(cls, p_el: ET.Element) -> Tuple[str, Optional[int]]:
        p_pr = p_el.find(f"{W_NS}pPr")
        heading_level: Optional[int] = None

        if p_pr is not None:
            p_style = p_pr.find(f"{W_NS}pStyle")
            if p_style is not None:
                val = (p_style.attrib.get(f"{W_NS}val") or "").strip()
                low = val.lower()
                if low == "title":
                    heading_level = 1
                elif low == "subtitle":
                    heading_level = 2
                else:
                    m = re.match(r"heading\s*(\d+)", low)
                    if m:
                        heading_level = int(m.group(1))
            if heading_level is None:
                outline = p_pr.find(f"{W_NS}outlineLvl")
                if outline is not None:
                    try:
                        lvl = int(outline.attrib.get(f"{W_NS}val", "9"))
                        if 0 <= lvl <= 5:
                            heading_level = lvl + 1
                    except ValueError:
                        pass

        # Collect text runs including tabs and breaks
        parts: List[str] = []
        for elem in p_el.iter():
            if elem.tag == f"{W_NS}t" and elem.text:
                parts.append(elem.text)
            elif elem.tag == f"{W_NS}tab":
                parts.append(" ")
            elif elem.tag == f"{W_NS}br":
                parts.append("\n")

        raw_text = "".join(parts)
        cleaned = TextCleaner.clean(raw_text)

        # Heuristic check for clean short markdown-like or numbered headings if style wasn't explicit
        if heading_level is None and cleaned and len(cleaned) <= 90 and "\n" not in cleaned:
            if re.match(r"^(?:\d+(?:\.\d+)*\.?\s+)?[A-Z][A-Za-z0-9\s,&/\-():]{2,60}$", cleaned) and not cleaned.endswith("."):
                # Avoid false positives on key-value lines unless it looks like a section header
                if ":" not in cleaned:
                    pass  # Keep conservative unless explicit style or clear heading

        return cleaned, heading_level

    @classmethod
    def _parse_docx_table(cls, tbl_el: ET.Element) -> List[str]:
        rows_out: List[str] = []
        for tr in tbl_el.findall(f"{W_NS}tr"):
            cells_text: List[str] = []
            for tc in tr.findall(f"{W_NS}tc"):
                cell_parts: List[str] = []
                for p in tc.findall(f".//{W_NS}p"):
                    t, _ = cls._parse_docx_paragraph(p)
                    if t:
                        cell_parts.append(t)
                cells_text.append(" ".join(cell_parts).strip())
            non_empty = [c for c in cells_text if c]
            if non_empty:
                rows_out.append(" | ".join(cells_text).strip())
        return rows_out

    @classmethod
    def _extract_txt(cls, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"TXT file not found at: {file_path}")

        with open(file_path, "rb") as f:
            raw = f.read()

        if not raw:
            raise EmptyDocumentError("The uploaded .txt file is empty.")

        has_utf16_bom = raw.startswith((b"\xff\xfe", b"\xfe\xff"))
        if not has_utf16_bom and b"\x00" in raw[:8192]:
            raise CorruptedDocumentError("The uploaded .txt file contains binary data.")

        decoded = cls._decode_text_bytes(raw)
        cleaned_full = TextCleaner.clean(decoded)
        if not TextCleaner.is_meaningful_text(cleaned_full, min_chars=1):
            raise EmptyDocumentError("The uploaded .txt file contains no extractable text.")

        raw_blocks = [b.strip() for b in re.split(r"\n\s*\n", cleaned_full) if b.strip()]
        paragraphs: List[Dict[str, Any]] = []
        para_idx = 0

        for block in raw_blocks:
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue

            # Detect Markdown heading (# Title) or underlined heading (Title\n===) or ALL-CAPS header
            first = lines[0]
            heading_level: Optional[int] = None
            block_text = block

            md_match = re.match(r"^(#{1,6})\s+(.+)$", first)
            if md_match and len(lines) == 1:
                heading_level = len(md_match.group(1))
                block_text = md_match.group(2).strip()
            elif md_match and len(lines) > 1:
                # Split heading line from body paragraph
                para_idx += 1
                paragraphs.append({
                    "paragraph_index": para_idx,
                    "text": md_match.group(2).strip(),
                    "heading_level": len(md_match.group(1)),
                    "is_heading": True,
                })
                block_text = "\n".join(lines[1:]).strip()
            elif len(lines) == 2 and re.match(r"^[=\-]{3,}$", lines[1]):
                heading_level = 1 if lines[1].startswith("=") else 2
                block_text = first
            elif len(lines) == 1 and len(first) <= 80 and not first.endswith("."):
                if first.isupper() or re.match(r"^(?:SECTION|PART|CHAPTER|APPENDIX)\s+[A-Z0-9]+", first, re.I):
                    heading_level = 2

            para_idx += 1
            paragraphs.append({
                "paragraph_index": para_idx,
                "text": block_text,
                "heading_level": heading_level,
                "is_heading": heading_level is not None,
            })

        return cls._build_sectioned_extraction(
            paragraphs=paragraphs,
            file_format="txt",
        )

    @classmethod
    def _build_sectioned_extraction(
        cls,
        paragraphs: List[Dict[str, Any]],
        file_format: str,
        raw_title: Optional[str] = None,
        raw_author: Optional[str] = None,
        raw_subject: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not paragraphs:
            return {
                "total_pages": 1,
                "extracted_pages": 0,
                "total_characters": 0,
                "is_scanned": True,
                "file_format": file_format,
                "citation_unit": "section",
                "pages": [],
                "headings": [],
                "metadata": {"title": raw_title or "", "author": raw_author or ""},
                "document_metadata": {
                    "title": raw_title,
                    "author": raw_author,
                    "subject": raw_subject,
                    "headings": [],
                    "total_paragraphs": 0,
                    "total_sections": 0,
                },
            }

        sections: List[Dict[str, Any]] = []
        headings: List[Dict[str, Any]] = []
        current_paras: List[Dict[str, Any]] = []
        current_title: Optional[str] = None
        current_chars = 0
        MAX_SECTION_CHARS = 2200

        def flush_section():
            nonlocal current_paras, current_title, current_chars
            if not current_paras:
                return
            sec_num = len(sections) + 1
            p_start = current_paras[0]["paragraph_index"]
            p_end = current_paras[-1]["paragraph_index"]
            sec_title = current_title or f"Section {sec_num} (Paragraphs {p_start}-{p_end})"
            sec_text = "\n\n".join(p["text"] for p in current_paras)
            sections.append({
                "page": sec_num,
                "section_index": sec_num,
                "section_title": sec_title,
                "paragraph_start": p_start,
                "paragraph_end": p_end,
                "text": sec_text,
                "char_count": len(sec_text),
                "is_empty": False,
                "has_images": False,
                "paragraphs": [
                    {
                        "paragraph_index": p["paragraph_index"],
                        "text": p["text"],
                        "is_heading": p["is_heading"],
                        "heading_level": p["heading_level"],
                    }
                    for p in current_paras
                ],
            })
            current_paras = []
            current_chars = 0

        for p in paragraphs:
            if p["is_heading"]:
                headings.append({
                    "level": p["heading_level"] or 1,
                    "text": p["text"],
                    "paragraph_index": p["paragraph_index"],
                })
                # Start new section at level 1/2 headings if current buffer already has body text
                if (p["heading_level"] or 1) <= 2 and current_chars >= 200:
                    flush_section()
                    current_title = p["text"][:120]
                elif not current_paras:
                    current_title = p["text"][:120]
            elif current_chars >= MAX_SECTION_CHARS:
                flush_section()
                current_title = None

            current_paras.append(p)
            current_chars += len(p["text"])

        flush_section()

        total_chars = sum(s["char_count"] for s in sections)
        detected_title = raw_title
        if not detected_title:
            if headings:
                detected_title = headings[0]["text"][:200]
            elif paragraphs:
                first_line = paragraphs[0]["text"].splitlines()[0].strip()
                if len(first_line) <= 140:
                    detected_title = first_line

        full_text = "\n\n".join(s["text"] for s in sections)
        doc_metadata = {
            "title": detected_title,
            "chapter_name": None,
            "chapter_number": None,
            "subject": raw_subject,
            "author": raw_author,
            "opening_snippet": full_text[:400].strip(),
            "headings": [h["text"] for h in headings[:25]],
            "total_paragraphs": len(paragraphs),
            "total_sections": len(sections),
            "file_format": file_format,
            "citation_unit": "section",
        }

        return {
            "total_pages": len(sections),
            "extracted_pages": len(sections),
            "total_characters": total_chars,
            "is_scanned": total_chars == 0,
            "file_format": file_format,
            "citation_unit": "section",
            "pages": sections,
            "headings": headings,
            "metadata": {
                "title": detected_title or "",
                "author": raw_author or "",
                "subject": raw_subject or "",
            },
            "document_metadata": doc_metadata,
        }


document_extractor = DocumentExtractorService()
