from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Document
from app.schemas.summary import SummaryGenerateRequest, SummaryResponse
from app.services.summary_service import summary_service

router = APIRouter()


@router.get("/{document_id}", response_model=SummaryResponse)
async def get_document_summary(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieve saved summary for a document from SQLite.
    Returns 404 if no summary has been generated yet.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    saved = summary_service.get_saved_summary(document_id, db)
    if not saved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not generated yet for this document")

    return saved


@router.post("/generate", response_model=SummaryResponse)
async def generate_summary(
    payload: SummaryGenerateRequest,
    db: Session = Depends(get_db)
):
    """
    Generate or retrieve executive overview, key takeaways, important concepts,
    formulas, chapter summaries, facts, and page references for a document.
    """
    doc = db.query(Document).filter(Document.id == payload.document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        result = summary_service.generate_summary(
            document_id=payload.document_id,
            db=db,
            format_type=payload.format or "comprehensive",
            force_regenerate=payload.force_regenerate
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate summary: {str(e)}")
