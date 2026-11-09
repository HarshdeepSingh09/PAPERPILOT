import os
import json
import uuid
import logging
from typing import List, Optional
import pymupdf
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db, SessionLocal
from app.db.models import Document, DocumentChunk
from app.schemas.document import (
    DocumentResponse,
    DocumentStatsResponse,
    DocumentChunksListResponse,
    DocumentEmbeddingStatusResponse,
    DocumentIndexResponse,
    DocumentIndexStatusResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    ChunkResponse
)
from app.services.pdf_service import (
    pdf_service,
    PasswordProtectedPDFError,
    CorruptedPDFError,
    PDFExtractionError
)
from app.services.chunking_service import default_chunker, TextChunk
from app.services.embedding_service import (
    embedding_service,
    MissingAPIKeyError,
    InvalidAPIKeyError,
    RateLimitExceededError,
    EmbeddingServiceError
)
from app.services.vector_store import (
    vector_store_service,
    VectorStoreError,
    DocumentNotFoundError,
    DocumentNotIndexedError,
    UnembeddedChunksError
)
from app.schemas.chat import (
    DocumentChatRequest,
    ChatResponse,
    MessageHistoryItem,
    ClearHistoryResponse
)
from app.services.rag_service import (
    rag_service,
    RAGServiceError,
    DocumentNotFoundError as RAGDocNotFoundError,
    DocumentNotReadyError,
    RAGGenerationError
)

logger = logging.getLogger(__name__)

router = APIRouter()


def execute_extraction_and_chunking(doc: Document, db: Session, next_status: str = "ready") -> Document:
    """
    Extracts text, cleans it, checks for scanned/image-only PDFs, generates chunks,
    and updates database records idempotently (clearing any existing chunks).
    """
    # 1. Clean existing chunks to prevent duplicates
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()

    # 2. Extract and inspect text
    extraction = pdf_service.inspect_and_extract(doc.file_path)

    doc.total_pages = extraction["total_pages"]
    doc.extracted_pages = extraction["extracted_pages"]
    doc.total_characters = extraction["total_characters"]

    doc_struct = extraction.get("document_metadata", {})
    doc.title = doc_struct.get("title")
    doc.chapter_name = doc_struct.get("chapter_name")
    doc.chapter_number = doc_struct.get("chapter_number")
    doc.subject = doc_struct.get("subject")
    doc.doc_metadata_json = json.dumps(doc_struct) if doc_struct else None

    # 3. Check for scanned / image-only PDFs
    if extraction["is_scanned"]:
        doc.status = "ocr_required"
        doc.error_message = (
            "No extractable text found. The document appears to be a scanned image or empty. "
            "OCR is not yet supported."
        )
        doc.total_chunks = 0
        doc.embedding_status = "failed"
        db.commit()
        db.refresh(doc)
        return doc

    # 4. Chunk document content
    chunks: List[TextChunk] = default_chunker.chunk_document(doc.id, extraction["pages"])

    # 5. Persist chunk records
    db_chunks = []
    for c in chunks:
        db_chunk = DocumentChunk(
            id=c.id,
            document_id=doc.id,
            chunk_index=c.chunk_index,
            content=c.content,
            char_count=c.char_count,
            page_start=c.page_start,
            page_end=c.page_end,
            pages_json=json.dumps(c.pages),
        )
        db_chunks.append(db_chunk)

    if db_chunks:
        db.bulk_save_objects(db_chunks)

    doc.total_chunks = len(chunks)
    doc.status = next_status
    doc.embedding_status = "pending"
    doc.error_message = None

    db.commit()
    db.refresh(doc)
    return doc


