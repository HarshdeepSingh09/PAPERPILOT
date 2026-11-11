from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.session import engine, Base
from app.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure SQLite tables and columns are synchronized
    from app.db.session import init_db, SessionLocal
    from app.db.models import Document
    init_db()

    # Handle documents interrupted by a server restart
    db = SessionLocal()
    try:
        interrupted = db.query(Document).filter(
            Document.status.in_(["uploaded", "extracting", "embedding", "indexing", "processing"])
        ).all()
        for d in interrupted:
            d.status = "failed"
            d.error_message = "Processing was interrupted by a server restart. Please click reprocess."
        if interrupted:
            db.commit()
    except Exception:
        pass
    finally:
        db.close()

    yield
    # Shutdown logic if needed


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
    version="1.0.0"
)

# Configure explicit allowed origins with credentials enabled for HttpOnly cookie auth
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
    expose_headers=["Content-Disposition", "Content-Range", "Accept-Ranges", "Content-Length"],
)

# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Health"])
def root():
    return {
        "app": settings.PROJECT_NAME,
        "status": "online",
        "docs_url": f"{settings.API_V1_STR}/docs",
        "version": "1.0.0"
    }


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy", "service": "paperpilot-backend"}
