import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


class MCQOption(BaseModel):
    id: str  # e.g., "A", "B", "C", "D"
    text: str


class QuizQuestionItem(BaseModel):
    id: int
    question: str
    options: List[MCQOption]
    question_type: str = "mcq"  # 'mcq', 'multiple_answer', 'true_false'
    correct_option_id: Optional[str] = None
    correct_options: Optional[List[str]] = None
    explanation: Optional[str] = None
    source_page: Optional[int] = None
    user_answer: Optional[Union[str, List[str]]] = None


class QuizGenerateRequest(BaseModel):
    document_id: str
    num_questions: int = 5
    difficulty: str = "medium"  # easy, medium, hard, mixed
    question_type: str = "mixed"  # mcq, true_false, mixed
    force_regenerate: bool = False


class QuizSubmitRequest(BaseModel):
    answers: Dict[str, Union[str, List[str]]]


class QuizResponse(BaseModel):
    id: str
    document_id: str
    title: str
    difficulty: str
    question_count: int
    total_questions: int
    completed: bool
    score: Optional[int] = None
    percentage: Optional[float] = None
    questions: List[QuizQuestionItem]
    created_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None


# Backwards compatibility models
MCQItem = QuizQuestionItem
