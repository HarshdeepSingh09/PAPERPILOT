import datetime
import hashlib
import logging
import secrets
import smtplib
from email.message import EmailMessage
from typing import Optional

import bcrypt

from app.core.config import settings

logger = logging.getLogger(__name__)


def validate_password_strength(password: str) -> None:
    """
    Validates user password complexity and bcrypt UTF-8 byte boundary (<= 72 bytes).
    Raises ValueError with clear user-safe feedback if invalid.
    """
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password cannot exceed 72 UTF-8 bytes.")


def hash_password(password: str) -> str:
    """
    Hashes a plaintext password with bcrypt and an automatic per-password salt.
    """
    validate_password_strength(password)
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    Verifies a candidate plaintext password against a stored bcrypt hash in constant time.
    """
    if not plain_password or not password_hash:
        return False
    pw_bytes = plain_password.encode("utf-8")
    if len(pw_bytes) > 72:
        return False
    try:
        return bcrypt.checkpw(pw_bytes, password_hash.encode("utf-8"))
    except Exception:
        return False


def generate_opaque_token(nbytes: int = 48) -> str:
    """Generates a cryptographically random URL-safe token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(raw_token: str) -> str:
    """Computes a deterministic SHA-256 hex digest so raw session/reset tokens are never stored."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def ensure_utc_aware(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    """Normalizes SQLite naive datetimes cleanly to UTC-aware datetime objects."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def is_smtp_configured() -> bool:
    """Returns True when minimal SMTP configuration is present to deliver reset emails."""
    return bool((settings.SMTP_HOST or "").strip() and (settings.SMTP_FROM_EMAIL or "").strip())


def send_password_reset_email(to_email: str, user_name: str, reset_url: str) -> bool:
    """
    Delivers a password reset email via configured SMTP relay.
    Returns True if sent, False if SMTP is not configured or delivery failed.
    """
    if not is_smtp_configured():
        logger.info(
            "Password reset requested for %s, but SMTP_HOST / SMTP_FROM_EMAIL are not configured; "
            "skipping email dispatch cleanly.",
            to_email,
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = "Reset your PaperPilot password"
    msg["From"] = settings.SMTP_FROM_EMAIL.strip()
    msg["To"] = to_email
    msg.set_content(
        f"Hello {user_name},\n\n"
        "A password reset was requested for your PaperPilot account.\n\n"
        f"Reset link (expires in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes):\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can safely ignore this message.\n"
    )

    try:
        with smtplib.SMTP(settings.SMTP_HOST.strip(), int(settings.SMTP_PORT), timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if (settings.SMTP_USER or "").strip() and (settings.SMTP_PASSWORD or "").strip():
                server.login(settings.SMTP_USER.strip(), settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as exc:
        logger.warning(f"Failed to send password reset email: {type(exc).__name__}")
        return False