def process_document_pipeline(document_id: str, db: Optional[Session] = None) -> Optional[Document]:
    """
    Complete automatic document processing pipeline:
    1. Extract text and create page-aware chunks (status: extracting)
    2. Extract document metadata (title, chapter name, chapter number, subject)
    3. Generate Gemini embeddings for all chunks (status: embedding)
    4. Index vectors with metadata into ChromaDB (status: indexing)
    5. Mark document as ready for chat (status: ready)

    If any step fails, catches error and records status: failed with error_message.
    """
    owns_session = False
    if db is None:
        db = SessionLocal()
        owns_session = True

    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"Cannot process non-existent document {document_id}")
            return None

        # Step 1: Extraction & Metadata & Chunking
        logger.info(f"Pipeline [1/3]: Extracting text and metadata for '{doc.original_filename}' ({doc.id})...")
        doc.status = "extracting"
        doc.error_message = None
        db.commit()
        db.refresh(doc)

        execute_extraction_and_chunking(doc, db, next_status="embedding")

        # If scanned / OCR required, stop pipeline gracefully
        if doc.status == "ocr_required":
            logger.warning(f"Pipeline stopped for '{doc.original_filename}' ({doc.id}): Scanned PDF (OCR required).")
            return doc

        # Step 2: Gemini Embeddings
        logger.info(f"Pipeline [2/3]: Generating Gemini embeddings for {doc.total_chunks} chunks ({doc.id})...")
        doc.status = "embedding"
        db.commit()
        db.refresh(doc)

        embed_result = embedding_service.embed_document_chunks(document_id=doc.id, db=db, force=False)
        if doc.embedding_status == "failed" or embed_result.status == "failed":
            raise EmbeddingServiceError(embed_result.error_message or "Failed to generate chunk embeddings")

        # Step 3: ChromaDB Vector Indexing
        logger.info(f"Pipeline [3/3]: Indexing vectors into ChromaDB for '{doc.original_filename}' ({doc.id})...")
        doc.status = "indexing"
        db.commit()
        db.refresh(doc)

        vector_store_service.index_document_chunks(document_id=doc.id, db=db, force=False)

        # Step 4: Ready
        doc.status = "ready"
        doc.error_message = None
        db.commit()
        db.refresh(doc)
        logger.info(f"Pipeline complete: '{doc.original_filename}' ({doc.id}) is now READY for chat.")
        return doc

    except Exception as e:
        logger.exception(f"Pipeline failed for document {document_id}: {e}")
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.status = "failed"
                doc.error_message = f"Automatic processing failed: {str(e)}"
                db.commit()
                db.refresh(doc)
        except Exception:
            pass
        if not owns_session:
            raise
        return None
    finally:
        if owns_session:
            db.close()


def ensure_document_metadata(doc: Document, db: Session) -> Document:
    """
    Backfills document title and chapter metadata if not yet extracted.
    """
    if doc.title is None and doc.file_path and os.path.exists(doc.file_path) and doc.status != "ocr_required":
        try:
            extraction = pdf_service.inspect_and_extract(doc.file_path)
            doc_struct = extraction.get("document_metadata", {})
            if doc_struct:
                doc.title = doc_struct.get("title")
                doc.chapter_name = doc_struct.get("chapter_name")
                doc.chapter_number = doc_struct.get("chapter_number")
                doc.subject = doc_struct.get("subject")
                doc.doc_metadata_json = json.dumps(doc_struct)
                db.commit()
                db.refresh(doc)
        except Exception:
            pass
    return doc


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    background: bool = Query(True, description="Whether to run pipeline in background or synchronously"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Upload a PDF document and immediately execute the automatic processing pipeline:
    extract text, clean, chunk, extract metadata, generate Gemini embeddings,
    and index vectors into ChromaDB.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF documents are supported."
        )

    doc_id = str(uuid.uuid4())
    stored_filename = f"{doc_id}.pdf"
    file_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, stored_filename))

    # Save uploaded file to disk
    file_size = 0
    with open(file_path, "wb") as buffer:
        while content := await file.read(1024 * 1024):  # 1MB chunks
            file_size += len(content)
            buffer.write(content)

    # Validate PDF structure and encryption upfront
    try:
        check_doc = pymupdf.open(file_path)
        if check_doc.is_encrypted:
            check_doc.close()
            if os.path.exists(file_path):
                os.remove(file_path)
            raise PasswordProtectedPDFError("The PDF document is password-protected. Please upload an unprotected PDF.")
        check_doc.close()
    except PasswordProtectedPDFError as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The uploaded file is corrupted or not a valid PDF: {str(e)}"
        )

    # Initial Document record in 'uploaded' status
    new_doc = Document(
        id=doc_id,
        filename=stored_filename,
        original_filename=file.filename,
        file_path=file_path,
        file_size_bytes=file_size,
        total_pages=0,
        status="uploaded",
        embedding_status="pending"
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    if background and background_tasks is not None:
        background_tasks.add_task(process_document_pipeline, doc_id)
        return new_doc
    else:
        processed_doc = process_document_pipeline(doc_id, db=db)
        return processed_doc or new_doc


@router.get("", response_model=List[DocumentResponse])
def list_documents(db: Session = Depends(get_db)):
    """
    List all uploaded documents ordered by creation time descending.
    """
    return db.query(Document).order_by(Document.created_at.desc()).all()


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)):
    """
    Retrieve document details, extraction status, and chunk counts by ID.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    ensure_document_metadata(doc, db)
    return doc


@router.get("/{document_id}/stats", response_model=DocumentStatsResponse)
def get_document_stats(document_id: str, db: Session = Depends(get_db)):
    """
    Retrieve detailed extraction statistics and page analysis for a document.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    ensure_document_metadata(doc, db)

    avg_chunk_size = 0.0
    if doc.total_chunks > 0 and doc.total_characters > 0:
        avg_chunk_size = round(doc.total_characters / doc.total_chunks, 1)

    # Optional detailed page char count inspection
    page_breakdown = None
    if os.path.exists(doc.file_path) and doc.status != "failed":
        try:
            extraction = pdf_service.inspect_and_extract(doc.file_path)
            page_breakdown = [
                {
                    "page": p["page"],
                    "char_count": p["char_count"],
                    "is_empty": p["is_empty"],
                    "has_images": p["has_images"]
                }
                for p in extraction["pages"]
            ]
        except Exception:
            page_breakdown = None

    return DocumentStatsResponse(
        document_id=doc.id,
        original_filename=doc.original_filename,
        total_pages=doc.total_pages,
        extracted_pages=doc.extracted_pages,
        total_characters=doc.total_characters,
        total_chunks=doc.total_chunks,
        status=doc.status,
        embedding_status=doc.embedding_status,
        embedding_model=doc.embedding_model,
        title=doc.title,
        chapter_name=doc.chapter_name,
        chapter_number=doc.chapter_number,
        subject=doc.subject,
        error_message=doc.error_message,
        average_chunk_size=avg_chunk_size,
        page_breakdown=page_breakdown
    )



