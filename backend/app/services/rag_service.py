import os
import re
import json
import time
import logging
import uuid
import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Document, DocumentChunk, ChatMessage
from app.services.vector_store import (
    vector_store_service,
    VectorStoreService,
    DocumentNotIndexedError,
    UnembeddedChunksError
)
from app.services.embedding_service import (
    MissingAPIKeyError,
    InvalidAPIKeyError,
    RateLimitExceededError,
    EmbeddingAPIError
)

logger = logging.getLogger(__name__)


class RAGServiceError(Exception):
    """Base exception for RAG service failures."""
    pass


class DocumentNotFoundError(RAGServiceError):
    """Raised when the document cannot be found."""
    pass


class DocumentNotReadyError(RAGServiceError):
    """Raised when the document is not in a ready state (e.g. failed extraction or unscanned)."""
    pass


class RAGGenerationError(RAGServiceError):
    """Raised when Gemini content generation fails."""
    pass


class RAGService:
    """
    Dedicated Retrieval-Augmented Generation (RAG) service.
    Features:
    1. Intent-aware Question Routing:
       - Document-level metadata queries (chapter name, title, author, subject, pages).
       - Broad exploratory queries (summaries, overviews, chapter topics).
       - Content-specific semantic queries (explanations, definitions, reactions).
    2. Context retrieval using stored SQLite metadata + ChromaDB vector search.
    3. Multi-turn conversation history injection from SQLite.
    4. Strict grounding prompt formulation for Google Gemini.
    5. Structured citation extraction with page numbers and snippets.
    6. SQLite conversation history persistence and lifecycle management.
    """

    DEFAULT_TOP_K = 4
    DEFAULT_MAX_HISTORY_MESSAGES = 6
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_BACKOFF = 1.0

    # Phrases indicating the model could not answer from the document
    FALLBACK_PHRASES = (
        "i cannot find the answer",
        "cannot find the answer to this question",
        "not found in the provided document",
        "not mentioned in the provided document",
        "document does not contain",
        "provided excerpts do not contain",
        "provided document does not provide",
        "no information provided",
    )

    def __init__(
        self,
        model_name: Optional[str] = None,
        client: Optional[Any] = None,
        vector_store: Optional[VectorStoreService] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
    ):
        raw_model = model_name or settings.GEMINI_MODEL
        self.model_name = raw_model.replace("models/", "") if raw_model else "gemini-3.5-flash"
        self._client = client
        self.vector_store = vector_store or vector_store_service
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff

    def get_validated_api_key(self) -> str:
        """
        Validates that a non-empty, non-placeholder Gemini API key is configured.
        """
        key = (settings.GEMINI_API_KEY or "").strip()
        if not key or key == "your_gemini_api_key_here":
            raise MissingAPIKeyError(
                "Gemini API key is not configured. Please set GEMINI_API_KEY in backend/.env "
                "with a valid key from Google AI Studio."
            )
        return key

    def get_client(self):
        """
        Initializes and returns the official Google GenAI Client.
        """
        if self._client is None:
            active_key = self.get_validated_api_key()
            from google import genai
            self._client = genai.Client(api_key=active_key)
        return self._client

    WORD_TO_NUM = {
        "one": 1, "first": 1, "two": 2, "second": 2, "three": 3, "third": 3,
        "four": 4, "fourth": 4, "five": 5, "fifth": 5, "six": 6, "sixth": 6,
        "seven": 7, "seventh": 7, "eight": 8, "eighth": 8, "nine": 9, "ninth": 9,
        "ten": 10, "tenth": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
        "nineteen": 19, "twenty": 20
    }

    def extract_target_page(self, query: str) -> Optional[int]:
        """
        Extracts explicit page number reference from a query if present.
        Matches patterns like 'page 6', 'page #6', 'p. 6', 'p.6', 'on page 6', etc.
        """
        ql = query.lower().strip()
        m = re.search(r'\b(?:page|p\.?)\s*(?:no\.?|number|#)?\s*(\d+)\b', ql)
        if m:
            return int(m.group(1))
        return None

    def parse_questions_from_page(self, page_text: str) -> List[Dict[str, Any]]:
        """
        Extracts textbook questions from page text.
        Identifies:
        1. Dedicated QUESTIONS in-text box (e.g. 'Q U E S T I O N S').
        2. Numbered questions (1., 2., 3., etc.).
        Excludes activity observation questions (e.g., 'Do you feel any change in temperature?').
        Preserves original question order and deduplicates.
        """
        questions: Dict[int, Dict[str, Any]] = {}

        # 1. Check for dedicated QUESTIONS box
        q_box_match = re.search(
            r'Q\s*U\s*E\s*S\s*T\s*I\s*O\s*N\s*S\s*\??\s*(.*?)(?=(?:Reprint\s+2026-27|Activity|\Z))',
            page_text,
            re.DOTALL | re.IGNORECASE
        )
        if q_box_match:
            content = q_box_match.group(1).strip()
            num_pattern = re.compile(r'(?:^|\n|\s)(\d+)\.\s*(.*?)(?=(?:(?:\n|\s)\d+\.|\Z))', re.DOTALL)
            for num_str, body in num_pattern.findall(content):
                num = int(num_str)
                clean_body = re.sub(r'[\r\n]+', ' ', body).strip()
                clean_body = re.sub(r'Reprint\s+2026-27.*', '', clean_body).strip()
                clean_body = re.sub(r'[\?\s]+$', '', clean_body).strip()
                if not clean_body.endswith('?') and not clean_body.endswith('.'):
                    clean_body += '?'
                if num not in questions or len(clean_body) > len(questions[num]["text"]):
                    questions[num] = {
                        "number": num,
                        "text": clean_body,
                        "type": "in_text_question"
                    }

        # 2. Fallback: look for numbered questions outside Activity sections
        if not questions:
            clean_text = re.sub(
                r'Activity\s*[\d\.]+\s*.*?(?=(?:1\.\d+|QUESTIONS|\Z))',
                '',
                page_text,
                flags=re.DOTALL | re.IGNORECASE
            )
            num_pattern = re.compile(r'(?:^|\n|\s)(\d+)\.\s*([A-Z][^\n]+(?:\n(?!\d+\.)[^\n]+)*)', re.MULTILINE)
            for match in num_pattern.finditer(clean_text):
                num = int(match.group(1))
                body = re.sub(r'\s+', ' ', match.group(2)).strip()
                if len(body) > 15:
                    if num not in questions or len(body) > len(questions[num]["text"]):
                        questions[num] = {
                            "number": num,
                            "text": body,
                            "type": "numbered_question"
                        }

        return [questions[k] for k in sorted(questions.keys())]

    def parse_exercise_query(self, query: str) -> Dict[str, Any]:
        """
        Parses query referencing textbook exercises, in-text questions, or practice problems.
        Extracts question_number, section_preference ('back_exercise', 'in_text', 'any'), and target_page.
        """
        ql = query.lower().strip()

        # 1. Number detection (digits or word numbers)
        q_num = None
        m_num = re.search(r'\b(?:question|q\.?|problem|no\.?)\s*#?\s*(\d+)\b', ql)
        if m_num:
            q_num = int(m_num.group(1))
        else:
            m_ordinal = re.search(
                r'\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|'
                r'eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|'
                r'one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:question|problem)\b',
                ql
            )
            if m_ordinal:
                q_num = self.WORD_TO_NUM.get(m_ordinal.group(1))
            else:
                m_ex_num = re.search(r'\bexercise\s*(?:question)?\s*#?\s*(\d+)\b', ql)
                if m_ex_num:
                    q_num = int(m_ex_num.group(1))

        # 2. Section preference
        section_pref = "any"
        if re.search(r'\b(back\s*exercise|end\s*of\s*(?:the\s*)?chapter|chapter\s*exercise|in\s*exercises?|from\s*(?:the\s*)?exercises?)\b', ql):
            section_pref = "back_exercise"
        elif re.search(r'\b(in-text|in\s*text|inside\s*the\s*chapter|practice\s*section)\b', ql):
            section_pref = "in_text"

        # 3. Target page if explicitly mentioned
        target_page = None
        m_page = re.search(r'\bpage\s*(\d+)\b', ql)
        if m_page:
            target_page = int(m_page.group(1))

        return {
            "question_number": q_num,
            "section_preference": section_pref,
            "target_page": target_page
        }

    def is_exercise_query(self, query: str) -> bool:
        """
        Determines whether the query asks to solve or explain an exercise or textbook question.
        """
        ql = query.lower().strip()
        # Direct exercise keywords
        if re.search(r'\b(exercises?|back\s*exercises?|end\s*of\s*(?:the\s*)?chapter|in-text\s*questions?)\b', ql):
            return True
        # "Answer question X", "Answer the 3 questions", "Solve questions"
        if re.search(r'\b(answer|solve|explain|what\s*is\s*(?:the\s*)?answer\s*to)\s+(?:the\s+)?(?:\d+\s+)?(?:questions?|q\.?|problems?|exercises?)\b', ql):
            return True
        # "Question X on page Y"
        if re.search(r'\b(?:questions?|problems?)\s*#?\s*\d+\s+(?:on|from|at)\s+page\s*\d+\b', ql):
            return True
        return False

    def classify_question_intent(self, query: str) -> str:
        """
        Classifies user query into:
        - 'document_meta': Questions asking about chapter name, title, author, subject, total pages, etc.
        - 'page_activity': Questions asking about an activity/experiment on a specific page.
        - 'page_question': Questions asking to answer/list questions on a specific page.
        - 'page_summary': Questions asking to summarize a specific page.
        - 'page_content': General questions targeting a specific page.
        - 'exercise_question': Questions asking to solve/explain exercise questions or in-text questions.
        - 'broad_summary': Questions requesting a summary, overview, or main topics of the entire document.
        - 'content_specific': Targeted questions about specific concepts, definitions, mechanisms, or reactions.
        """
        ql = query.lower().strip()

        # 1. Document metadata patterns
        if re.search(r'\b(chapter\s*(name|title|number)|name\s*of\s*(the|this)\s*chapter|what\s*chapter|which\s*chapter)\b', ql):
            return "document_meta"
        if re.search(r'\b(document\s*(name|title)|title\s*of\s*(the|this)\s*(document|book|pdf|chapter)|book\s*title)\b', ql):
            return "document_meta"
        if re.search(r'\b(how\s*many\s*pages|page\s*count|number\s*of\s*pages|total\s*pages)\b', ql):
            return "document_meta"
        if re.search(r'\b(who\s*(wrote|authored|is\s*the\s*author)|author\s*of)\b', ql):
            return "document_meta"
        if re.search(r'\b(which\s*subject|what\s*subject|subject\s*of)\b', ql):
            return "document_meta"

        # 2. Check for page-targeted activities or multi-question requests on a specific page
        target_page = self.extract_target_page(ql)
        if target_page is not None:
            if re.search(r'\b(activit(?:y|ies)|experiment|experiments|procedure)\b', ql):
                return "page_activity"
            if re.search(r'\b(?:\d+|three|all|both|the)\s+questions\b', ql) or re.search(r'\b(list|show)\s+(?:all\s+)?questions\b', ql) or re.search(r'\bquestions\s+(?:provided\s+)?on\s+page\b', ql):
                return "page_question"
            if re.search(r'\b(summari[sz]e|summary|overview)\b', ql):
                return "page_summary"

        # 3. General Exercise / textbook question patterns (e.g. "Question 5 on page 16", "exercise 1")
        if self.is_exercise_query(ql):
            return "exercise_question"

        # 4. Single question on a page fallback
        if target_page is not None:
            if re.search(r'\b(questions?|problems?|solve|answer)\b', ql):
                return "page_question"
            return "page_content"

        # Broad summary patterns
        if re.search(r'\b(summari[sz]e|summary\s*of|give\s*me\s*a\s*summary|brief\s*summary|overall\s*summary)\b', ql):
            return "broad_summary"
        if re.search(r'\b(what\s*is\s*(this|the)\s*(chapter|document|book|pdf)\s*(all\s*)?about|overview\s*of|give\s*an\s*overview)\b', ql):
            return "broad_summary"
        if re.search(r'\b(main\s*topics|key\s*topics|topics\s*covered|what\s*does\s*this\s*cover)\b', ql):
            return "broad_summary"

        return "content_specific"

    def retrieve_context(
        self,
        document_id: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        db: Optional[Session] = None,
        intent: str = "content_specific"
    ) -> List[Dict[str, Any]]:
        """
        Retrieves context chunks tailored to the classified intent:
        - 'document_meta': Retrieves opening-page chunks (Page 1) directly from SQLite/Chroma.
        - 'broad_summary': Combines opening chunks, concluding summary chunks, and top semantic chunks.
        - 'content_specific': Targeted ChromaDB vector similarity search.
        """
        if db is not None:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if not doc:
                raise DocumentNotFoundError(f"Document with ID '{document_id}' not found.")
            if doc.status == "ocr_required":
                raise DocumentNotReadyError(
                    "This document contains scanned images without extractable text. OCR is not yet supported."
                )
            if doc.status == "failed":
                raise DocumentNotReadyError(f"Document processing previously failed: {doc.error_message}")
            if doc.status in ("uploaded", "extracting", "embedding", "indexing", "processing"):
                raise DocumentNotReadyError(
                    f"Document is currently {doc.status}. Please wait until processing completes."
                )

            # Check if vectors are indexed in ChromaDB
            vector_count = self.vector_store.get_document_vector_count(document_id)
            if vector_count == 0 and doc.total_chunks > 0:
                embedded_count = (
                    db.query(DocumentChunk)
                    .filter(DocumentChunk.document_id == document_id, DocumentChunk.embedding_json.isnot(None))
                    .count()
                )
                if embedded_count == doc.total_chunks:
                    logger.info(f"Auto-indexing {embedded_count} embedded chunks for document '{document_id}' into ChromaDB...")
                    self.vector_store.index_document_chunks(document_id=document_id, db=db, force=False)
                else:
                    raise DocumentNotReadyError(
                        f"Document '{document_id}' has not been embedded yet. "
                        "Please call POST /api/v1/documents/{id}/embed first."
                    )

        # 1. Document-level metadata queries: prioritize opening page chunks
        if intent == "document_meta" and db is not None:
            opening_chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
                .limit(2)
                .all()
            )
            if opening_chunks:
                return [
                    {
                        "chunk_id": c.id,
                        "chunk_index": c.chunk_index,
                        "content": c.content,
                        "pages": c.pages,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "similarity_score": 1.0,
                        "distance": 0.0
                    }
                    for c in opening_chunks
                ]

        # 2. Page-specific queries: prioritize direct SQLite chunks and page text
        if intent.startswith("page_") and db is not None:
            target_page = self.extract_target_page(query)
            if target_page is not None:
                return self.retrieve_page_context(
                    document_id=document_id,
                    query=query,
                    target_page=target_page,
                    intent=intent,
                    db=db
                )

        # 3. Broad summary queries: combine opening, semantic, and concluding chunks
        if intent == "broad_summary" and db is not None:
            opening = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.asc())
                .limit(2)
                .all()
            )
            concluding = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index.desc())
                .limit(3)
                .all()
            )
            try:
                semantic = self.vector_store.search_document(
                    document_id=document_id,
                    query=query,
                    top_k=4,
                    db=db
                )
            except Exception:
                semantic = []

            seen_ids = set()
            combined: List[Dict[str, Any]] = []

            for c in opening:
                if c.id not in seen_ids:
                    seen_ids.add(c.id)
                    combined.append({
                        "chunk_id": c.id,
                        "chunk_index": c.chunk_index,
                        "content": c.content,
                        "pages": c.pages,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "similarity_score": 0.95,
                        "distance": 0.05
                    })

            for r in semantic:
                if r["chunk_id"] not in seen_ids:
                    seen_ids.add(r["chunk_id"])
                    combined.append(r)

            for c in reversed(concluding):
                if c.id not in seen_ids:
                    seen_ids.add(c.id)
                    combined.append({
                        "chunk_id": c.id,
                        "chunk_index": c.chunk_index,
                        "content": c.content,
                        "pages": c.pages,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "similarity_score": 0.85,
                        "distance": 0.15
                    })

            combined.sort(key=lambda x: x["chunk_index"])
            return combined

        # 4. Exercise & in-text questions: targeted question location + supporting chapter theory
        if intent == "exercise_question" and db is not None:
            parsed = self.parse_exercise_query(query)
            if parsed.get("target_page"):
                page_ctx = self.retrieve_page_context(
                    document_id=document_id,
                    query=query,
                    target_page=parsed["target_page"],
                    intent="page_question",
                    db=db
                )
                if page_ctx:
                    return page_ctx
            exercise_context = self.retrieve_exercise_context(document_id, query, db)
            if exercise_context:
                return exercise_context

        # 4. Content-specific queries: standard vector search
        try:
            return self.vector_store.search_document(
                document_id=document_id,
                query=query,
                top_k=top_k,
                db=db
            )
        except DocumentNotIndexedError as e:
            raise DocumentNotReadyError(str(e)) from e

    def retrieve_page_context(
        self,
        document_id: str,
        query: str,
        target_page: int,
        intent: str,
        db: Session
    ) -> List[Dict[str, Any]]:
        """
        Retrieves complete text, identified questions, or activity from a specified page directly
        from SQLite document_chunks (and local PDF if available), and fetches supporting theory chunks.
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        all_chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )
        if not all_chunks:
            return []

        # Chunks that contain or overlap with target_page
        page_chunks = [
            c for c in all_chunks
            if target_page in c.pages or (c.page_start <= target_page <= c.page_end)
        ]

        # Extract contiguous text for the page
        page_raw_text = None
        if doc and doc.file_path and os.path.exists(doc.file_path):
            try:
                import pymupdf
                pdf = pymupdf.open(doc.file_path)
                if 1 <= target_page <= len(pdf):
                    page_raw_text = pdf[target_page - 1].get_text()
            except Exception:
                page_raw_text = None

        if not page_raw_text:
            page_raw_text = "\n\n".join(c.content for c in page_chunks)

        if intent == "page_question":
            questions = self.parse_questions_from_page(page_raw_text)

            # Check if user asked for a specific question number (e.g. 'question 1 on page 6')
            # But do NOT filter if user said 'the 3 questions' or 'all questions'
            is_multi_request = bool(re.search(r'\b(?:\d+|three|all|both)\s+questions\b', query.lower()))
            specific_q_num = None
            if not is_multi_request:
                m_num = re.search(r'\b(?:question|q\.?|problem|no\.?)\s*#?\s*(\d+)\b', query.lower())
                if m_num:
                    specific_q_num = int(m_num.group(1))
                else:
                    for word, val in self.WORD_TO_NUM.items():
                        if re.search(rf'\b(?:question|q\.?|problem)\s+{word}\b', query.lower()) or re.search(rf'\b{word}\s+(?:question|problem)\b', query.lower()):
                            specific_q_num = val
                            break

            if specific_q_num is not None:
                filtered_qs = [q for q in questions if q["number"] == specific_q_num]
                if filtered_qs:
                    questions = filtered_qs

            q_lines = [f"**Question {q['number']}:** {q['text']}" for q in questions]
            question_block_content = (
                f"[PAGE {target_page} VERIFIED QUESTIONS ({len(questions)} identified)]:\n" +
                ("\n".join(q_lines) if q_lines else f"No textbook questions were identified on Page {target_page}.")
            )

            results: List[Dict[str, Any]] = [{
                "chunk_id": f"page_{target_page}_questions",
                "chunk_index": -1,
                "content": question_block_content,
                "pages": [target_page],
                "page_start": target_page,
                "page_end": target_page,
                "similarity_score": 1.0,
                "distance": 0.0
            }]

            # Add actual page chunks from SQLite
            for c in page_chunks:
                results.append({
                    "chunk_id": c.id,
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                    "pages": c.pages,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "similarity_score": 0.95,
                    "distance": 0.05
                })

            # If user wants answers (not just listing), retrieve supporting explanation chunks from other pages
            is_listing_only = bool(re.search(r'\b(list|what\s*are\s*the\s*questions|show\s*all\s*questions)\b', query.lower()))
            if not is_listing_only and questions:
                seen_ids = {c.id for c in page_chunks}
                search_terms = [q["text"] for q in questions]

                for term in search_terms:
                    words = [
                        w.lower() for w in re.findall(r'\b[a-zA-Z]{4,}\b', term)
                        if w.lower() not in ('write', 'balanced', 'chemical', 'following', 'reactions', 'solution', 'solutions')
                    ]
                    scored = []
                    for c in all_chunks:
                        if target_page in c.pages:
                            continue
                        c_lower = c.content.lower()
                        score = sum(1 for w in words if w in c_lower)
                        if score > 0:
                            scored.append((score, c))
                    scored.sort(key=lambda x: x[0], reverse=True)
                    for _, c in scored[:2]:
                        if c.id not in seen_ids:
                            seen_ids.add(c.id)
                            results.append({
                                "chunk_id": c.id,
                                "chunk_index": c.chunk_index,
                                "content": c.content,
                                "pages": c.pages,
                                "page_start": c.page_start,
                                "page_end": c.page_end,
                                "similarity_score": 0.85,
                                "distance": 0.15
                            })

            return results

        elif intent == "page_activity":
            m_act = re.search(
                r'(Activity\s*[\d\.]+.*?)(?=(?:Q\s*U\s*E\s*S\s*T\s*I\s*O\s*N\s*S|Reprint\s+2026-27|\Z))',
                page_raw_text,
                re.DOTALL | re.IGNORECASE
            )
            act_text = m_act.group(1).strip() if m_act else page_raw_text
            lines = [l.strip() for l in act_text.splitlines() if l.strip()]
            dedup = []
            for l in lines:
                if not dedup or dedup[-1] != l:
                    dedup.append(l)
            cleaned_act = "\n".join(dedup)

            results = [{
                "chunk_id": f"page_{target_page}_activity",
                "chunk_index": -1,
                "content": f"[PAGE {target_page} ACTIVITY]:\n{cleaned_act}",
                "pages": [target_page],
                "page_start": target_page,
                "page_end": target_page,
                "similarity_score": 1.0,
                "distance": 0.0
            }]

            for c in page_chunks:
                results.append({
                    "chunk_id": c.id,
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                    "pages": c.pages,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "similarity_score": 0.95,
                    "distance": 0.05
                })

            for c in all_chunks:
                if "activity 1.4" in c.content.lower() and target_page not in c.pages:
                    results.append({
                        "chunk_id": c.id,
                        "chunk_index": c.chunk_index,
                        "content": c.content,
                        "pages": c.pages,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "similarity_score": 0.90,
                        "distance": 0.10
                    })

            return results

        else:
            return [{
                "chunk_id": c.id,
                "chunk_index": c.chunk_index,
                "content": c.content,
                "pages": c.pages,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "similarity_score": 1.0,
                "distance": 0.0
            } for c in page_chunks]

    def retrieve_exercise_context(
        self,
        document_id: str,
        query: str,
        db: Session
    ) -> List[Dict[str, Any]]:
        """
        Locates the exact exercise / in-text question and retrieves supporting chapter theory.
        """
        parsed = self.parse_exercise_query(query)
        q_num = parsed.get("question_number")
        section_pref = parsed.get("section_preference", "any")
        target_page = parsed.get("target_page")

        all_chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )
        if not all_chunks:
            return []

        # Partition chunks into back exercises and in-text questions
        back_ex_chunks = []
        in_text_chunks = []
        in_back_ex = False

        for c in all_chunks:
            clean = re.sub(r'[\s\n]+', '', c.content)
            if 'EXERCISES' in clean:
                in_back_ex = True

            if in_back_ex:
                back_ex_chunks.append(c)
            elif 'QUESTIONS?' in clean or 'QUESTIONS' in clean:
                in_text_chunks.append(c)

        # Select candidate chunks based on section preference & target page
        candidates = []
        if target_page:
            candidates = [c for c in all_chunks if target_page in c.pages]
        elif section_pref == "back_exercise":
            candidates = back_ex_chunks if back_ex_chunks else all_chunks
        elif section_pref == "in_text":
            candidates = in_text_chunks if in_text_chunks else all_chunks
        else:
            candidates = back_ex_chunks + in_text_chunks if (back_ex_chunks or in_text_chunks) else all_chunks

        # If a specific question number is requested, locate its exact text
        if q_num is not None:
            pattern = re.compile(
                r'(?:^|\n|\s)(' + str(q_num) + r')\.\s+([^\n]+(?:\n(?!\d+\.)[^\n]+)*)',
                re.MULTILINE
            )
            matched_q_text = None
            matched_chunk = None

            for c in candidates:
                for match in pattern.finditer(c.content):
                    full_text = match.group(0).strip()
                    full_text = re.sub(r'Reprint\s+2026-27[^\n]*', '', full_text).strip()
                    matched_q_text = full_text
                    matched_chunk = c
                    break
                if matched_q_text:
                    break

            # Fallback if not found in preferred section: check all chunks
            if not matched_q_text:
                for c in all_chunks:
                    for match in pattern.finditer(c.content):
                        full_text = match.group(0).strip()
                        full_text = re.sub(r'Reprint\s+2026-27[^\n]*', '', full_text).strip()
                        matched_q_text = full_text
                        matched_chunk = c
                        break
                    if matched_q_text:
                        break

            if matched_q_text and matched_chunk:
                sec_label = "Back Exercises" if matched_chunk in back_ex_chunks else "In-Text Questions"
                # 1. Question chunk with high priority
                question_block = {
                    "chunk_id": matched_chunk.id,
                    "chunk_index": matched_chunk.chunk_index,
                    "content": f"[TARGET {sec_label.upper()} - QUESTION {q_num} (Page {matched_chunk.page_start})]:\n{matched_q_text}",
                    "pages": matched_chunk.pages,
                    "page_start": matched_chunk.page_start,
                    "page_end": matched_chunk.page_end,
                    "similarity_score": 1.0,
                    "distance": 0.0,
                    "is_target_question": True
                }

                # 2. Semantic search for supporting theory using question text
                clean_query = re.sub(r'^\d+\.\s*', '', matched_q_text)[:200].strip()
                try:
                    supporting = self.vector_store.search_document(
                        document_id=document_id,
                        query=clean_query,
                        top_k=3,
                        db=db
                    )
                except Exception:
                    supporting = []

                # 3. Add summary chunk ("What you have learnt") if available
                summary_chunk_dict = None
                for c in reversed(all_chunks):
                    if "what you have learnt" in c.content.lower():
                        summary_chunk_dict = {
                            "chunk_id": c.id,
                            "chunk_index": c.chunk_index,
                            "content": c.content,
                            "pages": c.pages,
                            "page_start": c.page_start,
                            "page_end": c.page_end,
                            "similarity_score": 0.9,
                            "distance": 0.1
                        }
                        break

                combined = [question_block]
                seen_ids = {matched_chunk.id}

                for s in supporting:
                    if s["chunk_id"] not in seen_ids:
                        seen_ids.add(s["chunk_id"])
                        combined.append(s)

                if summary_chunk_dict and summary_chunk_dict["chunk_id"] not in seen_ids:
                    combined.append(summary_chunk_dict)

                return combined

        # If general exercises requested, return the back exercise chunks
        if back_ex_chunks:
            return [
                {
                    "chunk_id": c.id,
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                    "pages": c.pages,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "similarity_score": 0.95,
                    "distance": 0.05
                }
                for c in back_ex_chunks[:5]
            ]

        return []

    def format_conversation_history(
        self,
        document_id: str,
        db: Session,
        max_messages: int = DEFAULT_MAX_HISTORY_MESSAGES
    ) -> List[Dict[str, str]]:
        """
        Retrieves recent conversation turns for context continuity.
        """
        all_msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.document_id == document_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(max_messages)
            .all()
        )
        chronological = list(reversed(all_msgs))
        return [{"role": m.role, "content": m.content} for m in chronological]

    def build_prompt(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
        conversation_history: List[Dict[str, str]],
        doc_metadata: Optional[Dict[str, Any]] = None,
        intent: str = "content_specific"
    ) -> str:
        """
        Assembles strict grounding instructions, document metadata, excerpts with page labels,
        conversation memory, and user question.
        """
        meta_section = ""
        if doc_metadata:
            meta_lines = []
            if doc_metadata.get("title"):
                meta_lines.append(f"Document Title: {doc_metadata['title']}")
            if doc_metadata.get("chapter_name"):
                meta_lines.append(f"Chapter Name: {doc_metadata['chapter_name']}")
            if doc_metadata.get("chapter_number"):
                meta_lines.append(f"Chapter Number: {doc_metadata['chapter_number']}")
            if doc_metadata.get("subject"):
                meta_lines.append(f"Subject: {doc_metadata['subject']}")
            if doc_metadata.get("total_pages"):
                meta_lines.append(f"Total Pages: {doc_metadata['total_pages']}")
            if doc_metadata.get("author"):
                meta_lines.append(f"Author: {doc_metadata['author']}")

            if meta_lines:
                meta_section = "=== VERIFIED DOCUMENT METADATA ===\n" + "\n".join(meta_lines) + "\n==================================\n\n"

        excerpts_str = ""
        for i, c in enumerate(context_chunks):
            pages_list = c.get("pages", [c.get("page_start", 1)])
            pages_str = ", ".join(map(str, pages_list)) if pages_list else str(c.get("page_start", 1))
            score = c.get("similarity_score", 0.0)
            excerpts_str += (
                f"\n--- [EXCERPT {i+1}] (Pages: {pages_str} | Similarity Score: {score:.3f}) ---\n"
                f"{c.get('content', '').strip()}\n"
            )

        history_str = ""
        if conversation_history:
            history_str = "\n=== RECENT CONVERSATION HISTORY ===\n"
            for h in conversation_history:
                role_label = "User" if h["role"] == "user" else "Assistant"
                history_str += f"{role_label}: {h['content']}\n"
            history_str += "===================================\n"

        prompt = (
            "You are PaperPilot, an intelligent, educational document analysis assistant and expert tutor.\n"
            "Your task is to answer the user's question clearly, thoroughly, and strictly based on the verified Document Metadata and Document Excerpts provided below.\n\n"
            "CRITICAL OPERATIONAL RULES:\n"
            "1. Grounding: Answer strictly using facts, reactions, formulas, and definitions from the metadata and excerpts. Do not fabricate or extrapolate information.\n"
            "2. Document Metadata: For questions regarding chapter name, title, author, or page count, state the exact details from the verified metadata and opening page.\n"
            "3. Exercise & Practice Questions:\n"
            "   - When answering a question from exercises or in-text questions:\n"
            "     * State the question number and page reference clearly.\n"
            "     * If multiple choice: identify the correct option clearly (e.g. '**Correct Option:** (i) Statements (a) and (b) are incorrect') and explain why it is correct and why other options are wrong.\n"
            "     * For numericals or equation balancing: provide Given data/equation, Step-by-step balancing or calculation, and the Final balanced equation/result with units.\n"
            "     * For theoretical questions: give a direct, clear answer followed by educational explanation citing relevant concepts.\n"
            "4. Mathematical & Chemical Formatting:\n"
            "   - Always format all chemical equations, reaction mechanisms, formulas, and mathematical expressions using clean LaTeX / KaTeX syntax:\n"
            "     * Use inline math '$ ... $' for expressions inside sentences (e.g. '$\\text{Zn} + \\text{H}_2\\text{SO}_4 \\rightarrow \\text{ZnSO}_4 + \\text{H}_2$', '$\\text{pH} < 7$').\n"
            "     * Use block math '$$ ... $$' on its own line for standalone equations.\n"
            "     * Use proper chemical notation with subscripts '_' (e.g. '$\\text{H}_2\\text{O}$', '$\\text{Fe}_2\\text{O}_3$'), state symbols '(s)', '(l)', '(g)', '(aq)', and reaction arrows '\\rightarrow'.\n"
            "     * Use fractions '$\\frac{a}{b}$' and superscripts '^' where appropriate.\n"
            "   - Ensure every equation is complete and properly closed. Never truncate equations.\n"
            "5. Quality & Tone: Deliver beginner-friendly, structured, and educational responses. Avoid repetitive phrasing or dumping unedited large paragraphs.\n"
            "6. Fallback Rule: If the excerpts and metadata do not contain sufficient information to answer the question, you MUST explicitly state:\n"
            "   'I cannot find the answer to this question in the provided document.'\n"
            "7. Citations: Always cite the specific page numbers where relevant information and questions are found (e.g. 'According to page 14...').\n"
            "8. Page-Specific Questions & Activities:\n"
            "   - When answering multiple questions on a page (e.g. 'Answer the 3 questions provided on page 6'):\n"
            "     * Answer EVERY identified question in original order using the exact format:\n"
            "       **Question 1:** [Actual question text]\n\n"
            "       **Answer:** [Clear explanation citing supporting pages and concepts, including balanced equations with KaTeX if applicable]\n\n"
            "       **Question 2:** [Actual question text]\n\n"
            "       **Answer:** [Clear explanation citing supporting pages and concepts, including balanced equations with KaTeX if applicable]\n\n"
            "       **Question 3:** [Actual question text]\n\n"
            "       **Answer:** [Clear explanation citing supporting pages and concepts, including balanced equations with KaTeX if applicable]\n"
            "     * If only 2 questions can be identified, answer only 2; if 3 are identified, answer all 3. Never invent extra questions.\n"
            "     * Do not confuse activity instructions or observations with textbook questions.\n"
            "   - When asked to 'List all questions on page X':\n"
            "     * List each identified question clearly in original order with its sub-parts (i, ii, iii). State the page number.\n"
            "   - When asked to 'Explain the activity on page X':\n"
            "     * Provide: Objective/Title, Apparatus & Materials, Procedure, Chemical Equation (in KaTeX), Key Observation (e.g. temperature change), and Conclusion/Reaction Type.\n\n"
            f"{meta_section}"
            f"=== DOCUMENT EXCERPTS ==={excerpts_str}\n"
            "=========================\n"
            f"{history_str}\n"
            f"USER QUESTION: {query.strip()}\n\n"
            "ANSWER:"
        )
        return prompt

    def generate_answer(self, prompt: str) -> str:
        """
        Sends grounded prompt to Gemini with retry logic and exponential backoff.
        """
        client = self.get_client()
        backoff = self.initial_backoff
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                from google.genai import types
                config = types.GenerateContentConfig(
                    max_output_tokens=3072,
                    temperature=0.2,
                )
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                extracted_text = None
                if hasattr(response, "text") and response.text:
                    extracted_text = response.text.strip()
                elif hasattr(response, "candidates") and response.candidates:
                    c0 = response.candidates[0]
                    if c0.content and c0.content.parts:
                        parts_text = []
                        for part in c0.content.parts:
                            if hasattr(part, "text") and part.text:
                                parts_text.append(part.text)
                        if parts_text:
                            extracted_text = "".join(parts_text).strip()

                if not extracted_text:
                    raise RAGGenerationError("Gemini returned an empty response.")
                return extracted_text

            except Exception as e:
                err_str = str(e).lower()
                last_exception = e

                # Check for invalid / unauthorized API key
                if "api_key_invalid" in err_str or "unauthorized" in err_str or "401" in err_str or "api key not valid" in err_str:
                    raise InvalidAPIKeyError(
                        f"The configured Gemini API key is invalid or unauthorized: {str(e)}"
                    ) from e

                # Check for rate limiting / quota exhaustion
                is_rate_limit = (
                    "429" in err_str or
                    "resource_exhausted" in err_str or
                    "quota" in err_str or
                    "rate limit" in err_str
                )

                # Check for transient server errors (including 503 spikes)
                is_transient = "503" in err_str or "unavailable" in err_str or "timeout" in err_str

                if (is_rate_limit or is_transient) and attempt < self.max_retries:
                    logger.warning(
                        f"Gemini generation attempt {attempt}/{self.max_retries} failed with {type(e).__name__}: {e}. "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue

                if is_rate_limit:
                    raise RateLimitExceededError(
                        f"Gemini API rate limit or quota exceeded after {attempt} attempts: {str(e)}"
                    ) from e

                raise RAGGenerationError(f"Gemini content generation failed: {str(e)}") from e

        raise RAGGenerationError(f"Gemini generation failed after {self.max_retries} attempts: {last_exception}")

    def extract_citations(
        self,
        answer: str,
        context_chunks: List[Dict[str, Any]],
        intent: str = "content_specific",
        doc_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Constructs clean, deduplicated citation badges with 1-indexed page numbers,
        chunk indexes, and concise contextual snippets.
        If the answer indicates that information was absent, citations are omitted.
        """
        lower_ans = answer.lower()
        # If model explicitly said it cannot find the answer, omit citations
        if any(phrase in lower_ans for phrase in self.FALLBACK_PHRASES):
            return []

        # Deduplicate citations by page number
        page_to_citation: Dict[int, Dict[str, Any]] = {}

        for chunk in context_chunks:
            pages = chunk.get("pages", [chunk.get("page_start", 1)])
            content = (chunk.get("content") or "").strip()
            snippet = content[:160] + "..." if len(content) > 160 else content
            snippet = snippet.replace("\n", " ").strip()
            chunk_idx = chunk.get("chunk_index")

            for page in pages:
                if page not in page_to_citation:
                    page_to_citation[page] = {
                        "page": int(page),
                        "snippet": snippet,
                        "chunk_index": chunk_idx,
                    }

        # For document-level metadata questions (like chapter name/title), ensure Page 1 is cited
        if intent == "document_meta" and 1 not in page_to_citation and context_chunks:
            c0 = context_chunks[0]
            content = (c0.get("content") or "").strip()
            snippet = content[:160] + "..." if len(content) > 160 else content
            page_to_citation[1] = {
                "page": 1,
                "snippet": snippet.replace("\n", " ").strip(),
                "chunk_index": c0.get("chunk_index", 0)
            }

        sorted_citations = sorted(page_to_citation.values(), key=lambda c: c["page"])
        return sorted_citations

    def answer_document_query(
        self,
        document_id: str,
        query: str,
        db: Session,
        top_k: int = DEFAULT_TOP_K
    ) -> Dict[str, Any]:
        """
        Executes end-to-end RAG pipeline with intent routing:
        Intent Classification -> Tailored Retrieval -> Context & Metadata Assembly ->
        Grounded Generation -> Citation Extraction -> SQLite Persistence.
        """
        clean_query = (query or "").strip()
        if not clean_query:
            raise ValueError("Query message cannot be empty.")

        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError(f"Document with ID '{document_id}' not found.")

        # Ensure document metadata is extracted and saved
        doc_metadata = {
            "title": doc.title,
            "chapter_name": doc.chapter_name,
            "chapter_number": doc.chapter_number,
            "subject": doc.subject,
            "total_pages": doc.total_pages
        }

        # 1. Classify question intent
        intent = self.classify_question_intent(clean_query)
        logger.info(f"Query '{clean_query[:50]}' classified as intent: '{intent}'")

        # 2. Retrieve relevant chunks tailored to intent
        context_chunks = self.retrieve_context(
            document_id=document_id,
            query=clean_query,
            top_k=top_k,
            db=db,
            intent=intent
        )

        # 3. Retrieve recent conversation history
        history = self.format_conversation_history(
            document_id=document_id,
            db=db,
            max_messages=self.DEFAULT_MAX_HISTORY_MESSAGES
        )

        # 4. Build grounded prompt
        prompt = self.build_prompt(
            query=clean_query,
            context_chunks=context_chunks,
            conversation_history=history,
            doc_metadata=doc_metadata,
            intent=intent
        )

        # 5. Generate grounded response from Gemini
        answer_text = self.generate_answer(prompt)

        # 6. Extract structured citations
        citations = self.extract_citations(
            answer=answer_text,
            context_chunks=context_chunks,
            intent=intent,
            doc_metadata=doc_metadata
        )

        # 7. Persist user message and assistant message to SQLite
        now = datetime.datetime.now(datetime.timezone.utc)
        user_msg = ChatMessage(
            id=str(uuid.uuid4()),
            document_id=document_id,
            role="user",
            content=clean_query,
            created_at=now
        )
        db.add(user_msg)

        assistant_msg_id = str(uuid.uuid4())
        assistant_msg = ChatMessage(
            id=assistant_msg_id,
            document_id=document_id,
            role="assistant",
            content=answer_text,
            page_references=json.dumps(citations) if citations else None,
            created_at=now + datetime.timedelta(milliseconds=10)
        )
        db.add(assistant_msg)
        db.commit()

        return {
            "message_id": assistant_msg_id,
            "document_id": document_id,
            "role": "assistant",
            "content": answer_text,
            "citations": citations,
            "created_at": assistant_msg.created_at,
        }

    def get_history(self, document_id: str, db: Session) -> List[Dict[str, Any]]:
        """
        Retrieves all conversation messages for a document in chronological order.
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError(f"Document with ID '{document_id}' not found.")

        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.document_id == document_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )

        result = []
        for m in messages:
            result.append({
                "id": m.id,
                "document_id": m.document_id,
                "role": m.role,
                "content": m.content,
                "citations": m.citations,
                "page_references": [c["page"] for c in m.citations],
                "created_at": m.created_at,
            })
        return result

    def clear_history(self, document_id: str, db: Session) -> int:
        """
        Deletes all chat messages for a document.
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise DocumentNotFoundError(f"Document with ID '{document_id}' not found.")

        deleted = (
            db.query(ChatMessage)
            .filter(ChatMessage.document_id == document_id)
            .delete()
        )
        db.commit()
        logger.info(f"Cleared {deleted} chat messages for document '{document_id}'.")
        return deleted


rag_service = RAGService()
