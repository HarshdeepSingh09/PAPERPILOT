from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Document
from app.schemas.quiz import QuizGenerateRequest, QuizSubmitRequest, QuizResponse
from app.schemas.revision import RevisionNotesGenerateRequest, RevisionNotesResponse
from app.services.quiz_service import quiz_service
from app.services.revision_service import revision_service

router = APIRouter()


@router.get("/document/{document_id}", response_model=QuizResponse)
async def get_latest_document_quiz(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieve the most recent quiz attempt for a document.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    quiz = quiz_service.get_latest_quiz(document_id, db)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No quiz generated yet for this document")

    return quiz


@router.get("/{quiz_id}", response_model=QuizResponse)
async def get_quiz(
    quiz_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieve quiz by ID.
    """
    quiz = quiz_service.get_quiz_by_id(quiz_id, db)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return quiz


@router.post("/generate", response_model=QuizResponse)
async def generate_quiz(
    payload: QuizGenerateRequest,
    db: Session = Depends(get_db)
):
    """
    Generate interactive assessment questions derived exclusively from the uploaded document.
    """
    doc = db.query(Document).filter(Document.id == payload.document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        result = quiz_service.generate_quiz(
            document_id=payload.document_id,
            num_questions=payload.num_questions,
            difficulty=payload.difficulty,
            question_type=payload.question_type,
            db=db,
            force_regenerate=payload.force_regenerate
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate quiz: {str(e)}")


@router.post("/{quiz_id}/submit", response_model=QuizResponse)
async def submit_quiz(
    quiz_id: str,
    payload: QuizSubmitRequest,
    db: Session = Depends(get_db)
):
    """
    Submit user answers, calculate score and percentage, and reveal explanations.
    """
    try:
        result = quiz_service.submit_quiz(quiz_id, payload.answers, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to submit quiz: {str(e)}")


# --- Revision Notes Endpoints ---

@router.get("/notes/{document_id}", response_model=RevisionNotesResponse)
async def get_revision_notes(
    document_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieve saved 8-section revision notes for a document from SQLite,
    or generate them if not previously created.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        result = revision_service.get_or_generate_revision_notes(document_id, db=db, force_regenerate=False)
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve revision notes: {str(e)}")


@router.post("/notes/generate", response_model=RevisionNotesResponse)
async def generate_revision_notes(
    payload: RevisionNotesGenerateRequest,
    db: Session = Depends(get_db)
):
    """
    Generate or regenerate 8-section revision notes for a document.
    """
    doc = db.query(Document).filter(Document.id == payload.document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        result = revision_service.get_or_generate_revision_notes(
            document_id=payload.document_id,
            db=db,
            force_regenerate=payload.force_regenerate
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate revision notes: {str(e)}")
