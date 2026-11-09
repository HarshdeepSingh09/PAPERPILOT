from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# SQLite configuration requires connect_args check_same_thread=False for FastAPI
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency that yields a scoped SQLAlchemy database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initializes database tables and safely applies column migrations if tables pre-existed.
    """
    # 1. Ensure all defined tables exist
    Base.metadata.create_all(bind=engine)

    # 2. Check and migrate SQLite columns for 'documents' table if needed
    inspector = inspect(engine)
    if "documents" in inspector.get_table_names():
        existing_cols = {col["name"] for col in inspector.get_columns("documents")}
        
        # Columns migration for documents
        doc_migrations = [
            ("extracted_pages", "INTEGER DEFAULT 0"),
            ("total_characters", "INTEGER DEFAULT 0"),
            ("total_chunks", "INTEGER DEFAULT 0"),
            ("embedding_status", "VARCHAR(50) DEFAULT 'pending'"),
            ("embedding_model", "VARCHAR(100)"),
            ("error_message", "TEXT"),
            ("title", "VARCHAR(255)"),
            ("chapter_name", "VARCHAR(255)"),
            ("chapter_number", "VARCHAR(50)"),
            ("subject", "VARCHAR(100)"),
            ("doc_metadata_json", "TEXT"),
        ]

        with engine.connect() as conn:
            for col_name, col_type in doc_migrations:
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                    except Exception as e:
                        print(f"Column migration warning for documents.{col_name}: {e}")

    # 3. Check and migrate SQLite columns for 'document_chunks' table if needed
    if "document_chunks" in inspector.get_table_names():
        chunk_cols = {col["name"] for col in inspector.get_columns("document_chunks")}
        chunk_migrations = [
            ("embedding_json", "TEXT"),
            ("embedding_dimension", "INTEGER"),
        ]
        with engine.connect() as conn:
            for col_name, col_type in chunk_migrations:
                if col_name not in chunk_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE document_chunks ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                    except Exception as e:
                        print(f"Column migration warning for document_chunks.{col_name}: {e}")
