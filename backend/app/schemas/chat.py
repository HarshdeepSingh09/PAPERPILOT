from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class Citation(BaseModel):
    page: int = Field(..., description="1-indexed PDF page number or DOCX/TXT section number")
    snippet: Optional[str] = Field(None, description="Concise text snippet from the cited location")
    chunk_index: Optional[int] = Field(None, description="Source chunk index")
    label: Optional[str] = Field(None, description="Human-readable citation label (e.g. Page 6 or Section 2)")
    source_type: Optional[str] = Field(None, description="'page' for PDF or 'section' for DOCX/TXT")
    section_title: Optional[str] = Field(None, description="Section heading for DOCX/TXT citations")


class DocumentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User question about the document")
    top_k: int = Field(default=4, ge=1, le=10, description="Number of context chunks to retrieve")


class ChatRequest(BaseModel):
    document_id: Optional[str] = Field(None, description="ID of the document to query")
    message: str = Field(..., min_length=1, max_length=2000, description="User question about the document")
    top_k: int = Field(default=4, ge=1, le=10, description="Number of context chunks to retrieve")


class ChatResponse(BaseModel):
    message_id: str
    document_id: str
    role: str = "assistant"
    content: str
    citations: List[Citation] = []
    created_at: datetime


class MessageHistoryItem(BaseModel):
    id: str
    document_id: str
    role: str
    content: str
    citations: List[Citation] = []
    page_references: Optional[List[int]] = []
    created_at: datetime

    class Config:
        from_attributes = True


class ClearHistoryResponse(BaseModel):
    document_id: str
    deleted_count: int
    message: str
