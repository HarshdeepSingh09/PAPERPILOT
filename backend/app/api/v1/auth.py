import datetime
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import extract_session_token, get_current_user
from app.core.security import (
    ensure_utc_aware,
    generate_opaque_token,
    hash_password,
    hash_token,
    is_smtp_configured,
    send_password_reset_email,
    verify_password,
)
from app.db.models import PasswordResetToken, User, UserSession
from app.db.session import get_db
from app.schemas.auth import (
    AuthSessionResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LogoutResponse,
    MessageResponse,
    ResetPasswordRequest,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
)

router = APIRouter()


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=settings.SESSION_EXPIRE_HOURS * 3600,
        httponly=True,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        secure=settings.SESSION_COOKIE_SECURE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        secure=settings.SESSION_COOKIE_SECURE,
    )


def _issue_session(user: User, request: Request, response: Response, db: Session) -> None:
    raw_token = generate_opaque_token(48)
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = now + datetime.timedelta(hours=settings.SESSION_EXPIRE_HOURS)
    user_agent = (request.headers.get("user-agent") or "")[:250] or None
    client_host = request.client.host[:60] if request.client and request.client.host else None

    session = UserSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=hash_token(raw_token),
        user_agent=user_agent,
        ip_address=client_host,
        created_at=now,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    _set_session_cookie(response, raw_token)


@router.post("/register", response_model=AuthSessionResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserRegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Create a new independent PaperPilot user account with a fresh empty workspace
    and establish an authenticated HttpOnly session cookie.
    """
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    try:
        pw_hash = hash_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    now = datetime.datetime.now(datetime.timezone.utc)
    user = User(
        id=str(uuid.uuid4()),
        name=payload.name,
        email=payload.email,
        password_hash=pw_hash,
        role="user",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _issue_session(user, request, response, db)
    return AuthSessionResponse(
        authenticated=True,
        user=UserProfileResponse.model_validate(user),
        message="Account created successfully.",
    )


@router.post("/login", response_model=AuthSessionResponse)
def login_user(
    payload: UserLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Authenticate an existing active user and issue an HttpOnly backend session cookie.
    """
    user = db.query(User).filter(User.email == payload.email).first()
    if (
        not user
        or not user.is_active
        or user.role == "legacy_archive"
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    _issue_session(user, request, response, db)
    return AuthSessionResponse(
        authenticated=True,
        user=UserProfileResponse.model_validate(user),
        message="Signed in successfully.",
    )


@router.post("/logout", response_model=LogoutResponse)
def logout_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Revoke the active server-side session in SQLite and clear the HttpOnly cookie.
    """
    raw_token = extract_session_token(request)
    if raw_token:
        token_digest = hash_token(raw_token)
        session = (
            db.query(UserSession)
            .filter(UserSession.token_hash == token_digest, UserSession.revoked_at.is_(None))
            .first()
        )
        if session:
            session.revoked_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()

    _clear_session_cookie(response)
    return LogoutResponse(authenticated=False, message="Signed out successfully.")


@router.get("/me", response_model=UserProfileResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Return the authenticated user's profile derived exclusively from the session.
    """
    return current_user


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Initiates a password reset without leaking whether an email address is registered.
    Dispatches an email when SMTP environment settings are configured.
    """
    user = (
        db.query(User)
        .filter(User.email == payload.email, User.is_active == True, User.role != "legacy_archive")
        .first()
    )
    if user:
        now = datetime.datetime.now(datetime.timezone.utc)
        # Invalidate any prior unused reset tokens for this user
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).update({"used_at": now})

        raw_token = generate_opaque_token(32)
        expires_at = now + datetime.timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
        reset_record = PasswordResetToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=expires_at,
            created_at=now,
        )
        db.add(reset_record)
        db.commit()

        reset_url = f"{settings.FRONTEND_APP_URL.rstrip('/')}/reset-password?token={raw_token}"
        send_password_reset_email(user.email, user.name, reset_url)

    return ForgotPasswordResponse(
        message="If an account with that email exists, password reset instructions have been issued.",
        email_delivery_configured=is_smtp_configured(),
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Completes password reset using a valid single-use reset token and revokes existing sessions.
    """
    token_digest = hash_token(payload.token)
    reset_record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_digest, PasswordResetToken.used_at.is_(None))
        .first()
    )
    if not reset_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = ensure_utc_aware(reset_record.expires_at)
    if not expires_at or expires_at <= now:
        reset_record.used_at = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has expired. Please request a new one.",
        )

    user = db.query(User).filter(User.id == reset_record.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    user.updated_at = now
    reset_record.used_at = now

    # Revoke all active user sessions after password change
    db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
    ).update({"revoked_at": now})
    db.commit()

    return MessageResponse(message="Your password has been updated. Please sign in with your new password.")
