from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_owned_document
from app.db.models import User
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse, MessageHistoryItem, ClearHistoryResponse
from app.services.rag_service import (
    rag_service,
    RAGServiceError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    RAGGenerationError
)
from app.services.embedding_service import (
    MissingAPIKeyError,
    InvalidAPIKeyError,
    RateLimitExceededError,
    EmbeddingServiceError
)

router = APIRouter()


@router.post("", response_model=ChatResponse)
def send_chat_message(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Process a chat message against an ownership-verified document with grounded RAG and Gemini.
    """
    if not payload.document_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document_id is required."
        )

    get_owned_document(payload.document_id, current_user, db)

    try:
        result = rag_service.answer_document_query(
            document_id=payload.document_id,
            query=payload.message,
            db=db,
            top_k=payload.top_k,
            user_id=current_user.id,
        )
        return ChatResponse(**result)
    except DocumentNotFoundError as e:
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
            detail=f"An error occurred while generating answer: {str(e)}"
        )


@router.get("/{document_id}/history", response_model=List[MessageHistoryItem])
def get_chat_history(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve message history for an ownership-verified document.
    """
    get_owned_document(document_id, current_user, db)
    try:
        history = rag_service.get_history(document_id=document_id, db=db, user_id=current_user.id)
        return [MessageHistoryItem(**item) for item in history]
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve chat history: {str(e)}"
        )


@router.delete("/{document_id}/history", response_model=ClearHistoryResponse)
def clear_chat_history(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Clear all message history for an ownership-verified document.
    """
    get_owned_document(document_id, current_user, db)
    try:
        deleted = rag_service.clear_history(document_id=document_id, db=db, user_id=current_user.id)
        return ClearHistoryResponse(
            document_id=document_id,
            deleted_count=deleted,
            message=f"Successfully cleared {deleted} message(s) for document."
        )
    except DocumentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear chat history: {str(e)}"
        )
