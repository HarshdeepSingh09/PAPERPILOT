import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import ensure_utc_aware, hash_token
from app.db.models import Document, Quiz, User, UserSession
from app.db.session import get_db


def extract_session_token(request: Request) -> Optional[str]:
    """
    Extracts the opaque session token strictly from the HttpOnly cookie (or
    explicit Authorization: Bearer header for programmatic API clients).
    Never reads tokens or user identities from URL query strings.
    """
    cookie_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_token and cookie_token.strip():
        return cookie_token.strip()

    auth_header = request.headers.get("Authorization") or ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI authentication dependency resolving the authenticated, active user
    exclusively from a validated non-revoked backend session.
    """
    raw_token = extract_session_token(request)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in to access your workspace.",
        )

    token_digest = hash_token(raw_token)
    session = (
        db.query(UserSession)
        .filter(
            UserSession.token_hash == token_digest,
            UserSession.revoked_at.is_(None),
        )
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please sign in again.",
        )

    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = ensure_utc_aware(session.expires_at)
    if not expires_at or expires_at <= now:
        session.revoked_at = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please sign in again.",
        )

    user = (
        db.query(User)
        .filter(User.id == session.user_id, User.is_active == True)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or unavailable.",
        )

    return user


def get_owned_document(
    document_id: str,
    current_user: User,
    db: Session,
) -> Document:
    """
    Enforces strict backend ownership verification for every document access.
    Returns HTTP 404 for both non-existent IDs and documents owned by another user
    to avoid leaking resource existence across accounts.
    """
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == current_user.id)
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return doc


def get_owned_quiz(
    quiz_id: str,
    current_user: User,
    db: Session,
) -> Quiz:
    """
    Enforces strict ownership on direct quiz lookup and submission by joining through Document.
    """
    quiz = (
        db.query(Quiz)
        .join(Document, Quiz.document_id == Document.id)
        .filter(Quiz.id == quiz_id, Document.user_id == current_user.id)
        .first()
    )
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )
    return quiz
