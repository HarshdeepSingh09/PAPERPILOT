import datetime
import json
from typing import List, Optional, Dict, Any
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Float, Boolean
from sqlalchemy.orm import relationship
from app.db.session import Base


class Document(Base):
    """
    Represents an uploaded PDF document and its extraction/processing status.
    """
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer, default=0)
    total_pages = Column(Integer, default=0)
    extracted_pages = Column(Integer, default=0)
    total_characters = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    status = Column(String(50), default="ready")  # ready, ocr_required, processing, failed
    embedding_status = Column(String(50), default="pending")  # pending, processing, completed, failed
    embedding_model = Column(String(100), nullable=True)
    title = Column(String(255), nullable=True)
    chapter_name = Column(String(255), nullable=True)
    chapter_number = Column(String(50), nullable=True)
    subject = Column(String(100), nullable=True)
    doc_metadata_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    chat_messages = relationship("ChatMessage", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan", order_by="DocumentChunk.chunk_index")

    @property
    def doc_metadata(self) -> dict:
        if not self.doc_metadata_json:
            return {}
        try:
            return json.loads(self.doc_metadata_json)
        except Exception:
            return {}


class DocumentChunk(Base):
    """
    Represents an extracted, normalized, bounded text chunk with source page range metadata.
    """
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False, index=True)
    content = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    pages_json = Column(Text, nullable=False)  # JSON-encoded array of contributing page numbers, e.g. "[1, 2]"
    embedding_json = Column(Text, nullable=True)  # JSON-encoded vector embedding, e.g. "[0.012, -0.045, ...]"
    embedding_dimension = Column(Integer, nullable=True)  # Vector length, e.g. 768
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationship
    document = relationship("Document", back_populates="chunks")

    @property
    def pages(self) -> List[int]:
        try:
            return json.loads(self.pages_json)
        except Exception:
            return [self.page_start]

    @property
    def embedding(self) -> Optional[List[float]]:
        if self.embedding_json:
            try:
                return json.loads(self.embedding_json)
            except Exception:
                return None
        return None


class ChatMessage(Base):
    """
    Represents conversation history linked to a specific document.
    """
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    page_references = Column(Text, nullable=True)  # JSON-encoded array of referenced pages, e.g. "[1, 3]"
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationship
    document = relationship("Document", back_populates="chat_messages")

    @property
    def citations(self) -> List[Dict[str, Any]]:
        if not self.page_references:
            return []
        try:
            parsed = json.loads(self.page_references)
            if isinstance(parsed, list):
                res = []
                for item in parsed:
                    if isinstance(item, dict) and "page" in item:
                        res.append(item)
                    elif isinstance(item, int):
                        res.append({"page": item, "snippet": None, "chunk_index": None})
                return res
        except Exception:
            pass
        return []


class DocumentSummary(Base):
    """
    Stores an AI-generated, structured multi-section document summary.
    """
    __tablename__ = "document_summaries"

    id = Column(String(36), primary_key=True, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    executive_overview = Column(Text, nullable=False)
    key_takeaways_json = Column(Text, nullable=False)  # JSON List[str]
    important_concepts_json = Column(Text, nullable=False)  # JSON List[{term, definition, source_page}]
    formulas_equations_json = Column(Text, nullable=False)  # JSON List[{name, equation_latex, explanation, source_page}]
    chapter_summaries_json = Column(Text, nullable=False)  # JSON List[{chapter_title, summary, key_points, source_page}]
    important_facts_json = Column(Text, nullable=False)  # JSON List[{fact, category, source_page}]
    page_references_json = Column(Text, nullable=False)  # JSON List[{page, topic, snippet}]
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))

    document = relationship("Document", backref="summary")


class Quiz(Base):
    """
    Stores an interactive document assessment, question bank, and user performance attempt.
    """
    __tablename__ = "quizzes"

    id = Column(String(36), primary_key=True, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    difficulty = Column(String(50), default="medium")  # easy, medium, hard, mixed
    question_count = Column(Integer, default=5)
    score = Column(Integer, nullable=True)
    total_questions = Column(Integer, default=5)
    percentage = Column(Float, nullable=True)
    completed = Column(Boolean, default=False)
    # Full questions array with options, correct answer, explanation, source page, user answer
    questions_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    document = relationship("Document", backref="quizzes")


class RevisionNote(Base):
    """
    Stores structured 8-section revision notes designed for exam review.
    """
    __tablename__ = "revision_notes"

    id = Column(String(36), primary_key=True, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    chapter_overview = Column(Text, nullable=False)
    definitions_json = Column(Text, nullable=False)  # JSON List[{term, definition, source_page}]
    key_concepts_json = Column(Text, nullable=False)  # JSON List[{concept, summary, key_points, source_page}]
    reactions_equations_json = Column(Text, nullable=False)  # JSON List[{reaction_type, equation_latex, description, source_page}]
    formulas_json = Column(Text, nullable=False)  # JSON List[{formula_name, formula_latex, usage, source_page}]
    differences_comparisons_json = Column(Text, nullable=False)  # JSON List[{topic, aspect_a, aspect_b, comparison_points: [{parameter, item_a, item_b}], source_page}]
    faqs_json = Column(Text, nullable=False)  # JSON List[{question, answer, source_page}]
    last_minute_points_json = Column(Text, nullable=False)  # JSON List[{point, source_page}]
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))

    document = relationship("Document", backref="revision_notes")

