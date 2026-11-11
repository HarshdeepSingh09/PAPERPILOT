from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_owned_document
from app.db.session import get_db
from app.db.models import User
from app.schemas.summary import SummaryGenerateRequest, SummaryResponse
from app.services.summary_service import summary_service

router = APIRouter()


@router.get("/{document_id}", response_model=SummaryResponse)
async def get_document_summary(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve saved summary for an ownership-verified document from SQLite.
    Returns 404 if document is missing/unauthorized or no summary has been generated yet.
    """
    get_owned_document(document_id, current_user, db)

    saved = summary_service.get_saved_summary(document_id, db, user_id=current_user.id)
    if not saved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not generated yet for this document")

    return saved


@router.post("/generate", response_model=SummaryResponse)
async def generate_summary(
    payload: SummaryGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate or retrieve multi-section summary strictly for a document owned by the authenticated user.
    """
    get_owned_document(payload.document_id, current_user, db)

    try:
        result = summary_service.generate_summary(
            document_id=payload.document_id,
            db=db,
            format_type=payload.format or "comprehensive",
            force_regenerate=payload.force_regenerate,
            user_id=current_user.id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate summary: {str(e)}")