@router.get("/{document_id}/chunks", response_model=DocumentChunksListResponse)
def get_document_chunks(
    document_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Inspect chunk metadata, page ranges, and content for debugging and verification.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    total_chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).count()
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    chunk_responses = [
        ChunkResponse(
            id=c.id,
            chunk_index=c.chunk_index,
            char_count=c.char_count,
            page_start=c.page_start,
            page_end=c.page_end,
            pages=c.pages,
            content=c.content,
            embedding_dimension=c.embedding_dimension,
            created_at=c.created_at
        )
        for c in chunks
    ]

    return DocumentChunksListResponse(
        document_id=document_id,
        total_chunks=total_chunks,
        chunks=chunk_responses
    )


@router.post("/{document_id}/embed", response_model=DocumentEmbeddingStatusResponse)
def generate_document_embeddings(
    document_id: str,
    force: bool = Query(False, description="Whether to regenerate embeddings if they already exist"),
    db: Session = Depends(get_db)
):
    """
    Generate Gemini semantic embeddings for all document chunks.
    Avoids regenerating if valid embeddings already exist unless force=True.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if doc.status == "ocr_required":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate embeddings for an image-only document. Text extraction must succeed first."
        )

    try:
        result = embedding_service.embed_document_chunks(document_id=doc.id, db=db, force=force)
        sample_preview = None
        if result.chunks and result.chunks[0].embedding:
            sample_preview = result.chunks[0].embedding[:5]

        return DocumentEmbeddingStatusResponse(
            document_id=doc.id,
            embedding_status=doc.embedding_status,
            embedding_model=doc.embedding_model,
            total_chunks=result.total_chunks,
            embedded_chunks=result.embedded_chunks,
            dimension=result.dimension,
            sample_vector_preview=sample_preview,
            error_message=result.error_message
        )
    except MissingAPIKeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except InvalidAPIKeyError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )
    except EmbeddingServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during embedding generation: {str(e)}"
        )


@router.get("/{document_id}/embeddings", response_model=DocumentEmbeddingStatusResponse)
def get_document_embedding_status(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieve embedding status, model name, and dimensions for a document.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )

    embedded_chunks = [c for c in chunks if c.embedding_json is not None]
    dimension = embedded_chunks[0].embedding_dimension if embedded_chunks else None
    sample_preview = None
    if embedded_chunks and embedded_chunks[0].embedding:
        sample_preview = embedded_chunks[0].embedding[:5]

    return DocumentEmbeddingStatusResponse(
        document_id=doc.id,
        embedding_status=doc.embedding_status or "pending",
        embedding_model=doc.embedding_model,
        total_chunks=len(chunks),
        embedded_chunks=len(embedded_chunks),
        dimension=dimension,
        sample_vector_preview=sample_preview,
        error_message=doc.error_message if doc.embedding_status == "failed" else None
    )


@router.post("/{document_id}/reprocess", response_model=DocumentResponse)
def reprocess_document(
    document_id: str,
    background: bool = Query(True, description="Whether to run pipeline in background"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Re-runs the complete automatic processing pipeline on an existing document.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF file not found on disk")

    doc.status = "uploaded"
    doc.error_message = None
    db.commit()
    db.refresh(doc)

    if background and background_tasks is not None:
        background_tasks.add_task(process_document_pipeline, doc.id)
        return doc
    else:
        processed = process_document_pipeline(doc.id, db=db)
        return processed or doc


@router.get("/{document_id}/file")
def get_document_file(document_id: str, db: Session = Depends(get_db)):
    """
    Stream the raw PDF file for rendering in the frontend PDF viewer with inline disposition.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    file_path = doc.file_path
    if not os.path.isabs(file_path):
        file_path = os.path.abspath(os.path.join(settings.UPLOAD_DIR, doc.filename))

    if not os.path.exists(file_path):
        fallback = os.path.abspath(os.path.join(settings.UPLOAD_DIR, doc.filename))
        if os.path.exists(fallback):
            file_path = fallback
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF file not found on disk")

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=doc.original_filename,
        content_disposition_type="inline",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{doc.original_filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition, Content-Range, Accept-Ranges"
        }
    )


