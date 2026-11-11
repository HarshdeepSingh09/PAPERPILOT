import os
import re
import json
import uuid
import shutil
import logging
from typing import List, Optional
import pymupdf
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_owned_document
from app.db.session import get_db, SessionLocal
from app.db.models import Document, DocumentChunk, User
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
    ChunkResponse,
    DocumentContentResponse,
    DocumentContentSection,
)
from app.schemas.insights import CategoryUpdateRequest
from app.services.pdf_service import (
    pdf_service,
    PasswordProtectedPDFError,
    CorruptedPDFError,
    PDFExtractionError
)
from app.services.document_extractor import (
    document_extractor,
    DocumentValidationError,
)
from app.services.classification_service import (
    classification_service,
    DOCUMENT_CATEGORIES,
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


def _sanitize_storage_filename(raw_name: Optional[str], file_format: str) -> str:
    """Normalizes a user-supplied filename into a safe single path component."""
    base = os.path.basename((raw_name or "").replace("\\", "/")).strip()
    safe = re.sub(r"[^A-Za-z0-9._\-]+", "_", base).strip("._")
    if not safe:
        safe = f"document.{file_format}"
    elif not safe.lower().endswith(f".{file_format}"):
        safe = f"{safe}.{file_format}"
    return safe[:160]


def _build_user_document_storage_path(
    user_id: str,
    doc_id: str,
    original_filename: Optional[str],
    file_format: str,
) -> tuple[str, str]:
    """
    Constructs isolated per-user, per-document storage paths:
    storage/uploads/{user_id}/{document_id}/{safe_original_filename}
    Validates strict containment inside settings.UPLOAD_DIR.
    """
    upload_root = os.path.abspath(settings.UPLOAD_DIR)
    safe_user = re.sub(r"[^A-Za-z0-9\-_]", "", str(user_id))
    safe_doc = re.sub(r"[^A-Za-z0-9\-_]", "", str(doc_id))
    if not safe_user or not safe_doc:
        raise ValueError("Invalid user or document storage identifier.")

    safe_filename = _sanitize_storage_filename(original_filename, file_format)
    doc_dir = os.path.abspath(os.path.join(upload_root, safe_user, safe_doc))
    full_path = os.path.abspath(os.path.join(doc_dir, safe_filename))

    if os.path.commonpath([upload_root, full_path]) != upload_root:
        raise ValueError("Resolved storage path escapes configured upload root.")

    os.makedirs(doc_dir, exist_ok=True)
    return safe_filename, full_path


def _resolve_safe_document_file_path(doc: Document) -> Optional[str]:
    """
    Resolves a document's path strictly inside UPLOAD_DIR without exposing internal path traversal.
    Supports both isolated per-user paths (storage/uploads/{user_id}/{doc_id}/...) and legacy flat paths.
    """
    upload_root = os.path.abspath(settings.UPLOAD_DIR)
    candidates = []
    if doc.file_path:
        raw_fp = doc.file_path if os.path.isabs(doc.file_path) else os.path.join(upload_root, doc.file_path)
        candidates.append(os.path.abspath(raw_fp))
    if doc.user_id and doc.id and doc.filename:
        candidates.append(os.path.abspath(os.path.join(upload_root, str(doc.user_id), str(doc.id), os.path.basename(doc.filename))))
    if doc.filename:
        candidates.append(os.path.abspath(os.path.join(upload_root, os.path.basename(doc.filename))))

    for cand in candidates:
        try:
            if os.path.commonpath([upload_root, cand]) == upload_root and os.path.isfile(cand):
                return cand
        except ValueError:
            continue
    return None


def execute_extraction_and_chunking(doc: Document, db: Session, next_status: str = "ready") -> Document:
    """
    Extracts text from PDF/DOCX/TXT, cleans it, checks for scanned/image-only PDFs,
    runs intelligent document classification, generates chunks, and updates SQLite idempotently.
    """
    # 1. Clean existing chunks to prevent duplicates
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()

    # 2. Extract and inspect text across supported formats
    doc_format = (getattr(doc, "file_format", None) or os.path.splitext(doc.file_path)[1].lstrip(".") or "pdf").lower()
    extraction = document_extractor.inspect_and_extract(doc.file_path, doc_format)

    doc.file_format = extraction.get("file_format", doc_format)
    doc.total_pages = extraction["total_pages"]
    doc.extracted_pages = extraction["extracted_pages"]
    doc.total_characters = extraction["total_characters"]

    doc_struct = extraction.get("document_metadata", {})
    doc.title = doc_struct.get("title")
    doc.chapter_name = doc_struct.get("chapter_name")
    doc.chapter_number = doc_struct.get("chapter_number")
    doc.subject = doc_struct.get("subject")
    doc.doc_metadata_json = json.dumps(doc_struct) if doc_struct else None

    # 3. Check for scanned / image-only PDFs or empty documents
    if extraction["is_scanned"]:
        if doc.file_format == "pdf":
            doc.status = "ocr_required"
            doc.error_message = (
                "No extractable text found. The document appears to be a scanned image or empty. "
                "OCR is not yet supported."
            )
        else:
            doc.status = "failed"
            doc.error_message = "No readable text could be extracted from the uploaded file."
        doc.total_chunks = 0
        doc.embedding_status = "failed"
        db.commit()
        db.refresh(doc)
        return doc

    # 4. Intelligent classification (skip overwriting if user already manually set category)
    if getattr(doc, "classification_source", None) != "manual":
        sample_parts = [p["text"] for p in extraction["pages"][:6] if p.get("text")]
        if len(extraction["pages"]) > 6:
            sample_parts.append(extraction["pages"][-1].get("text", ""))
        text_sample = "\n\n".join(sample_parts)[:6500]
        raw_headings = [h["text"] for h in extraction.get("headings", []) if isinstance(h, dict) and h.get("text")]
        if not raw_headings and isinstance(doc_struct.get("headings"), list):
            raw_headings = doc_struct.get("headings", [])

        cls_res = classification_service.classify_document(
            text_sample=text_sample,
            doc_metadata=doc_struct,
            headings=raw_headings,
            use_ai=True,
        )
        doc.document_category = cls_res["category"]
        doc.classification_confidence = cls_res["confidence"]
        doc.classification_source = cls_res["source"]
        doc.classification_reason = cls_res["reason"]

    # 5. Chunk document content
    chunks: List[TextChunk] = default_chunker.chunk_document(doc.id, extraction["pages"])

    # 6. Persist chunk records with owner user_id
    db_chunks = []
    for c in chunks:
        db_chunk = DocumentChunk(
            id=c.id,
            document_id=doc.id,
            user_id=doc.user_id,
            chunk_index=c.chunk_index,
            content=c.content,
            char_count=c.char_count,
            page_start=c.page_start,
            page_end=c.page_end,
            pages_json=json.dumps(c.pages),
            section_title=c.section_title,
            paragraph_range=c.paragraph_range,
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

        vector_store_service.index_document_chunks(document_id=doc.id, db=db, force=False, user_id=doc.user_id)

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
    Backfills document metadata if not yet extracted.
    """
    doc_fmt = (getattr(doc, "file_format", None) or "pdf").lower()
    if doc.title is None and doc.file_path and os.path.exists(doc.file_path) and doc.status != "ocr_required":
        try:
            extraction = document_extractor.inspect_and_extract(doc.file_path, doc_fmt)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a PDF, DOCX, or TXT document into the authenticated user's isolated storage directory
    and execute the automatic processing pipeline: extract text, classify category, clean, chunk,
    extract metadata, generate Gemini embeddings, and index vectors into ChromaDB tagged with user_id.
    """
    try:
        file_format = document_extractor.validate_extension_and_mime(
            file.filename or "",
            file.content_type,
        )
    except DocumentValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    doc_id = str(uuid.uuid4())
    try:
        stored_filename, file_path = _build_user_document_storage_path(
            user_id=current_user.id,
            doc_id=doc_id,
            original_filename=file.filename,
            file_format=file_format,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    # Save uploaded file to disk inside user-isolated folder while enforcing size limit
    file_size = 0
    try:
        with open(file_path, "wb") as buffer:
            while content := await file.read(1024 * 1024):  # 1MB chunks
                file_size += len(content)
                if file_size > max_bytes:
                    raise ValueError(
                        f"File exceeds maximum allowed upload limit of {settings.MAX_UPLOAD_SIZE_MB} MB."
                    )
                buffer.write(content)
    except ValueError as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        shutil.rmtree(os.path.dirname(file_path), ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(e),
        )

    # Validate file integrity, non-empty content, and non-encryption upfront
    try:
        document_extractor.validate_saved_file(
            file_path=file_path,
            file_format=file_format,
            file_size=file_size,
            max_size_bytes=max_bytes,
        )
    except DocumentValidationError as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        shutil.rmtree(os.path.dirname(file_path), ignore_errors=True)
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        shutil.rmtree(os.path.dirname(file_path), ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded file could not be validated.",
        )

    # Initial Document record bound strictly to authenticated current_user.id
    new_doc = Document(
        id=doc_id,
        user_id=current_user.id,
        filename=stored_filename,
        original_filename=os.path.basename((file.filename or stored_filename).replace("\\", "/")),
        file_path=file_path,
        file_size_bytes=file_size,
        total_pages=0,
        file_format=file_format,
        document_category="General Document",
        classification_confidence=0.0,
        classification_source="auto",
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


@router.get("/categories", response_model=List[str])
def list_document_categories(current_user: User = Depends(get_current_user)):
    """
    List all supported document categories for classification and manual override.
    """
    return DOCUMENT_CATEGORIES


@router.get("", response_model=List[DocumentResponse])
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all uploaded documents belonging strictly to the authenticated user.
    """
    return (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.patch("/{document_id}/category", response_model=DocumentResponse)
def update_document_category(
    document_id: str,
    payload: CategoryUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Allow users to manually override the detected document category for their own document.
    """
    doc = get_owned_document(document_id, current_user, db)

    if payload.category not in DOCUMENT_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category '{payload.category}'. Allowed: {', '.join(DOCUMENT_CATEGORIES)}"
        )

    doc.document_category = payload.category
    doc.classification_confidence = 1.0
    doc.classification_source = "manual"
    doc.classification_reason = "Manually selected by user"
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/{document_id}/content", response_model=DocumentContentResponse)
def get_document_content(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return structured extracted sections/pages for reading DOCX, TXT, or PDF content in-browser.
    """
    doc = get_owned_document(document_id, current_user, db)

    doc_fmt = (getattr(doc, "file_format", None) or "pdf").lower()
    citation_unit = "page" if doc_fmt == "pdf" else "section"

    if doc.file_path and os.path.exists(doc.file_path) and doc.status not in ("ocr_required", "failed"):
        try:
            extraction = document_extractor.inspect_and_extract(doc.file_path, doc_fmt)
            sections = [
                DocumentContentSection(
                    section_index=int(p.get("section_index") or p.get("page") or idx + 1),
                    section_title=p.get("section_title") or (f"Page {p.get('page', idx + 1)}" if doc_fmt == "pdf" else f"Section {idx + 1}"),
                    paragraph_start=p.get("paragraph_start"),
                    paragraph_end=p.get("paragraph_end"),
                    content=p.get("text") or "",
                    char_count=p.get("char_count") or len(p.get("text") or ""),
                )
                for idx, p in enumerate(extraction.get("pages", []))
                if p.get("text")
            ]
            return DocumentContentResponse(
                document_id=doc.id,
                original_filename=doc.original_filename,
                file_format=doc_fmt,
                citation_unit=citation_unit,
                total_sections=len(sections),
                headings=extraction.get("headings", []),
                sections=sections,
            )
        except Exception:
            pass

    # Fallback to persisted SQLite chunks
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    sections = [
        DocumentContentSection(
            section_index=c.page_start,
            section_title=getattr(c, "section_title", None) or (f"Page {c.page_start}" if doc_fmt == "pdf" else f"Section {c.page_start}"),
            content=c.content,
            char_count=c.char_count,
        )
        for c in chunks
    ]
    return DocumentContentResponse(
        document_id=doc.id,
        original_filename=doc.original_filename,
        file_format=doc_fmt,
        citation_unit=citation_unit,
        total_sections=len(sections),
        headings=[],
        sections=sections,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve document details, extraction status, and chunk counts by ID for the authenticated owner.
    """
    doc = get_owned_document(document_id, current_user, db)
    ensure_document_metadata(doc, db)
    return doc


@router.get("/{document_id}/stats", response_model=DocumentStatsResponse)
def get_document_stats(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve detailed extraction statistics and page analysis for an owned document.
    """
    doc = get_owned_document(document_id, current_user, db)
    ensure_document_metadata(doc, db)

    avg_chunk_size = 0.0
    if doc.total_chunks > 0 and doc.total_characters > 0:
        avg_chunk_size = round(doc.total_characters / doc.total_chunks, 1)

    # Optional detailed page/section char count inspection
    page_breakdown = None
    doc_fmt = (getattr(doc, "file_format", None) or "pdf").lower()
    if os.path.exists(doc.file_path) and doc.status != "failed":
        try:
            extraction = document_extractor.inspect_and_extract(doc.file_path, doc_fmt)
            page_breakdown = [
                {
                    "page": p["page"],
                    "char_count": p["char_count"],
                    "is_empty": p["is_empty"],
                    "has_images": p.get("has_images", False),
                    "section_title": p.get("section_title"),
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
        file_format=doc_fmt,
        document_category=getattr(doc, "document_category", "General Document") or "General Document",
        classification_confidence=getattr(doc, "classification_confidence", 0.0) or 0.0,
        classification_source=getattr(doc, "classification_source", "auto"),
        classification_reason=getattr(doc, "classification_reason", None),
        citation_unit="page" if doc_fmt == "pdf" else "section",
        error_message=doc.error_message,
        average_chunk_size=avg_chunk_size,
        page_breakdown=page_breakdown
    )



@router.get("/{document_id}/chunks", response_model=DocumentChunksListResponse)
def get_document_chunks(
    document_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Inspect chunk metadata, page ranges, and content for an owned document.
    """
    get_owned_document(document_id, current_user, db)

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
            section_title=getattr(c, "section_title", None),
            paragraph_range=getattr(c, "paragraph_range", None),
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate Gemini semantic embeddings for all owned document chunks.
    Avoids regenerating if valid embeddings already exist unless force=True.
    """
    doc = get_owned_document(document_id, current_user, db)

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve embedding status, model name, and dimensions for an owned document.
    """
    doc = get_owned_document(document_id, current_user, db)

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Re-runs the complete automatic processing pipeline on an ownership-verified document.
    """
    doc = get_owned_document(document_id, current_user, db)

    resolved_path = _resolve_safe_document_file_path(doc)
    if not resolved_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found")
    doc.file_path = resolved_path

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
def get_document_file(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Stream the raw file for an ownership-verified document with inline disposition.
    Never exposes internal filesystem paths.
    """
    doc = get_owned_document(document_id, current_user, db)

    file_path = _resolve_safe_document_file_path(doc)
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found")

    doc_fmt = (getattr(doc, "file_format", None) or "pdf").lower()
    media_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain; charset=utf-8",
    }

    safe_disp_name = os.path.basename((doc.original_filename or "document").replace('"', "").replace("\r", "").replace("\n", ""))
    return FileResponse(
        path=file_path,
        media_type=media_map.get(doc_fmt, "application/octet-stream"),
        filename=safe_disp_name,
        content_disposition_type="inline",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{safe_disp_name}"',
            "Access-Control-Expose-Headers": "Content-Disposition, Content-Range, Accept-Ranges"
        }
    )


@router.post("/{document_id}/index", response_model=DocumentIndexResponse)
def index_document_vectors(
    document_id: str,
    force: bool = Query(False, description="Whether to force re-indexing even if already indexed"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ingest existing embeddings from SQLite for an owned document into ChromaDB.
    """
    doc = get_owned_document(document_id, current_user, db)

    try:
        result = vector_store_service.index_document_chunks(
            document_id=doc.id,
            db=db,
            force=force,
            user_id=current_user.id,
        )
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Inspect ChromaDB vector indexing status for an owned document.
    """
    doc = get_owned_document(document_id, current_user, db)

    try:
        status_info = vector_store_service.get_indexing_status(
            document_id=doc.id,
            db=db,
            user_id=current_user.id,
        )
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Perform ownership-verified semantic similarity search on an owned document's chunks using ChromaDB.
    """
    doc = get_owned_document(document_id, current_user, db)

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
            db=db,
            user_id=current_user.id,
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Perform grounded Retrieval-Augmented Generation (RAG) chat against an ownership-verified document.
    """
    get_owned_document(document_id, current_user, db)
    try:
        result = rag_service.answer_document_query(
            document_id=document_id,
            query=request.message,
            db=db,
            top_k=request.top_k,
            user_id=current_user.id,
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve all conversation messages and citations for an ownership-verified document.
    """
    get_owned_document(document_id, current_user, db)
    try:
        history = rag_service.get_history(document_id=document_id, db=db, user_id=current_user.id)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete all conversation messages for an ownership-verified document.
    """
    get_owned_document(document_id, current_user, db)
    try:
        deleted = rag_service.clear_history(document_id=document_id, db=db, user_id=current_user.id)
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
def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete an ownership-verified document, its stored file and isolated folder, chunks, and ChromaDB vectors.
    """
    doc = get_owned_document(document_id, current_user, db)

    # Clean up vectors from ChromaDB scoped by user & document
    try:
        vector_store_service.delete_document_vectors(document_id, user_id=current_user.id)
    except Exception:
        pass

    resolved_path = _resolve_safe_document_file_path(doc)
    upload_root = os.path.abspath(settings.UPLOAD_DIR)
    user_doc_dir = os.path.abspath(os.path.join(upload_root, str(current_user.id), str(doc.id)))
    if resolved_path and os.path.exists(resolved_path):
        try:
            os.remove(resolved_path)
        except OSError:
            pass
    if os.path.commonpath([upload_root, user_doc_dir]) == upload_root and os.path.isdir(user_doc_dir):
        shutil.rmtree(user_doc_dir, ignore_errors=True)

    db.delete(doc)
    db.commit()
    return None
