import os
import sys
import json
import uuid
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import chromadb

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi import HTTPException
from app.db.session import SessionLocal, init_db
from app.db.models import Document, DocumentChunk, ChatMessage
from app.schemas.chat import DocumentChatRequest, ChatRequest
from app.services.vector_store import VectorStoreService
from app.services.rag_service import (
    RAGService,
    RAGServiceError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    RAGGenerationError
)
from app.api.v1.documents import (
    chat_with_document,
    get_document_chat_history,
    clear_document_chat_history
)
from app.api.v1.chat import (
    send_chat_message,
    get_chat_history,
    clear_chat_history
)


class TestRAGService(unittest.TestCase):
    """
    Automated unit test suite for PaperPilot Phase 2.3:
    Retrieval-Augmented Generation (RAG) and Document Chat.
    """

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.db = SessionLocal()
        # Isolated in-memory ChromaDB vector store
        self.chroma_client = chromadb.Client()
        self.vector_store = VectorStoreService(
            collection_name=f"test_rag_{uuid.uuid4().hex[:8]}",
            client=self.chroma_client
        )
        self.rag = RAGService(
            model_name="gemini-3.5-flash",
            vector_store=self.vector_store,
            max_retries=2,
            initial_backoff=0.01
        )

    def tearDown(self):
        self.db.close()

    def _create_mock_document(
        self,
        num_chunks=3,
        status="ready",
        embedded=True,
        title=None,
        chapter_name=None,
        chapter_number=None,
        subject=None
    ):
        doc_id = str(uuid.uuid4())
        doc_title = title if title is not None else "Chemical Reactions and Equations"
        doc_chapter = chapter_name if chapter_name is not None else "Chemical Reactions and Equations"
        doc_ch_num = chapter_number if chapter_number is not None else "Chapter 1"
        doc_subject = subject if subject is not None else "Science"

        doc = Document(
            id=doc_id,
            filename=f"{doc_id}.pdf",
            original_filename="science_test.pdf",
            file_path=os.path.join(tempfile.gettempdir(), f"{doc_id}.pdf"),
            file_size_bytes=4096,
            total_pages=num_chunks,
            extracted_pages=num_chunks,
            total_characters=2000,
            total_chunks=num_chunks,
            status=status,
            embedding_status="completed" if embedded else "pending",
            title=doc_title,
            chapter_name=doc_chapter,
            chapter_number=doc_ch_num,
            subject=doc_subject,
            doc_metadata_json=json.dumps({
                "title": doc_title,
                "chapter_name": doc_chapter,
                "chapter_number": doc_ch_num,
                "subject": doc_subject,
                "total_pages": num_chunks
            })
        )
        self.db.add(doc)

        dummy_vectors = [
            [0.1 if j % 2 == 0 else -0.1 for j in range(768)],
            [0.2 if j % 3 == 0 else -0.05 for j in range(768)],
            [0.3 if j % 4 == 0 else 0.05 for j in range(768)],
        ]

        sample_texts = [
            "Activity 1.1: Burning of a magnesium ribbon in air. It burns with a dazzling white flame and changes into a white powder of magnesium oxide.",
            "Chemical equation: 2Mg + O2 -> 2MgO. Magnesium and oxygen are reactants and magnesium oxide is the product.",
            "Corrosion and Rancidity: When fats and oils are oxidised, they become rancid and their smell and taste change. Antioxidants prevent oxidation."
        ]

        for i in range(num_chunks):
            emb = dummy_vectors[i % len(dummy_vectors)] if embedded else None
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=doc_id,
                chunk_index=i,
                content=sample_texts[i % len(sample_texts)],
                char_count=len(sample_texts[i % len(sample_texts)]),
                page_start=i + 1,
                page_end=i + 1,
                pages_json=json.dumps([i + 1]),
                embedding_json=json.dumps(emb) if emb else None,
                embedding_dimension=768 if emb else None
            )
            self.db.add(chunk)

        self.db.commit()

        if embedded:
            self.vector_store.index_document_chunks(doc_id, self.db)

        return doc

    # 1. Prompt Construction & Grounding Formatting
    def test_build_prompt(self):
        chunks = [
            {
                "content": "Magnesium burns with a white flame to form magnesium oxide.",
                "pages": [1, 2],
                "page_start": 1,
                "similarity_score": 0.85,
                "chunk_index": 0
            }
        ]
        history = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there"}]
        prompt = self.rag.build_prompt("What happens to magnesium?", chunks, history)

        self.assertIn("USER QUESTION: What happens to magnesium?", prompt)
        self.assertIn("Pages: 1, 2", prompt)
        self.assertIn("Magnesium burns with a white flame", prompt)
        self.assertIn("User: Hello", prompt)
        self.assertIn("CRITICAL OPERATIONAL RULES", prompt)

    # 1b. Prompt Construction with Document Metadata
    def test_build_prompt_with_metadata(self):
        chunks = [
            {"content": "Chapter 1 Chemical Reactions.", "pages": [1], "page_start": 1, "similarity_score": 1.0, "chunk_index": 0}
        ]
        meta = {
            "title": "Chemical Reactions and Equations",
            "chapter_name": "Chemical Reactions and Equations",
            "chapter_number": "Chapter 1",
            "subject": "Science",
            "total_pages": 16
        }
        prompt = self.rag.build_prompt(
            "What is the chapter name?",
            chunks,
            conversation_history=[],
            doc_metadata=meta,
            intent="document_meta"
        )
        self.assertIn("=== VERIFIED DOCUMENT METADATA ===", prompt)
        self.assertIn("Chapter Name: Chemical Reactions and Equations", prompt)
        self.assertIn("Chapter Number: Chapter 1", prompt)
        self.assertIn("Subject: Science", prompt)

    # 1c. Question Intent Classification Routing
    def test_classify_question_intent(self):
        # Document-level metadata queries
        self.assertEqual(self.rag.classify_question_intent("What is the chapter name?"), "document_meta")
        self.assertEqual(self.rag.classify_question_intent("What is the name of this chapter?"), "document_meta")
        self.assertEqual(self.rag.classify_question_intent("What is the document title?"), "document_meta")
        self.assertEqual(self.rag.classify_question_intent("How many pages are in this book?"), "document_meta")
        self.assertEqual(self.rag.classify_question_intent("Which subject is this?"), "document_meta")

        # Broad exploratory queries
        self.assertEqual(self.rag.classify_question_intent("Summarise the chapter."), "broad_summary")
        self.assertEqual(self.rag.classify_question_intent("What is this chapter about?"), "broad_summary")
        self.assertEqual(self.rag.classify_question_intent("Give me an overview of the main topics"), "broad_summary")

        # Exercise & textbook question queries
        self.assertEqual(self.rag.classify_question_intent("Answer question 1 in exercises."), "exercise_question")
        self.assertEqual(self.rag.classify_question_intent("Solve question 2 from the back exercise."), "exercise_question")
        self.assertEqual(self.rag.classify_question_intent("Explain the second question at the end of the chapter."), "exercise_question")
        self.assertEqual(self.rag.classify_question_intent("What is the answer to question 5 on page 16?"), "exercise_question")
        self.assertEqual(self.rag.classify_question_intent("Solve question 2 from the practice section."), "exercise_question")
        self.assertEqual(self.rag.classify_question_intent("Answer in-text question 1 on page 6."), "exercise_question")

        # Content-specific queries
        self.assertEqual(self.rag.classify_question_intent("What happens when magnesium ribbon is burned in air?"), "content_specific")
        self.assertEqual(self.rag.classify_question_intent("What is rancidity?"), "content_specific")
        self.assertEqual(self.rag.classify_question_intent("Define exothermic reaction."), "content_specific")

    # 1c-2. Exercise Query Parsing
    def test_parse_exercise_query(self):
        p1 = self.rag.parse_exercise_query("Answer question 1 in exercises.")
        self.assertEqual(p1["question_number"], 1)
        self.assertEqual(p1["section_preference"], "back_exercise")

        p2 = self.rag.parse_exercise_query("Explain the second question at the end of the chapter.")
        self.assertEqual(p2["question_number"], 2)
        self.assertEqual(p2["section_preference"], "back_exercise")

        p3 = self.rag.parse_exercise_query("What is the answer to question 5 on page 16?")
        self.assertEqual(p3["question_number"], 5)
        self.assertEqual(p3["target_page"], 16)

        p4 = self.rag.parse_exercise_query("In-text question 3 on page 13")
        self.assertEqual(p4["question_number"], 3)
        self.assertEqual(p4["section_preference"], "in_text")
        self.assertEqual(p4["target_page"], 13)

    # 1c-3. Exercise Context Retrieval
    def test_retrieve_context_exercise_question(self):
        doc = self._create_mock_document(num_chunks=4)
        # Add an exercise chunk with numbered question
        ex_chunk = DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=doc.id,
            chunk_index=4,
            content="EXERCISES\n1. Which of the statements about the reaction below are incorrect? 2PbO + C -> 2Pb + CO2\n2. Fe2O3 + 2Al -> Al2O3 + 2Fe",
            char_count=150,
            page_start=14,
            page_end=15,
            pages_json=json.dumps([14, 15]),
            embedding_json=json.dumps([0.1] * 768),
            embedding_dimension=768
        )
        self.db.add(ex_chunk)
        self.db.commit()

        dummy_query_vec = [[0.1] * 768]
        with patch("app.services.vector_store.embedding_service.generate_embeddings_for_batch", return_value=dummy_query_vec):
            context = self.rag.retrieve_context(
                document_id=doc.id,
                query="Answer question 1 in exercises.",
                intent="exercise_question",
                db=self.db
            )
        self.assertTrue(len(context) > 0)
        # First chunk must be the target exercise question
        self.assertIn("Which of the statements", context[0]["content"])
        self.assertIn(14, context[0]["pages"])

    # 1d. Intent-Tailored Context Retrieval for Document Metadata
    def test_retrieve_context_document_meta(self):
        doc = self._create_mock_document(num_chunks=5)
        # Should retrieve opening chunks (indices 0 and 1) with score 1.0
        context = self.rag.retrieve_context(
            document_id=doc.id,
            query="What is the chapter name?",
            intent="document_meta",
            db=self.db
        )
        self.assertEqual(len(context), 2)
        self.assertEqual(context[0]["chunk_index"], 0)
        self.assertEqual(context[1]["chunk_index"], 1)
        self.assertEqual(context[0]["page_start"], 1)

    # 1e. Intent-Tailored Context Retrieval for Broad Summary
    def test_retrieve_context_broad_summary(self):
        doc = self._create_mock_document(num_chunks=6)
        dummy_query_vector = [[0.1] * 768]
        with patch("app.services.vector_store.embedding_service.generate_embeddings_for_batch", return_value=dummy_query_vector):
            context = self.rag.retrieve_context(
                document_id=doc.id,
                query="Summarise the chapter.",
                intent="broad_summary",
                db=self.db
            )
        # Should include opening chunks (0, 1) and concluding chunks (4, 5)
        indices = [c["chunk_index"] for c in context]
        self.assertIn(0, indices)
        self.assertIn(5, indices)

    # 1f. Answer Document Metadata Query E2E
    def test_answer_document_metadata_query(self):
        doc = self._create_mock_document(
            num_chunks=3,
            title="Chemical Reactions and Equations",
            chapter_name="Chemical Reactions and Equations",
            chapter_number="Chapter 1"
        )
        mock_answer = (
            "The chapter name is 'Chemical Reactions and Equations' (Chapter 1) as indicated on page 1."
        )
        with patch.object(self.rag, "generate_answer", return_value=mock_answer):
            result = self.rag.answer_document_query(
                document_id=doc.id,
                query="What is the chapter name?",
                db=self.db
            )
        self.assertEqual(result["content"], mock_answer)
        self.assertTrue(len(result["citations"]) > 0)
        self.assertEqual(result["citations"][0]["page"], 1)

    # 2. Structured Citation Extraction
    def test_extract_citations(self):
        chunks = [
            {"pages": [1], "page_start": 1, "content": "Burning magnesium ribbon produces magnesium oxide.", "chunk_index": 0},
            {"pages": [2, 3], "page_start": 2, "content": "The reaction is represented as 2Mg + O2 -> 2MgO.", "chunk_index": 1}
        ]
        answer = "When magnesium burns, it forms magnesium oxide as explained on page 1 and page 2."
        citations = self.rag.extract_citations(answer, chunks)

        self.assertEqual(len(citations), 3)  # Pages 1, 2, 3
        pages = [c["page"] for c in citations]
        self.assertEqual(pages, [1, 2, 3])
        self.assertTrue(all("snippet" in c for c in citations))

    # 3. Citation Omission on Fallback / Unanswered Questions
    def test_extract_citations_omitted_for_fallback(self):
        chunks = [
            {"pages": [1], "page_start": 1, "content": "Some chemistry topic.", "chunk_index": 0}
        ]
        fallback_answer = "I cannot find the answer to this question in the provided document."
        citations = self.rag.extract_citations(fallback_answer, chunks)
        self.assertEqual(citations, [])

    # 4. End-to-End Grounded Question & Answer with Citations
    def test_answer_document_query_success(self):
        doc = self._create_mock_document()
        dummy_query_vector = [[0.1 if j % 2 == 0 else -0.1 for j in range(768)]]
        mock_answer = (
            "When a magnesium ribbon is burned in air, it reacts with oxygen to form magnesium oxide "
            "as a white powder, accompanied by a dazzling white flame (Pages 1, 2)."
        )

        with patch("app.services.vector_store.embedding_service.generate_embeddings_for_batch", return_value=dummy_query_vector):
            with patch.object(self.rag, "generate_answer", return_value=mock_answer):
                result = self.rag.answer_document_query(
                    document_id=doc.id,
                    query="What happens when magnesium burns in air?",
                    db=self.db,
                    top_k=2
                )

        self.assertEqual(result["document_id"], doc.id)
        self.assertEqual(result["role"], "assistant")
        self.assertEqual(result["content"], mock_answer)
        self.assertTrue(len(result["citations"]) > 0)
        self.assertIn("message_id", result)

        # Verify messages persisted in SQLite
        history = self.db.query(ChatMessage).filter(ChatMessage.document_id == doc.id).all()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].role, "user")
        self.assertEqual(history[0].content, "What happens when magnesium burns in air?")
        self.assertEqual(history[1].role, "assistant")
        self.assertEqual(history[1].content, mock_answer)

    # 5. Question Absent from Document Returns Explicit Fallback
    def test_answer_document_query_absent_question(self):
        doc = self._create_mock_document()
        dummy_query_vector = [[0.01] * 768]
        fallback_answer = "I cannot find the answer to this question in the provided document."

        with patch("app.services.vector_store.embedding_service.generate_embeddings_for_batch", return_value=dummy_query_vector):
            with patch.object(self.rag, "generate_answer", return_value=fallback_answer):
                result = self.rag.answer_document_query(
                    document_id=doc.id,
                    query="What is the capital of Australia?",
                    db=self.db,
                    top_k=2
                )

        self.assertEqual(result["content"], fallback_answer)
        # Citations must be empty for ungrounded/absent topics
        self.assertEqual(result["citations"], [])

    # 6. Chat History Retrieval
    def test_get_history(self):
        doc = self._create_mock_document()
        # Seed 2 conversation rounds
        msg1 = ChatMessage(id=str(uuid.uuid4()), document_id=doc.id, role="user", content="Question 1")
        msg2 = ChatMessage(id=str(uuid.uuid4()), document_id=doc.id, role="assistant", content="Answer 1", page_references=json.dumps([{"page": 1, "snippet": "Text 1"}]))
        self.db.add_all([msg1, msg2])
        self.db.commit()

        history = self.rag.get_history(doc.id, self.db)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[1]["citations"][0]["page"], 1)

    # 7. Clear Chat History
    def test_clear_history(self):
        doc = self._create_mock_document()
        msg1 = ChatMessage(id=str(uuid.uuid4()), document_id=doc.id, role="user", content="Question 1")
        self.db.add(msg1)
        self.db.commit()

        deleted = self.rag.clear_history(doc.id, self.db)
        self.assertEqual(deleted, 1)

        history_after = self.rag.get_history(doc.id, self.db)
        self.assertEqual(len(history_after), 0)

    # 8. Document Isolation in Chat History
    def test_document_isolation(self):
        doc1 = self._create_mock_document()
        doc2 = self._create_mock_document()

        msg1 = ChatMessage(id=str(uuid.uuid4()), document_id=doc1.id, role="user", content="Doc 1 query")
        msg2 = ChatMessage(id=str(uuid.uuid4()), document_id=doc2.id, role="user", content="Doc 2 query")
        self.db.add_all([msg1, msg2])
        self.db.commit()

        h1 = self.rag.get_history(doc1.id, self.db)
        h2 = self.rag.get_history(doc2.id, self.db)

        self.assertEqual(len(h1), 1)
        self.assertEqual(h1[0]["content"], "Doc 1 query")
        self.assertEqual(len(h2), 1)
        self.assertEqual(h2[0]["content"], "Doc 2 query")

    # 9. Invalid Document ID Handling
    def test_invalid_document_raises_not_found(self):
        with self.assertRaises(DocumentNotFoundError):
            self.rag.answer_document_query("invalid-uuid-1234", "test query", self.db)

    # 10. Unindexed / Image-only Document Handling
    def test_unindexed_document_handling(self):
        doc = self._create_mock_document(num_chunks=2, status="ocr_required", embedded=False)
        with self.assertRaises(DocumentNotReadyError):
            self.rag.answer_document_query(doc.id, "test query", self.db)

    # 11. Empty Query Validation
    def test_empty_query_raises_value_error(self):
        doc = self._create_mock_document()
        with self.assertRaises(ValueError):
            self.rag.answer_document_query(doc.id, "   ", self.db)


