from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_owned_document, get_owned_quiz
from app.db.session import get_db
from app.db.models import User
from app.schemas.quiz import QuizGenerateRequest, QuizSubmitRequest, QuizResponse
from app.schemas.revision import RevisionNotesGenerateRequest, RevisionNotesResponse
from app.services.quiz_service import quiz_service
from app.services.revision_service import revision_service

router = APIRouter()


@router.get("/document/{document_id}", response_model=QuizResponse)
async def get_latest_document_quiz(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve the most recent quiz attempt for an ownership-verified document.
    """
    get_owned_document(document_id, current_user, db)

    quiz = quiz_service.get_latest_quiz(document_id, db, user_id=current_user.id)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No quiz generated yet for this document")

    return quiz


@router.get("/{quiz_id}", response_model=QuizResponse)
async def get_quiz(
    quiz_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve quiz by ID strictly after verifying parent document ownership.
    """
    get_owned_quiz(quiz_id, current_user, db)
    quiz = quiz_service.get_quiz_by_id(quiz_id, db, user_id=current_user.id)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return quiz


@router.post("/generate", response_model=QuizResponse)
async def generate_quiz(
    payload: QuizGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate interactive assessment questions derived exclusively from an ownership-verified document.
    """
    get_owned_document(payload.document_id, current_user, db)

    try:
        result = quiz_service.generate_quiz(
            document_id=payload.document_id,
            num_questions=payload.num_questions,
            difficulty=payload.difficulty,
            question_type=payload.question_type,
            db=db,
            force_regenerate=payload.force_regenerate,
            user_id=current_user.id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate quiz: {str(e)}")


@router.post("/{quiz_id}/submit", response_model=QuizResponse)
async def submit_quiz(
    quiz_id: str,
    payload: QuizSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit user answers for an ownership-verified quiz, calculate score, and reveal explanations.
    """
    get_owned_quiz(quiz_id, current_user, db)
    try:
        result = quiz_service.submit_quiz(quiz_id, payload.answers, db, user_id=current_user.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to submit quiz: {str(e)}")


# --- Revision Notes Endpoints ---

@router.get("/notes/{document_id}", response_model=RevisionNotesResponse)
async def get_revision_notes(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve saved 8-section revision notes for an ownership-verified document.
    """
    get_owned_document(document_id, current_user, db)

    try:
        result = revision_service.get_or_generate_revision_notes(
            document_id,
            db=db,
            force_regenerate=False,
            user_id=current_user.id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve revision notes: {str(e)}")


@router.post("/notes/generate", response_model=RevisionNotesResponse)
async def generate_revision_notes(
    payload: RevisionNotesGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate or regenerate 8-section revision notes for an ownership-verified document.
    """
    get_owned_document(payload.document_id, current_user, db)

    try:
        result = revision_service.get_or_generate_revision_notes(
            document_id=payload.document_id,
            db=db,
            force_regenerate=payload.force_regenerate,
            user_id=current_user.id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate revision notes: {str(e)}")
