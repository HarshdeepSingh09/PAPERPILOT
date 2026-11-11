import os
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Settings(BaseSettings):
    PROJECT_NAME: str = "PaperPilot"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    
    # Server Host & Port
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS Configuration
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # SQLite Database
    DATABASE_URL: str = f"sqlite:///{os.path.join(BASE_BACKEND_DIR, 'paperpilot.db')}"

    # Storage Paths
    UPLOAD_DIR: str = os.path.join(BASE_BACKEND_DIR, "storage", "uploads")
    CHROMA_PERSIST_DIR: str = os.path.join(BASE_BACKEND_DIR, "storage", "chroma_db")
    MAX_UPLOAD_SIZE_MB: int = 25

    @field_validator("UPLOAD_DIR", "CHROMA_PERSIST_DIR", mode="after")
    def resolve_storage_paths(cls, v: str) -> str:
        if not os.path.isabs(v):
            return os.path.abspath(os.path.join(BASE_BACKEND_DIR, v))
        return os.path.abspath(v)

    # Authentication & Session Configuration
    SESSION_COOKIE_NAME: str = "paperpilot_session"
    SESSION_EXPIRE_HOURS: int = 168  # 7 days
    SESSION_COOKIE_SAMESITE: str = "lax"
    SESSION_COOKIE_SECURE: bool = False  # Set True in HTTPS production deployments
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    FRONTEND_APP_URL: str = "http://localhost:5173"

    # Optional SMTP Email Configuration (for password reset emails)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True

    # AI Configuration
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"

    @field_validator("GEMINI_MODEL", "GEMINI_EMBEDDING_MODEL", mode="after")
    def normalize_ai_models(cls, v: str) -> str:
        if v.startswith("models/"):
            return v.replace("models/", "", 1)
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()

# Ensure storage directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