class TestRAGEndpoints(unittest.TestCase):
    """
    Automated integration tests for PaperPilot Chat & RAG endpoints.
    """

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.db = SessionLocal()
        self.doc_id = str(uuid.uuid4())
        self.doc = Document(
            id=self.doc_id,
            filename=f"{self.doc_id}.pdf",
            original_filename="api_chat_doc.pdf",
            file_path=os.path.join(tempfile.gettempdir(), f"{self.doc_id}.pdf"),
            file_size_bytes=2048,
            total_pages=2,
            extracted_pages=2,
            total_characters=1000,
            total_chunks=2,
            status="ready",
            embedding_status="completed"
        )
        self.db.add(self.doc)

        # Add chunks with dummy embeddings
        for i in range(2):
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=self.doc_id,
                chunk_index=i,
                content=f"Content for chunk {i} on chemistry and thermodynamics.",
                char_count=50,
                page_start=i + 1,
                page_end=i + 1,
                pages_json=json.dumps([i + 1]),
                embedding_json=json.dumps([0.1] * 768),
                embedding_dimension=768
            )
            self.db.add(chunk)

        self.db.commit()

    def tearDown(self):
        self.db.query(ChatMessage).filter(ChatMessage.document_id == self.doc_id).delete()
        self.db.query(DocumentChunk).filter(DocumentChunk.document_id == self.doc_id).delete()
        self.db.query(Document).filter(Document.id == self.doc_id).delete()
        self.db.commit()
        self.db.close()

    # 12. Endpoint: POST /documents/{id}/chat
    def test_endpoint_document_chat(self):
        dummy_query_vec = [[0.1] * 768]
        mock_answer = "This is a grounded answer from page 1."

        with patch("app.services.vector_store.embedding_service.generate_embeddings_for_batch", return_value=dummy_query_vec):
            with patch("app.services.rag_service.rag_service.generate_answer", return_value=mock_answer):
                resp = chat_with_document(
                    self.doc_id,
                    DocumentChatRequest(message="Tell me about chemistry", top_k=2),
                    db=self.db
                )

        self.assertEqual(resp.document_id, self.doc_id)
        self.assertEqual(resp.role, "assistant")
        self.assertEqual(resp.content, mock_answer)
        self.assertTrue(len(resp.citations) > 0)

    # 13. Endpoint: GET /documents/{id}/chat/history
    def test_endpoint_get_chat_history(self):
        # Insert a user and assistant message
        msg1 = ChatMessage(id=str(uuid.uuid4()), document_id=self.doc_id, role="user", content="Hi")
        msg2 = ChatMessage(id=str(uuid.uuid4()), document_id=self.doc_id, role="assistant", content="Hello", page_references=json.dumps([{"page": 1}]))
        self.db.add_all([msg1, msg2])
        self.db.commit()

        history = get_document_chat_history(self.doc_id, db=self.db)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].role, "user")
        self.assertEqual(history[1].role, "assistant")

    # 14. Endpoint: DELETE /documents/{id}/chat/history
    def test_endpoint_clear_chat_history(self):
        msg = ChatMessage(id=str(uuid.uuid4()), document_id=self.doc_id, role="user", content="Temporary")
        self.db.add(msg)
        self.db.commit()

        resp = clear_document_chat_history(self.doc_id, db=self.db)
        self.assertEqual(resp.document_id, self.doc_id)
        self.assertEqual(resp.deleted_count, 1)

        # Confirm history is now empty
        history = get_document_chat_history(self.doc_id, db=self.db)
        self.assertEqual(len(history), 0)

    # 15. Endpoint: POST /chat (Legacy route support)
    def test_endpoint_legacy_chat_route(self):
        dummy_query_vec = [[0.1] * 768]
        mock_answer = "Legacy route answer."

        with patch("app.services.vector_store.embedding_service.generate_embeddings_for_batch", return_value=dummy_query_vec):
            with patch("app.services.rag_service.rag_service.generate_answer", return_value=mock_answer):
                resp = send_chat_message(
                    ChatRequest(document_id=self.doc_id, message="Hello via legacy route"),
                    db=self.db
                )

        self.assertEqual(resp.content, mock_answer)

    # 16. Endpoint: Invalid Document Returns 404
    def test_endpoint_invalid_document_returns_404(self):
        with self.assertRaises(HTTPException) as ctx:
            chat_with_document(
                "non-existent-uuid",
                DocumentChatRequest(message="test"),
                db=self.db
            )
        self.assertEqual(ctx.exception.status_code, 404)

    # 17. Page-Aware Intent Classification and Page Number Extraction
    def test_page_aware_intent_and_extraction(self):
        from app.services.rag_service import rag_service
        self.assertEqual(rag_service.extract_target_page("Answer the 3 questions provided on page 6."), 6)
        self.assertEqual(rag_service.extract_target_page("Explain the activity on page 6."), 6)
        self.assertEqual(rag_service.extract_target_page("Summarize page 8."), 8)
        self.assertEqual(rag_service.extract_target_page("Explain the question on page 4."), 4)
        self.assertEqual(rag_service.extract_target_page("What is on p. 12?"), 12)
        self.assertIsNone(rag_service.extract_target_page("What is the chapter name?"))

        self.assertEqual(rag_service.classify_question_intent("Answer the 3 questions provided on page 6."), "page_question")
        self.assertEqual(rag_service.classify_question_intent("List all questions on page 6."), "page_question")
        self.assertEqual(rag_service.classify_question_intent("Explain the activity on page 6."), "page_activity")
        self.assertEqual(rag_service.classify_question_intent("Summarize page 8."), "page_summary")

    # 18. Page Question Parsing (Deduplication and Observation Exclusion)
    def test_parse_questions_from_page(self):
        from app.services.rag_service import rag_service
        sample_page_text = (
            "1.2.1 Combination Reaction\n"
            "Activity 1.4\n"
            "Take a small amount of calcium oxide or quick lime in a beaker.\n"
            "Do you feel any change in temperature?\n"
            "CaO + H2O -> Ca(OH)2 + Heat\n"
            "Q U E S T I O N S\n"
            "1. Why should a magnesium ribbon be cleaned before burning in air?\n"
            "2. Write the balanced equation for the following chemical reactions.\n"
            "(i) Hydrogen + Chlorine -> Hydrogen chloride\n"
            "3. Write a balanced chemical equation with state symbols for the following reactions.\n"
            "(i) Solutions of barium chloride and sodium sulphate react to give insoluble barium sulphate.\n"
        )
        questions = rag_service.parse_questions_from_page(sample_page_text)
        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0]["number"], 1)
        self.assertIn("magnesium ribbon", questions[0]["text"])
        self.assertEqual(questions[1]["number"], 2)
        self.assertIn("Hydrogen + Chlorine", questions[1]["text"])
        self.assertEqual(questions[2]["number"], 3)
        self.assertIn("state symbols", questions[2]["text"])
        # Ensure activity observation ("Do you feel any change in temperature?") is NOT included
        for q in questions:
            self.assertNotIn("change in temperature", q["text"])

    # 19. Page Context Retrieval from SQLite Chunks
    def test_retrieve_page_context(self):
        from app.services.rag_service import rag_service
        # Insert test chunks touching page 6
        c1 = DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=self.doc_id,
            chunk_index=0,
            content="Activity 1.4: Calcium oxide with water forms slaked lime. CaO + H2O -> Ca(OH)2 + Heat",
            char_count=80,
            page_start=6,
            page_end=6,
            pages_json=json.dumps([6])
        )
        c2 = DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=self.doc_id,
            chunk_index=1,
            content=(
                "Q U E S T I O N S\n"
                "1. Why should a magnesium ribbon be cleaned before burning in air?\n"
                "2. Write the balanced equation for Hydrogen + Chlorine.\n"
                "3. Write balanced equation with state symbols."
            ),
            char_count=180,
            page_start=6,
            page_end=7,
            pages_json=json.dumps([6, 7])
        )
        self.db.add_all([c1, c2])
        self.db.commit()

        # Test page question retrieval
        ctx = rag_service.retrieve_page_context(
            document_id=self.doc_id,
            query="Answer the 3 questions provided on page 6.",
            target_page=6,
            intent="page_question",
            db=self.db
        )
        self.assertTrue(len(ctx) >= 2)
        # Verify first chunk is the verified questions block
        self.assertEqual(ctx[0]["chunk_id"], "page_6_questions")
        self.assertIn("PAGE 6 VERIFIED QUESTIONS", ctx[0]["content"])
        self.assertIn("Question 1", ctx[0]["content"])
        self.assertIn("Question 2", ctx[0]["content"])
        self.assertIn("Question 3", ctx[0]["content"])


if __name__ == "__main__":
    unittest.main()
