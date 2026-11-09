from fastapi import APIRouter
from app.api.v1 import documents, chat, summaries, quizzes

api_router = APIRouter()

api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(summaries.router, prefix="/summaries", tags=["Summaries"])
api_router.include_router(quizzes.router, prefix="/quizzes", tags=["Quizzes"])
