import datetime
import io
import os
import shutil
import sys
import unittest
import uuid
from http.cookies import SimpleCookie
from unittest.mock import patch

import chromadb
import pymupdf
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import Response

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import verify_password
from app.db.models import (
    LEGACY_OWNER_USER_ID,
    ChatMessage,
    Document,
    DocumentChunk,
    DocumentInsight,
    DocumentSummary,
    PasswordResetToken,
    Quiz,
    RevisionNote,
    User,
    UserSession,
)
from app.db.session import SessionLocal, init_db
from app.api.v1.auth import (
    forgot_password,
    get_me,
    login_user,
    logout_user,
    register_user,
    reset_password,
)
from app.api.v1.documents import (
    clear_document_chat_history,
    chat_with_document,
    delete_document,
    get_document,
    get_document_chat_history,
    get_document_chunks,
    get_document_content,
    get_document_embedding_status,
    get_document_file,
    get_document_index_status,
    get_document_stats,
    list_documents,
    reprocess_document,
    search_document_chunks,
    update_document_category,
    upload_document,
)
from app.api.v1.chat import clear_chat_history, get_chat_history, send_chat_message
from app.api.v1.summaries import generate_summary, get_document_summary
from app.api.v1.quizzes import (
    generate_quiz,
    generate_revision_notes,
    get_latest_document_quiz,
    get_quiz,
    get_revision_notes,
    submit_quiz,
)
from app.api.v1.insights import generate_document_insights, get_document_insights
from app.schemas.auth import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
)
from app.schemas.chat import ChatRequest, DocumentChatRequest
from app.schemas.document import SearchRequest
from app.schemas.insights import CategoryUpdateRequest, InsightsGenerateRequest
from app.schemas.quiz import QuizGenerateRequest, QuizSubmitRequest
from app.schemas.revision import RevisionNotesGenerateRequest
from app.schemas.summary import SummaryGenerateRequest
from app.services.classification_service import classification_service
from app.services.rag_service import RAGService
from app.services.vector_store import VectorStoreService


class _FakeUploadFile:
    def __init__(self, filename: str, data: bytes, content_type: str = "application/pdf"):
        self.filename = filename
        self.content_type = content_type
        self._buf = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)


def _run_coro_sync(coro):
    try:
        coro.send(None)
    except StopIteration as exc:
        return exc.value
    raise RuntimeError("Unexpected pending await inside synchronous helper")


