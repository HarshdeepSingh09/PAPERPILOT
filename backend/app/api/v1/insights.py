from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_owned_document
from app.db.session import get_db
from app.db.models import User
from app.schemas.insights import AdaptiveInsightsResponse, InsightsGenerateRequest
from app.services.adaptive_insights_service import adaptive_insights_service

router = APIRouter()


@router.get("/{document_id}", response_model=AdaptiveInsightsResponse)
def get_document_insights(
    document_id: str,
    category: Optional[str] = Query(None, description="Optional category override for lookup"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve saved category-adaptive insights for an ownership-verified document from SQLite.
    Returns 404 if document is missing/unauthorized or insights have not yet been generated.
    """
    doc = get_owned_document(document_id, current_user, db)

    target_cat = category or getattr(doc, "document_category", "General Document") or "General Document"
    saved = adaptive_insights_service.get_saved_insights(
        document_id,
        target_cat,
        db,
        user_id=current_user.id,
    )
    if not saved:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Adaptive insights not generated yet for category '{target_cat}'."
        )
    return saved


@router.post("/generate", response_model=AdaptiveInsightsResponse)
def generate_document_insights(
    payload: InsightsGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate (or return cached) category-specific structured insights strictly for an ownership-verified document.
    """
    doc = get_owned_document(payload.document_id, current_user, db)

    if doc.status in ("uploaded", "extracting", "embedding", "indexing", "processing"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document is currently {doc.status}. Please wait until processing finishes."
        )
    if doc.status in ("ocr_required", "failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=doc.error_message or f"Document cannot be analyzed (status: {doc.status})."
        )

    try:
        result = adaptive_insights_service.get_or_generate_insights(
            document_id=payload.document_id,
            db=db,
            category=payload.category,
            force_regenerate=payload.force_regenerate,
            user_id=current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate adaptive insights: {str(e)}"
        )
