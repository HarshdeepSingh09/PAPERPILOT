import os
import sys
import json
import uuid
import unittest
from unittest.mock import patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.db.session import SessionLocal, init_db
from app.db.models import Document, DocumentChunk, DocumentSummary, Quiz, RevisionNote, LEGACY_OWNER_USER_ID
from app.services.summary_service import summary_service
from app.services.quiz_service import quiz_service
from app.services.revision_service import revision_service
from app.schemas.summary import SummaryGenerateRequest
from app.schemas.quiz import QuizGenerateRequest, QuizSubmitRequest
from app.schemas.revision import RevisionNotesGenerateRequest


class TestStudyFeatures(unittest.TestCase):
    """
    Automated unit test suite for PaperPilot Study & Assessment Features:
    - AI Document Summaries (7 sections, caching, SQLite persistence)
    - Interactive Quiz Engine (configured count, difficulty, hidden answers, scoring, citations)
    - High-Yield Revision Notes (8 sections, KaTeX equations, SQLite persistence)
    """

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.db = SessionLocal()
        self.document_id = str(uuid.uuid4())

        # Seed sample document and chunks
        self.test_doc = Document(
            id=self.document_id,
            user_id=LEGACY_OWNER_USER_ID,
            filename=f"test_{self.document_id[:8]}.pdf",
            original_filename="Test_Science_Chapter.pdf",
            file_path="storage/uploads/test.pdf",
            file_size_bytes=10240,
            status="ready",
            title="Chemical Reactions and Equations",
            chapter_name="Chemical Reactions and Equations",
            chapter_number=1,
            subject="Science",
            total_pages=5
        )
        self.db.add(self.test_doc)

        chunks_data = [
            (0, 1, 1, [1], "A complete chemical equation represents reactants, products and their physical states symbolically. Magnesium burns in oxygen to form magnesium oxide white powder."),
            (1, 2, 2, [2], "A chemical reaction is balanced so that the numbers of atoms of each type involved in a chemical reaction are the same on the reactant and product sides of the equation."),
            (2, 3, 3, [3], "In a combination reaction two or more substances combine to form a new single substance. CaO + H2O -> Ca(OH)2 + Heat. This is exothermic."),
            (3, 4, 4, [4], "Decomposition reactions are opposite to combination reactions. In a decomposition reaction, a single substance decomposes to give two or more substances."),
            (4, 5, 5, [5], "Corrosion and rancidity are effects of oxidation reactions in everyday life. Iron gets coated with reddish brown powder when exposed to moisture.")
        ]

        for c_idx, p_start, p_end, pages, content in chunks_data:
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=self.document_id,
                chunk_index=c_idx,
                page_start=p_start,
                page_end=p_end,
                pages_json=json.dumps(pages),
                content=content,
                char_count=len(content)
            )
            self.db.add(chunk)

        self.db.commit()

    def tearDown(self):
        try:
            self.db.query(DocumentSummary).filter(DocumentSummary.document_id == self.document_id).delete()
            self.db.query(Quiz).filter(Quiz.document_id == self.document_id).delete()
            self.db.query(RevisionNote).filter(RevisionNote.document_id == self.document_id).delete()
            self.db.query(DocumentChunk).filter(DocumentChunk.document_id == self.document_id).delete()
            self.db.query(Document).filter(Document.id == self.document_id).delete()
            self.db.commit()
        except Exception:
            self.db.rollback()
        finally:
            self.db.close()

    # --- Summary Service Tests ---

    def test_summary_generation_and_persistence(self):
        """Test document summary generation, SQLite persistence, and 7 sections."""
        with patch.object(summary_service, "get_client", return_value=None):
            res = summary_service.generate_summary(self.document_id, self.db, force_regenerate=True)
            
        self.assertEqual(res.document_id, self.document_id)
        self.assertTrue(len(res.executive_overview) > 0)
        self.assertTrue(len(res.key_takeaways) >= 3)
        self.assertTrue(len(res.important_concepts) >= 1)
        self.assertTrue(len(res.formulas_equations) >= 1)
        self.assertTrue(len(res.chapter_summaries) >= 1)
        self.assertTrue(len(res.important_facts) >= 1)
        self.assertTrue(len(res.page_references) >= 1)

        # Verify saved in SQLite
        record = self.db.query(DocumentSummary).filter(DocumentSummary.document_id == self.document_id).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.document_id, self.document_id)

    def test_summary_cache_retrieval(self):
        """Test that get_saved_summary retrieves cached record without re-synthesizing."""
        with patch.object(summary_service, "get_client", return_value=None):
            summary_service.generate_summary(self.document_id, self.db)

        # Retrieve cached without any client
        cached = summary_service.get_saved_summary(self.document_id, self.db)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.document_id, self.document_id)

    # --- Quiz Service Tests ---

    def test_quiz_generation_and_answer_hiding(self):
        """Test quiz generation, configurable count, and answer hiding before submission."""
        with patch.object(quiz_service, "get_client", return_value=None):
            quiz = quiz_service.generate_quiz(
                document_id=self.document_id,
                num_questions=5,
                difficulty="medium",
                question_type="mixed",
                db=self.db,
                force_regenerate=True
            )

        self.assertEqual(quiz.document_id, self.document_id)
        self.assertEqual(quiz.total_questions, 5)
        self.assertFalse(quiz.completed)
        self.assertIsNone(quiz.score)

        # Ensure answers and explanations are stripped for uncompleted quiz
        for q in quiz.questions:
            self.assertIsNone(q.correct_option_id)
            self.assertIsNone(q.correct_options)
            self.assertIsNone(q.explanation)
            self.assertTrue(len(q.options) >= 2)
            self.assertIsNotNone(q.source_page)

    def test_quiz_submission_and_scoring(self):
        """Test quiz submission, score calculation, percentage, and revealed explanations."""
        with patch.object(quiz_service, "get_client", return_value=None):
            quiz = quiz_service.generate_quiz(
                document_id=self.document_id,
                num_questions=5,
                difficulty="easy",
                question_type="mixed",
                db=self.db
            )

        record = self.db.query(Quiz).filter(Quiz.id == quiz.id).first()
        raw_questions = json.loads(record.questions_json)

        answers = {}
        for q in raw_questions:
            answers[q["id"]] = q.get("correct_option_id") or "opt_a"

        submitted_quiz = quiz_service.submit_quiz(quiz.id, answers, self.db)

        self.assertTrue(submitted_quiz.completed)
        self.assertIsNotNone(submitted_quiz.score)
        self.assertIsNotNone(submitted_quiz.percentage)
        self.assertGreaterEqual(submitted_quiz.score, 0)
        self.assertGreaterEqual(submitted_quiz.percentage, 0.0)

        for q in submitted_quiz.questions:
            self.assertIsNotNone(q.correct_option_id)
            self.assertIsNotNone(q.explanation)
            self.assertIsNotNone(q.user_answer)

    def test_quiz_retrieval(self):
        """Test get_latest_quiz and get_quiz_by_id operations."""
        with patch.object(quiz_service, "get_client", return_value=None):
            created = quiz_service.generate_quiz(
                document_id=self.document_id,
                num_questions=5,
                difficulty="hard",
                question_type="mixed",
                db=self.db,
                force_regenerate=True
            )

        latest = quiz_service.get_latest_quiz(self.document_id, self.db)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.id, created.id)

        by_id = quiz_service.get_quiz_by_id(created.id, self.db)
        self.assertIsNotNone(by_id)
        self.assertEqual(by_id.id, created.id)

    # --- Revision Notes Tests ---

    def test_revision_notes_generation_and_persistence(self):
        """Test 8-section revision notes generation, KaTeX formulas, and persistence."""
        with patch.object(revision_service, "get_client", return_value=None):
            res = revision_service.get_or_generate_revision_notes(self.document_id, self.db, force_regenerate=True)

        self.assertEqual(res.document_id, self.document_id)
        self.assertTrue(len(res.chapter_overview) > 0)
        self.assertTrue(len(res.definitions) >= 2)
        self.assertTrue(len(res.key_concepts) >= 2)
        self.assertTrue(len(res.reactions_equations) >= 2)
        self.assertTrue(len(res.formulas) >= 1)
        self.assertTrue(len(res.differences_comparisons) >= 1)
        self.assertTrue(len(res.faqs) >= 2)
        self.assertTrue(len(res.last_minute_points) >= 3)

        # Verify KaTeX equation presence
        for rxn in res.reactions_equations:
            self.assertTrue("$$" in rxn.equation_latex or "\\" in rxn.equation_latex or "->" in rxn.equation_latex)

        # Verify persistence in SQLite
        record = self.db.query(RevisionNote).filter(RevisionNote.document_id == self.document_id).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.document_id, self.document_id)

    def test_revision_notes_cache_retrieval(self):
        """Test revision notes retrieval and cache checking without AI re-calls."""
        with patch.object(revision_service, "get_client", return_value=None):
            revision_service.get_or_generate_revision_notes(self.document_id, self.db)

        cached = revision_service.get_saved_notes(self.document_id, self.db)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.document_id, self.document_id)


if __name__ == "__main__":
    unittest.main()