def _make_pdf_bytes(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    raw = doc.tobytes()
    doc.close()
    return raw


def _make_request(cookie_token: str | None = None, bearer_token: str | None = None) -> Request:
    headers = [(b"user-agent", b"PaperPilot-SecurityTest/1.0")]
    if cookie_token is not None:
        cookie_str = f"{settings.SESSION_COOKIE_NAME}={cookie_token}"
        headers.append((b"cookie", cookie_str.encode("latin-1")))
    if bearer_token is not None:
        headers.append((b"authorization", f"Bearer {bearer_token}".encode("latin-1")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
    }
    return Request(scope)


def _extract_cookie_from_response(response: Response, cookie_name: str = settings.SESSION_COOKIE_NAME) -> str:
    set_cookie_headers = [
        v.decode("latin-1")
        for k, v in response.raw_headers
        if k.lower() == b"set-cookie"
    ]
    for raw_hdr in set_cookie_headers:
        jar = SimpleCookie()
        jar.load(raw_hdr)
        if cookie_name in jar:
            return jar[cookie_name].value
    raise AssertionError(f"Expected HttpOnly cookie '{cookie_name}' in Set-Cookie headers: {set_cookie_headers}")


def _collect_app_api_routes(routes, prefix: str = "") -> list[tuple[str, APIRoute]]:
    collected: list[tuple[str, APIRoute]] = []
    for r in routes:
        if hasattr(r, "original_router") and hasattr(r, "include_context"):
            sub_prefix = prefix + (getattr(r.include_context, "prefix", "") or "")
            collected.extend(_collect_app_api_routes(r.original_router.routes, sub_prefix))
        elif isinstance(r, APIRoute):
            collected.append((prefix + r.path, r))
    return collected


class TestPhase5AuthAndIsolation(unittest.TestCase):
    """
    Phase 5 Comprehensive Multi-User Security & Data Isolation Test Suite.
    Verifies all authentication flows, HttpOnly cookie sessions, backend ownership guards,
    SQLite/ChromaDB/File-Storage isolation, fresh workspaces, and legacy data preservation.
    """

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.db = SessionLocal()
        self.created_user_ids: list[str] = []
        self.created_doc_ids: list[str] = []
        self.chroma_client = chromadb.Client()
        self.vector_store = VectorStoreService(
            collection_name=f"test_sec_{uuid.uuid4().hex[:8]}",
            client=self.chroma_client,
        )
        self.rag = RAGService(
            model_name="gemini-3.5-flash",
            vector_store=self.vector_store,
            max_retries=1,
            initial_backoff=0.01,
        )

    def tearDown(self):
        for doc_id in self.created_doc_ids:
            try:
                self.db.query(DocumentInsight).filter(DocumentInsight.document_id == doc_id).delete()
                self.db.query(RevisionNote).filter(RevisionNote.document_id == doc_id).delete()
                self.db.query(Quiz).filter(Quiz.document_id == doc_id).delete()
                self.db.query(DocumentSummary).filter(DocumentSummary.document_id == doc_id).delete()
                self.db.query(ChatMessage).filter(ChatMessage.document_id == doc_id).delete()
                self.db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
                self.db.query(Document).filter(Document.id == doc_id).delete()
                self.db.commit()
            except Exception:
                self.db.rollback()

        for uid in self.created_user_ids:
            try:
                self.db.query(PasswordResetToken).filter(PasswordResetToken.user_id == uid).delete()
                self.db.query(UserSession).filter(UserSession.user_id == uid).delete()
                self.db.query(Document).filter(Document.user_id == uid).delete()
                self.db.query(User).filter(User.id == uid).delete()
                self.db.commit()
            except Exception:
                self.db.rollback()
            shutil.rmtree(os.path.join(settings.UPLOAD_DIR, uid), ignore_errors=True)

        self.db.close()

    def _register_user_with_cookie(self, name: str, email: str, password: str) -> tuple[User, str, Response]:
        resp = Response()
        req = _make_request()
        auth_res = register_user(
            payload=UserRegisterRequest(name=name, email=email, password=password),
            request=req,
            response=resp,
            db=self.db,
        )
        token = _extract_cookie_from_response(resp)
        user = self.db.query(User).filter(User.id == auth_res.user.id).first()
        self.created_user_ids.append(user.id)
        return user, token, resp

    def test_route_dependency_audit_every_private_endpoint_requires_auth(self):
        """
        Inspects the FastAPI route table to verify EVERY non-public endpoint
        declares get_current_user in its dependency tree.
        """
        public_paths = {
            "/",
            "/health",
            "/api/v1/openapi.json",
            "/api/v1/docs",
            "/api/v1/redoc",
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/logout",
            "/api/v1/auth/forgot-password",
            "/api/v1/auth/reset-password",
        }
        all_routes = _collect_app_api_routes(app.routes)
        protected_checked = 0
        for full_path, route in all_routes:
            if full_path in public_paths:
                continue
            dep_calls = [d.call for d in route.dependant.dependencies]
            self.assertIn(
                get_current_user,
                dep_calls,
                f"Security audit failure: route {full_path} is missing get_current_user!",
            )
            protected_checked += 1
        self.assertGreaterEqual(protected_checked, 25)

    def test_authentication_lifecycle_hashing_cookies_logout_and_password_reset(self):
        """
        Verifies registration, bcrypt hashing, duplicate prevention, HttpOnly cookie attributes,
        session persistence across simulated refresh, logout revocation, unauthenticated rejection,
        and non-enumerating password reset.
        """
        email_a = f"alice_{uuid.uuid4().hex[:8]}@example.com"
        password_a = "AliceStrongPass!2026"
        alice, cookie_a, reg_resp = self._register_user_with_cookie("Alice Tester", email_a, password_a)

        # Password never stored as plaintext
        self.assertNotEqual(alice.password_hash, password_a)
        self.assertTrue(alice.password_hash.startswith("$2"))
        self.assertTrue(verify_password(password_a, alice.password_hash))

        # HttpOnly & SameSite attributes on Set-Cookie header
        raw_set_cookie = b"".join(v for k, v in reg_resp.raw_headers if k.lower() == b"set-cookie").decode("latin-1")
        self.assertIn("HttpOnly", raw_set_cookie)
        self.assertIn("SameSite=lax", raw_set_cookie)

        # Token is NOT leaked in UserProfileResponse serialization
        dumped_profile = UserProfileResponse.model_validate(alice).model_dump()
        self.assertNotIn("password_hash", dumped_profile)
        self.assertNotIn("token", dumped_profile)

        # Duplicate account prevention (case-insensitive) -> 409
        with self.assertRaises(HTTPException) as dup_ctx:
            register_user(
                payload=UserRegisterRequest(name="Alice Clone", email=email_a.upper(), password=password_a),
                request=_make_request(),
                response=Response(),
                db=self.db,
            )
        self.assertEqual(dup_ctx.exception.status_code, 409)

        # Simulated browser refresh using HttpOnly cookie -> resolves Alice
        refreshed_user = get_current_user(_make_request(cookie_token=cookie_a), db=self.db)
        self.assertEqual(refreshed_user.id, alice.id)
        self.assertEqual(get_me(refreshed_user).email, email_a)

        # Unauthenticated request rejected with 401
        with self.assertRaises(HTTPException) as unauth_ctx:
            get_current_user(_make_request(cookie_token=None), db=self.db)
        self.assertEqual(unauth_ctx.exception.status_code, 401)

        # Legacy archive account cannot be logged into
        with self.assertRaises(HTTPException) as legacy_ctx:
            login_user(
                payload=UserLoginRequest(email="legacy-archive@paperpilot.internal", password="anything"),
                request=_make_request(),
                response=Response(),
                db=self.db,
            )
        self.assertEqual(legacy_ctx.exception.status_code, 401)

        # Logout revokes session in SQLite and blocks further access even if old cookie is replayed
        logout_resp = Response()
        logout_res = logout_user(request=_make_request(cookie_token=cookie_a), response=logout_resp, db=self.db)
        self.assertFalse(logout_res.authenticated)

        with self.assertRaises(HTTPException) as post_logout_ctx:
            get_current_user(_make_request(cookie_token=cookie_a), db=self.db)
        self.assertEqual(post_logout_ctx.exception.status_code, 401)

        # Re-login issues a new valid cookie
        login_resp = Response()
        login_res = login_user(
            payload=UserLoginRequest(email=email_a, password=password_a),
            request=_make_request(),
            response=login_resp,
            db=self.db,
        )
        new_cookie_a = _extract_cookie_from_response(login_resp)
        self.assertNotEqual(new_cookie_a, cookie_a)
        self.assertEqual(login_res.user.id, alice.id)

        # Forgot password returns identical generic message and captures reset link via email hook
        captured_urls: list[str] = []
        with patch("app.api.v1.auth.send_password_reset_email", side_effect=lambda to, nm, url: captured_urls.append(url) or True):
            fp_known = forgot_password(ForgotPasswordRequest(email=email_a), db=self.db)
            fp_unknown = forgot_password(ForgotPasswordRequest(email="nobody_here@example.com"), db=self.db)
        self.assertEqual(fp_known.message, fp_unknown.message)
        self.assertEqual(len(captured_urls), 1)
        reset_token = captured_urls[0].split("token=")[-1]

        # Complete reset password -> invalidates active sessions & switches password hash
        new_password_a = "AliceUpdatedPass!2026"
        reset_res = reset_password(ResetPasswordRequest(token=reset_token, new_password=new_password_a), db=self.db)
        self.assertIn("updated", reset_res.message.lower())

        with self.assertRaises(HTTPException) as revoked_ctx:
            get_current_user(_make_request(cookie_token=new_cookie_a), db=self.db)
        self.assertEqual(revoked_ctx.exception.status_code, 401)

        with self.assertRaises(HTTPException) as old_pw_ctx:
            login_user(
                payload=UserLoginRequest(email=email_a, password=password_a),
                request=_make_request(),
                response=Response(),
                db=self.db,
            )
        self.assertEqual(old_pw_ctx.exception.status_code, 401)

        post_reset_resp = Response()
        post_reset_login = login_user(
            payload=UserLoginRequest(email=email_a, password=new_password_a),
            request=_make_request(),
            response=post_reset_resp,
            db=self.db,
        )
        self.assertEqual(post_reset_login.user.id, alice.id)

    def test_complete_multi_user_isolation_sqlite_chroma_files_and_ai_endpoints(self):
        """
        Executes all multi-user security & isolation verification cases between User A and User B,
        newly registered User C fresh workspace, and legacy dev archive preservation.
        """
        alice, cookie_a, _ = self._register_user_with_cookie("User A", f"user_a_{uuid.uuid4().hex[:6]}@example.com", "AlphaPass123!")
        bob, cookie_b, _ = self._register_user_with_cookie("User B", f"user_b_{uuid.uuid4().hex[:6]}@example.com", "BetaPass123!")
        charlie, cookie_c, _ = self._register_user_with_cookie("User C", f"user_c_{uuid.uuid4().hex[:6]}@example.com", "GammaPass123!")

        # 14. Newly registered user gets a fresh empty workspace (and sees 0 legacy dev docs!)
        self.assertEqual(list_documents(current_user=charlie, db=self.db), [])
        self.assertEqual(list_documents(current_user=alice, db=self.db), [])
        self.assertEqual(list_documents(current_user=bob, db=self.db), [])

        pdf_a = _make_pdf_bytes("Confidential Alpha Formula: Magnesium reacts with oxygen to yield MgO.")
        pdf_b = _make_pdf_bytes("Secret Beta Clause: Beta Corp owes $9.5 million under California Arbitration.")
        vec_a = [0.8 if i % 2 == 0 else 0.1 for i in range(768)]
        vec_b = [0.1 if i % 2 == 0 else 0.8 for i in range(768)]

        def fake_embed_for_user(texts, api_key=None):
            res = []
            for t in texts:
                if "Alpha" in t or "Magnesium" in t:
                    res.append(vec_a)
                else:
                    res.append(vec_b)
            return res

        with patch("app.services.embedding_service.embedding_service.generate_embeddings_for_batch", side_effect=fake_embed_for_user), \
             patch("app.services.vector_store.embedding_service.generate_embeddings_for_batch", side_effect=fake_embed_for_user), \
             patch("app.api.v1.documents.vector_store_service", self.vector_store), \
             patch("app.api.v1.documents.rag_service", self.rag), \
             patch("app.api.v1.chat.rag_service", self.rag), \
             patch.object(classification_service, "get_client", return_value=None):

            doc_a = _run_coro_sync(
                upload_document(
                    file=_FakeUploadFile("alpha_secret.pdf", pdf_a),
                    background=False,
                    background_tasks=None,
                    current_user=alice,
                    db=self.db,
                )
            )
            self.created_doc_ids.append(doc_a.id)

            doc_b = _run_coro_sync(
                upload_document(
                    file=_FakeUploadFile("beta_secret.pdf", pdf_b),
                    background=False,
                    background_tasks=None,
                    current_user=bob,
                    db=self.db,
                )
            )
            self.created_doc_ids.append(doc_b.id)

            # 10. Per-user separated file storage structure: storage/uploads/{user_id}/{document_id}/{filename}
            expected_dir_a = os.path.abspath(os.path.join(settings.UPLOAD_DIR, alice.id, doc_a.id))
            expected_dir_b = os.path.abspath(os.path.join(settings.UPLOAD_DIR, bob.id, doc_b.id))
            self.assertEqual(os.path.dirname(os.path.abspath(doc_a.file_path)), expected_dir_a)
            self.assertEqual(os.path.dirname(os.path.abspath(doc_b.file_path)), expected_dir_b)
            self.assertTrue(os.path.isfile(doc_a.file_path))
            self.assertTrue(os.path.isfile(doc_b.file_path))

            # 1 & 2. User A sees ONLY Document A; User B sees ONLY Document B; User C still sees []
            list_a = list_documents(current_user=alice, db=self.db)
            list_b = list_documents(current_user=bob, db=self.db)
            list_c = list_documents(current_user=charlie, db=self.db)
            self.assertEqual([d.id for d in list_a], [doc_a.id])
            self.assertEqual([d.id for d in list_b], [doc_b.id])
            self.assertEqual(list_c, [])

            # API response schemas do not expose internal file_path or user_id hashes
            from app.schemas.document import DocumentResponse
            serialized_a = DocumentResponse.model_validate(doc_a).model_dump()
            self.assertNotIn("file_path", serialized_a)

            # User A generates Summary, Chat, Quiz, Revision Notes, Adaptive Insights on Document A
            with patch("app.services.summary_service.summary_service.get_client", return_value=None):
                sum_a = _run_coro_sync(
                    generate_summary(
                        SummaryGenerateRequest(document_id=doc_a.id, force_regenerate=True),
                        current_user=alice,
                        db=self.db,
                    )
                )
            self.assertEqual(sum_a.document_id, doc_a.id)

            with patch.object(self.rag, "generate_answer", return_value="Alpha MgO grounded answer (Page 1)."):
                chat_a = chat_with_document(
                    doc_a.id,
                    DocumentChatRequest(message="What happens in Alpha Formula?"),
                    current_user=alice,
                    db=self.db,
                )
            self.assertIn("Alpha", chat_a.content)

            with patch("app.services.quiz_service.quiz_service.get_client", return_value=None):
                quiz_a = _run_coro_sync(
                    generate_quiz(
                        QuizGenerateRequest(document_id=doc_a.id, num_questions=5),
                        current_user=alice,
                        db=self.db,
                    )
                )
            with patch("app.services.revision_service.revision_service.get_client", return_value=None):
                rev_a = _run_coro_sync(
                    generate_revision_notes(
                        RevisionNotesGenerateRequest(document_id=doc_a.id),
                        current_user=alice,
                        db=self.db,
                    )
                )
            with patch("app.services.adaptive_insights_service.adaptive_insights_service.get_client", return_value=None):
                ins_a = generate_document_insights(
                    InsightsGenerateRequest(document_id=doc_a.id, force_regenerate=True),
                    current_user=alice,
                    db=self.db,
                )
            self.assertEqual(ins_a["document_id"], doc_a.id)
            self.assertEqual(rev_a.document_id, doc_a.id)

            # User B generates Summary & Chat on Document B
            with patch("app.services.summary_service.summary_service.get_client", return_value=None):
                sum_b = _run_coro_sync(
                    generate_summary(
                        SummaryGenerateRequest(document_id=doc_b.id, force_regenerate=True),
                        current_user=bob,
                        db=self.db,
                    )
                )
            self.assertEqual(sum_b.document_id, doc_b.id)
            with patch.object(self.rag, "generate_answer", return_value="Beta Corp California answer (Page 1)."):
                chat_b = chat_with_document(
                    doc_b.id,
                    DocumentChatRequest(message="What about Beta Corp?"),
                    current_user=bob,
                    db=self.db,
                )
            self.assertIn("Beta", chat_b.content)

            # --- 3..10: Exhaustive Cross-User IDOR Blocking Verification (A -> B and B -> A) ---
            cross_calls = [
                lambda: get_document(doc_b.id, current_user=alice, db=self.db),
                lambda: get_document(doc_a.id, current_user=bob, db=self.db),
                lambda: get_document_stats(doc_b.id, current_user=alice, db=self.db),
                lambda: get_document_chunks(doc_b.id, current_user=alice, db=self.db),
                lambda: get_document_content(doc_b.id, current_user=alice, db=self.db),
                lambda: update_document_category(doc_b.id, CategoryUpdateRequest(category="Legal Document"), current_user=alice, db=self.db),
                lambda: get_document_embedding_status(doc_b.id, current_user=alice, db=self.db),
                lambda: reprocess_document(doc_b.id, background=False, current_user=alice, db=self.db),
                lambda: get_document_file(doc_b.id, current_user=alice, db=self.db),
                lambda: get_document_file(doc_a.id, current_user=bob, db=self.db),
                lambda: get_document_index_status(doc_b.id, current_user=alice, db=self.db),
                lambda: search_document_chunks(doc_b.id, SearchRequest(query="Beta", top_k=2), current_user=alice, db=self.db),
                lambda: chat_with_document(doc_b.id, DocumentChatRequest(message="Steal Beta"), current_user=alice, db=self.db),
                lambda: get_document_chat_history(doc_b.id, current_user=alice, db=self.db),
                lambda: clear_document_chat_history(doc_b.id, current_user=alice, db=self.db),
                lambda: send_chat_message(ChatRequest(document_id=doc_b.id, message="Steal"), current_user=alice, db=self.db),
                lambda: get_chat_history(doc_b.id, current_user=alice, db=self.db),
                lambda: clear_chat_history(doc_b.id, current_user=alice, db=self.db),
                lambda: delete_document(doc_b.id, current_user=alice, db=self.db),
                lambda: _run_coro_sync(get_document_summary(doc_b.id, current_user=alice, db=self.db)),
                lambda: _run_coro_sync(generate_summary(SummaryGenerateRequest(document_id=doc_b.id), current_user=alice, db=self.db)),
                lambda: _run_coro_sync(get_latest_document_quiz(doc_a.id, current_user=bob, db=self.db)),
                lambda: _run_coro_sync(get_quiz(quiz_a.id, current_user=bob, db=self.db)),
                lambda: _run_coro_sync(submit_quiz(quiz_a.id, QuizSubmitRequest(answers={"1": "A"}), current_user=bob, db=self.db)),
                lambda: _run_coro_sync(generate_quiz(QuizGenerateRequest(document_id=doc_a.id), current_user=bob, db=self.db)),
                lambda: _run_coro_sync(get_revision_notes(doc_a.id, current_user=bob, db=self.db)),
                lambda: _run_coro_sync(generate_revision_notes(RevisionNotesGenerateRequest(document_id=doc_a.id), current_user=bob, db=self.db)),
                lambda: get_document_insights(doc_a.id, current_user=bob, db=self.db),
                lambda: generate_document_insights(InsightsGenerateRequest(document_id=doc_a.id), current_user=bob, db=self.db),
            ]

            for idx, fn in enumerate(cross_calls):
                with self.assertRaises(HTTPException, msg=f"Cross-user check #{idx} failed to reject!") as exc_ctx:
                    fn()
                self.assertEqual(exc_ctx.exception.status_code, 404)

            # Owner CAN download own file securely
            own_file_resp = get_document_file(doc_a.id, current_user=alice, db=self.db)
            self.assertIsInstance(own_file_resp, FileResponse)

            # 9. ChromaDB metadata isolation: workspace-wide & document-scoped search never leak across users
            ws_a = self.vector_store.search_user_documents(user_id=alice.id, query="Beta Corp California", top_k=5, db=self.db)
            ws_b = self.vector_store.search_user_documents(user_id=bob.id, query="Magnesium Alpha Formula", top_k=5, db=self.db)
            self.assertTrue(all(r["document_id"] == doc_a.id for r in ws_a))
            self.assertTrue(all(r["document_id"] == doc_b.id for r in ws_b))
            self.assertFalse(any("Beta Corp" in r["content"] for r in ws_a))
            self.assertFalse(any("Alpha Formula" in r["content"] for r in ws_b))

            # 15. Legacy pre-auth development data remains preserved & isolated from Alice/Bob/Charlie
            legacy_count = self.db.query(Document).filter(Document.user_id == LEGACY_OWNER_USER_ID).count()
            self.assertGreaterEqual(legacy_count, 200)
            legacy_doc = self.db.query(Document).filter(Document.user_id == LEGACY_OWNER_USER_ID).first()
            with self.assertRaises(HTTPException) as leg_ctx:
                get_document(legacy_doc.id, current_user=alice, db=self.db)
            self.assertEqual(leg_ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
