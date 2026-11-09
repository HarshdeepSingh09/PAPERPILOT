from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DocumentBase(BaseModel):
    original_filename: str


class DocumentCreate(DocumentBase):
    pass


class DocumentResponse(DocumentBase):
    id: str
    filename: str
    file_size_bytes: int
    total_pages: int
    extracted_pages: int = 0
    total_characters: int = 0
    total_chunks: int = 0
    status: str
    embedding_status: Optional[str] = "pending"
    embedding_model: Optional[str] = None
    title: Optional[str] = None
    chapter_name: Optional[str] = None
    chapter_number: Optional[str] = None
    subject: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChunkResponse(BaseModel):
    id: str
    chunk_index: int
    char_count: int
    page_start: int
    page_end: int
    pages: List[int]
    content: str
    embedding_dimension: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentChunksListResponse(BaseModel):
    document_id: str
    total_chunks: int
    chunks: List[ChunkResponse]


class DocumentStatsResponse(BaseModel):
    document_id: str
    original_filename: str
    total_pages: int
    extracted_pages: int
    total_characters: int
    total_chunks: int
    status: str
    embedding_status: Optional[str] = "pending"
    embedding_model: Optional[str] = None
    title: Optional[str] = None
    chapter_name: Optional[str] = None
    chapter_number: Optional[str] = None
    subject: Optional[str] = None
    error_message: Optional[str] = None
    average_chunk_size: float = 0.0
    page_breakdown: Optional[List[Dict[str, Any]]] = None


class DocumentEmbeddingStatusResponse(BaseModel):
    document_id: str
    embedding_status: str
    embedding_model: Optional[str] = None
    total_chunks: int
    embedded_chunks: int
    dimension: Optional[int] = None
    sample_vector_preview: Optional[List[float]] = None
    error_message: Optional[str] = None


class DocumentIndexResponse(BaseModel):
    document_id: str
    collection_name: str
    indexed_vectors: int
    total_chunks: int
    status: str
    message: str


class DocumentIndexStatusResponse(BaseModel):
    document_id: str
    collection_name: str
    indexed_vectors: int
    total_chunks: int
    is_indexed: bool
    status: str  # "indexed", "partial", "not_indexed"


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Natural-language search query")
    top_k: int = Field(default=4, ge=1, le=20, description="Number of relevant chunks to retrieve")


class SearchResultItem(BaseModel):
    chunk_id: str
    chunk_index: int
    content: str
    page_start: int
    page_end: int
    pages: List[int]
    distance: float
    similarity_score: float


class SearchResponse(BaseModel):
    document_id: str
    query: str
    total_results: int
    results: List[SearchResultItem]

