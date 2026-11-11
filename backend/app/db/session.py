import datetime
import secrets
from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# SQLite configuration requires connect_args check_same_thread=False for FastAPI
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

_CHROMA_OWNERSHIP_BACKFILLED = False


def get_db():
    """
    FastAPI dependency that yields a scoped SQLAlchemy database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_legacy_archive_user(conn) -> str:
    """
    Creates the locked, non-loginable legacy archive user account that isolates
    all pre-authentication development/test documents from new user workspaces.
    """
    from app.db.models import LEGACY_OWNER_USER_ID
    from app.core.security import hash_password

    row = conn.execute(
        text("SELECT id FROM users WHERE id = :uid"),
        {"uid": LEGACY_OWNER_USER_ID},
    ).fetchone()
    if not row:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # Generate an unusable high-entropy password hash; account is also marked is_active=0.
        locked_hash = hash_password(secrets.token_urlsafe(32))
        conn.execute(
            text(
                "INSERT INTO users (id, name, email, password_hash, role, is_active, created_at, updated_at) "
                "VALUES (:id, :name, :email, :password_hash, :role, :is_active, :created_at, :updated_at)"
            ),
            {
                "id": LEGACY_OWNER_USER_ID,
                "name": "Legacy Development Archive",
                "email": "legacy-archive@paperpilot.internal",
                "password_hash": locked_hash,
                "role": "legacy_archive",
                "is_active": 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.commit()
    return LEGACY_OWNER_USER_ID


def _sync_chroma_legacy_ownership(conn) -> None:
    """
    Non-destructively tags any existing ChromaDB vectors missing user_id metadata
    with their SQLite Document.user_id (or LEGACY_OWNER_USER_ID if unlinked),
    preserving all existing 768-dimensional embeddings without regeneration.
    """
    global _CHROMA_OWNERSHIP_BACKFILLED
    if _CHROMA_OWNERSHIP_BACKFILLED:
        return
    try:
        import chromadb
        from app.db.models import LEGACY_OWNER_USER_ID

        client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        collection = client.get_or_create_collection(
            name="paperpilot_documents",
            metadata={"hnsw:space": "cosine"},
        )
        total = collection.count()
        if total == 0:
            _CHROMA_OWNERSHIP_BACKFILLED = True
            return

        doc_owners = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT id, user_id FROM documents")).fetchall()
        }

        data = collection.get(include=["metadatas"])
        ids = data.get("ids") or []
        metadatas = data.get("metadatas") or []

        ids_to_update = []
        metas_to_update = []
        for idx, meta in zip(ids, metadatas):
            m = dict(meta or {})
            doc_id = m.get("document_id")
            expected_uid = doc_owners.get(doc_id, LEGACY_OWNER_USER_ID)
            if m.get("user_id") != expected_uid:
                m["user_id"] = expected_uid
                ids_to_update.append(idx)
                metas_to_update.append(m)

        batch_size = 200
        for i in range(0, len(ids_to_update), batch_size):
            collection.update(
                ids=ids_to_update[i : i + batch_size],
                metadatas=metas_to_update[i : i + batch_size],
            )
        _CHROMA_OWNERSHIP_BACKFILLED = True
    except Exception as e:
        print(f"ChromaDB legacy ownership metadata sync warning: {e}")


def init_db():
    """
    Initializes database tables and safely applies non-destructive column and
    ownership migrations if tables pre-existed.
    """
    # Ensure ORM models are registered on Base.metadata
    import app.db.models  # noqa: F401
    from app.db.models import LEGACY_OWNER_USER_ID

    # 1. Ensure all defined tables exist (including users, user_sessions, password_reset_tokens)
    Base.metadata.create_all(bind=engine)

    # 2. Ensure locked legacy archive owner account exists before backfilling foreign keys
    with engine.connect() as conn:
        _ensure_legacy_archive_user(conn)

    # 3. Check and migrate SQLite columns for 'documents' table if needed
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "documents" in tables:
        existing_cols = {col["name"] for col in inspector.get_columns("documents")}

        # Columns migration for documents
        doc_migrations = [
            ("user_id", "VARCHAR(36)"),
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
            ("file_format", "VARCHAR(20) DEFAULT 'pdf'"),
            ("document_category", "VARCHAR(100) DEFAULT 'General Document'"),
            ("classification_confidence", "FLOAT DEFAULT 0.0"),
            ("classification_source", "VARCHAR(50) DEFAULT 'auto'"),
            ("classification_reason", "TEXT"),
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

            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_user_id ON documents (user_id)"))
                conn.commit()
            except Exception as e:
                print(f"Index migration warning for documents.user_id: {e}")

            # Non-destructively isolate pre-existing unowned legacy documents under the locked archive owner
            try:
                conn.execute(
                    text(
                        "UPDATE documents SET user_id = :legacy_uid "
                        "WHERE user_id IS NULL OR TRIM(user_id) = ''"
                    ),
                    {"legacy_uid": LEGACY_OWNER_USER_ID},
                )
                conn.commit()
            except Exception as e:
                print(f"Legacy document ownership migration warning: {e}")

            # Backfill legacy documents with explicit educational chapter metadata
            try:
                conn.execute(text(
                    "UPDATE documents "
                    "SET file_format = COALESCE(NULLIF(file_format, ''), 'pdf'), "
                    "    document_category = CASE "
                    "        WHEN (document_category IS NULL OR document_category = '' OR document_category = 'General Document') "
                    "             AND (chapter_name IS NOT NULL OR chapter_number IS NOT NULL OR subject IS NOT NULL) "
                    "        THEN 'Educational Material' "
                    "        ELSE COALESCE(NULLIF(document_category, ''), 'General Document') "
                    "    END, "
                    "    classification_confidence = CASE "
                    "        WHEN (classification_confidence IS NULL OR classification_confidence = 0.0) "
                    "             AND (chapter_name IS NOT NULL OR chapter_number IS NOT NULL OR subject IS NOT NULL) "
                    "        THEN 0.85 "
                    "        ELSE COALESCE(classification_confidence, 0.0) "
                    "    END "
                    "WHERE file_format IS NULL OR document_category IS NULL "
                    "   OR (classification_source IS NULL) "
                    "   OR ((classification_confidence IS NULL OR classification_confidence = 0.0) "
                    "       AND (chapter_name IS NOT NULL OR chapter_number IS NOT NULL OR subject IS NOT NULL))"
                ))
                conn.commit()
            except Exception as e:
                print(f"Document backfill warning: {e}")

    # 4. Check and migrate SQLite columns for 'document_chunks' table
    if "document_chunks" in tables:
        chunk_cols = {col["name"] for col in inspector.get_columns("document_chunks")}
        chunk_migrations = [
            ("user_id", "VARCHAR(36)"),
            ("embedding_json", "TEXT"),
            ("embedding_dimension", "INTEGER"),
            ("section_title", "VARCHAR(255)"),
            ("paragraph_range", "VARCHAR(50)"),
        ]
        with engine.connect() as conn:
            for col_name, col_type in chunk_migrations:
                if col_name not in chunk_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE document_chunks ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                    except Exception as e:
                        print(f"Column migration warning for document_chunks.{col_name}: {e}")
            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_document_chunks_user_id ON document_chunks (user_id)"))
                conn.commit()
            except Exception:
                pass

    # 5. Add user_id column & backfill ownership from parent Document on all derived child tables
    derived_tables = [
        "document_chunks",
        "chat_messages",
        "document_summaries",
        "quizzes",
        "revision_notes",
        "document_insights",
    ]
    with engine.connect() as conn:
        for tbl in derived_tables:
            if tbl not in tables:
                continue
            cols = {col["name"] for col in inspector.get_columns(tbl)}
            if "user_id" not in cols:
                try:
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN user_id VARCHAR(36)"))
                    conn.commit()
                except Exception as e:
                    print(f"Column migration warning for {tbl}.user_id: {e}")
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{tbl}_user_id ON {tbl} (user_id)"))
                conn.execute(
                    text(
                        f"UPDATE {tbl} SET user_id = COALESCE("
                        f"(SELECT d.user_id FROM documents d WHERE d.id = {tbl}.document_id), :legacy_uid) "
                        f"WHERE user_id IS NULL OR TRIM(user_id) = ''"
                    ),
                    {"legacy_uid": LEGACY_OWNER_USER_ID},
                )
                conn.commit()
            except Exception as e:
                print(f"Ownership backfill warning for {tbl}: {e}")

        # 6. Tag pre-existing ChromaDB vectors with legacy ownership non-destructively
        _sync_chroma_legacy_ownership(conn)
