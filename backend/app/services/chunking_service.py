import re
import uuid
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class SentenceUnit:
    """Represents a discrete sentence or text block associated with its source page or section."""
    text: str
    page: int
    section_title: Optional[str] = None
    paragraph_range: Optional[str] = None


@dataclass
class TextChunk:
    """Represents a bounded, overlapping chunk of text with complete page/section range metadata."""
    id: str
    document_id: str
    chunk_index: int
    content: str
    char_count: int
    page_start: int
    page_end: int
    pages: List[int]
    section_title: Optional[str] = None
    paragraph_range: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "char_count": self.char_count,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "pages": self.pages,
            "section_title": self.section_title,
            "paragraph_range": self.paragraph_range,
        }


class IntelligentChunker:
    """
    Divides cleaned multi-page document text into meaningful, overlapping chunks.
    Preserves sentence integrity and accurate multi-page citation ranges.
    """

    # Sentence boundary regex (matches terminal punctuation followed by space and capital/symbol)
    _SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'\(\[])")

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be strictly less than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_into_sentence_units(self, pages_data: List[Dict[str, Any]]) -> List[SentenceUnit]:
        """
        Decomposes page text into ordered sentence units tagged with their 1-indexed page number.
        """
        units: List[SentenceUnit] = []

        for page_item in pages_data:
            page_num = page_item.get("page", 1)
            section_title = page_item.get("section_title")
            p_start = page_item.get("paragraph_start")
            p_end = page_item.get("paragraph_end")
            para_range = f"{p_start}-{p_end}" if p_start is not None and p_end is not None else None
            raw_text = page_item.get("text", "").strip()
            if not raw_text:
                continue

            # Split text by paragraph first
            paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]

            for para in paragraphs:
                # Split paragraph into sentences
                sentences = self._SENTENCE_BOUNDARY.split(para)

                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue

                    # If a single sentence is unusually long (> chunk_size), break it on clause boundaries
                    if len(sent) > self.chunk_size:
                        sub_parts = self._split_long_sentence(sent, max_len=self.chunk_size)
                        for part in sub_parts:
                            if part.strip():
                                units.append(SentenceUnit(
                                    text=part.strip(),
                                    page=page_num,
                                    section_title=section_title,
                                    paragraph_range=para_range,
                                ))
                    else:
                        units.append(SentenceUnit(
                            text=sent,
                            page=page_num,
                            section_title=section_title,
                            paragraph_range=para_range,
                        ))

        return units

    def _split_long_sentence(self, text: str, max_len: int) -> List[str]:
        """
        Splits an oversized sentence at clause punctuation (; , : - space) to fit within max_len.
        """
        parts = []
        remaining = text

        while len(remaining) > max_len:
            # Look for split points (; , : \n space) within the first max_len characters
            split_idx = -1
            for sep in ["; ", ", ", ": ", " - ", "\n", " "]:
                idx = remaining[:max_len].rfind(sep)
                if idx > int(max_len * 0.4):  # Ensure reasonable split progress
                    split_idx = idx + len(sep)
                    break

            if split_idx == -1:
                # Hard fallback to max_len boundary if no whitespace/punctuation exists
                split_idx = max_len

            parts.append(remaining[:split_idx].strip())
            remaining = remaining[split_idx:].strip()

        if remaining:
            parts.append(remaining)

        return parts

    def chunk_document(self, document_id: str, pages_data: List[Dict[str, Any]]) -> List[TextChunk]:
        """
        Chunks a document's pages into overlapping text chunks.
        Tracks source page start, page end, and list of contributing pages.
        """
        sentence_units = self.split_into_sentence_units(pages_data)
        if not sentence_units:
            return []

        chunks: List[TextChunk] = []
        start_idx = 0
        chunk_index = 0
        total_units = len(sentence_units)

        while start_idx < total_units:
            current_units: List[SentenceUnit] = []
            current_len = 0
            idx = start_idx

            while idx < total_units:
                unit = sentence_units[idx]
                unit_len = len(unit.text)
                separator_len = 1 if current_units else 0

                if not current_units:
                    current_units.append(unit)
                    current_len = unit_len
                    idx += 1
                elif current_len + separator_len + unit_len <= self.chunk_size:
                    current_units.append(unit)
                    current_len += separator_len + unit_len
                    idx += 1
                else:
                    # Allow slight overflow (up to 15%) if chunk is currently underfilled (< 70% target)
                    if current_len < int(self.chunk_size * 0.70) and (current_len + separator_len + unit_len) <= int(self.chunk_size * 1.15):
                        current_units.append(unit)
                        current_len += separator_len + unit_len
                        idx += 1
                    break

            if not current_units:
                break

            # Synthesize chunk content
            chunk_content = " ".join(u.text for u in current_units)
            contributing_pages = sorted(list(set(u.page for u in current_units)))
            page_start = contributing_pages[0]
            page_end = contributing_pages[-1]
            sec_titles = [u.section_title for u in current_units if u.section_title]
            primary_section = sec_titles[0] if sec_titles else None
            para_ranges = [u.paragraph_range for u in current_units if u.paragraph_range]
            primary_para_range = para_ranges[0] if para_ranges else None

            chunk_id = str(uuid.uuid4())
            chunks.append(
                TextChunk(
                    id=chunk_id,
                    document_id=document_id,
                    chunk_index=chunk_index,
                    content=chunk_content,
                    char_count=len(chunk_content),
                    page_start=page_start,
                    page_end=page_end,
                    pages=contributing_pages,
                    section_title=primary_section,
                    paragraph_range=primary_para_range,
                )
            )
            chunk_index += 1

            # Termination check
            if idx >= total_units:
                break

            # Calculate next start index based on chunk_overlap
            overlap_accum = 0
            next_start = idx

            for back_i in range(idx - 1, start_idx, -1):
                overlap_accum += len(sentence_units[back_i].text) + 1
                next_start = back_i
                if overlap_accum >= self.chunk_overlap:
                    break

            # Strictly enforce forward progress to prevent infinite loops
            if next_start <= start_idx:
                next_start = start_idx + 1

            start_idx = next_start

        return chunks


# Default singleton instance configured with 1000 char size and 200 char overlap
default_chunker = IntelligentChunker(chunk_size=1000, chunk_overlap=200)