@router.post("/{document_id}/index", response_model=DocumentIndexResponse)
def index_document_vectors(
    document_id: str,
    force: bool = Query(False, description="Whether to force re-indexing even if already indexed"),
    db: Session = Depends(get_db)
):
    """
    Ingest existing embeddings from SQLite for the given document into ChromaDB.
    Avoids regenerating embeddings and guarantees zero duplicate vectors.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        result = vector_store_service.index_document_chunks(document_id=doc.id, db=db, force=force)
        return DocumentIndexResponse(**result)
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnembeddedChunksError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except VectorStoreError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during vector indexing: {str(e)}"
        )


@router.get("/{document_id}/index-status", response_model=DocumentIndexStatusResponse)
def get_document_index_status(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    Inspect ChromaDB vector indexing status, vector counts, and collection details for a document.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        status_info = vector_store_service.get_indexing_status(document_id=doc.id, db=db)
        return DocumentIndexStatusResponse(**status_info)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking indexing status: {str(e)}"
        )


@router.post("/{document_id}/search", response_model=SearchResponse)
def search_document_chunks(
    document_id: str,
    request: SearchRequest,
    db: Session = Depends(get_db)
):
    """
    Perform semantic similarity search on a document's chunks using ChromaDB.
    Generates a query embedding, queries ChromaDB, and returns ranked chunks with page citations.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if doc.status != "ready":
        if doc.status == "ocr_required":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This document contains scanned images without extractable text. OCR is not yet supported.")
        if doc.status == "failed":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Document processing previously failed: {doc.error_message}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Document is currently '{doc.status}'. Search will be available once processing completes.")

    try:
        results = vector_store_service.search_document(
            document_id=doc.id,
            query=request.query,
            top_k=request.top_k,
            db=db
        )
        return SearchResponse(
            document_id=doc.id,
            query=request.query,
            total_results=len(results),
            results=[SearchResultItem(**r) for r in results]
        )
    except DocumentNotIndexedError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except MissingAPIKeyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InvalidAPIKeyError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except RateLimitExceededError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except EmbeddingServiceError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error performing semantic search: {str(e)}"
        )


@router.post("/{document_id}/chat", response_model=ChatResponse)
def chat_with_document(
    document_id: str,
    request: DocumentChatRequest,
    db: Session = Depends(get_db)
):
    """
    Perform grounded Retrieval-Augmented Generation (RAG) chat against a document.
    Retrieves semantic excerpts, generates answers with Gemini, persists conversation,
    and returns verified page citations.
    """
    try:
        result = rag_service.answer_document_query(
            document_id=document_id,
            query=request.message,
            db=db,
            top_k=request.top_k
        )
        return ChatResponse(**result)
    except (DocumentNotFoundError, RAGDocNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DocumentNotReadyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except MissingAPIKeyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InvalidAPIKeyError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except RateLimitExceededError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except (EmbeddingServiceError, RAGGenerationError) as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while answering document chat query: {str(e)}"
        )


@router.get("/{document_id}/chat/history", response_model=List[MessageHistoryItem])
def get_document_chat_history(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieve all conversation messages and citations for a document in chronological order.
    """
    try:
        history = rag_service.get_history(document_id=document_id, db=db)
        return [MessageHistoryItem(**item) for item in history]
    except (DocumentNotFoundError, RAGDocNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve chat history: {str(e)}"
        )


@router.delete("/{document_id}/chat/history", response_model=ClearHistoryResponse)
def clear_document_chat_history(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    Delete all conversation messages for a document.
    """
    try:
        deleted = rag_service.clear_history(document_id=document_id, db=db)
        return ClearHistoryResponse(
            document_id=document_id,
            deleted_count=deleted,
            message=f"Successfully cleared {deleted} message(s) for document."
        )
    except (DocumentNotFoundError, RAGDocNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear chat history: {str(e)}"
        )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, db: Session = Depends(get_db)):
    """
    Delete a document, its stored PDF file, its chunks (cascade), and ChromaDB vectors.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Clean up vectors from ChromaDB
    try:
        vector_store_service.delete_document_vectors(document_id)
    except Exception:
        pass

    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError:
            pass

    db.delete(doc)
    db.commit()
    return None
